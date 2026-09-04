import json

import pytest

from patch_engine.canonical import canonical_json_bytes
from patch_engine.enrichments import export_faq_json, validate_faq_parity
from patch_engine.markers import parse_marked_blocks
from patch_engine.patches import PatchInvariantError, apply_patch_set


# --- FAQ Markdown -> JSON deterministic projection ---


def test_faq_json_is_a_deterministic_projection_of_markdown(faq_fixture):
    first = export_faq_json(faq_fixture.markdown.read_bytes())
    second = export_faq_json(faq_fixture.markdown.read_bytes())
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert validate_faq_parity(faq_fixture.markdown.read_bytes(), first) == []


def test_faq_json_orders_questions_by_first_appearance_not_id_or_concept(faq_fixture):
    projection = export_faq_json(faq_fixture.markdown.read_bytes())
    ids = [question["id"] for question in projection["questions"]]
    assert ids == ["q-context-object", "q-backend-protocol", "q-glossary-scope"]


def test_faq_json_matches_the_committed_projection_shape(faq_fixture):
    projection = export_faq_json(faq_fixture.markdown.read_bytes())
    assert projection["schema_version"] == "1.0"
    backend = next(q for q in projection["questions"] if q["id"] == "q-backend-protocol")
    assert backend == {
        "id": "q-backend-protocol",
        "concept_ids": [42],
        "question": "What is the backend protocol?",
        "answer_markdown": "The backend protocol defines how services exchange requests and responses.",
        "source": "faq.md",
    }


def test_parity_fails_when_committed_json_diverges_from_markdown(faq_fixture):
    markdown = faq_fixture.markdown.read_bytes()
    committed = export_faq_json(markdown)
    committed["questions"][0]["answer_markdown"] = "A stale, hand-edited answer that no longer matches faq.md."
    errors = validate_faq_parity(markdown, committed)
    assert errors == ["faq-chatbot-training.json is not the deterministic projection of faq.md"]


def test_parity_fails_when_committed_json_is_missing_a_question(faq_fixture):
    markdown = faq_fixture.markdown.read_bytes()
    committed = export_faq_json(markdown)
    committed["questions"].pop()
    assert validate_faq_parity(markdown, committed) != []


def test_committed_fixture_json_matches_export(faq_fixture):
    committed = json.loads((faq_fixture.root / "textbook" / "docs" / "faq-chatbot-training.json").read_text())
    assert validate_faq_parity(faq_fixture.markdown.read_bytes(), committed) == []


# --- Patch application over paired enrichment blocks (faq/glossary/quiz/reference) ---


def test_replace_requires_matching_kind_and_id_in_content(enrichment_fixture):
    fixture = enrichment_fixture("glossary")
    fixture.patch_set["files"][0]["operations"][0]["content"] = (
        "<!-- glossary:some-other-id concepts:42 -->\n#### Backend Protocol\n\nRevised.\n<!-- /glossary:some-other-id -->\n"
    )
    with pytest.raises(PatchInvariantError, match="must be exactly one complete"):
        apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)


def test_delete_removes_entire_enrichment_block_including_markers(enrichment_fixture):
    fixture = enrichment_fixture("quiz")
    fixture.patch_set["files"][0]["operations"][0] = {
        "operation": "delete",
        "kind": "quiz",
        "id": "q2-backend-protocol",
    }
    result = apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)
    after = fixture.path.read_bytes()
    assert b"q2-backend-protocol" not in after
    assert 42 in result.effective_concept_ids


def test_insert_after_adds_a_new_enrichment_block(enrichment_fixture):
    fixture = enrichment_fixture("reference")
    fixture.invocation["targets"]["enrichment_ids"] = ["ref-11"]
    fixture.patch_set["files"][0]["operations"][0] = {
        "operation": "insert_after",
        "kind": "reference",
        "id": "ref-10",
        "content": (
            "<!-- reference:ref-11 concepts:39 -->\n"
            "11. [Extra Resource](https://verified-example.org/extra) - Example Docs - Supplemental "
            "material added after the original ten references.\n"
            "<!-- /reference:ref-11 -->\n"
        ),
    }
    result = apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)
    after = fixture.path.read_bytes()
    assert b"ref-11" in after
    assert result.effective_concept_ids == (39,)
    blocks = parse_marked_blocks(after, "reference")
    assert [b.id for b in blocks][-1] == "ref-11"


def test_insert_rejects_id_already_present(enrichment_fixture):
    fixture = enrichment_fixture("quiz")
    fixture.invocation["targets"]["enrichment_ids"] = ["q1-context-object"]
    fixture.patch_set["files"][0]["operations"][0] = {
        "operation": "insert_after",
        "kind": "quiz",
        "id": "q2-backend-protocol",
        "content": (
            "<!-- quiz:q1-context-object concepts:10 -->\n#### 4. Duplicate?\n\nBody.\n<!-- /quiz:q1-context-object -->\n"
        ),
    }
    with pytest.raises(PatchInvariantError, match="already-present"):
        apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)


def test_replace_undeclared_enrichment_id_is_rejected(enrichment_fixture):
    fixture = enrichment_fixture("faq")
    fixture.invocation["targets"]["enrichment_ids"] = []
    with pytest.raises(PatchInvariantError, match="not declared in invocation targets"):
        apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)


def test_nested_paired_marker_inside_enrichment_replacement_is_rejected(enrichment_fixture):
    fixture = enrichment_fixture("glossary")
    fixture.patch_set["files"][0]["operations"][0]["content"] = (
        "<!-- glossary:backend-protocol concepts:42 -->\n"
        "#### Backend Protocol\n\n"
        "<!-- glossary:nested concepts:1 -->\n"
        "Inner\n"
        "<!-- /glossary:nested -->\n"
        "<!-- /glossary:backend-protocol -->\n"
    )
    with pytest.raises(PatchInvariantError, match="nested paired marker"):
        apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)


def test_insert_before_sharing_offset_with_replace_of_same_block_is_rejected(enrichment_fixture):
    # Adversarial case: insert_before(q-backend-protocol) is positioned at
    # the anchor block's raw start, exactly where the fixture's simultaneous
    # replace of that same block also starts (enrichment "replace" splices
    # over [block.start, block.close_end), unlike concept "replace" which
    # starts after the marker line). This is the paired-enrichment-marker
    # analogue of the concept-marker same-offset splice hazard and must be
    # rejected outright rather than spliced ambiguously.
    fixture = enrichment_fixture("faq")
    fixture.invocation["targets"]["enrichment_ids"].append("q-new")
    fixture.patch_set["files"][0]["operations"].append(
        {
            "operation": "insert_before",
            "kind": "faq",
            "id": "q-backend-protocol",
            "content": "<!-- faq:q-new concepts:42 -->\n### New question?\n\nNew body.\n<!-- /faq:q-new -->\n",
        }
    )
    before = fixture.read_bytes()

    with pytest.raises(PatchInvariantError, match="ambiguous insert position"):
        apply_patch_set(fixture.root, fixture.invocation, fixture.patch_set)
    assert fixture.read_bytes() == before
