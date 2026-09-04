"""Byte-offset parsing and coverage validation for chapter concept markers.

Also parses the separate, paired ``<!-- KIND:ID concepts:N,N --> ... <!--
/KIND:ID -->`` marker syntax used by the FAQ, glossary, quiz, and reference
enrichment skills (``KIND`` is one of ``faq``/``glossary``/``quiz``/
``reference``). The two marker syntaxes are independent: a single-line
``<!-- concept:N -->`` marker introduces a section of chapter prose, while a
paired ``KIND:ID`` marker wraps one complete, independently patchable
enrichment block (one FAQ question, one glossary entry, one quiz question, one
reference item) and carries its own ``concepts:`` association back to the
learning graph.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

class MarkerInvariantError(ValueError):
    """Raised when a Markdown concept-marker or paired-marker block is malformed."""


@dataclass(frozen=True)
class ConceptBlock:
    concept_ids: tuple[int, ...]
    start: int
    content_start: int
    end: int


@dataclass(frozen=True)
class MarkedBlock:
    """A paired ``<!-- KIND:ID concepts:N,N --> ... <!-- /KIND:ID -->`` block.

    ``start``, ``content_start``, and ``end`` mirror :class:`ConceptBlock`:
    ``start`` is the opening tag's first byte, ``content_start`` is the first
    byte of the block body (immediately after the opening tag's own line),
    and ``end`` is the first byte of the closing tag -- the same "content
    span" meaning as ``ConceptBlock.end``, so a body-only replacement uses
    ``content_start:end`` exactly like a concept block does. ``close_end`` is
    the one addition a paired marker needs beyond ``ConceptBlock``: the first
    byte *after* the closing tag, i.e. the end of the whole block including
    both markers, needed to delete or wholesale-replace a block.
    """

    kind: str
    id: str
    concept_ids: tuple[int, ...]
    start: int
    content_start: int
    end: int
    close_end: int


ENRICHMENT_KINDS = ("faq", "glossary", "quiz", "reference")

_MARKER_LINE = re.compile(rb"^[ \t]*<!--\s*concept\s*:\s*([^>]*)-->[ \t]*(?:\r?\n|$)", re.IGNORECASE)
_MARKER_HINT = re.compile(rb"<!--\s*concept\s*:", re.IGNORECASE)
_HEADING = re.compile(rb"^[ \t]*#{1,6}(?:[ \t]+|$)")
_HTML_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)

# Full-line grammar for a paired marker's opening/closing tag, used to parse
# whole enrichment artifact files (faq.md, glossary.md, one chapter's
# quiz.md/references.md) into MarkedBlock spans. Unlike the loose tag-shaped
# regexes below (used only to scan arbitrary patch *content* for nesting),
# these require the marker to occupy its own line and the opening tag to
# carry a well-formed ``concepts:`` list -- matching ConceptBlock's own-line
# requirement for ``<!-- concept:N -->``.
_PAIRED_OPEN_LINE = re.compile(
    rb"^[ \t]*<!--\s*(faq|glossary|quiz|reference)\s*:\s*([a-z0-9][a-z0-9-]*)"
    rb"[ \t]+concepts\s*:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\s*-->[ \t]*(?:\r?\n|$)",
    re.IGNORECASE,
)
_PAIRED_CLOSE_LINE = re.compile(
    rb"^[ \t]*<!--\s*/\s*(faq|glossary|quiz|reference)\s*:\s*([a-z0-9][a-z0-9-]*)\s*-->[ \t]*(?:\r?\n|$)",
    re.IGNORECASE,
)
_PAIRED_HINT = re.compile(rb"<!--\s*/?\s*(?:faq|glossary|quiz|reference)\s*:", re.IGNORECASE)
_CONCEPT_ID_TOKEN = re.compile(r"^[1-9][0-9]*$")

# Loose tag-shaped grammar (id required, ``concepts:`` optional, no own-line
# requirement) used only to scan arbitrary bytes -- e.g. a proposed patch
# replacement -- for genuinely nested/overlapping paired markers. This is
# deliberately more permissive than ``_PAIRED_OPEN_LINE``/``_PAIRED_CLOSE_LINE``
# because it must also catch markers embedded mid-sentence in documentation
# examples, not just well-formed artifact files.
_PAIRED_TAG_OPEN = re.compile(
    rb"<!--\s*(faq|glossary|quiz|reference)\s*:\s*([a-z0-9-]+)"
    rb"(?:[ \t]+concepts\s*:\s*[0-9]+(?:,[0-9]+)*)?\s*-->",
    re.IGNORECASE,
)
_PAIRED_TAG_CLOSE = re.compile(
    rb"<!--\s*/\s*(faq|glossary|quiz|reference)\s*:\s*([a-z0-9-]+)\s*-->",
    re.IGNORECASE,
)
_FENCE_LINE = re.compile(rb"^[ \t]{0,3}(`{3,}|~{3,})[^\r\n]*(?:\r?\n|\Z)", re.MULTILINE)


def _heading_level(line: bytes) -> int:
    """Count leading '#' characters of a matched heading line."""
    stripped = line.lstrip(b" \t")
    level = 0
    for byte in stripped:
        if byte != 0x23:  # '#'
            break
        level += 1
    return level


def _lines(markdown: bytes) -> list[tuple[int, int, bytes]]:
    result: list[tuple[int, int, bytes]] = []
    offset = 0
    for line in markdown.splitlines(keepends=True):
        result.append((offset, offset + len(line), line))
        offset += len(line)
    if not result or offset < len(markdown):
        result.append((offset, len(markdown), markdown[offset:]))
    return result


def _parse(markdown: bytes, *, reject_duplicates: bool) -> tuple[ConceptBlock, ...]:
    if not isinstance(markdown, bytes):
        raise MarkerInvariantError("markdown must be bytes")
    lines = _lines(markdown)
    marker_lines: dict[int, int] = {}
    marker_values: dict[int, int] = {}
    for index, (start, end, line) in enumerate(lines):
        match = _MARKER_LINE.match(line)
        if match:
            raw = match.group(1).strip()
            if not raw.isdigit() or int(raw) < 1:
                raise MarkerInvariantError(f"malformed concept marker at byte {start}")
            marker_lines[index] = start
            marker_values[index] = int(raw)
        elif _MARKER_HINT.search(line):
            raise MarkerInvariantError(f"malformed concept marker at byte {start}")

    clusters: list[tuple[list[int], int, int]] = []
    index = 0
    while index < len(lines):
        if index not in marker_lines:
            index += 1
            continue
        ids: list[int] = []
        first = marker_lines[index]
        last_end = lines[index][1]
        while index < len(lines) and index in marker_lines:
            ids.append(marker_values[index])
            last_end = lines[index][1]
            index += 1
        clusters.append((ids, first, last_end))

    counts: dict[int, int] = defaultdict(int)
    for ids, _, _ in clusters:
        for concept_id in ids:
            counts[concept_id] += 1
    duplicates = sorted((concept_id, count) for concept_id, count in counts.items() if count > 1)
    if reject_duplicates and duplicates:
        concept_id, count = duplicates[0]
        raise MarkerInvariantError(f"concept {concept_id} has {count} markers; expected exactly 1")

    blocks: list[ConceptBlock] = []
    for cluster_index, (ids, start, content_start) in enumerate(clusters):
        next_marker = clusters[cluster_index + 1][1] if cluster_index + 1 < len(clusters) else len(markdown)
        end = next_marker
        # A heading immediately following the marker cluster (skipping any
        # blank lines in between) is the section's own heading, not a
        # boundary. Deeper subheadings within that section are content, not
        # boundaries; only a heading at the same-or-higher level than the
        # section's own heading begins closing/new material.
        introducing_level: int | None = None
        seen_non_blank = False
        for line_start, _, line in lines:
            if line_start < content_start or line_start >= next_marker:
                continue
            if not line.strip():
                continue
            is_introducing_candidate = not seen_non_blank
            seen_non_blank = True
            if not _HEADING.match(line):
                continue
            if is_introducing_candidate:
                introducing_level = _heading_level(line)
                continue
            if introducing_level is not None and _heading_level(line) > introducing_level:
                continue
            end = line_start
            break
        content = markdown[content_start:end]
        # Marker comments and whitespace do not constitute educational content.
        substantive = _HTML_COMMENT.sub(b"", content).strip()
        if not substantive:
            raise MarkerInvariantError(f"concept marker cluster at byte {start} has no substantive content")
        blocks.append(ConceptBlock(tuple(ids), start, content_start, end))
    return tuple(blocks)


def parse_concept_blocks(markdown: bytes) -> tuple[ConceptBlock, ...]:
    """Parse adjacent marker clusters while preserving exact UTF-8 byte offsets."""
    return _parse(markdown, reject_duplicates=True)


def validate_concept_coverage(graph: dict, chapter_root: Path) -> list[str]:
    """Return deterministic errors for active concept marker placement and coverage."""
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["graph must be an object"]
    nodes = graph.get("nodes", [])
    if not isinstance(nodes, list):
        return ["graph nodes must be an array"]
    active = {
        node.get("id"): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), int) and not isinstance(node.get("id"), bool)
    }
    locations: dict[int, list[str]] = defaultdict(list)
    try:
        files = sorted(path for path in chapter_root.rglob("*.md") if path.is_file())
    except OSError as error:
        return [f"could not read chapter root {chapter_root}: {error}"]
    for path in files:
        try:
            blocks = _parse(path.read_bytes(), reject_duplicates=False)
        except (OSError, MarkerInvariantError) as error:
            errors.append(f"{path.relative_to(chapter_root).as_posix()}: {error}")
            continue
        relative = path.relative_to(chapter_root)
        chapter = relative.parts[0] if len(relative.parts) > 1 else ""
        for block in blocks:
            for concept_id in block.concept_ids:
                locations[concept_id].append(relative.as_posix())
                if concept_id not in active:
                    # Retirement is tracked in the separate retired-concepts.json
                    # ledger, not on this graph object, and this function's
                    # signature (graph, chapter_root) has no ledger to consult.
                    # Every inactive marker is therefore reported uniformly as
                    # "unknown"; the plan's actual requirement -- no retired or
                    # unknown concept markers -- is still fully enforced.
                    errors.append(f"unknown concept {concept_id} appears in marker: {relative.as_posix()}")
                elif active[concept_id].get("chapter") != chapter:
                    errors.append(
                        f"concept {concept_id} marker is in chapter {chapter!r}; "
                        f"graph assigns {active[concept_id].get('chapter')!r}"
                    )
    for concept_id in sorted(active):
        count = len(locations.get(concept_id, []))
        if count != 1:
            errors.append(f"concept {concept_id} has {count} markers; expected exactly 1")
    return sorted(set(errors))


def fenced_code_ranges(content: bytes) -> list[tuple[int, int]]:
    """Return the byte ranges of every fenced code block (``` or ~~~ delimited).

    A fence line opens with three-or-more identical backtick or tilde
    characters (optionally indented up to three spaces, per CommonMark) and
    closes on the next fence line using the same character with at least as
    many repeats. An unterminated fence runs to the end of the content.
    """
    ranges: list[tuple[int, int]] = []
    fence_char: bytes | None = None
    fence_len = 0
    fence_start = 0
    for match in _FENCE_LINE.finditer(content):
        marker = match.group(1)
        if fence_char is None:
            fence_char = marker[:1]
            fence_len = len(marker)
            fence_start = match.start()
        elif marker[:1] == fence_char and len(marker) >= fence_len:
            ranges.append((fence_start, match.end()))
            fence_char = None
            fence_len = 0
    if fence_char is not None:
        ranges.append((fence_start, len(content)))
    return ranges


def _inside_any_range(offset: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def assert_no_nested_paired_markers(content: bytes, *, context: str) -> None:
    """Reject genuinely nested/overlapping paired-marker (faq/glossary/quiz/reference) tags.

    Sibling paired markers that close before the next one opens are valid; an open
    tag encountered while another open tag's matching close is still pending, or a
    close tag that does not match the innermost pending open, is a nested paired
    marker and is rejected outright.

    Marker-like tags inside a fenced code block are documentation/example text,
    not real markers, and are excluded from the scan.
    """
    fenced_ranges = fenced_code_ranges(content)
    tags: list[tuple[int, bool, bytes, bytes]] = []
    for match in _PAIRED_TAG_OPEN.finditer(content):
        if _inside_any_range(match.start(), fenced_ranges):
            continue
        tags.append((match.start(), False, match.group(1).lower(), match.group(2)))
    for match in _PAIRED_TAG_CLOSE.finditer(content):
        if _inside_any_range(match.start(), fenced_ranges):
            continue
        tags.append((match.start(), True, match.group(1).lower(), match.group(2)))
    tags.sort(key=lambda item: item[0])

    stack: list[tuple[bytes, bytes]] = []
    for _, is_close, marker_type, marker_id in tags:
        if not is_close:
            if stack:
                open_type, open_id = stack[-1]
                raise MarkerInvariantError(
                    f"{context}: nested paired marker: "
                    f"<!-- {marker_type.decode()}:{marker_id.decode()} --> opens before "
                    f"<!-- /{open_type.decode()}:{open_id.decode()} --> closes"
                )
            stack.append((marker_type, marker_id))
        else:
            if not stack:
                raise MarkerInvariantError(
                    f"{context}: nested paired marker: "
                    f"<!-- /{marker_type.decode()}:{marker_id.decode()} --> has no matching open marker"
                )
            open_type, open_id = stack.pop()
            if (open_type, open_id) != (marker_type, marker_id):
                raise MarkerInvariantError(
                    f"{context}: nested paired marker: "
                    f"<!-- /{marker_type.decode()}:{marker_id.decode()} --> does not match "
                    f"innermost open <!-- {open_type.decode()}:{open_id.decode()} -->"
                )
    if stack:
        open_type, open_id = stack[-1]
        raise MarkerInvariantError(
            f"{context}: nested paired marker: "
            f"<!-- {open_type.decode()}:{open_id.decode()} --> was never closed"
        )


def _parse_sorted_concept_ids(raw: bytes, *, context: str) -> tuple[int, ...]:
    parts = [part.strip() for part in raw.decode("utf-8").split(",")]
    ids: list[int] = []
    for part in parts:
        if not _CONCEPT_ID_TOKEN.match(part):
            raise MarkerInvariantError(f"malformed concepts list at {context}: {raw.decode('utf-8')!r}")
        ids.append(int(part))
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise MarkerInvariantError(
            f"concepts list at {context} must be sorted, unique, and ascending: {raw.decode('utf-8')!r}"
        )
    return tuple(ids)


def _scan_paired_tags(markdown: bytes) -> list[tuple[int, bool, str, str, tuple[int, ...] | None, int]]:
    """Scan every own-line paired-marker open/close tag in document order.

    Returns ``(start, is_close, kind, id, concept_ids_or_None, tag_end)``
    tuples. A line that merely looks like a paired marker (matches
    ``_PAIRED_HINT``) but does not match the full open/close grammar is
    malformed and raises immediately, mirroring ``_parse``'s strict handling
    of ``<!-- concept: ... -->``-shaped lines.

    Lines inside a fenced code block are excluded from the scan, matching
    ``assert_no_nested_paired_markers``'s treatment of marker-like text in
    documentation examples: an artifact file (faq.md, glossary.md, a
    chapter's quiz.md/references.md) is free to show the marker syntax
    inside a fenced example without becoming unparseable.
    """
    fenced_ranges = fenced_code_ranges(markdown)
    events: list[tuple[int, bool, str, str, tuple[int, ...] | None, int]] = []
    for start, end, line in _lines(markdown):
        if _inside_any_range(start, fenced_ranges):
            continue
        open_match = _PAIRED_OPEN_LINE.match(line)
        if open_match:
            kind = open_match.group(1).decode("ascii").lower()
            block_id = open_match.group(2).decode("utf-8").lower()
            concept_ids = _parse_sorted_concept_ids(open_match.group(3), context=f"byte {start}")
            events.append((start, False, kind, block_id, concept_ids, end))
            continue
        close_match = _PAIRED_CLOSE_LINE.match(line)
        if close_match:
            kind = close_match.group(1).decode("ascii").lower()
            block_id = close_match.group(2).decode("utf-8").lower()
            events.append((start, True, kind, block_id, None, end))
            continue
        if _PAIRED_HINT.search(line):
            raise MarkerInvariantError(f"malformed paired marker at byte {start}")
    return events


def _build_marked_blocks(events: list[tuple[int, bool, str, str, tuple[int, ...] | None, int]], kind: str) -> tuple[MarkedBlock, ...]:
    stack: list[tuple[str, str, int, int, tuple[int, ...]]] = []
    blocks: list[MarkedBlock] = []
    seen_ids: set[str] = set()
    for start, is_close, event_kind, event_id, concept_ids, tag_end in events:
        if not is_close:
            if stack:
                open_kind, open_id, *_ = stack[-1]
                raise MarkerInvariantError(
                    f"nested paired marker: <!-- {event_kind}:{event_id} --> opens before "
                    f"<!-- /{open_kind}:{open_id} --> closes"
                )
            stack.append((event_kind, event_id, start, tag_end, concept_ids or ()))
            continue
        if not stack:
            raise MarkerInvariantError(
                f"nested paired marker: <!-- /{event_kind}:{event_id} --> has no matching open marker"
            )
        open_kind, open_id, open_start, content_start, open_concept_ids = stack.pop()
        if (open_kind, open_id) != (event_kind, event_id):
            raise MarkerInvariantError(
                f"nested paired marker: <!-- /{event_kind}:{event_id} --> does not match "
                f"innermost open <!-- {open_kind}:{open_id} -->"
            )
        if open_kind == kind:
            if open_id in seen_ids:
                raise MarkerInvariantError(f"{kind} id {open_id!r} has 2 markers; expected exactly 1")
            seen_ids.add(open_id)
            blocks.append(MarkedBlock(open_kind, open_id, open_concept_ids, open_start, content_start, start, tag_end))
    if stack:
        open_kind, open_id, *_ = stack[-1]
        raise MarkerInvariantError(f"paired marker <!-- {open_kind}:{open_id} --> was never closed")
    return tuple(blocks)


def parse_marked_blocks(markdown: bytes, kind: str) -> tuple[MarkedBlock, ...]:
    """Parse every ``kind`` paired-marker block in ``markdown``, in document order.

    Byte spans are exact and no prose or whitespace is normalized -- the
    returned ``content_start``/``end`` span is copied verbatim by patch
    application. Mismatched open/close ids, nesting, duplicate ids for
    ``kind``, and unsorted/duplicate/malformed ``concepts:`` lists are all
    rejected. Markers of a *different* kind are still scanned (for nesting
    purposes) but are not returned.
    """
    if kind not in ENRICHMENT_KINDS:
        raise MarkerInvariantError(f"unknown enrichment kind: {kind!r}")
    if not isinstance(markdown, bytes):
        raise MarkerInvariantError("markdown must be bytes")
    events = _scan_paired_tags(markdown)
    return _build_marked_blocks(events, kind)


def select_enrichment_blocks(markdown: bytes, kind: str, affected_concept_ids: set[int]) -> tuple[MarkedBlock, ...]:
    """Select only the existing ``kind`` blocks affected by a concept change.

    A block is selected when its ``concept_ids`` set intersects
    ``affected_concept_ids``. This never returns a whole-file signal -- only
    the specific blocks that need attention. Selecting blocks for a newly
    added concept (choosing a stable id and insertion anchor) and deciding
    delete-vs-update for a retired concept are both out of scope here; see
    :func:`plan_retired_concept_removal` for the latter.
    """
    affected = set(affected_concept_ids)
    return tuple(block for block in parse_marked_blocks(markdown, kind) if set(block.concept_ids) & affected)


@dataclass(frozen=True)
class RetiredConceptDecision:
    """What an incremental skill should do with one block after a concept retires.

    ``action`` is ``"delete"`` when removing the retired id leaves the
    block's concept set empty -- nothing anchors it to any active concept any
    more -- and ``"update"`` when the block still names at least one other
    concept, so only its ``concepts:`` metadata (and, via an explicit
    reviewed patch, its prose) needs to drop the retired id.
    """

    block: MarkedBlock
    action: str
    remaining_concept_ids: tuple[int, ...]


def plan_retired_concept_removal(
    markdown: bytes, kind: str, retired_concept_ids: set[int]
) -> tuple[RetiredConceptDecision, ...]:
    """Classify every ``kind`` block touched by a concept retirement as delete-or-update.

    Only blocks whose concept set intersects ``retired_concept_ids`` are
    returned, mirroring :func:`select_enrichment_blocks`'s "only the blocks
    that need attention" contract. The actual delete/replace patch operation
    is still an explicit, reviewed edit -- this function only classifies.
    """
    retired = set(retired_concept_ids)
    decisions: list[RetiredConceptDecision] = []
    for block in parse_marked_blocks(markdown, kind):
        if not (set(block.concept_ids) & retired):
            continue
        remaining = tuple(sorted(set(block.concept_ids) - retired))
        decisions.append(RetiredConceptDecision(block, "delete" if not remaining else "update", remaining))
    return tuple(decisions)
