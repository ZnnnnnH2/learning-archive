from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from literature_research_core import (
    AMinerProvider,
    CandidateSource,
    DemoProvider,
    FirecrawlProvider,
    LiteratureMatrixRow,
    LiteratureProvider,
    LiteratureResearchError,
    QueryPlan,
    ResearchScope,
    build_matrix_row,
    build_query_plan_from_scope,
    build_research_scope,
    clean_env,
    discover_seed_papers,
    emit_progress,
    execute_repair_plan,
    repair_literature_matrix,
    repair_query_plan,
    repair_research_scope,
    repair_seed_papers,
    resolve_output_path,
    run_literature_research,
    validate_repair_plan,
    validate_literature_matrix,
    validate_query_plan,
    validate_research_scope,
    validate_seed_papers,
    write_matrix_csv,
    write_matrix_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run staged OpenClaw literature research skill commands.")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    scope = subparsers.add_parser("scope")
    scope_sub = scope.add_subparsers(dest="action", required=True)
    scope_build = scope_sub.add_parser("build")
    scope_build.add_argument("--topic", required=True)
    scope_build.add_argument("--output", required=True)
    scope_build.add_argument("--demo-fast", action="store_true")
    scope_validate = scope_sub.add_parser("validate")
    scope_validate.add_argument("--scope-file", required=True)
    scope_validate.add_argument("--output", required=True)
    scope_repair = scope_sub.add_parser("repair")
    scope_repair.add_argument("--scope-file", required=True)
    scope_repair.add_argument("--output", required=True)

    seed = subparsers.add_parser("seed")
    seed_sub = seed.add_subparsers(dest="action", required=True)
    seed_discover = seed_sub.add_parser("discover")
    seed_discover.add_argument("--scope-file", required=True)
    seed_discover.add_argument("--output", required=True)
    add_provider_args(seed_discover)
    seed_validate = seed_sub.add_parser("validate")
    seed_validate.add_argument("--scope-file", required=True)
    seed_validate.add_argument("--seed-file", required=True)
    seed_validate.add_argument("--output", required=True)
    seed_repair = seed_sub.add_parser("repair")
    seed_repair.add_argument("--scope-file", required=True)
    seed_repair.add_argument("--seed-file", required=True)
    seed_repair.add_argument("--output", required=True)
    add_provider_args(seed_repair)

    query = subparsers.add_parser("query")
    query_sub = query.add_subparsers(dest="action", required=True)
    query_build = query_sub.add_parser("build")
    query_build.add_argument("--scope-file", required=True)
    query_build.add_argument("--seed-file")
    query_build.add_argument("--output", required=True)
    query_build.add_argument("--max-queries", type=int, default=8)
    query_build.add_argument("--demo-fast", action="store_true")
    query_validate = query_sub.add_parser("validate")
    query_validate.add_argument("--scope-file", required=True)
    query_validate.add_argument("--query-plan", required=True)
    query_validate.add_argument("--output", required=True)
    query_repair = query_sub.add_parser("repair")
    query_repair.add_argument("--scope-file", required=True)
    query_repair.add_argument("--query-plan", required=True)
    query_repair.add_argument("--output", required=True)
    query_repair.add_argument("--max-queries", type=int, default=8)

    matrix = subparsers.add_parser("matrix")
    matrix_sub = matrix.add_subparsers(dest="action", required=True)
    matrix_build = matrix_sub.add_parser("build")
    matrix_build.add_argument("--query-plan", required=True)
    matrix_build.add_argument("--scope-file")
    matrix_build.add_argument("--seed-selection")
    matrix_build.add_argument("--seed-selection-policy")
    matrix_build.add_argument(
        "--output-dir",
        help=(
            "Directory for matrix and trace artifacts. Defaults to a workspace-level "
            "literature-runs/YYYYMMDD-HHMMSS-<topic> folder."
        ),
    )
    matrix_build.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Allow overwriting existing final matrix artifacts after backing them up.",
    )
    add_provider_args(matrix_build)
    matrix_validate = matrix_sub.add_parser("validate")
    matrix_validate.add_argument("--matrix-file", required=True)
    matrix_validate.add_argument("--output", required=True)
    matrix_repair = matrix_sub.add_parser("repair")
    matrix_repair.add_argument("--matrix-file", required=True)
    matrix_repair.add_argument("--topic", required=True)
    matrix_repair.add_argument(
        "--output-dir",
        help=(
            "Directory for repaired matrix artifacts. Defaults to a workspace-level "
            "literature-runs/YYYYMMDD-HHMMSS-<topic> folder."
        ),
    )
    add_provider_args(matrix_repair)

    repair = subparsers.add_parser("repair")
    repair_sub = repair.add_subparsers(dest="action", required=True)
    repair_validate = repair_sub.add_parser("validate")
    repair_validate.add_argument("--repair-plan", required=True)
    repair_validate.add_argument("--output", required=True)
    repair_execute = repair_sub.add_parser("execute")
    repair_execute.add_argument("--repair-plan", required=True)
    repair_execute.add_argument("--topic", required=True)
    repair_execute.add_argument("--matrix-file")
    repair_execute.add_argument(
        "--output-dir",
        help="Directory for repair_trace.json and updated artifacts.",
    )
    add_provider_args(repair_execute)
    repair_summarize = repair_sub.add_parser("summarize")
    repair_summarize.add_argument("--repair-trace", required=True)
    repair_summarize.add_argument("--output", required=True)

    return parser


def add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--channels", default="aminer,firecrawl")
    parser.add_argument("--max-results", type=int, default=40)
    parser.add_argument("--scrape-markdown", action="store_true")
    parser.add_argument("--demo-fast", action="store_true")


def build_providers(channels: str, *, demo_fast: bool, scrape_markdown: bool) -> list[LiteratureProvider]:
    if demo_fast:
        return [DemoProvider()]
    selected = {channel.strip().lower() for channel in channels.split(",") if channel.strip()}
    unknown = selected - {"aminer", "firecrawl"}
    if unknown:
        raise LiteratureResearchError(f"Unknown channel(s): {', '.join(sorted(unknown))}.")
    providers: list[LiteratureProvider] = []
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
        emit_progress("cli.stage", "research_skill command started", stage=args.stage, action=args.action)
        payload = run_command(args)
        emit_progress("cli.stage", "research_skill command completed", stage=args.stage, action=args.action, status=payload.get("status"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    except (LiteratureResearchError, OSError, ValueError, KeyError, TypeError) as exc:
        emit_progress("cli.stage", "research_skill command failed", stage=getattr(args, "stage", ""), action=getattr(args, "action", ""), error=type(exc).__name__, message=str(exc)[:200])
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.stage == "scope":
        return run_scope_command(args)
    if args.stage == "seed":
        return run_seed_command(args)
    if args.stage == "query":
        return run_query_command(args)
    if args.stage == "matrix":
        return run_matrix_command(args)
    if args.stage == "repair":
        return run_repair_command(args)
    raise LiteratureResearchError(f"Unknown stage: {args.stage}")


def run_scope_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "build":
        emit_progress("scope.build", "building research scope", topic=args.topic, output=args.output, demo_fast=args.demo_fast)
        scope = build_research_scope(args.topic, demo_fast=args.demo_fast)
        write_json(Path(args.output), asdict(scope))
        emit_progress("scope.build", "research scope written", output=args.output)
        return {"artifact": args.output, "status": "ok"}
    scope = load_scope(Path(args.scope_file))
    if args.action == "validate":
        emit_progress("scope.validate", "validating research scope", scope_file=args.scope_file, output=args.output)
        report = validate_research_scope(scope)
        write_json(Path(args.output), asdict(report))
        emit_progress("scope.validate", "research scope validation completed", status=report.status, issue_count=len(report.issues))
        return {"artifact": args.output, "status": report.status}
    if args.action == "repair":
        emit_progress("scope.repair", "repairing research scope", scope_file=args.scope_file, output=args.output)
        repaired = repair_research_scope(scope)
        write_json(Path(args.output), asdict(repaired))
        emit_progress("scope.repair", "research scope repair written", output=args.output)
        return {"artifact": args.output, "status": "ok"}
    raise LiteratureResearchError(f"Unknown scope action: {args.action}")


def run_seed_command(args: argparse.Namespace) -> dict[str, Any]:
    scope = load_scope(Path(args.scope_file))
    if args.action == "discover":
        emit_progress("seed.discover", "seed discover command starting", scope_file=args.scope_file, output=args.output, channels=args.channels, max_results=args.max_results)
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        seeds = discover_seed_papers(scope, providers=providers, max_results=args.max_results)
        write_seed_file(Path(args.output), scope.topic, seeds, demo_fast=args.demo_fast)
        emit_progress("seed.discover", "seed discover command completed", output=args.output, count=len(seeds))
        return {"artifact": args.output, "status": "ok", "count": len(seeds)}
    seeds = load_seed_file(Path(args.seed_file))
    if args.action == "validate":
        emit_progress("seed.validate", "validating seed papers", seed_file=args.seed_file, output=args.output, count=len(seeds))
        report = validate_seed_papers(scope, seeds)
        write_json(Path(args.output), asdict(report))
        emit_progress("seed.validate", "seed validation completed", status=report.status, issue_count=len(report.issues))
        return {"artifact": args.output, "status": report.status}
    if args.action == "repair":
        emit_progress("seed.repair", "repairing seed papers", seed_file=args.seed_file, output=args.output, channels=args.channels)
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        repaired = repair_seed_papers(scope, seeds, providers=providers, max_results=args.max_results)
        write_seed_file(Path(args.output), scope.topic, repaired, demo_fast=args.demo_fast)
        emit_progress("seed.repair", "seed repair completed", output=args.output, count=len(repaired))
        return {"artifact": args.output, "status": "ok", "count": len(repaired)}
    raise LiteratureResearchError(f"Unknown seed action: {args.action}")


def run_query_command(args: argparse.Namespace) -> dict[str, Any]:
    scope = load_scope(Path(args.scope_file))
    if args.action == "build":
        emit_progress("query.build", "query build command starting", scope_file=args.scope_file, output=args.output, demo_fast=args.demo_fast)
        if not args.demo_fast:
            raise LiteratureResearchError(
                "query build is a demo/bootstrap helper only. Real mode must consume an OpenClaw-authored query_plan.json."
            )
        plan = build_query_plan_from_scope(scope, max_queries=args.max_queries)
        plan.demo_fast = True
        plan.quality_level = "schema_smoke_only"
        write_json(Path(args.output), asdict(plan))
        emit_progress("query.build", "query plan written", output=args.output, count=len(plan.queries))
        return {"artifact": args.output, "status": "ok", "count": len(plan.queries)}
    plan = load_query_plan(Path(args.query_plan))
    if args.action == "validate":
        emit_progress("query.validate", "validating query plan", query_plan=args.query_plan, output=args.output)
        report = validate_query_plan(scope, plan)
        write_json(Path(args.output), asdict(report))
        emit_progress("query.validate", "query validation completed", status=report.status, issue_count=len(report.issues))
        return {"artifact": args.output, "status": report.status}
    if args.action == "repair":
        raise LiteratureResearchError(
            "query repair is out of real-mode scope. Use `repair validate` and `repair execute` with an OpenClaw-authored repair_plan.json."
        )
        repaired = repair_query_plan(scope, plan, max_queries=args.max_queries)
        write_json(Path(args.output), asdict(repaired))
        return {"artifact": args.output, "status": "ok", "count": len(repaired.queries)}
    raise LiteratureResearchError(f"Unknown query action: {args.action}")


def run_matrix_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "build":
        emit_progress("matrix.command", "matrix build command starting", query_plan=args.query_plan, scope_file=args.scope_file, output_dir=args.output_dir)
        plan = load_query_plan(Path(args.query_plan))
        scope = load_scope(Path(args.scope_file)) if args.scope_file else None
        seed_selection = read_json(Path(args.seed_selection)) if args.seed_selection else None
        seed_selection_policy = read_json(Path(args.seed_selection_policy)) if args.seed_selection_policy else None
        output_dir = resolve_output_path(args.output_dir, topic=plan.topic, must_be_dir=True)
        if (output_dir / "literature_matrix.json").exists() and not args.force_overwrite:
            raise LiteratureResearchError(
                "Refusing to overwrite existing literature_matrix.json. "
                "Read diagnostics first, use partial_literature_matrix.json if present, "
                "or rerun with --force-overwrite after accepting a backup."
            )
        backup_dir = backup_existing_matrix_artifacts(output_dir) if args.force_overwrite else None
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        emit_progress(
            "matrix.command",
            "matrix build inputs ready",
            output_dir=str(output_dir),
            query_count=len(plan.queries),
            providers=[getattr(provider, "name", "") for provider in providers],
            max_results=args.max_results,
            force_overwrite=args.force_overwrite,
            backup_dir=str(backup_dir) if backup_dir else "",
        )
        result = run_literature_research(
            topic=plan.topic,
            output_dir=output_dir,
            providers=providers,
            max_results=args.max_results,
            max_queries=len(plan.queries),
            scope=scope,
            query_plan=plan,
            seed_selection=seed_selection,
            seed_selection_policy=seed_selection_policy,
        )
        emit_progress("matrix.command", "matrix build command completed", output_dir=str(output_dir), count=len(result.matrix))
        return {
            "artifact_dir": str(output_dir),
            "status": "ok",
            "count": len(result.matrix),
            "output_paths": result.output_paths,
            "backup_dir": str(backup_dir) if backup_dir else "",
        }
    matrix = load_matrix_file(Path(args.matrix_file))
    if args.action == "validate":
        emit_progress("matrix.validate", "validating matrix", matrix_file=args.matrix_file, output=args.output, row_count=len(matrix))
        report = validate_literature_matrix(matrix)
        write_json(Path(args.output), asdict(report))
        emit_progress("matrix.validate", "matrix validation completed", status=report.status, issue_count=len(report.issues))
        return {"artifact": args.output, "status": report.status}
    if args.action == "repair":
        emit_progress("matrix.repair", "repairing matrix", matrix_file=args.matrix_file, output_dir=args.output_dir, row_count=len(matrix))
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        repaired = repair_literature_matrix(topic=args.topic, matrix=matrix, providers=providers, max_results=args.max_results)
        output_dir = resolve_output_path(args.output_dir, topic=args.topic, must_be_dir=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        matrix_json = output_dir / "literature_matrix.json"
        matrix_csv = output_dir / "literature_matrix.csv"
        matrix_md = output_dir / "literature_matrix.md"
        diagnostics_json = output_dir / "matrix_diagnostics.json"
        report = validate_literature_matrix(repaired)
        write_json(matrix_json, {"topic": args.topic, "demo_fast": args.demo_fast, "count": len(repaired), "items": [asdict(row) for row in repaired]})
        write_json(diagnostics_json, asdict(report))
        write_matrix_csv(matrix_csv, repaired)
        write_matrix_markdown(matrix_md, topic=args.topic, matrix=repaired)
        emit_progress("matrix.repair", "matrix repair completed", output_dir=str(output_dir), status=report.status, count=len(repaired))
        return {"artifact_dir": str(output_dir), "status": report.status, "count": len(repaired)}
    raise LiteratureResearchError(f"Unknown matrix action: {args.action}")


def backup_existing_matrix_artifacts(output_dir: Path) -> Path | None:
    names = [
        "literature_matrix.json",
        "literature_matrix.csv",
        "literature_matrix.md",
        "matrix_diagnostics.json",
        "orchestration_summary.json",
        "llm_extraction_trace.json",
        "extraction_failures.json",
        "partial_literature_matrix.json",
        "partial_literature_matrix.csv",
        "partial_literature_matrix.md",
        "partial_extraction_checkpoint.json",
    ]
    existing = [output_dir / name for name in names if (output_dir / name).exists()]
    if not existing:
        return None
    backup_dir = output_dir / "_artifact_backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in existing:
        shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def run_repair_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "validate":
        emit_progress("repair.validate", "validating repair plan", repair_plan=args.repair_plan, output=args.output)
        plan = read_json(Path(args.repair_plan))
        report = validate_repair_plan(plan)
        write_json(Path(args.output), asdict(report))
        emit_progress("repair.validate", "repair validation completed", status=report.status, issue_count=len(report.issues))
        return {"artifact": args.output, "status": report.status}
    if args.action == "execute":
        emit_progress("repair.command", "repair execute command starting", repair_plan=args.repair_plan, output_dir=args.output_dir)
        plan = read_json(Path(args.repair_plan))
        output_dir = resolve_output_path(args.output_dir, topic=args.topic, must_be_dir=True)
        matrix = load_matrix_file(Path(args.matrix_file)) if args.matrix_file else []
        providers = build_providers(args.channels, demo_fast=args.demo_fast, scrape_markdown=args.scrape_markdown)
        result = execute_repair_plan(
            plan,
            topic=args.topic,
            output_dir=output_dir,
            providers=providers,
            matrix=matrix,
            max_results=args.max_results,
            demo_fast=args.demo_fast,
        )
        emit_progress("repair.command", "repair execute command completed", output_dir=str(output_dir), status=result["status"])
        return {"artifact_dir": str(output_dir), "status": result["status"], "repair_trace": str(output_dir / "repair_trace.json")}
    if args.action == "summarize":
        emit_progress("repair.summarize", "summarizing repair trace", repair_trace=args.repair_trace, output=args.output)
        trace = read_json(Path(args.repair_trace))
        summary = {
            "repair_run_id": trace.get("repair_run_id", ""),
            "actions_executed": len(trace.get("actions_executed", [])),
            "actions_skipped": len(trace.get("actions_skipped", [])),
            "failures": len(trace.get("failures", [])),
            "changed_artifacts": trace.get("changed_artifacts", []),
        }
        write_json(Path(args.output), summary)
        emit_progress("repair.summarize", "repair summary written", output=args.output)
        return {"artifact": args.output, "status": "ok"}
    raise LiteratureResearchError(f"Unknown repair action: {args.action}")


def load_scope(path: Path) -> ResearchScope:
    payload = read_json(path)
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
    payload = read_json(path)
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


def load_seed_file(path: Path) -> list[CandidateSource]:
    payload = read_json(path)
    items = payload.get("items", payload if isinstance(payload, list) else [])
    field_names = set(CandidateSource.__dataclass_fields__)
    return [CandidateSource(**{key: value for key, value in item.items() if key in field_names}) for item in items if isinstance(item, dict)]


def load_matrix_file(path: Path) -> list[LiteratureMatrixRow]:
    payload = read_json(path)
    items = payload.get("items", payload if isinstance(payload, list) else [])
    field_names = set(LiteratureMatrixRow.__dataclass_fields__)
    return [LiteratureMatrixRow(**{key: value for key, value in item.items() if key in field_names}) for item in items if isinstance(item, dict)]


def write_seed_file(path: Path, topic: str, seeds: list[CandidateSource], *, demo_fast: bool) -> None:
    write_json(path, {"topic": topic, "demo_fast": demo_fast, "count": len(seeds), "items": [asdict(seed) for seed in seeds]})


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path = resolve_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
