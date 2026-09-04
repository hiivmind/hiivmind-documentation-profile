"""FAQ Markdown/JSON parity and enrichment-marker validation/selection helpers.

Byte-offset parsing and the paired-marker grammar itself live in
``markers.py`` (``parse_marked_blocks``, ``select_enrichment_blocks``,
``plan_retired_concept_removal``); this module builds the FAQ-specific
Markdown-to-JSON projection on top of that parsing, plus the thin
error-list-returning wrappers the CLI (``enrichments affected|validate`` and
``faq export|validate``) needs.
"""

from __future__ import annotations

import re

from .canonical import canonical_json_bytes

from .markers import (
    ENRICHMENT_KINDS,
    MarkerInvariantError,
    parse_marked_blocks,
    select_enrichment_blocks,
)

FAQ_SOURCE_FILENAME = "faq.md"

_HEADING_LINE = re.compile(rb"^[ \t]*(#{1,6})[ \t]+(.*?)[ \t]*(?:\r?\n|$)")


def validate_enrichment_markers(markdown: bytes, kind: str) -> list[str]:
    """Return deterministic structural errors for a kind's paired-marker blocks.

    Mismatched open/close ids, nesting, duplicate ids, and unsorted/duplicate/
    malformed ``concepts:`` lists are all surfaced here (via
    ``parse_marked_blocks``) as a plain error list, matching the
    ``validate_concept_coverage``/``markers validate`` convention rather than
    raising.
    """
    if kind not in ENRICHMENT_KINDS:
        return [f"unknown enrichment kind: {kind!r}"]
    try:
        parse_marked_blocks(markdown, kind)
    except MarkerInvariantError as error:
        return [str(error)]
    return []


def affected_block_ids(markdown: bytes, kind: str, affected_concept_ids: set[int]) -> list[str]:
    """Return the ids of the ``kind`` blocks affected by a concept change, in document order."""
    return [block.id for block in select_enrichment_blocks(markdown, kind, affected_concept_ids)]


def _split_heading_and_answer(body: bytes) -> tuple[str, str]:
    """Split a FAQ block's body into its question heading text and answer markdown.

    The heading is the first non-blank line, which must be a Markdown ATX
    heading (``#`` through ``######``); its leading ``#`` characters and
    surrounding whitespace are stripped to produce the question text. Every
    remaining line forms the answer, with leading/trailing blank lines
    trimmed but internal formatting (including links) preserved verbatim.
    """
    lines = body.splitlines(keepends=True)
    heading_index = None
    for index, line in enumerate(lines):
        if line.strip():
            heading_index = index
            break
    if heading_index is None:
        raise MarkerInvariantError("faq block has no question heading")
    heading_match = _HEADING_LINE.match(lines[heading_index])
    if not heading_match:
        raise MarkerInvariantError("faq block's first non-blank line is not a Markdown heading")
    question = heading_match.group(2).decode("utf-8").strip()
    answer_bytes = b"".join(lines[heading_index + 1 :]).strip(b"\r\n \t")
    return question, answer_bytes.decode("utf-8")


def export_faq_json(faq_markdown: bytes) -> dict:
    """Compute the deterministic ``faq-chatbot-training.json`` projection of ``faq_markdown``.

    Questions are ordered by first appearance in the Markdown (document
    order), which is exactly the order ``parse_marked_blocks`` already
    returns blocks in.
    """
    questions = []
    for block in parse_marked_blocks(faq_markdown, "faq"):
        body = faq_markdown[block.content_start : block.end]
        question, answer_markdown = _split_heading_and_answer(body)
        questions.append(
            {
                "id": block.id,
                "concept_ids": list(block.concept_ids),
                "question": question,
                "answer_markdown": answer_markdown,
                "source": FAQ_SOURCE_FILENAME,
            }
        )
    return {"schema_version": "1.0", "questions": questions}


def validate_faq_parity(faq_markdown: bytes, chatbot_json: dict) -> list[str]:
    """Return a non-empty error list unless ``chatbot_json`` is exactly ``export_faq_json(faq_markdown)``."""
    try:
        expected = export_faq_json(faq_markdown)
    except MarkerInvariantError as error:
        return [str(error)]
    if canonical_json_bytes(expected) != canonical_json_bytes(chatbot_json):
        return ["faq-chatbot-training.json is not the deterministic projection of faq.md"]
    return []
