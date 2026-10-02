from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from literature_research_core import (
    AMinerProvider,
    DemoProvider,
    FirecrawlProvider,
    LiteratureProvider,
    LiteratureResearchError,
    QueryPlan,
    ResearchScope,
    clean_env,
    emit_progress,
    resolve_output_path,
    run_literature_research,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run independent literature research and export a literature matrix."
    )
    parser.add_argument("--topic", required=True, help="Research topic or question.")
    parser.add_argument("--scope-file", help="OpenClaw-authored scope_plan/research_scope JSON for real mode.")
    parser.add_argument("--query-plan", help="OpenClaw-authored query_plan JSON for real mode.")
    parser.add_argument("--seed-selection", help="OpenClaw-approved seed_selection JSON for citation expansion.")
    parser.add_argument("--seed-selection-policy", help="OpenClaw-authored seed_selection_policy JSON.")
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for matrix and trace artifacts. Defaults to a workspace-level "
            "literature-runs/YYYYMMDD-HHMMSS-<topic> folder."
        ),
    )
    parser.add_argument(
        "--channels",
        default="aminer,firecrawl",
        help="Comma-separated provider list: aminer,firecrawl. Ignored when --demo-fast is set.",
    )
    parser.add_argument("--max-results", type=int, default=40, help="Maximum deduplicated matrix rows.")
    parser.add_argument("--max-queries", type=int, default=6, help="Maximum generated search queries.")
    parser.add_argument(
        "--scrape-markdown",
        action="store_true",
        help="Ask Firecrawl to scrape markdown content for returned search results.",
    )
    parser.add_argument(
        "--demo-fast",
        action="store_true",
        help="Run deterministic mocked provider output without network or credentials.",
    )
    return parser


def build_providers(channels: str, *, demo_fast: bool, scrape_markdown: bool) -> list[LiteratureProvider]:
    if demo_fast:
        return [DemoProvider()]

    providers: list[LiteratureProvider] = []
    selected = {channel.strip().lower() for channel in channels.split(",") if channel.strip()}
    unknown = selected - {"aminer", "firecrawl"}
    if unknown:
        raise LiteratureResearchError(f"Unknown channel(s): {', '.join(sorted(unknown))}.")

    missing_env: list[str] = []
    if "aminer" in selected and not clean_env("AMINER_SEARCH_API_TOKEN"):
        missing_env.append("AMINER_SEARCH_API_TOKEN")
    if "firecrawl" in selected and not clean_env("FIRECRAWL_API_KEY"):
        missing_env.append("FIRECRAWL_API_KEY")
    if missing_env:
        raise LiteratureResearchError(
            "Missing provider environment variable(s): "
            + ", ".join(missing_env)
            + ". For OpenClaw indirect invocation, inject them through skills.entries.<skill>.env."
        )

    if "aminer" in selected:
        providers.append(AMinerProvider())
    if "firecrawl" in selected:
        providers.append(FirecrawlProvider(scrape_markdown=scrape_markdown))
    if not providers:
        raise LiteratureResearchError("Select at least one channel or use --demo-fast.")
    return providers


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        emit_progress(
            "cli.run",
            "run_literature_search started",
            topic=args.topic,
            channels=args.channels,
            max_results=args.max_results,
            max_queries=args.max_queries,
            demo_fast=args.demo_fast,
        )
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        emit_progress("cli.run", "providers initialized", providers=[getattr(provider, "name", "") for provider in providers])
        if not args.demo_fast and not args.query_plan:
            raise LiteratureResearchError(
                "Real mode requires --query-plan. Topic-only generation is limited to --demo-fast/bootstrap smoke."
            )
        emit_progress("cli.run", "loading input artifacts", scope_file=args.scope_file, query_plan=args.query_plan)
        scope = load_scope(Path(args.scope_file)) if args.scope_file else None
        query_plan = load_query_plan(Path(args.query_plan)) if args.query_plan else None
        seed_selection = load_json(Path(args.seed_selection)) if args.seed_selection else None
        seed_selection_policy = load_json(Path(args.seed_selection_policy)) if args.seed_selection_policy else None
        output_dir = resolve_output_path(args.output_dir, topic=args.topic, must_be_dir=True)
        emit_progress("cli.run", "resolved output directory", output_dir=str(output_dir))
        result = run_literature_research(
            topic=args.topic,
            output_dir=output_dir,
            providers=providers,
            max_results=args.max_results,
            max_queries=args.max_queries,
            scope=scope,
            query_plan=query_plan,
            seed_selection=seed_selection,
            seed_selection_policy=seed_selection_policy,
        )
        payload = {
            "topic": result.topic,
            "candidate_count": result.candidate_count,
            "matrix_count": len(result.matrix),
            "query_plan": asdict(result.query_plan),
            "output_paths": result.output_paths,
            "trace": [asdict(event) for event in result.trace],
        }
        emit_progress("cli.run", "run_literature_search completed", matrix_count=len(result.matrix), candidate_count=result.candidate_count)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except (LiteratureResearchError, OSError, ValueError) as exc:
        emit_progress("cli.run", "run_literature_search failed", error=type(exc).__name__, message=str(exc)[:200])
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def load_scope(path: Path) -> ResearchScope:
    payload = load_json(path)
    return ResearchScope(
        topic=str(payload["topic"]),
        research_question=str(payload.get("research_question") or payload.get("research_questions") or ""),
        time_range=str(payload.get("time_range") or ""),
        focus_dimensions=[str(item) for item in payload.get("focus_dimensions", payload.get("must_cover_facets", []))],
        inclusion_criteria=[str(item) for item in payload.get("inclusion_criteria", payload.get("in_scope", []))],
        exclusion_criteria=[str(item) for item in payload.get("exclusion_criteria", payload.get("out_of_scope", []))],
        demo_fast=bool(payload.get("demo_fast", False)),
        quality_level=str(payload.get("quality_level") or ""),
    )


def load_query_plan(path: Path) -> QueryPlan:
    payload = load_json(path)
    query_groups = {
        str(key): [str(query) for query in value]
        for key, value in dict(payload.get("query_groups", {})).items()
        if isinstance(value, list)
    }
    queries = [str(query) for query in payload.get("queries", [])]
    if not queries:
        queries = [query for group in query_groups.values() for query in group]
    return QueryPlan(
        topic=str(payload["topic"]),
        queries=queries,
        scope_note=str(payload.get("scope_note", "")),
        query_groups=query_groups,
        demo_fast=bool(payload.get("demo_fast", False)),
        keywords=[str(item) for item in payload.get("keywords", [])],
        synonyms=[str(item) for item in payload.get("synonyms", [])],
        broader_terms=[str(item) for item in payload.get("broader_terms", [])],
        narrower_terms=[str(item) for item in payload.get("narrower_terms", [])],
        domain_terms=[str(item) for item in payload.get("domain_terms", [])],
        negative_terms=[str(item) for item in payload.get("negative_terms", [])],
        provider_targets={
            str(key): [str(query) for query in value]
            for key, value in dict(payload.get("provider_targets", {})).items()
            if isinstance(value, list)
        },
        facet_intent={str(key): str(value) for key, value in dict(payload.get("facet_intent", {})).items()},
        max_results=int(payload["max_results"]) if payload.get("max_results") is not None else None,
        language=str(payload.get("language") or ""),
        notes=str(payload.get("notes") or ""),
        quality_level=str(payload.get("quality_level") or ""),
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
