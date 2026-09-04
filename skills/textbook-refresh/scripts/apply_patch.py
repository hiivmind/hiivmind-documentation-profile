#!/usr/bin/env python3
"""CLI wrapper around ``patch_engine`` for the ``textbook-refresh`` skill.

Deterministic, stdlib-only operations a skill run can shell out to instead of
hand-editing chapter/FAQ/glossary/quiz/reference bytes inline:

    apply_patch.py apply --project-root DIR --invocation invocation.json --patch-set patch-set.json
    apply_patch.py plan  --project-root DIR --invocation invocation.json --patch-set patch-set.json
    apply_patch.py faq-export --faq faq.md
    apply_patch.py faq-verify --faq faq.md --json faq-chatbot-training.json
    apply_patch.py coverage --graph learning-graph.json --chapters docs/chapters

Exit codes: 0 success, 1 invalid usage, 2 patch/marker invariant violated
(including stale input), 3 verification found errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from patch_engine.enrichments import export_faq_json, validate_faq_parity
from patch_engine.markers import validate_concept_coverage
from patch_engine.patches import PatchInvariantError, apply_patch_set, plan_patch_set


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _cmd_apply(args: argparse.Namespace) -> int:
    invocation = _load(args.invocation)
    patch_set = _load(args.patch_set)
    try:
        result = (plan_patch_set if args.dry_run else apply_patch_set)(Path(args.project_root), invocation, patch_set)
    except PatchInvariantError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "outputs": list(result.outputs),
        "requested_concept_ids": list(result.requested_concept_ids),
        "effective_concept_ids": list(result.effective_concept_ids),
        "preserved": list(result.preserved),
    }, indent=2))
    return 0


def _cmd_faq_export(args: argparse.Namespace) -> int:
    print(json.dumps(export_faq_json(Path(args.faq).read_bytes()), indent=2))
    return 0


def _cmd_faq_verify(args: argparse.Namespace) -> int:
    markdown = Path(args.faq).read_bytes()
    committed = _load(args.json)
    errors = validate_faq_parity(markdown, committed)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 3
    print("ok: faq-chatbot-training.json matches faq.md")
    return 0


def _cmd_coverage(args: argparse.Namespace) -> int:
    graph = _load(args.graph)
    errors = validate_concept_coverage(graph, Path(args.chapters))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 3
    print("ok: every active concept has exactly one marker in its assigned chapter")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, dry_run in (("apply", False), ("plan", True)):
        sub = subparsers.add_parser(name, help=f"{'Dry-run' if dry_run else 'Apply'} a patch set")
        sub.add_argument("--project-root", required=True)
        sub.add_argument("--invocation", required=True, help="Path to an invocation JSON file")
        sub.add_argument("--patch-set", required=True, help="Path to a patch-set JSON file")
        sub.set_defaults(func=_cmd_apply, dry_run=dry_run)

    export = subparsers.add_parser("faq-export", help="Print the deterministic faq.md -> JSON projection")
    export.add_argument("--faq", required=True)
    export.set_defaults(func=_cmd_faq_export)

    verify = subparsers.add_parser("faq-verify", help="Check faq-chatbot-training.json matches faq.md")
    verify.add_argument("--faq", required=True)
    verify.add_argument("--json", required=True)
    verify.set_defaults(func=_cmd_faq_verify)

    coverage = subparsers.add_parser("coverage", help="Check every active concept has exactly one chapter marker")
    coverage.add_argument("--graph", required=True)
    coverage.add_argument("--chapters", required=True)
    coverage.set_defaults(func=_cmd_coverage)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
