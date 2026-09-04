"""Stale-safe, byte-bounded, atomic application of Markdown concept-marker patch sets.

A patch set targets one or more marker blocks (see ``markers.py``) across one or
more project-relative files. Every file's declared base digest and every
operation across the WHOLE patch set is validated before any file is written
(a two-phase plan-then-apply design): if any single check fails, nothing on
disk changes. Byte ranges are always computed against the pre-patch bytes
returned by ``parse_concept_blocks`` and spliced from the highest offset to
the lowest so that earlier (lower-offset) pending ranges are never invalidated
by a preceding edit. The spliced result is re-parsed and diffed against an
independently recomputed prefix/gap/suffix expectation before being accepted,
proving byte preservation outside the targeted blocks rather than merely
assuming it.

Design choice: deleting a single member of a shared (multi-concept) marker
cluster is rejected outright rather than guessing which sibling markers
should survive -- the whole cluster is one atomic future-update unit, so a
partial delete is ambiguous and requires an explicit human-reviewed edit
instead of an automated patch operation.

This module is deliberately dependency-free (stdlib only). There is no JSON
Schema/protocol envelope here -- ``invocation`` and ``patch_set`` are plain
dicts checked with ordinary Python, not validated against an external schema
file. This tool is meant to be invoked by a human-supervised skill run, not
by unattended cross-repo automation, so that extra ceremony was cut.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import sha256_bytes
from .markers import (
    ENRICHMENT_KINDS,
    ConceptBlock,
    MarkedBlock,
    MarkerInvariantError,
    assert_no_nested_paired_markers,
    parse_concept_blocks,
    parse_marked_blocks,
)

_MARKER_HINT = re.compile(rb"<!--\s*concept\s*:", re.IGNORECASE)
_CONCEPT_ID = re.compile(r"^[1-9][0-9]*$")
_ENRICHMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PatchInvariantError(ValueError):
    """Raised when a patch set would violate bounded, atomic-application invariants."""


class StaleInputError(PatchInvariantError):
    """Raised when a patch's declared base digest no longer matches the file on disk."""


@dataclass(frozen=True)
class PatchResult:
    outputs: tuple[dict, ...]
    requested_concept_ids: tuple[int, ...]
    effective_concept_ids: tuple[int, ...]
    preserved: tuple[dict, ...]
    warnings: tuple[dict, ...]


@dataclass(frozen=True)
class _SpliceRange:
    start: int
    end: int
    replacement: bytes


@dataclass(frozen=True)
class _FilePlan:
    abs_path: Path
    relative: str
    original: bytes
    result: bytes


def _validate_patch_set_shape(patch_set: dict) -> None:
    """Plain-Python structural check, replacing what a JSON Schema used to gate.

    Deeper per-field validation (concept-id/enrichment-id patterns, operation
    shape) is already done by ``_concept_id``/``_enrichment_id``/the
    kind-and-action dispatch in ``_plan_file`` -- this only guards the direct
    ``dict[...]`` indexing this module does before that point.
    """
    files = patch_set.get("files")
    if not isinstance(files, list) or not files:
        raise PatchInvariantError("patch_set.files must be a non-empty array")
    for entry in files:
        if not isinstance(entry, dict):
            raise PatchInvariantError("each patch_set.files entry must be an object")
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            raise PatchInvariantError("each patch_set.files entry requires a non-empty 'path'")
        if not isinstance(entry.get("base_sha256"), str) or not entry["base_sha256"]:
            raise PatchInvariantError("each patch_set.files entry requires a 'base_sha256' string")
        operations = entry.get("operations")
        if not isinstance(operations, list) or not operations:
            raise PatchInvariantError(f"{entry.get('path')}: 'operations' must be a non-empty array")
        for operation in operations:
            if not isinstance(operation, dict):
                raise PatchInvariantError(f"{entry.get('path')}: each operation must be an object")


def _relative_path(raw: Any) -> PurePosixPath:
    if not isinstance(raw, str) or not raw:
        raise PatchInvariantError(f"patch target path must be a non-empty string: {raw!r}")
    if "\\" in raw:
        raise PatchInvariantError(f"path is not project-relative: {raw}")
    parsed = PurePosixPath(raw)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise PatchInvariantError(f"path escapes the project root: {raw}")
    return parsed


def _resolve_within(project_root: Path, relative: PurePosixPath) -> Path:
    root = project_root.resolve()
    candidate = (root / Path(str(relative))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PatchInvariantError(f"path escapes the project root: {relative.as_posix()}") from error
    return candidate


def _allowed_output(relative: PurePosixPath, allowed_outputs: list) -> bool:
    allowed = {PurePosixPath(item).as_posix() for item in allowed_outputs if isinstance(item, str)}
    return relative.as_posix() in allowed


def _concept_id(raw: Any) -> int:
    if isinstance(raw, str) and _CONCEPT_ID.match(raw):
        return int(raw)
    raise PatchInvariantError(f"concept id must be a positive-integer string: {raw!r}")


def _declared_targets(invocation: dict) -> set[int]:
    targets = invocation.get("targets")
    if not isinstance(targets, dict):
        raise PatchInvariantError("invocation targets must be an object")
    concept_ids = targets.get("concept_ids")
    if not isinstance(concept_ids, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in concept_ids
    ):
        raise PatchInvariantError("invocation targets.concept_ids must be an array of integers")
    return set(concept_ids)


def _enrichment_id(raw: Any) -> str:
    if isinstance(raw, str) and _ENRICHMENT_ID.match(raw):
        return raw
    raise PatchInvariantError(f"enrichment id must be a lowercase slug string: {raw!r}")


def _declared_enrichment_ids(invocation: dict) -> set[str]:
    """Return the flat set of enrichment ids ``targets.enrichment_ids`` declares.

    Deliberately not kind-scoped: a declared id authorizes a patch to any
    kind's block sharing that id string, not just the kind it was presumably
    declared for. The practical risk is low: a cross-kind collision requires
    a same-named block of a *different* kind to genuinely exist in a file
    targeted by the same patch set.
    """
    targets = invocation.get("targets")
    if not isinstance(targets, dict):
        raise PatchInvariantError("invocation targets must be an object")
    enrichment_ids = targets.get("enrichment_ids", [])
    if not isinstance(enrichment_ids, list) or not all(isinstance(item, str) for item in enrichment_ids):
        raise PatchInvariantError("invocation targets.enrichment_ids must be an array of strings")
    return set(enrichment_ids)


def _contains_marker_syntax(content: bytes) -> bool:
    return bool(_MARKER_HINT.search(content))


def _assert_no_nested_paired_markers(content: bytes, *, context: str) -> None:
    """Reject genuinely nested/overlapping paired-marker (faq/glossary/quiz/reference) tags.

    The scan itself lives in ``markers.py`` (shared with ``parse_marked_blocks``,
    which needs the identical invariant while also building byte spans) so
    there is exactly one nesting-detection implementation; this wrapper only
    translates ``MarkerInvariantError`` into this module's ``PatchInvariantError``.
    """
    try:
        assert_no_nested_paired_markers(content, context=context)
    except MarkerInvariantError as error:
        raise PatchInvariantError(str(error)) from error


def _splice(original: bytes, ranges: list[_SpliceRange]) -> bytes:
    """Apply every range from the highest offset to the lowest against a mutable copy.

    Ranges are computed once against ``original``. Processing from the
    highest start offset down means a range's own substitution can never
    shift the offsets of a range with a lower (still-pending) start, so no
    offset needs to be recomputed mid-application.
    """
    result = bytearray(original)
    for item in sorted(ranges, key=lambda entry: entry.start, reverse=True):
        result[item.start : item.end] = item.replacement
    return bytes(result)


def _assert_byte_preservation(original: bytes, result: bytes, ranges: list[_SpliceRange]) -> None:
    """Independently recompute prefix/gap/suffix expectations and diff them against ``result``.

    This does not trust ``_splice``'s construction; it re-derives the
    untouched byte regions from ``original`` and ``ranges`` alone and proves
    they land, unchanged, at the corresponding position in ``result``.
    """
    ordered = sorted(ranges, key=lambda entry: entry.start)
    orig_cursor = 0
    res_cursor = 0
    for item in ordered:
        gap = original[orig_cursor : item.start]
        if result[res_cursor : res_cursor + len(gap)] != gap:
            raise PatchInvariantError("byte-preservation invariant violated outside targeted blocks")
        res_cursor += len(gap) + len(item.replacement)
        orig_cursor = item.end
    tail = original[orig_cursor:]
    if result[res_cursor:] != tail:
        raise PatchInvariantError("byte-preservation invariant violated outside targeted blocks")


def _parse_blocks(content: bytes, *, context: str) -> tuple[ConceptBlock, ...]:
    try:
        return parse_concept_blocks(content)
    except MarkerInvariantError as error:
        raise PatchInvariantError(f"{context}: {error}") from error


def _parse_marked(content: bytes, kind: str, *, context: str) -> tuple[MarkedBlock, ...]:
    try:
        return parse_marked_blocks(content, kind)
    except MarkerInvariantError as error:
        raise PatchInvariantError(f"{context}: {error}") from error


def _plan_file(
    project_root: Path,
    allowed_outputs: list,
    declared_targets: set[int],
    declared_enrichment_ids: set[str],
    entry: dict,
) -> tuple[_FilePlan, set[int]]:
    relative = _relative_path(entry.get("path"))
    if not _allowed_output(relative, allowed_outputs):
        raise PatchInvariantError(f"path is outside allowed_outputs: {relative.as_posix()}")
    abs_path = _resolve_within(project_root, relative)
    if not abs_path.is_file():
        raise PatchInvariantError(f"patch target does not exist: {relative.as_posix()}")

    original = abs_path.read_bytes()
    expected = entry.get("base_sha256")
    actual = sha256_bytes(original)
    if expected != actual:
        raise StaleInputError(
            f"stale file sha256 digest for {relative.as_posix()}: expected {expected}, actual {actual}"
        )

    original_blocks = _parse_blocks(original, context=relative.as_posix())
    block_by_id: dict[int, ConceptBlock] = {}
    for block in original_blocks:
        for concept_id in block.concept_ids:
            block_by_id[concept_id] = block

    enrichment_block_by_id: dict[tuple[str, str], MarkedBlock] = {}
    for enrichment_kind in ENRICHMENT_KINDS:
        for block in _parse_marked(original, enrichment_kind, context=relative.as_posix()):
            enrichment_block_by_id[(enrichment_kind, block.id)] = block

    ranges: list[_SpliceRange] = []
    touched_ids: set[int] = set()
    deleted_ids: set[int] = set()
    inserted_ids: set[int] = set()
    touched_enrichment_kinds: set[str] = set()

    for operation in entry["operations"]:
        kind = operation.get("kind")
        action = operation.get("operation")

        if kind == "concept":
            anchor_id = _concept_id(operation.get("id"))

            if action == "replace":
                if anchor_id not in declared_targets:
                    raise PatchInvariantError(f"concept {anchor_id} is not declared in invocation targets")
                block = block_by_id.get(anchor_id)
                if block is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: no marker found for concept {anchor_id}")
                content_bytes = str(operation.get("content", "")).encode("utf-8")
                if _contains_marker_syntax(content_bytes):
                    raise PatchInvariantError(
                        f"replacement for concept {anchor_id} changes marker identity: "
                        "content embeds a concept marker"
                    )
                _assert_no_nested_paired_markers(
                    content_bytes, context=f"{relative.as_posix()}: concept {anchor_id} replacement"
                )
                ranges.append(_SpliceRange(block.content_start, block.end, content_bytes))
                touched_ids.update(block.concept_ids)

            elif action == "delete":
                if anchor_id not in declared_targets:
                    raise PatchInvariantError(f"concept {anchor_id} is not declared in invocation targets")
                block = block_by_id.get(anchor_id)
                if block is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: no marker found for concept {anchor_id}")
                if len(block.concept_ids) > 1:
                    raise PatchInvariantError(
                        f"delete of concept {anchor_id} targets one member of shared marker cluster "
                        f"{block.concept_ids}; deleting a shared-cluster member is unsupported, "
                        "retarget the whole cluster with an explicit reviewed edit"
                    )
                ranges.append(_SpliceRange(block.start, block.end, b""))
                touched_ids.update(block.concept_ids)
                deleted_ids.update(block.concept_ids)

            elif action in ("insert_before", "insert_after"):
                anchor = block_by_id.get(anchor_id)
                if anchor is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: insert anchor concept {anchor_id} not found")
                content_bytes = str(operation.get("content", "")).encode("utf-8")
                _assert_no_nested_paired_markers(
                    content_bytes, context=f"{relative.as_posix()}: {action} content for concept {anchor_id}"
                )
                new_blocks = _parse_blocks(content_bytes, context=f"{relative.as_posix()}: insert content")
                if len(new_blocks) != 1 or new_blocks[0].start != 0 or new_blocks[0].end != len(content_bytes):
                    raise PatchInvariantError(
                        f"{action} content must be exactly one complete marked block"
                    )
                new_ids = new_blocks[0].concept_ids
                already_present = [new_id for new_id in new_ids if new_id in block_by_id]
                if already_present:
                    raise PatchInvariantError(
                        f"insert introduces already-present concept marker(s): {already_present}"
                    )
                undeclared = [new_id for new_id in new_ids if new_id not in declared_targets]
                if undeclared:
                    raise PatchInvariantError(
                        f"inserted concept(s) not declared in invocation targets: {undeclared}"
                    )
                position = anchor.start if action == "insert_before" else anchor.end
                ranges.append(_SpliceRange(position, position, content_bytes))
                touched_ids.update(new_ids)
                inserted_ids.update(new_ids)

            else:
                raise PatchInvariantError(f"unsupported patch operation: {action!r}")

        elif kind in ENRICHMENT_KINDS:
            anchor_id = _enrichment_id(operation.get("id"))
            touched_enrichment_kinds.add(kind)

            if action == "replace":
                if anchor_id not in declared_enrichment_ids:
                    raise PatchInvariantError(f"{kind} id {anchor_id} is not declared in invocation targets")
                block = enrichment_block_by_id.get((kind, anchor_id))
                if block is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: no {kind} marker found for id {anchor_id}")
                content_bytes = str(operation.get("content", "")).encode("utf-8")
                new_blocks = _parse_marked(
                    content_bytes, kind, context=f"{relative.as_posix()}: replacement for {kind} {anchor_id}"
                )
                if (
                    len(new_blocks) != 1
                    or new_blocks[0].id != anchor_id
                    or new_blocks[0].start != 0
                    or new_blocks[0].close_end != len(content_bytes)
                ):
                    raise PatchInvariantError(
                        f"replacement for {kind} {anchor_id} must be exactly one complete "
                        f"{kind}:{anchor_id} marked block (open and close markers included)"
                    )
                ranges.append(_SpliceRange(block.start, block.close_end, content_bytes))
                touched_ids.update(block.concept_ids)
                touched_ids.update(new_blocks[0].concept_ids)

            elif action == "delete":
                if anchor_id not in declared_enrichment_ids:
                    raise PatchInvariantError(f"{kind} id {anchor_id} is not declared in invocation targets")
                block = enrichment_block_by_id.get((kind, anchor_id))
                if block is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: no {kind} marker found for id {anchor_id}")
                ranges.append(_SpliceRange(block.start, block.close_end, b""))
                touched_ids.update(block.concept_ids)

            elif action in ("insert_before", "insert_after"):
                anchor = enrichment_block_by_id.get((kind, anchor_id))
                if anchor is None:
                    raise PatchInvariantError(f"{relative.as_posix()}: insert anchor {kind} {anchor_id} not found")
                content_bytes = str(operation.get("content", "")).encode("utf-8")
                new_blocks = _parse_marked(
                    content_bytes, kind, context=f"{relative.as_posix()}: {action} content for {kind} {anchor_id}"
                )
                if len(new_blocks) != 1 or new_blocks[0].start != 0 or new_blocks[0].close_end != len(content_bytes):
                    raise PatchInvariantError(f"{action} content must be exactly one complete {kind} marked block")
                new_block = new_blocks[0]
                if (kind, new_block.id) in enrichment_block_by_id:
                    raise PatchInvariantError(f"insert introduces already-present {kind} marker: {new_block.id}")
                if new_block.id not in declared_enrichment_ids:
                    raise PatchInvariantError(
                        f"inserted {kind} id not declared in invocation targets: {new_block.id}"
                    )
                position = anchor.start if action == "insert_before" else anchor.close_end
                ranges.append(_SpliceRange(position, position, content_bytes))
                touched_ids.update(new_block.concept_ids)

            else:
                raise PatchInvariantError(f"unsupported patch operation: {action!r}")

        else:
            raise PatchInvariantError(f"unsupported patch target kind: {kind!r}")

    by_start: dict[int, list[_SpliceRange]] = {}
    for item in ranges:
        by_start.setdefault(item.start, []).append(item)
    for start, group in by_start.items():
        if len(group) > 1 and any(item.start == item.end for item in group):
            # A zero-width insert sharing its offset with the START of any other
            # operation's range (another zero-width insert, or a replace/delete)
            # is inherently ambiguous: _splice's highest-offset-first ordering ties
            # break on insertion order, so which side of the shared boundary the
            # insert lands on is undefined and can silently corrupt the result
            # (the inserted content can be clobbered by, or bleed into, the
            # adjacent replace/delete). Reject outright rather than guess.
            raise PatchInvariantError(
                f"{relative.as_posix()}: ambiguous insert position: conflicts with a replace/delete "
                f"boundary at byte {start}"
            )

    ordered = sorted(ranges, key=lambda item: (item.start, item.end))
    for previous, current in zip(ordered, ordered[1:]):
        if current.start < previous.end:
            raise PatchInvariantError(f"{relative.as_posix()}: overlapping or duplicate patch operations")

    result = _splice(original, ordered)
    _assert_byte_preservation(original, result, ordered)
    _assert_no_nested_paired_markers(result, context=f"{relative.as_posix()}: patch result")

    result_blocks = _parse_blocks(result, context=f"{relative.as_posix()}: patch result")
    original_ids = {concept_id for block in original_blocks for concept_id in block.concept_ids}
    expected_ids = (original_ids - deleted_ids) | inserted_ids
    result_ids = {concept_id for block in result_blocks for concept_id in block.concept_ids}
    if result_ids != expected_ids:
        raise PatchInvariantError(
            f"{relative.as_posix()}: patch result marker coverage changed unexpectedly "
            f"(expected {sorted(expected_ids)}, got {sorted(result_ids)})"
        )

    # Every enrichment kind actually touched by an operation in this file has
    # its structural integrity (mismatched/nested/duplicate markers, sorted
    # concepts:) re-checked on the whole result, not just the spliced range --
    # a splice can only be trusted once the file re-parses cleanly. Kinds
    # never targeted by an operation are left alone: blindly re-scanning
    # unrelated content for every kind would misfire on ordinary prose or
    # fenced-code documentation examples that merely resemble marker syntax.
    for enrichment_kind in touched_enrichment_kinds:
        _parse_marked(result, enrichment_kind, context=f"{relative.as_posix()}: patch result")

    return _FilePlan(abs_path, relative.as_posix(), original, result), touched_ids


def _requested_concept_ids(patch_set: dict) -> set[int]:
    requested: set[int] = set()
    for entry in patch_set["files"]:
        for operation in entry["operations"]:
            if operation.get("kind") == "concept":
                requested.add(_concept_id(operation.get("id")))
    return requested


def _plan(project_root: Path, invocation: dict, patch_set: dict) -> tuple[list[_FilePlan], set[int], set[int]]:
    if not isinstance(project_root, Path):
        raise PatchInvariantError("project_root must be a Path")
    if not isinstance(invocation, dict):
        raise PatchInvariantError("invocation must be an object")
    if not isinstance(patch_set, dict):
        raise PatchInvariantError("patch_set must be an object")

    _validate_patch_set_shape(patch_set)

    allowed_outputs = invocation.get("allowed_outputs")
    if not isinstance(allowed_outputs, list):
        raise PatchInvariantError("invocation allowed_outputs must be an array")
    declared_targets = _declared_targets(invocation)
    declared_enrichment_ids = _declared_enrichment_ids(invocation)
    requested_ids = _requested_concept_ids(patch_set)

    entries = patch_set["files"]
    normalized = [_relative_path(entry["path"]).as_posix() for entry in entries]
    if len(set(normalized)) != len(normalized):
        raise PatchInvariantError("patch set targets the same file more than once")

    plans: list[_FilePlan] = []
    effective_ids: set[int] = set()
    for entry in entries:
        plan, touched_ids = _plan_file(project_root, allowed_outputs, declared_targets, declared_enrichment_ids, entry)
        plans.append(plan)
        effective_ids.update(touched_ids)

    return plans, requested_ids, effective_ids


def _preserved_inputs(invocation: dict, project_root: Path, touched: set[str]) -> tuple[dict, ...]:
    inputs = invocation.get("inputs")
    if not isinstance(inputs, list):
        return ()
    preserved: list[dict] = []
    for item in inputs:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            continue
        try:
            relative = _relative_path(raw_path)
        except PatchInvariantError:
            continue
        if relative.as_posix() in touched:
            continue
        candidate = project_root / Path(str(relative))
        if not candidate.is_file():
            continue
        preserved.append({"path": relative.as_posix(), "sha256": sha256_bytes(candidate.read_bytes())})
    return tuple(preserved)


def _output_entries(plans: list[_FilePlan]) -> tuple[dict, ...]:
    return tuple(
        {
            "path": plan.relative,
            "sha256": sha256_bytes(plan.result),
            "change": "unchanged" if plan.result == plan.original else "modified",
        }
        for plan in plans
    )


def plan_patch_set(project_root: Path, invocation: dict, patch_set: dict) -> PatchResult:
    """Validate a patch set and compute its effect without writing any file (dry run)."""
    plans, requested_ids, effective_ids = _plan(project_root, invocation, patch_set)
    touched = {plan.relative for plan in plans}
    return PatchResult(
        outputs=_output_entries(plans),
        requested_concept_ids=tuple(sorted(requested_ids)),
        effective_concept_ids=tuple(sorted(effective_ids)),
        preserved=_preserved_inputs(invocation, project_root, touched),
        warnings=(),
    )


def _write_temp(directory: Path, prefix: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=prefix, dir=directory)
    handle = None
    try:
        handle = os.fdopen(fd, "wb")
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:
        if handle is None:
            os.close(fd)
        else:
            handle.close()
        Path(name).unlink(missing_ok=True)
        raise
    else:
        handle.close()
    return Path(name)


def _atomic_write_all(plans: list[_FilePlan]) -> None:
    """Replace every planned file, restoring every already-written file if any replacement fails.

    A rollback failure (an ``OSError`` raised while restoring an
    already-written file's original bytes) MUST propagate rather than be
    swallowed: the caller needs to know when recovery itself failed, since a
    disk-full or permissions error during rollback can otherwise leave files
    half-applied with no signal at all.
    """
    temporaries = [(plan, _write_temp(plan.abs_path.parent, f".{plan.abs_path.name}.tmp-", plan.result)) for plan in plans]
    written: list[_FilePlan] = []
    try:
        for plan, temporary in temporaries:
            os.replace(temporary, plan.abs_path)
            written.append(plan)
    except Exception:
        for plan in written:
            rollback = _write_temp(plan.abs_path.parent, f".{plan.abs_path.name}.rollback-", plan.original)
            try:
                os.replace(rollback, plan.abs_path)
            finally:
                rollback.unlink(missing_ok=True)
        raise
    finally:
        for _, temporary in temporaries:
            temporary.unlink(missing_ok=True)


def apply_patch_set(project_root: Path, invocation: dict, patch_set: dict) -> PatchResult:
    """Apply a stale-safe, bounded patch set atomically across every targeted file.

    Every file's base digest and every operation across the whole patch set is
    validated (see :func:`plan_patch_set`) before any file is written. Only
    once every candidate output validates are the files replaced; a failure
    partway through the write phase rolls every already-written file in this
    application back to its original bytes.
    """
    plans, requested_ids, effective_ids = _plan(project_root, invocation, patch_set)
    _atomic_write_all(plans)
    touched = {plan.relative for plan in plans}
    return PatchResult(
        outputs=_output_entries(plans),
        requested_concept_ids=tuple(sorted(requested_ids)),
        effective_concept_ids=tuple(sorted(effective_ids)),
        preserved=_preserved_inputs(invocation, project_root, touched),
        warnings=(),
    )
