import json
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest

from patch_engine.canonical import sha256_bytes
from patch_engine.markers import ConceptBlock, MarkedBlock, parse_concept_blocks, parse_marked_blocks, select_enrichment_blocks


@pytest.fixture
def graph() -> dict:
    root = Path(__file__).parent / "fixtures" / "chapters" / "assigned"
    return deepcopy(json.loads((root / "learning-graph.json").read_text()))


@pytest.fixture
def chapter_root(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "chapters" / "assigned" / "chapters"
    target = tmp_path / "chapters"
    shutil.copytree(source, target)
    return target


@dataclass
class ContentFixture:
    root: Path
    chapter: Path
    second_chapter: Path

    def _invocation(self, concept_ids: list[int]) -> dict:
        return {
            "invocation_id": "content-patch-fixture",
            "project_root": str(self.root),
            "inputs": [
                {
                    "path": "textbook/docs/chapters/01-foundations/index.md",
                    "sha256": sha256_bytes(self.chapter.read_bytes()),
                }
            ],
            "allowed_outputs": ["textbook/docs/chapters/01-foundations/index.md"],
            "targets": {"concept_ids": list(concept_ids), "enrichment_ids": []},
        }

    def _patch_set(self, path: str, base_sha256: str, operations: list[dict]) -> dict:
        return {"files": [{"path": path, "base_sha256": base_sha256, "operations": deepcopy(operations)}]}

    def single_concept_update(self) -> tuple[bytes, dict, dict]:
        before = self.chapter.read_bytes()
        invocation = self._invocation([42])
        patch_set = self._patch_set(
            "textbook/docs/chapters/01-foundations/index.md",
            sha256_bytes(before),
            [
                {
                    "operation": "replace",
                    "kind": "concept",
                    "id": "42",
                    "content": "## Backend Protocol\n\nRevised content for concept 42.\n",
                }
            ],
        )
        return deepcopy(before), deepcopy(invocation), deepcopy(patch_set)

    def shared_concept_update(self, requested: int) -> tuple[bytes, dict, dict]:
        before = self.chapter.read_bytes()
        invocation = self._invocation([requested])
        patch_set = self._patch_set(
            "textbook/docs/chapters/01-foundations/index.md",
            sha256_bytes(before),
            [
                {
                    "operation": "replace",
                    "kind": "concept",
                    "id": str(requested),
                    "content": "## Mountainash Expressions and Relations\n\nRevised shared content.\n",
                }
            ],
        )
        return deepcopy(before), deepcopy(invocation), deepcopy(patch_set)

    def block(self, content: bytes, concept_id: int) -> ConceptBlock:
        for block in parse_concept_blocks(content):
            if concept_id in block.concept_ids:
                return block
        raise AssertionError(f"concept {concept_id} not found in content")


@pytest.fixture
def content_fixture(tmp_path: Path) -> ContentFixture:
    source = Path(__file__).parent / "fixtures" / "content" / "base" / "project"
    root = tmp_path / "project"
    shutil.copytree(source, root)
    chapter = root / "textbook" / "docs" / "chapters" / "01-foundations" / "index.md"
    second_chapter = root / "textbook" / "docs" / "chapters" / "02-second" / "index.md"
    return ContentFixture(root, chapter, second_chapter)


class EnrichmentFixture:
    """An isolated copy of one enrichment kind's fixture project.

    ``invocation``/``patch_set`` are a ready-to-apply pair that replaces the
    fixture's concept-42-linked block (see ``_EnrichmentFixtureFactory``'s
    concept-42 id table); tests that need a different edit build their own
    patch set from ``invocation``/``path``/``root`` directly.
    """

    def __init__(self, root: Path, path: Path, kind: str, invocation: dict, patch_set: dict) -> None:
        self.root = root
        self.path = path
        self.kind = kind
        self.invocation = invocation
        self.patch_set = patch_set

    @property
    def markdown(self) -> Path:
        return self.path

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def block(self, content: bytes, id: str) -> MarkedBlock:
        for candidate in parse_marked_blocks(content, self.kind):
            if candidate.id == id:
                return candidate
        raise AssertionError(f"{self.kind} block {id!r} not found")


class _EnrichmentFixtureFactory:
    """Callable ``enrichment_fixture(kind)`` factory that also exposes ``expected_ids``."""

    _SOURCE_ROOT = Path(__file__).parent / "fixtures" / "enrichments"
    _RELATIVE_PATHS = {
        "faq": "textbook/docs/faq.md",
        "glossary": "textbook/docs/glossary.md",
        "quiz": "textbook/docs/chapters/01-example/quiz.md",
        "reference": "textbook/docs/chapters/01-example/references.md",
    }
    _CONCEPT_42_BLOCK_ID = {
        "faq": "q-backend-protocol",
        "glossary": "backend-protocol",
        "quiz": "q2-backend-protocol",
        "reference": "ref-04",
    }
    _REPLACEMENT_BODY = {
        "faq": (
            "<!-- faq:{id} concepts:42 -->\n"
            "### What is the backend protocol?\n\n"
            "The backend protocol defines the exact request/response contract used between "
            "services, revised for clarity.\n"
            "<!-- /faq:{id} -->\n"
        ),
        "glossary": (
            "<!-- glossary:{id} concepts:42 -->\n"
            "#### Backend Protocol\n\n"
            "The backend protocol defines the exact request/response contract used between "
            "services, revised for clarity.\n"
            "<!-- /glossary:{id} -->\n"
        ),
        "quiz": (
            "<!-- quiz:{id} concepts:42 -->\n"
            "#### 2. What defines the backend protocol precisely?\n\n"
            '<div class="upper-alpha" markdown>\n'
            "1. The frontend styling\n"
            "2. The exact request/response contract between services\n"
            "3. The build pipeline\n"
            "4. The test runner\n"
            "</div>\n\n"
            '??? question "Show Answer"\n'
            "    The correct answer is **B**. The backend protocol defines the exact "
            "request/response contract used between services.\n\n"
            "    **Concept Tested:** Backend Protocol\n"
            "<!-- /quiz:{id} -->\n"
        ),
        "reference": (
            "<!-- reference:{id} concepts:42 -->\n"
            "4. Distributed Systems Protocols (4th Edition) - Jamie Rivera - Northlight Press - "
            "Revised: chapter 6 covers backend request/response contracts in depth.\n"
            "<!-- /reference:{id} -->\n"
        ),
    }

    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path

    def __call__(self, kind: str) -> EnrichmentFixture:
        source = self._SOURCE_ROOT / kind / "project"
        root = self._tmp_path / f"{kind}-project"
        shutil.copytree(source, root)
        relative = self._RELATIVE_PATHS[kind]
        path = root / relative
        block_id = self._CONCEPT_42_BLOCK_ID[kind]
        base_sha256 = sha256_bytes(path.read_bytes())
        invocation = {
            "invocation_id": f"{kind}-enrichment-fixture",
            "project_root": str(root),
            "inputs": [{"path": relative, "sha256": base_sha256}],
            "allowed_outputs": [relative],
            "targets": {"concept_ids": [42], "enrichment_ids": [block_id]},
        }
        patch_set = {
            "files": [
                {
                    "path": relative,
                    "base_sha256": base_sha256,
                    "operations": [
                        {
                            "operation": "replace",
                            "kind": kind,
                            "id": block_id,
                            "content": self._REPLACEMENT_BODY[kind].format(id=block_id),
                        }
                    ],
                }
            ]
        }
        return EnrichmentFixture(root=root, path=path, kind=kind, invocation=invocation, patch_set=patch_set)

    def expected_ids(self, kind: str, concept_id: int) -> list[str]:
        source = self._SOURCE_ROOT / kind / "project" / self._RELATIVE_PATHS[kind]
        blocks = select_enrichment_blocks(source.read_bytes(), kind, {concept_id})
        return [block.id for block in blocks]


@pytest.fixture
def enrichment_fixture(tmp_path: Path) -> _EnrichmentFixtureFactory:
    return _EnrichmentFixtureFactory(tmp_path)


@pytest.fixture
def faq_fixture(enrichment_fixture: _EnrichmentFixtureFactory) -> EnrichmentFixture:
    return enrichment_fixture("faq")
