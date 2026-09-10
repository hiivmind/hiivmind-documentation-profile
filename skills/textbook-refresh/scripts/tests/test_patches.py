import pytest

from patch_engine.canonical import sha256_bytes
from patch_engine.patches import PatchInvariantError, StaleInputError, apply_patch_set
from patch_engine import patches


def test_concept_patch_preserves_every_byte_outside_atomic_block(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    old_block = content_fixture.block(before, 42)
    new_block = content_fixture.block(after, 42)
    assert before[: old_block.start] == after[: new_block.start]
    assert before[old_block.end :] == after[new_block.end :]
    assert result.effective_concept_ids == (42,)


def test_targeting_member_of_shared_block_expands_effective_targets(content_fixture):
    _, invocation, patch_set = content_fixture.shared_concept_update(requested=8)
    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    assert result.effective_concept_ids == (8, 9)


def test_patch_refuses_file_changed_after_planning(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    content_fixture.chapter.write_text(content_fixture.chapter.read_text() + "\neditor change\n")
    with pytest.raises(StaleInputError, match="sha256"):
        apply_patch_set(content_fixture.root, invocation, patch_set)


def test_path_traversal_in_patch_target_is_rejected(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["path"] = "../outside.md"
    before = content_fixture.chapter.read_bytes()
    with pytest.raises(PatchInvariantError, match="escapes the project root"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_path_outside_allowed_outputs_is_rejected(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    invocation["allowed_outputs"] = ["textbook/docs/chapters/99-other/index.md"]
    with pytest.raises(PatchInvariantError, match="allowed_outputs"):
        apply_patch_set(content_fixture.root, invocation, patch_set)


def test_duplicate_marker_in_target_file_is_rejected_before_any_write(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    mutated = content_fixture.chapter.read_bytes().replace(
        b"<!-- concept:42 -->", b"<!-- concept:42 -->\n<!-- concept:42 -->", 1
    )
    content_fixture.chapter.write_bytes(mutated)
    patch_set["files"][0]["base_sha256"] = sha256_bytes(mutated)

    with pytest.raises(PatchInvariantError, match="42"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == mutated


def test_operation_targeting_undeclared_concept_is_rejected(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0]["id"] = "1"
    with pytest.raises(PatchInvariantError, match="target"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_replacement_embedding_different_marker_changes_identity(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0]["content"] = (
        "## Backend Protocol\n\nRevised.\n\n<!-- concept:99 -->\n## Sneaky\n\nBody.\n"
    )
    with pytest.raises(PatchInvariantError, match="marker identity"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_replacement_with_nested_paired_marker_is_rejected(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0]["content"] = (
        "## Backend Protocol\n\n"
        "<!-- faq:q-context-object concepts:1 -->\n"
        "### Q\n\n"
        "Body with <!-- faq:q-nested concepts:2 -->\n"
        "Inner\n"
        "<!-- /faq:q-nested -->\n"
        "<!-- /faq:q-context-object -->\n"
    )
    with pytest.raises(PatchInvariantError, match="nested paired marker"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_replacement_with_flat_paired_marker_is_accepted(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0]["content"] = (
        "## Backend Protocol\n\n"
        "<!-- faq:q-context-object concepts:1 -->\n"
        "### What is a context object?\n\n"
        "A context object supplies values evaluated against rules.\n"
        "<!-- /faq:q-context-object -->\n"
    )

    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    assert result.effective_concept_ids == (42,)
    assert b"<!-- faq:q-context-object concepts:1 -->" in after
    assert b"<!-- /faq:q-context-object -->" in after


def test_delete_removes_entire_block_including_marker(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0] = {"operation": "delete", "kind": "concept", "id": "42"}

    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    assert result.effective_concept_ids == (42,)
    assert b"concept:42" not in after
    assert b"Backend Protocol" not in after


def test_delete_of_shared_cluster_member_is_rejected(content_fixture):
    before, invocation, patch_set = content_fixture.shared_concept_update(requested=8)
    patch_set["files"][0]["operations"][0] = {"operation": "delete", "kind": "concept", "id": "8"}

    with pytest.raises(PatchInvariantError, match="shared"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_insert_after_adds_new_block_without_disturbing_anchor(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    invocation["targets"]["concept_ids"] = [50]
    patch_set["files"][0]["operations"][0] = {
        "operation": "insert_after",
        "kind": "concept",
        "id": "42",
        "content": "<!-- concept:50 -->\n## New Section\n\nBrand new content.\n",
    }

    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    anchor_before = content_fixture.block(before, 42)
    anchor_after = content_fixture.block(after, 42)
    assert before[: anchor_before.end] == after[: anchor_after.end]
    assert result.effective_concept_ids == (50,)
    new_block = content_fixture.block(after, 50)
    assert b"Brand new content." in after[new_block.content_start : new_block.end]


def test_insert_before_adds_new_block_immediately_before_anchor(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    invocation["targets"]["concept_ids"] = [50]
    patch_set["files"][0]["operations"][0] = {
        "operation": "insert_before",
        "kind": "concept",
        "id": "42",
        "content": "<!-- concept:50 -->\n## New Section\n\nBrand new content.\n",
    }

    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    anchor_before = content_fixture.block(before, 42)
    anchor_after = content_fixture.block(after, 42)
    new_block = content_fixture.block(after, 50)

    # The new block lands immediately before the anchor, not after it.
    assert new_block.end == anchor_after.start
    assert b"Brand new content." in after[new_block.content_start : new_block.end]

    # The anchor's own bytes are completely undisturbed by the insertion.
    assert before[anchor_before.start : anchor_before.end] == after[anchor_after.start : anchor_after.end]

    # Byte preservation holds for everything else: the prefix up to the
    # anchor's original start, and the suffix after the anchor's end.
    assert before[: anchor_before.start] == after[: new_block.start]
    assert before[anchor_before.end :] == after[anchor_after.end :]
    assert result.effective_concept_ids == (50,)


def test_two_inserts_at_same_anchor_offset_are_rejected_as_ambiguous(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    invocation["targets"]["concept_ids"] = [50, 51]
    patch_set["files"][0]["operations"] = [
        {
            "operation": "insert_after",
            "kind": "concept",
            "id": "42",
            "content": "<!-- concept:50 -->\n## New Section A\n\nFirst.\n",
        },
        {
            "operation": "insert_after",
            "kind": "concept",
            "id": "42",
            "content": "<!-- concept:51 -->\n## New Section B\n\nSecond.\n",
        },
    ]

    with pytest.raises(PatchInvariantError, match="ambiguous"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_insert_before_sharing_offset_with_delete_of_same_anchor_is_rejected(content_fixture):
    # Adversarial case: insert_before(42) is positioned at the anchor's raw
    # start, which is exactly where a simultaneous delete(42) of the same
    # anchor also starts. _splice's highest-offset-first ordering ties break
    # on insertion order, so applying the insert first (as would happen here)
    # silently drops it and lets a garbage tail from the deleted range leak
    # into the output -- this must be rejected outright, not spliced.
    before, invocation, patch_set = content_fixture.single_concept_update()
    invocation["targets"]["concept_ids"] = [42, 50]
    patch_set["files"][0]["operations"] = [
        {"operation": "delete", "kind": "concept", "id": "42"},
        {
            "operation": "insert_before",
            "kind": "concept",
            "id": "42",
            "content": "<!-- concept:50 -->\n## New Section\n\nContent.\n",
        },
    ]

    with pytest.raises(PatchInvariantError, match="ambiguous insert position"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_splice_corrupts_when_zero_width_insert_shares_offset_with_replace():
    """Documents the exact hazard the ``_plan_file`` ambiguity check exists to prevent.

    ``_splice`` trusts its caller to hand it a conflict-free range list.
    Given a zero-width insert and a replace that start at the same byte
    offset, the stable tie-break in ``_splice``'s highest-offset-first
    ordering applies the insert first, and the replace then silently
    clobbers it while leaking a tail fragment of the replaced range into the
    result. This is why ``_plan_file`` rejects such range sets before they
    ever reach ``_splice`` (see the ``ambiguous insert position`` tests
    above); this test pins the raw hazard so a future change to the
    tie-break rule can't silently reopen it.
    """
    original = b"AAAABBBBCCCC"
    ranges = [
        patches._SpliceRange(4, 4, b"XX"),
        patches._SpliceRange(4, 8, b"RRRR"),
    ]

    result = patches._splice(original, ranges)

    assert result == b"AAAARRRRBBCCCC"
    assert result != b"AAAAXXRRRRCCCC"


def test_nested_paired_marker_inside_fenced_code_block_is_ignored(content_fixture):
    _, invocation, patch_set = content_fixture.single_concept_update()
    patch_set["files"][0]["operations"][0]["content"] = (
        "## Backend Protocol\n\n"
        "Example marker syntax shown for documentation purposes:\n\n"
        "```markdown\n"
        "<!-- faq:q-context-object concepts:1 -->\n"
        "Body with <!-- faq:q-nested concepts:2 -->\n"
        "Inner\n"
        "<!-- /faq:q-nested -->\n"
        "<!-- /faq:q-context-object -->\n"
        "```\n\n"
        "Real content follows.\n"
    )

    result = apply_patch_set(content_fixture.root, invocation, patch_set)
    after = content_fixture.chapter.read_bytes()

    assert result.effective_concept_ids == (42,)
    assert b"<!-- faq:q-nested concepts:2 -->" in after


def test_insert_requires_a_complete_marked_block(content_fixture):
    before, invocation, patch_set = content_fixture.single_concept_update()
    invocation["targets"]["concept_ids"] = [50]
    patch_set["files"][0]["operations"][0] = {
        "operation": "insert_after",
        "kind": "concept",
        "id": "42",
        "content": "## New Section\n\nMissing its marker.\n",
    }

    with pytest.raises(PatchInvariantError, match="marked block"):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before


def test_multi_file_patch_is_all_or_nothing_on_planning_failure(content_fixture):
    before_one, invocation, patch_set = content_fixture.single_concept_update()
    before_two = content_fixture.second_chapter.read_bytes()
    invocation["allowed_outputs"].append("textbook/docs/chapters/02-second/index.md")
    invocation["targets"]["concept_ids"].append(7)
    patch_set["files"].append(
        {
            "path": "textbook/docs/chapters/02-second/index.md",
            "base_sha256": "sha256:" + "0" * 64,
            "operations": [{"operation": "replace", "kind": "concept", "id": "7", "content": "## Second\n\nRevised.\n"}],
        }
    )

    with pytest.raises(StaleInputError):
        apply_patch_set(content_fixture.root, invocation, patch_set)
    assert content_fixture.chapter.read_bytes() == before_one
    assert content_fixture.second_chapter.read_bytes() == before_two


def test_write_phase_rolls_back_all_files_when_a_later_write_fails(content_fixture, monkeypatch):
    before_one, invocation, patch_set = content_fixture.single_concept_update()
    before_two = content_fixture.second_chapter.read_bytes()
    invocation["allowed_outputs"].append("textbook/docs/chapters/02-second/index.md")
    invocation["targets"]["concept_ids"].append(7)
    patch_set["files"].append(
        {
            "path": "textbook/docs/chapters/02-second/index.md",
            "base_sha256": sha256_bytes(before_two),
            "operations": [{"operation": "replace", "kind": "concept", "id": "7", "content": "## Second\n\nRevised.\n"}],
        }
    )

    real_replace = patches.os.replace
    calls = {"count": 0}

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated write failure")
        return real_replace(src, dst)

    monkeypatch.setattr(patches.os, "replace", flaky_replace)

    with pytest.raises(OSError):
        apply_patch_set(content_fixture.root, invocation, patch_set)

    assert content_fixture.chapter.read_bytes() == before_one
    assert content_fixture.second_chapter.read_bytes() == before_two
