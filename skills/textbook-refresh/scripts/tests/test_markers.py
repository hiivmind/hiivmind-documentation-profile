import pytest

from patch_engine.markers import (
    MarkerInvariantError,
    parse_concept_blocks,
    parse_marked_blocks,
    plan_retired_concept_removal,
    select_enrichment_blocks,
    validate_concept_coverage,
)


# --- Single-line ``<!-- concept:N -->`` markers ---


def test_adjacent_markers_form_one_atomic_block():
    text = b"""# Chapter\n\n<!-- concept:8 -->\n<!-- concept:9 -->\n## Expressions\n\nBody.\n\n## Key Takeaways\n\nEnd.\n"""
    blocks = parse_concept_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].concept_ids == (8, 9)
    assert text[blocks[0].end :].startswith(b"## Key Takeaways")


def test_subheading_within_section_does_not_truncate_block():
    text = (
        b"# Chapter\n\n"
        b"<!-- concept:8 -->\n"
        b"## Expressions\n\n"
        b"Body.\n\n"
        b"### Subsection\n\n"
        b"More body.\n\n"
        b"## Key Takeaways\n\n"
        b"End.\n"
    )
    blocks = parse_concept_blocks(text)
    assert len(blocks) == 1
    content = text[blocks[0].content_start : blocks[0].end]
    assert b"### Subsection" in content
    assert b"More body." in content
    assert text[blocks[0].end :].startswith(b"## Key Takeaways")


def test_offsets_are_bytes():
    text = "# Café\n\n<!-- concept:1 -->\n## Sí\n\nBody.\n".encode()
    block = parse_concept_blocks(text)[0]
    assert text[block.start : block.start + len(b"<!-- concept:1 -->")] == b"<!-- concept:1 -->"
    assert text[block.content_start :].startswith(b"## S\xc3\xad")


def test_blank_line_between_marker_and_heading_still_counts_as_introducing():
    text = b"<!-- concept:1 -->\n\n## H\n\nBody.\n"
    blocks = parse_concept_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].concept_ids == (1,)
    content = text[blocks[0].content_start : blocks[0].end]
    assert b"Body." in content


def test_duplicate_concept_marker_is_rejected(graph, chapter_root):
    path = chapter_root / "01-foundations" / "index.md"
    path.write_bytes(path.read_bytes().replace(b"<!-- concept:1 -->", b"<!-- concept:1 -->\n<!-- concept:1 -->", 1))
    assert validate_concept_coverage(graph, chapter_root) == [
        "concept 1 has 2 markers; expected exactly 1"
    ]


# --- Paired ``<!-- KIND:ID concepts:N,N --> ... <!-- /KIND:ID -->`` markers ---


def test_parses_a_flat_sequence_of_paired_blocks_preserving_byte_spans():
    text = (
        b"# Glossary\n\n"
        b"<!-- glossary:alpha concepts:1 -->\n"
        b"#### Alpha\n\nFirst definition.\n"
        b"<!-- /glossary:alpha -->\n\n"
        b"<!-- glossary:beta concepts:2,3 -->\n"
        b"#### Beta\n\nSecond definition.\n"
        b"<!-- /glossary:beta -->\n"
    )
    blocks = parse_marked_blocks(text, "glossary")
    assert [block.id for block in blocks] == ["alpha", "beta"]
    assert blocks[0].concept_ids == (1,)
    assert blocks[1].concept_ids == (2, 3)
    assert text[blocks[0].content_start : blocks[0].end] == b"#### Alpha\n\nFirst definition.\n"
    assert text[blocks[0].start : blocks[0].close_end].startswith(b"<!-- glossary:alpha")
    assert text[blocks[0].start : blocks[0].close_end].endswith(b"<!-- /glossary:alpha -->\n")


def test_marker_shaped_text_inside_a_fenced_code_block_is_not_scanned():
    # A legitimate artifact file documenting the marker syntax in a fenced
    # example must remain parseable: the strict own-line scanner excludes
    # fenced ranges the same way the loose nesting scanner already does.
    text = (
        b"# Glossary\n\n"
        b"Marker syntax example:\n\n"
        b"```markdown\n"
        b"<!-- glossary:example concepts:1 -->\n"
        b"#### Example\n\nBody.\n"
        b"<!-- /glossary:example -->\n"
        b"```\n\n"
        b"<!-- glossary:alpha concepts:1 -->\n"
        b"#### Alpha\n\nFirst definition.\n"
        b"<!-- /glossary:alpha -->\n"
    )
    blocks = parse_marked_blocks(text, "glossary")
    assert [block.id for block in blocks] == ["alpha"]


def test_ignores_blocks_of_a_different_kind():
    text = (
        b"<!-- faq:q1 concepts:1 -->\n### Q1\n\nA1\n<!-- /faq:q1 -->\n\n"
        b"<!-- glossary:g1 concepts:1 -->\n#### G1\n\nDef\n<!-- /glossary:g1 -->\n"
    )
    assert [b.id for b in parse_marked_blocks(text, "faq")] == ["q1"]
    assert [b.id for b in parse_marked_blocks(text, "glossary")] == ["g1"]


def test_mismatched_closing_id_is_rejected():
    text = b"<!-- faq:a concepts:1 -->\n### A\n\nBody.\n<!-- /faq:b -->\n"
    with pytest.raises(MarkerInvariantError, match="does not match"):
        parse_marked_blocks(text, "faq")


def test_close_without_matching_open_is_rejected():
    text = b"### A\n\nBody.\n<!-- /faq:a -->\n"
    with pytest.raises(MarkerInvariantError, match="no matching open marker"):
        parse_marked_blocks(text, "faq")


def test_open_without_matching_close_is_rejected():
    text = b"<!-- faq:a concepts:1 -->\n### A\n\nBody.\n"
    with pytest.raises(MarkerInvariantError, match="never closed"):
        parse_marked_blocks(text, "faq")


def test_nested_open_before_prior_close_is_rejected():
    text = (
        b"<!-- faq:a concepts:1 -->\n### A\n\n"
        b"<!-- faq:b concepts:2 -->\n### B\n\nInner\n<!-- /faq:b -->\n"
        b"<!-- /faq:a -->\n"
    )
    with pytest.raises(MarkerInvariantError, match="opens before"):
        parse_marked_blocks(text, "faq")


def test_duplicate_enrichment_id_within_same_kind_is_rejected():
    text = (
        b"<!-- faq:q-context-object concepts:1 -->\n### A\n\nBody.\n<!-- /faq:q-context-object -->\n\n"
        b"<!-- faq:q-context-object concepts:2 -->\n### B\n\nBody.\n<!-- /faq:q-context-object -->\n"
    )
    with pytest.raises(MarkerInvariantError, match="has 2 markers; expected exactly 1"):
        parse_marked_blocks(text, "faq")


def test_unsorted_concepts_list_is_rejected():
    text = b"<!-- faq:a concepts:39,10 -->\n### A\n\nBody.\n<!-- /faq:a -->\n"
    with pytest.raises(MarkerInvariantError, match="sorted, unique, and ascending"):
        parse_marked_blocks(text, "faq")


def test_duplicate_concept_in_concepts_list_is_rejected():
    text = b"<!-- faq:a concepts:10,10 -->\n### A\n\nBody.\n<!-- /faq:a -->\n"
    with pytest.raises(MarkerInvariantError, match="sorted, unique, and ascending"):
        parse_marked_blocks(text, "faq")


def test_malformed_concepts_token_is_rejected():
    text = b"<!-- faq:a concepts:01,2 -->\n### A\n\nBody.\n<!-- /faq:a -->\n"
    with pytest.raises(MarkerInvariantError, match="malformed concepts list"):
        parse_marked_blocks(text, "faq")


def test_missing_concepts_list_is_rejected_as_malformed():
    text = b"<!-- faq:a -->\n### A\n\nBody.\n<!-- /faq:a -->\n"
    with pytest.raises(MarkerInvariantError, match="malformed paired marker"):
        parse_marked_blocks(text, "faq")


def test_unknown_kind_is_rejected():
    with pytest.raises(MarkerInvariantError, match="unknown enrichment kind"):
        parse_marked_blocks(b"anything", "story")


def test_select_enrichment_blocks_never_returns_whole_file_signal():
    text = (
        b"<!-- faq:a concepts:1 -->\n### A\n\nBody.\n<!-- /faq:a -->\n\n"
        b"<!-- faq:b concepts:2 -->\n### B\n\nBody.\n<!-- /faq:b -->\n"
    )
    selected = select_enrichment_blocks(text, "faq", {2})
    assert [block.id for block in selected] == ["b"]


def test_plan_retired_concept_removal_only_reports_affected_blocks():
    text = (
        b"<!-- glossary:a concepts:1 -->\n#### A\n\nBody.\n<!-- /glossary:a -->\n\n"
        b"<!-- glossary:b concepts:2,3 -->\n#### B\n\nBody.\n<!-- /glossary:b -->\n"
    )
    decisions = plan_retired_concept_removal(text, "glossary", {1})
    assert len(decisions) == 1
    assert decisions[0].block.id == "a"
    assert decisions[0].action == "delete"
