from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import urljoin

import requests


DEFAULT_AMINER_SEARCH_BASE_URL = "https://agentic-search.aminer.cn"
DEFAULT_AMINER_SEARCH_ENDPOINT = "/paper/search"
DEFAULT_AMINER_DETAIL_URL = "https://datacenter.aminer.cn/gateway/open_platform/api/paper/detail"
DEFAULT_AMINER_RELATION_URL = "https://datacenter.aminer.cn/gateway/open_platform/api/paper/relation"
DEFAULT_AMINER_AUTHOR_URL = ""
DEFAULT_AMINER_VENUE_URL = ""
DEFAULT_FIRECRAWL_BASE_URL = "https://api.firecrawl.dev"
DEFAULT_LLM_ENDPOINT = "/v1/chat/completions"
SKILL_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_PROVIDERS = {"aminer", "firecrawl"}
SUPPORTED_REPAIR_ACTIONS = {
    "run_provider_search",
    "expand_citations",
    "fetch_fulltext",
    "rerun_llm_extraction",
    "enrich_metadata",
    "merge_and_deduplicate",
    "rebuild_matrix",
}
REQUIRED_EXTRACTION_KEYS = {
    "task",
    "method",
    "dataset",
    "core_contribution",
    "limitations",
    "suggested_section",
    "evidence_snippets",
    "confidence",
    "missing_evidence",
}


class LiteratureResearchError(RuntimeError):
    """Raised when literature research cannot complete."""


def is_relative_to_path(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def workspace_output_base(cwd: Path | None = None) -> Path:
    current = (cwd or Path.cwd()).resolve()
    skill_root = SKILL_ROOT.resolve()
    if not is_relative_to_path(current, skill_root):
        return current

    parts = list(skill_root.parts)
    if ".cmdop" in parts:
        return Path(*parts[: parts.index(".cmdop")])
    if skill_root.parent.name == "skills":
        return skill_root.parent.parent
    return skill_root.parent


def slugify_for_path(value: str, *, max_length: int = 48) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (slug[:max_length].strip("-._") or "literature-run").lower()


def timestamped_output_dir(topic: str, *, base_dir: Path | None = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (base_dir or workspace_output_base()) / "literature-runs" / f"{timestamp}-{slugify_for_path(topic)}"


def resolve_output_path(path: Path | str | None, *, topic: str | None = None, must_be_dir: bool = False) -> Path:
    if path is None:
        if not must_be_dir or topic is None:
            raise LiteratureResearchError("Output path is required.")
        resolved = timestamped_output_dir(topic).resolve()
    else:
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        else:
            resolved = resolved.resolve()

    skill_root = SKILL_ROOT.resolve()
    if resolved == skill_root or is_relative_to_path(resolved, skill_root):
        raise LiteratureResearchError(
            f"Refusing to write artifacts inside the skill folder: {resolved}. "
            "Use a workspace output folder such as literature-runs/<timestamp>-<topic>."
        )
    return resolved


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit_progress(progress_stage: str, progress_message: str, **fields: Any) -> None:
    """Emit a compact stdout progress line for OpenClaw process monitors."""
    safe_fields = {
        key: value
        for key, value in fields.items()
        if value is not None and value != ""
    }
    suffix = ""
    if safe_fields:
        suffix = " " + json.dumps(safe_fields, ensure_ascii=False, sort_keys=True, default=str)
    print(f"[literature-progress] {utc_timestamp()} {progress_stage}: {progress_message}{suffix}", flush=True)


@dataclass(slots=True)
class DiagnosticIssue:
    type: str
    severity: str
    message: str
    repair_options: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    issue_id: str = ""
    affected_source_ids: list[str] = field(default_factory=list)
    affected_artifacts: list[str] = field(default_factory=list)
    metric: str = ""
    threshold: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    candidate_actions: list[str] = field(default_factory=list)
    blocking: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.issue_id:
            self.issue_id = self.type
        if self.repair_options and not self.candidate_actions:
            self.candidate_actions = list(self.repair_options)


@dataclass(slots=True)
class DiagnosticReport:
    status: str
    issues: list[DiagnosticIssue] = field(default_factory=list)
    stage: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    affected_artifacts: list[str] = field(default_factory=list)
    generated_at: str = ""
    requires_openclaw_decision: bool = False
    requires_user_decision: bool = False

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = utc_timestamp()


@dataclass(slots=True)
class ResearchScope:
    topic: str
    research_question: str
    time_range: str
    focus_dimensions: list[str]
    inclusion_criteria: list[str]
    exclusion_criteria: list[str]
    demo_fast: bool = False
    quality_level: str = ""


@dataclass(slots=True)
class QueryPlan:
    topic: str
    queries: list[str] = field(default_factory=list)
    scope_note: str = ""
    query_groups: dict[str, list[str]] = field(default_factory=dict)
    demo_fast: bool = False
    keywords: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    broader_terms: list[str] = field(default_factory=list)
    narrower_terms: list[str] = field(default_factory=list)
    domain_terms: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    provider_targets: dict[str, list[str]] = field(default_factory=dict)
    facet_intent: dict[str, str] = field(default_factory=dict)
    max_results: int | None = None
    language: str = ""
    notes: str = ""
    quality_level: str = ""


@dataclass(slots=True)
class CandidateSource:
    source_id: str
    title: str
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    url: str = ""
    pdf: str = ""
    doi: str = ""
    arxiv_id: str = ""
    citation_count: int = 0
    provider: str = ""
    source_type: str = "paper"
    raw: dict[str, Any] = field(default_factory=dict)
    content_text: str = ""
    content_type: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LiteratureMatrixRow:
    paper_id: str
    title: str
    year: int | None
    authors: str
    venue: str
    source_channel: str
    source_type: str
    url: str
    doi: str
    arxiv_id: str
    task: str
    method: str
    dataset: str
    core_contribution: str
    limitations: str
    citation_value: str
    suggested_section: str
    relevance_score: float
    credibility_score: float
    read_priority: str
    notes: str
    evidence_snippets: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    missing_evidence: list[str] = field(default_factory=list)
    extraction_status: str = ""
    extraction_basis: str = ""
    extraction_method: str = ""
    demo_fast: bool = False
    quality_level: str = ""
    score_breakdown: dict[str, float] = field(default_factory=dict)
    priority_reason: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class PaperExtraction:
    source_id: str
    task: str = ""
    method: str = ""
    dataset: str = ""
    core_contribution: str = ""
    limitations: str = ""
    suggested_section: str = ""
    evidence_snippets: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    missing_evidence: list[str] = field(default_factory=list)
    extraction_status: str = "pending"
    extraction_basis: str = ""
    extraction_method: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchTraceEvent:
    provider: str
    query: str
    endpoint: str
    status: str
    result_count: int
    elapsed_seconds: float
    error: str = ""
    request_params: dict[str, Any] = field(default_factory=dict)
    normalization_path: str = ""


@dataclass(slots=True)
class LiteratureResearchResult:
    topic: str
    query_plan: QueryPlan
    candidate_count: int
    matrix: list[LiteratureMatrixRow]
    trace: list[SearchTraceEvent]
    output_paths: dict[str, str]
    scope: ResearchScope | None = None
    diagnostics: dict[str, DiagnosticReport] = field(default_factory=dict)
    demo_fast: bool = False


class LiteratureProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> tuple[list[CandidateSource], SearchTraceEvent]:
        ...


def clean_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        cleaned = value.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    return None


def build_research_scope(topic: str, *, demo_fast: bool = False) -> ResearchScope:
    cleaned = " ".join(topic.strip().split())
    if not cleaned:
        raise LiteratureResearchError("Topic must not be empty.")
    return ResearchScope(
        topic=cleaned,
        research_question=f"What are the representative literature, methods, evaluations, and limitations for {cleaned}?",
        time_range="recent and foundational work, with emphasis on the last 5 years",
        focus_dimensions=["surveys and reviews", "core methods", "benchmarks and evaluation", "applications", "limitations"],
        inclusion_criteria=[
            "scholarly papers, benchmarks, technical reports, official docs, and project pages directly relevant to the topic",
            "sources with enough metadata or snippet text to support screening",
        ],
        exclusion_criteria=[
            "marketing-only pages without technical evidence",
            "sources whose relation to the topic is only incidental",
        ],
        demo_fast=demo_fast,
        quality_level="schema_smoke_only" if demo_fast else "bootstrap_template",
    )


def validate_research_scope(scope: ResearchScope) -> DiagnosticReport:
    issues: list[DiagnosticIssue] = []
    if len(scope.topic.split()) < 2:
        issues.append(
            DiagnosticIssue(
                type="scope_too_broad",
                severity="high",
                message="The topic is too short to guide focused literature search.",
                repair_options=["narrow_focus_dimensions"],
            )
        )
    if not scope.time_range.strip():
        issues.append(
            DiagnosticIssue(
                type="missing_time_range",
                severity="medium",
                message="No time range is recorded for traceable screening.",
                repair_options=["add_time_range"],
            )
        )
    if not scope.focus_dimensions:
        issues.append(
            DiagnosticIssue(
                type="missing_focus_dimensions",
                severity="high",
                message="No focus dimensions are available for query planning.",
                repair_options=["narrow_focus_dimensions"],
            )
        )
    if not scope.exclusion_criteria:
        issues.append(
            DiagnosticIssue(
                type="vague_exclusion_criteria",
                severity="medium",
                message="No exclusion criteria are recorded for screening.",
                repair_options=["add_exclusion_criteria"],
            )
        )
    return DiagnosticReport(
        status="blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok",
        issues=issues,
        stage="scope_validate",
        requires_openclaw_decision=bool(issues),
    )


def repair_research_scope(scope: ResearchScope) -> ResearchScope:
    repaired = ResearchScope(**asdict(scope))
    if not repaired.time_range.strip():
        repaired.time_range = "recent and foundational work, with emphasis on the last 5 years"
    if not repaired.focus_dimensions:
        repaired.focus_dimensions = ["surveys and reviews", "core methods", "benchmarks and evaluation", "applications", "limitations"]
    if not repaired.inclusion_criteria:
        repaired.inclusion_criteria = ["sources directly relevant to the topic with usable metadata or snippet evidence"]
    if not repaired.exclusion_criteria:
        repaired.exclusion_criteria = ["marketing-only or incidentally related sources"]
    return repaired


def build_query_plan(topic: str, *, max_queries: int = 8) -> QueryPlan:
    return build_query_plan_from_scope(build_research_scope(topic), max_queries=max_queries)


def build_query_plan_from_scope(scope: ResearchScope, *, max_queries: int = 8) -> QueryPlan:
    cleaned = scope.topic
    query_groups = {
        "core": [cleaned],
        "survey_review": [f"{cleaned} survey", f"{cleaned} review"],
        "benchmark_dataset": [f"{cleaned} benchmark", f"{cleaned} dataset"],
        "method_system": [f"{cleaned} method", f"{cleaned} framework", f"{cleaned} system"],
        "application": [f"{cleaned} applications"],
        "limitation_risk": [f"{cleaned} limitations", f"{cleaned} challenges"],
        "recent_work": [f"{cleaned} recent work"],
        "foundation_classic": [f"{cleaned} foundational work"],
        "fulltext_web": [f"{cleaned} technical report", f"{cleaned} project documentation"],
    }
    variants = [query for group in query_groups.values() for query in group]
    unique: list[str] = []
    seen: set[str] = set()
    for query in variants:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(query)
        if len(unique) >= max(1, max_queries):
            break
    return QueryPlan(
        topic=cleaned,
        queries=unique,
        scope_note=(
            "Demo/bootstrap query plan generated from the topic for schema smoke only. "
            "Real mode must consume an OpenClaw-authored query_plan.json."
        ),
        query_groups={name: [query for query in queries if query in unique] for name, queries in query_groups.items()},
        demo_fast=scope.demo_fast,
        keywords=[cleaned],
        provider_targets={"aminer": unique, "firecrawl": unique},
        max_results=None,
        language="en",
        quality_level="schema_smoke_only" if scope.demo_fast else "bootstrap_template",
    )


def executable_queries(query_plan: QueryPlan) -> list[str]:
    variants = list(query_plan.queries)
    if not variants:
        variants.extend(query for group in query_plan.query_groups.values() for query in group)
    unique: list[str] = []
    seen: set[str] = set()
    for query in variants:
        cleaned = " ".join(str(query).split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def validate_query_plan(scope: ResearchScope, query_plan: QueryPlan) -> DiagnosticReport:
    issues: list[DiagnosticIssue] = []
    queries = executable_queries(query_plan)
    if not queries:
        issues.append(
            DiagnosticIssue(
                type="generic_queries",
                severity="high",
                message="The query plan contains no executable queries.",
                repair_options=["provide_query_plan"],
            )
        )
    required_groups = {"core", "survey_review", "benchmark_dataset", "method_system", "fulltext_web"}
    present_groups = {name for name, queries in query_plan.query_groups.items() if queries}
    missing = [] if query_plan.demo_fast else sorted(required_groups - present_groups)
    if missing:
        issues.append(
            DiagnosticIssue(
                type="unbalanced_query_groups",
                severity="medium",
                message="The query plan is missing required query groups.",
                repair_options=["provide_query_plan"],
                missing=missing,
            )
        )
    unknown_providers = sorted(set(query_plan.provider_targets) - SUPPORTED_PROVIDERS)
    if unknown_providers:
        issues.append(
            DiagnosticIssue(
                type="unsupported_provider_targets",
                severity="high",
                message="The query plan targets providers outside the frozen AMiner plus Firecrawl scope.",
                repair_options=["provide_query_plan"],
                missing=unknown_providers,
                blocking=True,
            )
        )
    if queries and all(query.lower() == scope.topic.lower() for query in queries):
        issues.append(
            DiagnosticIssue(
                type="missing_synonyms",
                severity="medium",
                message="The query plan does not expand beyond the raw topic.",
                repair_options=["provide_query_plan"],
            )
        )
    return DiagnosticReport(
        status="blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok",
        issues=issues,
        stage="query_validate",
        metrics={"query_count": len(queries), "query_group_count": len(present_groups)},
        requires_openclaw_decision=bool(issues),
    )


def repair_query_plan(scope: ResearchScope, query_plan: QueryPlan, *, max_queries: int = 8) -> QueryPlan:
    repaired = build_query_plan_from_scope(scope, max_queries=max(max_queries, len(query_plan.queries), 8))
    existing = list(query_plan.queries)
    for query in repaired.queries:
        if query not in existing:
            existing.append(query)
    repaired.queries = existing[: max(1, max_queries)]
    repaired.query_groups = {
        name: [query for query in queries if query in repaired.queries]
        for name, queries in repaired.query_groups.items()
    }
    return repaired


class AMinerProvider:
    name = "aminer"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        endpoint: str | None = None,
        token: str | None = None,
        model: str | None = None,
        detail_url: str | None = None,
        relation_url: str | None = None,
        author_url: str | None = None,
        venue_url: str | None = None,
        timeout: int = 90,
    ) -> None:
        self.base_url = (base_url or clean_env("AMINER_SEARCH_API_BASE_URL") or DEFAULT_AMINER_SEARCH_BASE_URL).rstrip("/")
        self.endpoint = endpoint or clean_env("AMINER_SEARCH_API_ENDPOINT") or DEFAULT_AMINER_SEARCH_ENDPOINT
        self.token = token if token is not None else clean_env("AMINER_SEARCH_API_TOKEN")
        self.model = model or clean_env("AMINER_SEARCH_MODEL") or "glm-4.5"
        self.detail_url = detail_url or clean_env("AMINER_DETAIL_URL") or DEFAULT_AMINER_DETAIL_URL
        self.relation_url = relation_url or clean_env("AMINER_RELATION_URL") or DEFAULT_AMINER_RELATION_URL
        self.author_url = author_url if author_url is not None else clean_env("AMINER_AUTHOR_URL") or DEFAULT_AMINER_AUTHOR_URL
        self.venue_url = venue_url if venue_url is not None else clean_env("AMINER_VENUE_URL") or DEFAULT_AMINER_VENUE_URL
        self.timeout = timeout
        self.session = requests.Session()
        self.detail_trace: list[dict[str, Any]] = []
        self.relation_trace: list[dict[str, Any]] = []
        self.authority_trace: list[dict[str, Any]] = []

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.endpoint if self.endpoint.startswith('/') else '/' + self.endpoint}"

    def search(self, query: str, *, limit: int) -> tuple[list[CandidateSource], SearchTraceEvent]:
        started = time.perf_counter()
        payload = {
            "query": query,
            "max_papers": max(1, min(limit, 100)),
            "pdf_only": False,
            "verbose": False,
            "model_config": {"model": self.model},
        }
        if not self.token:
            emit_progress("provider.search", "skipped missing AMiner token", provider=self.name, query=query)
            return [], SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="skipped",
                result_count=0,
                elapsed_seconds=0.0,
                error=(
                    "AMINER_SEARCH_API_TOKEN is not configured. For OpenClaw indirect invocation, "
                    "inject it through the skill env contract instead of PATH."
                ),
                request_params=safe_request_params(payload),
                normalization_path="aminer.search",
            )
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = self.token
        emit_progress(
            "provider.search",
            "starting AMiner search",
            provider=self.name,
            query=query,
            limit=payload["max_papers"],
            timeout_seconds=self.timeout,
        )
        try:
            response = self.session.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                raise LiteratureResearchError(str(data.get("error") or data.get("detail") or data))
            items = _extract_items(data)
            emit_progress(
                "provider.search",
                "AMiner search returned items",
                provider=self.name,
                query=query,
                item_count=len(items),
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            sources: list[CandidateSource] = []
            for index, item in enumerate(items, start=1):
                source = normalize_aminer_item(item)
                emit_progress(
                    "provider.detail",
                    "starting AMiner detail enrichment",
                    provider=self.name,
                    index=index,
                    total=len(items),
                    source_id=source.source_id,
                    title=source.title[:120],
                )
                sources.append(self.enrich_detail(source))
            return sources, SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="ok",
                result_count=len(sources),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                request_params=safe_request_params(payload),
                normalization_path="aminer.search->normalize_aminer_item->aminer.detail",
            )
        except Exception as exc:
            emit_progress(
                "provider.search",
                "AMiner search failed",
                provider=self.name,
                query=query,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=type(exc).__name__,
            )
            return [], SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="error",
                result_count=0,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(payload),
                normalization_path="aminer.search",
            )

    def enrich_detail(self, source: CandidateSource) -> CandidateSource:
        started = time.perf_counter()
        trace_event = {
            "provider": self.name,
            "source_id": source.source_id,
            "endpoint": self.detail_url,
            "status": "skipped",
            "failure_type": "",
            "elapsed_seconds": 0.0,
        }
        if not source.source_id:
            trace_event["failure_type"] = "missing_aminer_id"
            self.detail_trace.append(trace_event)
            emit_progress("provider.detail", "skipped AMiner detail missing id", provider=self.name)
            return source
        if not self.token:
            trace_event["failure_type"] = "unauthorized"
            self.detail_trace.append(trace_event)
            emit_progress("provider.detail", "skipped AMiner detail missing token", provider=self.name, source_id=source.source_id)
            return source
        try:
            response = self.session.get(
                self.detail_url,
                params={"id": source.source_id},
                headers={"Authorization": self.token},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            detail = _extract_detail_item(data)
            if not detail:
                trace_event.update(
                    status="needs_review",
                    failure_type="empty_detail",
                    elapsed_seconds=round(time.perf_counter() - started, 3),
                )
                self.detail_trace.append(trace_event)
                emit_progress(
                    "provider.detail",
                    "AMiner detail empty",
                    provider=self.name,
                    source_id=source.source_id,
                    elapsed_seconds=trace_event["elapsed_seconds"],
                )
                return source
            enriched = normalize_aminer_item({**detail, "id": detail.get("id") or source.source_id})
            trace_event.update(status="ok", elapsed_seconds=round(time.perf_counter() - started, 3))
            self.detail_trace.append(trace_event)
            emit_progress(
                "provider.detail",
                "AMiner detail completed",
                provider=self.name,
                source_id=source.source_id,
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return merge_candidate_detail(source, enriched)
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            trace_event.update(
                status="failed",
                failure_type=classify_http_failure(status_code),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
            )
            self.detail_trace.append(trace_event)
            emit_progress(
                "provider.detail",
                "AMiner detail failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return source
        except Exception as exc:
            trace_event.update(
                status="failed",
                failure_type="malformed_response",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
            )
            self.detail_trace.append(trace_event)
            emit_progress(
                "provider.detail",
                "AMiner detail failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return source

    def fetch_references(self, source: CandidateSource, *, limit: int = 50) -> tuple[list[CandidateSource], dict[str, Any]]:
        started = time.perf_counter()
        trace_event: dict[str, Any] = {
            "provider": self.name,
            "seed_source_id": source.source_id,
            "endpoint": self.relation_url,
            "status": "pending",
            "relation": "references",
            "result_count": 0,
            "elapsed_seconds": 0.0,
        }
        if not source.source_id:
            trace_event.update(status="skipped", failure_type="missing_aminer_id")
            self.relation_trace.append(trace_event)
            emit_progress("citation.expand", "skipped references missing AMiner id", provider=self.name)
            return [], trace_event
        raw_refs = extract_reference_candidates(source)
        if raw_refs:
            refs = [candidate_from_reference_payload(item, seed=source) for item in raw_refs[:limit]]
            trace_event.update(status="ok", result_count=len(refs), normalization_path="aminer.detail.references")
            self.relation_trace.append(trace_event)
            emit_progress(
                "citation.expand",
                "used embedded references",
                provider=self.name,
                source_id=source.source_id,
                result_count=len(refs),
            )
            return refs, trace_event
        if not self.token:
            trace_event.update(status="skipped", failure_type="unauthorized", error="AMINER_SEARCH_API_TOKEN is not configured.")
            self.relation_trace.append(trace_event)
            emit_progress("citation.expand", "skipped references missing token", provider=self.name, source_id=source.source_id)
            return [], trace_event
        params = {"id": source.source_id, "type": "references", "limit": max(1, min(limit, 100))}
        emit_progress(
            "citation.expand",
            "starting AMiner reference fetch",
            provider=self.name,
            source_id=source.source_id,
            limit=params["limit"],
            timeout_seconds=self.timeout,
        )
        try:
            response = self.session.get(
                self.relation_url,
                params=params,
                headers={"Authorization": self.token},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            refs = [candidate_from_reference_payload(item, seed=source) for item in _extract_relation_items(data)[:limit]]
            trace_event.update(
                status="ok",
                result_count=len(refs),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                request_params=safe_request_params(params),
                normalization_path="aminer.relation.references->normalize_aminer_item",
            )
            self.relation_trace.append(trace_event)
            emit_progress(
                "citation.expand",
                "AMiner reference fetch completed",
                provider=self.name,
                source_id=source.source_id,
                result_count=len(refs),
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return refs, trace_event
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            trace_event.update(
                status="failed",
                failure_type=classify_http_failure(status_code),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(params),
            )
            self.relation_trace.append(trace_event)
            emit_progress(
                "citation.expand",
                "AMiner reference fetch failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return [], trace_event
        except Exception as exc:
            trace_event.update(
                status="failed",
                failure_type="malformed_response",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(params),
            )
            self.relation_trace.append(trace_event)
            emit_progress(
                "citation.expand",
                "AMiner reference fetch failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return [], trace_event

    def enrich_authority(self, source: CandidateSource) -> CandidateSource:
        if source.provider and "aminer" not in source.provider:
            return source
        enriched = CandidateSource(**asdict(source))
        authority = extract_provider_authority(enriched)
        if self.author_url and self.token:
            scores = []
            for author in enriched.authors[:5]:
                score = self.fetch_authority_score(self.author_url, author, authority_type="author")
                if score is not None:
                    scores.append(score)
            if scores:
                authority["author_authority"] = max(float(authority.get("author_authority") or 0), max(scores))
        if self.venue_url and self.token and enriched.venue:
            score = self.fetch_authority_score(self.venue_url, enriched.venue, authority_type="venue")
            if score is not None:
                authority["venue_authority"] = max(float(authority.get("venue_authority") or 0), score)
        enriched.signals.update(authority)
        return enriched

    def fetch_authority_score(self, endpoint: str, name: str, *, authority_type: str) -> float | None:
        started = time.perf_counter()
        trace_event: dict[str, Any] = {
            "provider": self.name,
            "authority_type": authority_type,
            "name": name,
            "endpoint": endpoint,
            "status": "pending",
            "elapsed_seconds": 0.0,
        }
        try:
            emit_progress("metadata.authority", "starting authority lookup", provider=self.name, authority_type=authority_type, name=name)
            response = self.session.get(endpoint, params={"name": name}, headers={"Authorization": self.token or ""}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            score = authority_score_from_payload(payload, authority_type=authority_type)
            trace_event.update(status="ok", score=score, elapsed_seconds=round(time.perf_counter() - started, 3))
            self.authority_trace.append(trace_event)
            emit_progress(
                "metadata.authority",
                "authority lookup completed",
                provider=self.name,
                authority_type=authority_type,
                name=name,
                score=score,
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return score
        except Exception as exc:
            trace_event.update(status="failed", error=str(exc), elapsed_seconds=round(time.perf_counter() - started, 3))
            self.authority_trace.append(trace_event)
            emit_progress(
                "metadata.authority",
                "authority lookup failed",
                provider=self.name,
                authority_type=authority_type,
                name=name,
                elapsed_seconds=trace_event["elapsed_seconds"],
                error=type(exc).__name__,
            )
            return None


class FirecrawlProvider:
    name = "firecrawl"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
        scrape_markdown: bool = False,
    ) -> None:
        self.api_key = api_key if api_key is not None else clean_env("FIRECRAWL_API_KEY")
        self.base_url = (base_url or clean_env("FIRECRAWL_BASE_URL") or DEFAULT_FIRECRAWL_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.scrape_markdown = scrape_markdown
        self.session = requests.Session()

    @property
    def url(self) -> str:
        return f"{self.base_url}/search" if self.base_url.endswith("/v2") else f"{self.base_url}/v2/search"

    @property
    def scrape_url(self) -> str:
        return f"{self.base_url}/scrape" if self.base_url.endswith("/v2") else f"{self.base_url}/v2/scrape"

    def search(self, query: str, *, limit: int) -> tuple[list[CandidateSource], SearchTraceEvent]:
        started = time.perf_counter()
        if not self.api_key:
            emit_progress("provider.search", "skipped Firecrawl search missing key", provider=self.name, query=query)
            return [], SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="skipped",
                result_count=0,
                elapsed_seconds=0.0,
                error="FIRECRAWL_API_KEY is not configured.",
            )
        payload: dict[str, Any] = {
            "query": query,
            "limit": max(1, min(limit, 100)),
            "sources": [{"type": "web"}],
            "categories": [{"type": "research"}, {"type": "pdf"}],
            "timeout": self.timeout * 1000,
        }
        if self.scrape_markdown:
            payload["scrapeOptions"] = {"formats": [{"type": "markdown"}]}
        emit_progress(
            "provider.search",
            "starting Firecrawl search",
            provider=self.name,
            query=query,
            limit=payload["limit"],
            timeout_seconds=self.timeout,
            scrape_markdown=self.scrape_markdown,
        )
        try:
            response = self.session.post(
                self.url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                raise LiteratureResearchError(str(data.get("error") or data))
            items = _extract_firecrawl_items(data)
            sources = [normalize_firecrawl_item(item) for item in items]
            emit_progress(
                "provider.search",
                "Firecrawl search completed",
                provider=self.name,
                query=query,
                result_count=len(sources),
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            return sources, SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="ok",
                result_count=len(sources),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                request_params=safe_request_params(payload),
                normalization_path="firecrawl.search->normalize_firecrawl_item",
            )
        except Exception as exc:
            emit_progress(
                "provider.search",
                "Firecrawl search failed",
                provider=self.name,
                query=query,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=type(exc).__name__,
            )
            return [], SearchTraceEvent(
                provider=self.name,
                query=query,
                endpoint=self.url,
                status="error",
                result_count=0,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(payload),
                normalization_path="firecrawl.search",
            )

    def scrape(self, source: CandidateSource) -> tuple[CandidateSource, dict[str, Any]]:
        started = time.perf_counter()
        trace_event: dict[str, Any] = {
            "provider": self.name,
            "source_id": source.source_id,
            "url": source.pdf or source.url,
            "endpoint": self.scrape_url,
            "status": "pending",
            "elapsed_seconds": 0.0,
        }
        target_url = source.pdf or source.url
        if not target_url:
            trace_event.update(status="skipped", failure_type="missing_url")
            emit_progress("fulltext.fetch", "skipped scrape missing url", provider=self.name, source_id=source.source_id)
            return source, trace_event
        if not self.api_key:
            trace_event.update(status="skipped", failure_type="unauthorized", error="FIRECRAWL_API_KEY is not configured.")
            emit_progress("fulltext.fetch", "skipped scrape missing key", provider=self.name, source_id=source.source_id)
            return source, trace_event
        payload = {
            "url": target_url,
            "formats": [{"type": "markdown"}],
            "timeout": self.timeout * 1000,
        }
        emit_progress(
            "fulltext.fetch",
            "starting Firecrawl scrape",
            provider=self.name,
            source_id=source.source_id,
            source_type=source.source_type,
            timeout_seconds=self.timeout,
        )
        try:
            response = self.session.post(
                self.scrape_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("success") is False:
                raise LiteratureResearchError(str(data.get("error") or data))
            markdown = extract_firecrawl_markdown(data)
            updated = CandidateSource(**asdict(source))
            updated.content_text = markdown
            updated.content_type = classify_firecrawl_content(url=target_url, title=source.title, markdown=markdown)
            if not updated.abstract and markdown:
                updated.abstract = summarize_markdown_for_snippet(markdown)
            trace_event.update(
                status="ok" if markdown else "empty_content",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                character_count=len(markdown),
                content_type=updated.content_type,
                request_params=safe_request_params(payload),
            )
            emit_progress(
                "fulltext.fetch",
                "Firecrawl scrape completed",
                provider=self.name,
                source_id=source.source_id,
                status=trace_event["status"],
                character_count=len(markdown),
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return updated, trace_event
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            trace_event.update(
                status="failed",
                failure_type=classify_http_failure(status_code),
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(payload),
            )
            emit_progress(
                "fulltext.fetch",
                "Firecrawl scrape failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return source, trace_event
        except Exception as exc:
            trace_event.update(
                status="failed",
                failure_type="malformed_response",
                elapsed_seconds=round(time.perf_counter() - started, 3),
                error=str(exc),
                request_params=safe_request_params(payload),
            )
            emit_progress(
                "fulltext.fetch",
                "Firecrawl scrape failed",
                provider=self.name,
                source_id=source.source_id,
                failure_type=trace_event["failure_type"],
                elapsed_seconds=trace_event["elapsed_seconds"],
            )
            return source, trace_event

    def enrich_authority(self, source: CandidateSource) -> CandidateSource:
        if source.provider and "firecrawl" not in source.provider:
            return source
        enriched = CandidateSource(**asdict(source))
        authority = extract_provider_authority(enriched)
        enriched.signals.update(authority)
        return enriched


class DemoProvider:
    name = "demo"

    def search(self, query: str, *, limit: int) -> tuple[list[CandidateSource], SearchTraceEvent]:
        started = time.perf_counter()
        emit_progress("provider.search", "starting demo search", provider=self.name, query=query, limit=limit)
        sources = [
            CandidateSource(
                source_id="demo-seed-survey",
                title=f"Survey Foundations for {query}",
                abstract="A survey-style seed source used for deterministic literature matrix smoke tests.",
                authors=["Demo Author"],
                year=2026,
                venue="Demo Proceedings",
                url="https://example.org/demo-survey",
                citation_count=42,
                provider=self.name,
                source_type="paper",
                raw={"demo": True},
            ),
            CandidateSource(
                source_id="demo-benchmark",
                title=f"Benchmarking Methods in {query}",
                abstract="A benchmark-style source with method, dataset, limitation, and evaluation signals.",
                authors=["Demo Researcher"],
                year=2025,
                venue="Demo Benchmark Track",
                url="https://example.org/demo-benchmark",
                citation_count=12,
                provider=self.name,
                source_type="paper",
                raw={"demo": True},
            ),
        ]
        emit_progress("provider.search", "demo search completed", provider=self.name, query=query, result_count=len(sources))
        return sources, SearchTraceEvent(
            provider=self.name,
            query=query,
            endpoint="demo://literature-research",
            status="ok",
            result_count=len(sources),
            elapsed_seconds=round(time.perf_counter() - started, 3),
            request_params={"query": query, "limit": limit, "demo_fast": True},
            normalization_path="demo.provider",
        )

    def scrape(self, source: CandidateSource) -> tuple[CandidateSource, dict[str, Any]]:
        updated = CandidateSource(**asdict(source))
        updated.content_text = updated.content_text or f"# Demo content\n\nDeterministic fulltext smoke content for {updated.title}."
        updated.content_type = "scraped_markdown"
        return updated, {
            "provider": self.name,
            "source_id": source.source_id,
            "url": source.url,
            "endpoint": "demo://firecrawl-scrape",
            "status": "ok",
            "elapsed_seconds": 0.0,
            "character_count": len(updated.content_text),
            "content_type": updated.content_type,
            "demo_fast": True,
        }

    def fetch_references(self, source: CandidateSource, *, limit: int = 50) -> tuple[list[CandidateSource], dict[str, Any]]:
        refs = [
            CandidateSource(
                source_id=f"{source.source_id}-reference",
                title=f"Demo backward reference for {source.title}",
                authors=["Demo Reference Author"],
                year=(source.year or 2026) - 1,
                venue="Demo Reference Venue",
                url=f"{source.url.rstrip('/')}/reference" if source.url else "",
                provider=self.name,
                source_type="paper",
                raw={"demo_fast": True},
                provenance=[{"introduced_by": "citation_expansion", "seed_source_id": source.source_id, "edge_type": "references", "provider": self.name}],
            )
        ][: max(1, min(limit, 1))]
        return refs, {
            "provider": self.name,
            "seed_source_id": source.source_id,
            "endpoint": "demo://aminer-references",
            "status": "ok",
            "relation": "references",
            "result_count": len(refs),
            "elapsed_seconds": 0.0,
            "demo_fast": True,
        }


class LLMExtractor:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        timeout: int = 90,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or clean_env("LITERATURE_LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key if api_key is not None else clean_env("LITERATURE_LLM_API_KEY")
        self.model = model or clean_env("LITERATURE_LLM_MODEL") or ""
        self.endpoint = endpoint or clean_env("LITERATURE_LLM_ENDPOINT") or DEFAULT_LLM_ENDPOINT
        if self.base_url.lower().endswith("/v1") and self.endpoint.lstrip("/").lower().startswith("v1/"):
            self.base_url = self.base_url[:-3].rstrip("/")
            emit_progress(
                "llm.config",
                "normalized LLM base URL to avoid duplicate /v1 path",
                endpoint=self.endpoint,
            )
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        missing = [
            name
            for name, value in (
                ("LITERATURE_LLM_BASE_URL", self.base_url),
                ("LITERATURE_LLM_API_KEY", self.api_key),
                ("LITERATURE_LLM_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            raise LiteratureResearchError(
                "Missing LLM environment variable(s): "
                + ", ".join(missing)
                + ". Real mode requires LLM-only extraction; use --demo-fast for schema smoke."
            )

    @property
    def url(self) -> str:
        return urljoin(self.base_url + "/", self.endpoint.lstrip("/"))

    def extract(self, source: CandidateSource, *, topic: str) -> tuple[PaperExtraction, dict[str, Any]]:
        evidence_text, basis = extraction_input_for_source(source)
        trace: dict[str, Any] = {
            "source_id": source.source_id,
            "title": source.title,
            "basis": basis,
            "status": "pending",
            "attempts": [],
            "endpoint": self.url,
            "model": self.model,
        }
        if not evidence_text.strip():
            emit_progress(
                "llm.extract",
                "skipped extraction missing evidence",
                source_id=source.source_id,
                title=source.title[:120],
            )
            extraction = PaperExtraction(
                source_id=source.source_id,
                missing_evidence=["content"],
                extraction_status="failed",
                extraction_basis="metadata",
                extraction_method="llm",
            )
            trace["status"] = "failed"
            trace["error"] = "No usable abstract, snippet, metadata, or Firecrawl content was available."
            return extraction, trace

        prompt = build_extraction_prompt(source, topic=topic, evidence_text=evidence_text)
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            emit_progress(
                "llm.extract",
                "starting LLM extraction attempt",
                source_id=source.source_id,
                title=source.title[:120],
                basis=basis,
                attempt=attempt,
                max_attempts=self.max_retries + 1,
                timeout_seconds=self.timeout,
            )
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Extract literature matrix fields from the supplied evidence. "
                                "Return one strict JSON object only. Do not infer unsupported claims."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                }
                response = self.session.post(
                    self.url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                text = extract_llm_message(data)
                parsed = parse_llm_json(text)
                extraction = extraction_from_payload(source.source_id, parsed, basis=basis, method="llm")
                trace["status"] = extraction.extraction_status
                elapsed_seconds = round(time.perf_counter() - started, 3)
                trace["attempts"].append(
                    {
                        "attempt": attempt,
                        "status": "ok",
                        "elapsed_seconds": elapsed_seconds,
                    }
                )
                emit_progress(
                    "llm.extract",
                    "LLM extraction completed",
                    source_id=source.source_id,
                    status=extraction.extraction_status,
                    confidence=extraction.confidence,
                    elapsed_seconds=elapsed_seconds,
                )
                return extraction, trace
            except Exception as exc:
                last_error = str(exc)
                elapsed_seconds = round(time.perf_counter() - started, 3)
                trace["attempts"].append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "elapsed_seconds": elapsed_seconds,
                        "error": last_error,
                    }
                )
                emit_progress(
                    "llm.extract",
                    "LLM extraction attempt failed",
                    source_id=source.source_id,
                    attempt=attempt,
                    elapsed_seconds=elapsed_seconds,
                    error=type(exc).__name__,
                )
                prompt += "\n\nPrevious response was invalid. Return strict JSON only using the required keys."

        extraction = PaperExtraction(
            source_id=source.source_id,
            missing_evidence=["valid_llm_json"],
            extraction_status="failed",
            extraction_basis=basis,
            extraction_method="llm",
        )
        trace["status"] = "failed"
        trace["error"] = last_error
        emit_progress(
            "llm.extract",
            "LLM extraction failed",
            source_id=source.source_id,
            attempts=self.max_retries + 1,
            error=last_error[:160],
        )
        return extraction, trace


def run_literature_research(
    *,
    topic: str,
    output_dir: Path,
    providers: list[LiteratureProvider],
    max_results: int = 40,
    max_queries: int = 6,
    scope: ResearchScope | None = None,
    query_plan: QueryPlan | None = None,
    seed_selection: dict[str, Any] | None = None,
    seed_selection_policy: dict[str, Any] | None = None,
) -> LiteratureResearchResult:
    output_dir = resolve_output_path(output_dir, topic=topic, must_be_dir=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    emit_progress(
        "matrix.build",
        "run started",
        topic=topic,
        output_dir=str(output_dir),
        provider_count=len(providers),
        max_results=max_results,
        max_queries=max_queries,
    )
    demo_fast = all(getattr(provider, "name", "") == "demo" for provider in providers)
    if not demo_fast and query_plan is None:
        raise LiteratureResearchError(
            "Real mode requires an OpenClaw-authored query_plan.json. "
            "Use --query-plan or --demo-fast for deterministic schema smoke."
        )
    if scope is None:
        scope = build_research_scope(topic, demo_fast=demo_fast)
    if query_plan is None:
        query_plan = build_query_plan_from_scope(scope, max_queries=max_queries)
    query_plan.queries = executable_queries(query_plan)[: max(1, max_queries or len(executable_queries(query_plan)))]
    query_plan.demo_fast = demo_fast or query_plan.demo_fast
    emit_progress(
        "matrix.build",
        "scope and query plan ready",
        demo_fast=demo_fast,
        query_count=len(query_plan.queries),
        providers=[getattr(provider, "name", "") for provider in providers],
    )
    if not demo_fast:
        emit_progress("matrix.build", "validating LLM extraction configuration")
        ensure_real_mode_llm_config()
    scope_diagnostics = validate_research_scope(scope)
    query_diagnostics = validate_query_plan(scope, query_plan)
    emit_progress(
        "matrix.build",
        "diagnostics completed",
        scope_status=scope_diagnostics.status,
        query_status=query_diagnostics.status,
    )
    per_query_limit = max(1, min(100, max_results))
    trace: list[SearchTraceEvent] = []
    candidates: list[CandidateSource] = []

    total_searches = len(query_plan.queries) * len(providers)
    search_index = 0
    for query_index, query in enumerate(query_plan.queries, start=1):
        for provider in providers:
            search_index += 1
            emit_progress(
                "matrix.search",
                "starting provider query",
                index=search_index,
                total=total_searches,
                query_index=query_index,
                query_count=len(query_plan.queries),
                provider=getattr(provider, "name", ""),
                query=query,
                limit=per_query_limit,
            )
            provider_sources, event = provider.search(query, limit=per_query_limit)
            trace.append(event)
            candidates.extend(provider_sources)
            emit_progress(
                "matrix.search",
                "provider query completed",
                index=search_index,
                total=total_searches,
                provider=event.provider,
                status=event.status,
                result_count=event.result_count,
                elapsed_seconds=event.elapsed_seconds,
            )

    emit_progress("matrix.dedupe", "deduplicating candidates", candidate_count=len(candidates))
    unique_candidates, dedupe_trace = deduplicate_sources_with_trace(candidates)
    emit_progress("matrix.dedupe", "dedupe completed", unique_count=len(unique_candidates))
    emit_progress("metadata.authority", "starting provider authority enrichment", source_count=len(unique_candidates))
    unique_candidates = enrich_candidates_authority(unique_candidates, providers)
    emit_progress("metadata.authority", "authority enrichment completed", source_count=len(unique_candidates))
    seed_candidate_artifact = build_seed_candidates_artifact(scope, unique_candidates, policy=seed_selection_policy, demo_fast=demo_fast)
    emit_progress("seed.selection", "applying seed selection", candidate_count=len(unique_candidates))
    seed_papers, seed_selection_artifact, seed_diagnostics = apply_seed_selection(
        seed_candidate_artifact,
        unique_candidates,
        selection=seed_selection,
        policy=seed_selection_policy,
        demo_fast=demo_fast,
    )
    emit_progress("seed.selection", "seed selection completed", seed_count=len(seed_papers), status=seed_diagnostics.status)
    emit_progress("fulltext.fetch", "starting fulltext fetch", source_count=len(unique_candidates))
    fulltext_sources, fulltext_trace = fetch_fulltext_for_sources(unique_candidates, providers=providers, demo_fast=demo_fast)
    emit_progress("fulltext.fetch", "fulltext fetch completed", source_count=len(fulltext_sources), event_count=len(fulltext_trace.get("events", [])))
    emit_progress("matrix.dedupe", "deduplicating after fulltext fetch", candidate_count=len(fulltext_sources))
    unique_candidates, dedupe_trace = deduplicate_sources_with_trace(fulltext_sources)
    emit_progress("matrix.dedupe", "post-fulltext dedupe completed", unique_count=len(unique_candidates))
    emit_progress("artifacts.content", "writing content artifacts", source_count=len(unique_candidates))
    content_artifacts = write_content_artifacts(output_dir, unique_candidates, demo_fast=demo_fast)
    emit_progress("artifacts.content", "content artifacts written", output_dir=str(output_dir / "content"))
    emit_progress("llm.extract", "starting matrix field extraction", source_count=len(unique_candidates), demo_fast=demo_fast)
    extractions, extraction_trace, extraction_failures = extract_matrix_fields(
        unique_candidates,
        topic=query_plan.topic,
        demo_fast=demo_fast,
        output_dir=output_dir,
    )
    emit_progress("llm.extract", "matrix field extraction completed", failure_count=len(extraction_failures))
    emit_progress("matrix.rows", "building matrix rows", source_count=len(unique_candidates), max_results=max_results)
    matrix = [
        build_matrix_row(source, topic=query_plan.topic, extraction=extractions.get(source.source_id), demo_fast=demo_fast)
        for source in sorted(unique_candidates, key=_candidate_sort_key)
    ][:max_results]
    matrix_diagnostics = validate_literature_matrix(matrix)
    emit_progress("matrix.rows", "matrix rows built", row_count=len(matrix), diagnostics_status=matrix_diagnostics.status)
    emit_progress("citation.expand", "starting citation artifacts", seed_count=len(seed_papers))
    citation_artifacts = build_citation_artifacts(seed_papers, providers=providers, demo_fast=demo_fast)
    emit_progress("citation.expand", "citation artifacts completed", seed_count=len(seed_papers))
    emit_progress("matrix.gaps", "building gap and provider reports")
    gap_report = build_gap_report(matrix, trace=trace, extraction_failures=extraction_failures, demo_fast=demo_fast)
    provider_status = build_provider_status(providers, trace=trace, demo_fast=demo_fast)
    detail_trace = collect_detail_trace(providers)
    aminer_detail_diagnostics = build_aminer_detail_diagnostics(detail_trace, demo_fast=demo_fast)
    fulltext_diagnostics = build_fulltext_diagnostics(content_artifacts["manifest"], demo_fast=demo_fast)
    dedupe_diagnostics = build_dedupe_diagnostics(dedupe_trace, demo_fast=demo_fast)
    orchestration_summary = build_orchestration_summary(
        stage="matrix_build",
        diagnostics=[scope_diagnostics, seed_diagnostics, query_diagnostics, matrix_diagnostics, citation_artifacts["diagnostics"], aminer_detail_diagnostics, fulltext_diagnostics, dedupe_diagnostics],
        artifact_paths={},
        demo_fast=demo_fast,
    )

    diagnostics = {
        "scope": scope_diagnostics,
        "seed": seed_diagnostics,
        "query": query_diagnostics,
        "matrix": matrix_diagnostics,
        "fulltext": fulltext_diagnostics,
        "dedupe": dedupe_diagnostics,
    }
    emit_progress("artifacts.write", "writing final artifacts", output_dir=str(output_dir), row_count=len(matrix))
    output_paths = write_outputs(
        output_dir,
        topic=query_plan.topic,
        scope=scope,
        scope_diagnostics=scope_diagnostics,
        seed_papers=seed_papers,
        seed_diagnostics=seed_diagnostics,
        query_plan=query_plan,
        query_diagnostics=query_diagnostics,
        matrix=matrix,
        matrix_diagnostics=matrix_diagnostics,
        trace=trace,
        provider_status=provider_status,
        detail_trace=detail_trace,
        aminer_detail_diagnostics=aminer_detail_diagnostics,
        content_artifacts=content_artifacts,
        seed_candidate_artifact=seed_candidate_artifact,
        seed_selection_artifact=seed_selection_artifact,
        extraction_trace=extraction_trace,
        extraction_failures=extraction_failures,
        gap_report=gap_report,
        citation_artifacts=citation_artifacts,
        dedupe_trace=dedupe_trace,
        dedupe_diagnostics=dedupe_diagnostics,
        fulltext_diagnostics=fulltext_diagnostics,
        fulltext_trace=fulltext_trace,
        orchestration_summary=orchestration_summary,
        demo_fast=demo_fast,
    )
    update_orchestration_summary_path(output_dir / "orchestration_summary.json", orchestration_summary, output_paths)
    emit_progress("matrix.build", "run completed", output_dir=str(output_dir), row_count=len(matrix), artifact_count=len(output_paths))
    return LiteratureResearchResult(
        topic=query_plan.topic,
        query_plan=query_plan,
        candidate_count=len(unique_candidates),
        matrix=matrix,
        trace=trace,
        output_paths=output_paths,
        scope=scope,
        diagnostics=diagnostics,
        demo_fast=demo_fast,
    )


def discover_seed_papers(
    scope: ResearchScope,
    *,
    providers: list[LiteratureProvider],
    max_results: int = 20,
) -> list[CandidateSource]:
    seed_queries = [scope.topic, f"{scope.topic} survey", f"{scope.topic} benchmark"]
    candidates: list[CandidateSource] = []
    per_query_limit = max(1, min(20, max_results))
    emit_progress("seed.discover", "starting seed discovery", query_count=len(seed_queries), provider_count=len(providers))
    for query_index, query in enumerate(seed_queries, start=1):
        for provider_index, provider in enumerate(providers, start=1):
            emit_progress(
                "seed.discover",
                "starting seed query",
                query_index=query_index,
                query_count=len(seed_queries),
                provider_index=provider_index,
                provider=getattr(provider, "name", ""),
                query=query,
                limit=per_query_limit,
            )
            provider_sources, _event = provider.search(query, limit=per_query_limit)
            candidates.extend(provider_sources)
            emit_progress(
                "seed.discover",
                "seed query completed",
                query_index=query_index,
                provider=getattr(provider, "name", ""),
                result_count=len(provider_sources),
            )
    result = deduplicate_sources(candidates)[:max_results]
    emit_progress("seed.discover", "seed discovery completed", candidate_count=len(result))
    return result


def validate_seed_papers(scope: ResearchScope, seed_papers: list[CandidateSource]) -> DiagnosticReport:
    issues: list[DiagnosticIssue] = []
    minimum_seed_count = 2 if scope.demo_fast else 3
    if len(seed_papers) < minimum_seed_count:
        issues.append(
            DiagnosticIssue(
                type="too_few_seed_papers",
                severity="high",
                message=f"Fewer than {minimum_seed_count} seed sources were found.",
                repair_options=["provide_seed_selection", "provide_repair_plan"],
            )
        )
    haystack = " ".join(f"{source.title} {source.abstract}" for source in seed_papers).lower()
    missing: list[str] = []
    if "survey" not in haystack and "review" not in haystack:
        missing.append("survey")
    if "benchmark" not in haystack and "dataset" not in haystack:
        missing.append("benchmark")
    if missing:
        issues.append(
            DiagnosticIssue(
                type="missing_seed_type",
                severity="medium",
                message="Seed set lacks one or more useful source types.",
                repair_options=["provide_seed_selection", "provide_repair_plan"],
                missing=missing,
            )
        )
    return DiagnosticReport(
        status="blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok",
        issues=issues,
        stage="seed_validate",
        metrics={"seed_count": len(seed_papers)},
        requires_openclaw_decision=bool(issues),
    )


def enrich_candidates_authority(candidates: list[CandidateSource], providers: list[LiteratureProvider]) -> list[CandidateSource]:
    enriched: list[CandidateSource] = []
    for candidate in candidates:
        current = candidate
        for provider in providers:
            if hasattr(provider, "enrich_authority"):
                current = provider.enrich_authority(current)  # type: ignore[attr-defined]
        if "provider_authority" not in current.signals:
            current.signals.update(extract_provider_authority(current))
        enriched.append(current)
    return enriched


def build_seed_candidates_artifact(scope: ResearchScope, candidates: list[CandidateSource], *, policy: dict[str, Any] | None = None, demo_fast: bool) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        signals = candidate_signals(candidate)
        candidate.signals.update(signals)
        score_breakdown = seed_candidate_score_breakdown(candidate, signals, policy=policy)
        items.append(
            {
                "source_id": candidate.source_id,
                "title": candidate.title,
                "year": candidate.year,
                "provider": candidate.provider,
                "source_type": candidate.source_type,
                "url": candidate.url,
                "doi": candidate.doi,
                "arxiv_id": candidate.arxiv_id,
                "citation_count": candidate.citation_count,
                "signals": signals,
                "score_breakdown": score_breakdown,
                "objective_score": score_breakdown["objective_score"],
                "ranking_score": score_breakdown["ranking_score"],
                "venue_weight": score_breakdown["venue_weight"],
                "author_weight": score_breakdown["author_weight"],
                "provenance": candidate.provenance,
            }
        )
    items.sort(
        key=lambda item: (
            -float(item.get("ranking_score") or item["objective_score"]),
            -float(item["objective_score"]),
            -(int(item["year"] or 0)),
            str(item["title"]).lower(),
        )
    )
    return {
        "topic": scope.topic,
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "seed_candidates",
        "count": len(items),
        "items": items,
        "generated_at": utc_timestamp(),
    }


def apply_seed_selection(
    seed_candidates: dict[str, Any],
    candidates: list[CandidateSource],
    *,
    selection: dict[str, Any] | None,
    policy: dict[str, Any] | None,
    demo_fast: bool,
) -> tuple[list[CandidateSource], dict[str, Any], DiagnosticReport]:
    by_id = {candidate.source_id: candidate for candidate in candidates}
    selected_ids: list[str] = []
    created_by = ""
    policy_applied = False
    if selection:
        created_by = str(selection.get("created_by") or "")
        selected_ids = normalize_selected_seed_ids(selection)
    elif policy:
        selected_ids = select_seed_ids_by_policy(seed_candidates, policy)
        created_by = str(policy.get("created_by") or "openclaw_policy")
        policy_applied = True
    elif demo_fast:
        selected_ids = [str(item["source_id"]) for item in seed_candidates.get("items", [])[:2]]
        created_by = "demo_fast"
        policy_applied = True

    selected_sources = [by_id[source_id] for source_id in selected_ids if source_id in by_id]
    artifact = {
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "seed_selection",
        "created_by": created_by,
        "policy_applied": policy_applied,
        "count": len(selected_sources),
        "selected_source_ids": [source.source_id for source in selected_sources],
        "items": [asdict(source) for source in selected_sources],
        "generated_at": utc_timestamp(),
    }
    issues: list[DiagnosticIssue] = []
    if not selected_sources:
        issues.append(
            DiagnosticIssue(
                type="seed_selection_required",
                severity="high" if not demo_fast else "medium",
                message="Citation expansion requires OpenClaw-approved seed papers.",
                repair_options=["provide_seed_selection"],
                blocking=not demo_fast,
            )
        )
    unknown_ids = [source_id for source_id in selected_ids if source_id not in by_id]
    if unknown_ids:
        issues.append(
            DiagnosticIssue(
                type="seed_selection_unknown_ids",
                severity="medium",
                message="Seed selection referenced source IDs not present in seed candidates.",
                repair_options=["provide_seed_selection"],
                missing=unknown_ids,
            )
        )
    if selected_sources:
        validation = validate_seed_papers(
            ResearchScope(
                topic=str(seed_candidates.get("topic") or ""),
                research_question="",
                time_range="",
                focus_dimensions=[],
                inclusion_criteria=[],
                exclusion_criteria=[],
                demo_fast=demo_fast,
            ),
            selected_sources,
        )
        for issue in validation.issues:
            if issue.type == "too_few_seed_papers" and (selection or policy):
                issue.severity = "medium"
                issue.blocking = False
                issue.message += " OpenClaw policy/selection may explicitly accept a smaller seed set."
            issues.append(issue)
    report = DiagnosticReport(
        status="blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok",
        issues=issues,
        stage="seed_selection",
        metrics={"candidate_count": int(seed_candidates.get("count") or 0), "selected_count": len(selected_sources)},
        requires_openclaw_decision=bool(issues) and not demo_fast,
    )
    return selected_sources, artifact, report


def normalize_selected_seed_ids(selection: dict[str, Any]) -> list[str]:
    raw = selection.get("selected_source_ids") or selection.get("approved_source_ids") or selection.get("seed_source_ids")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    items = selection.get("items")
    if isinstance(items, list):
        selected: list[str] = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("source_id") or item.get("paper_id") or item.get("id")
                if value:
                    selected.append(str(value))
        return selected
    return []


def select_seed_ids_by_policy(seed_candidates: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    max_seeds = int(policy.get("max_seeds") or policy.get("limit") or 8)
    min_score = float(policy.get("min_objective_score") or 0)
    required_signals = [str(signal) for signal in policy.get("required_signals", [])]
    selected: list[str] = []
    for item in seed_candidates.get("items", []):
        if not isinstance(item, dict):
            continue
        signals = item.get("signals", {})
        if not isinstance(signals, dict):
            signals = {}
        if float(item.get("objective_score") or 0) < min_score:
            continue
        if required_signals and not any(signals.get(signal) for signal in required_signals):
            continue
        selected.append(str(item.get("source_id") or ""))
        if len(selected) >= max(1, max_seeds):
            break
    return [source_id for source_id in selected if source_id]


def candidate_signals(source: CandidateSource) -> dict[str, bool]:
    text = f"{source.title} {source.abstract} {source.venue} {source.url}".lower()
    return {
        "survey_or_review": "survey" in text or "review" in text,
        "benchmark_or_dataset": "benchmark" in text or "dataset" in text or "corpus" in text,
        "system_or_framework": "system" in text or "framework" in text or "platform" in text,
        "method_paper": "method" in text or "approach" in text or source.source_type == "paper",
        "recent_work": bool(source.year and source.year >= 2021),
        "classic_high_citation": source.citation_count >= 100,
        "open_fulltext_available": bool(source.pdf or source.content_text or source.url),
        "weak_metadata": not bool(source.year and source.authors and source.venue),
        "low_relevance": False,
    }


def seed_candidate_score(signals: dict[str, bool]) -> float:
    return seed_candidate_score_breakdown(None, signals, policy=None)["objective_score"]


def seed_candidate_score_breakdown(source: CandidateSource | None, signals: dict[str, bool], *, policy: dict[str, Any] | None) -> dict[str, float]:
    weights = {
        "survey_or_review": 0.18,
        "benchmark_or_dataset": 0.14,
        "system_or_framework": 0.1,
        "method_paper": 0.12,
        "recent_work": 0.12,
        "classic_high_citation": 0.12,
        "open_fulltext_available": 0.12,
        "weak_metadata": -0.12,
        "low_relevance": -0.2,
    }
    policy = policy or {}
    signal_weights = policy.get("signal_weights")
    if isinstance(signal_weights, dict):
        for key, value in signal_weights.items():
            try:
                weights[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    base_signal_score = 0.35 + sum(weight for signal, weight in weights.items() if signals.get(signal))
    venue_weight = venue_weight_for_source(source, policy=policy) if source else 0.0
    author_weight = author_weight_for_source(source, policy=policy) if source else 0.0
    citation_weight = min(0.18, ((source.citation_count if source else 0) / 500) * 0.18)
    recency_weight = 0.08 if source and source.year and source.year >= 2021 else 0.03 if source and source.year else 0.0
    fulltext_weight = 0.08 if source and (source.content_text or source.pdf or source.url) else 0.0
    metadata_penalty = -0.08 if signals.get("weak_metadata") else 0.0
    ranking_score = max(
        0.0,
        base_signal_score
        + venue_weight
        + author_weight
        + citation_weight
        + recency_weight
        + fulltext_weight
        + metadata_penalty,
    )
    objective = min(1.0, ranking_score)
    return {
        "base_signal_score": round(max(0.0, min(1.0, base_signal_score)), 3),
        "venue_weight": round(venue_weight, 3),
        "author_weight": round(author_weight, 3),
        "citation_weight": round(citation_weight, 3),
        "recency_weight": round(recency_weight, 3),
        "fulltext_weight": round(fulltext_weight, 3),
        "metadata_penalty": round(metadata_penalty, 3),
        "ranking_score": round(ranking_score, 3),
        "objective_score": round(objective, 3),
    }


def venue_weight_for_source(source: CandidateSource | None, *, policy: dict[str, Any]) -> float:
    if source is None:
        return 0.0
    venue = normalize_weight_key(source.venue)
    configured = lookup_weight(policy.get("venue_weights"), venue)
    if configured is not None:
        return clamp_weight(configured)
    preferred = [normalize_weight_key(item) for item in policy.get("preferred_venues", [])] if isinstance(policy.get("preferred_venues"), list) else []
    if venue and any(item and item in venue for item in preferred):
        return 0.15
    provider_score = parse_float(source.signals.get("venue_authority"), default=0.0)
    return round(min(0.16, provider_score * 0.16), 3)


def author_weight_for_source(source: CandidateSource | None, *, policy: dict[str, Any]) -> float:
    if source is None:
        return 0.0
    configured = 0.0
    for author in source.authors:
        weight = lookup_weight(policy.get("author_weights"), normalize_weight_key(author))
        if weight is not None:
            configured = max(configured, clamp_weight(weight))
    preferred = [normalize_weight_key(item) for item in policy.get("preferred_authors", [])] if isinstance(policy.get("preferred_authors"), list) else []
    if preferred:
        configured = max(configured, 0.12 if any(normalize_weight_key(author) in preferred for author in source.authors) else 0.0)
    provider_score = parse_float(source.signals.get("author_authority"), default=0.0)
    return round(max(configured, min(0.18, provider_score * 0.18)), 3)


def lookup_weight(mapping: Any, key: str) -> float | None:
    if not isinstance(mapping, dict) or not key:
        return None
    normalized = {normalize_weight_key(str(map_key)): value for map_key, value in mapping.items()}
    for candidate_key, value in normalized.items():
        if candidate_key == key or (candidate_key and candidate_key in key):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def normalize_weight_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def clamp_weight(value: float) -> float:
    return round(max(-0.25, min(0.25, value)), 3)


def repair_seed_papers(
    scope: ResearchScope,
    seed_papers: list[CandidateSource],
    *,
    providers: list[LiteratureProvider],
    max_results: int = 20,
) -> list[CandidateSource]:
    if not all(getattr(provider, "name", "") == "demo" for provider in providers):
        raise LiteratureResearchError(
            "Real-mode seed repair requires an OpenClaw-authored repair_plan.json. "
            "Use `repair validate` and `repair execute`; fixed worker-generated repair queries are out of scope."
        )
    repaired = list(seed_papers)
    repair_queries = [f"{scope.topic} systematic survey", f"{scope.topic} benchmark dataset evaluation"]
    for query in repair_queries:
        for provider in providers:
            provider_sources, _event = provider.search(query, limit=max(1, min(20, max_results)))
            repaired.extend(provider_sources)
    return deduplicate_sources(repaired)[:max_results]


def deduplicate_sources(sources: Iterable[CandidateSource]) -> list[CandidateSource]:
    unique, _trace = deduplicate_sources_with_trace(sources)
    return unique


def deduplicate_sources_with_trace(sources: Iterable[CandidateSource]) -> tuple[list[CandidateSource], dict[str, Any]]:
    source_list = list(sources)
    unique: list[CandidateSource] = []
    by_key: dict[str, int] = {}
    merges: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for source in source_list:
        key = dedupe_key(source)
        if not key:
            skipped.append({"source_id": source.source_id, "title": source.title, "reason": "missing_identity"})
            continue
        if key in by_key:
            index = by_key[key]
            original = unique[index]
            merged = merge_duplicate_source(original, source)
            unique[index] = merged
            merges.append(
                {
                    "identity_key": key,
                    "kept_source_id": merged.source_id,
                    "merged_source_id": source.source_id,
                    "providers": sorted({provider for provider in [original.provider, source.provider] if provider}),
                    "reason": "exact_identity_match",
                    "confidence": 1.0,
                }
            )
            continue
        fuzzy_index, fuzzy_reason, fuzzy_confidence = find_fuzzy_duplicate(source, unique)
        if fuzzy_index is not None and fuzzy_confidence >= 0.92:
            original = unique[fuzzy_index]
            merged = merge_duplicate_source(original, source)
            unique[fuzzy_index] = merged
            merges.append(
                {
                    "identity_key": key,
                    "kept_source_id": merged.source_id,
                    "merged_source_id": source.source_id,
                    "providers": sorted({provider for provider in [original.provider, source.provider] if provider}),
                    "reason": fuzzy_reason,
                    "confidence": fuzzy_confidence,
                }
            )
            continue
        if fuzzy_index is not None:
            original = unique[fuzzy_index]
            ambiguous.append(
                {
                    "source_id": source.source_id,
                    "possible_duplicate_source_id": original.source_id,
                    "reason": fuzzy_reason,
                    "confidence": fuzzy_confidence,
                    "requires_openclaw_decision": True,
                }
            )
        by_key[key] = len(unique)
        unique.append(source)
    return unique, {
        "demo_fast": all(source.provider == "demo" for source in unique) if unique else False,
        "quality_level": "schema_smoke_only" if all(source.provider == "demo" for source in unique) and unique else "artifact_trace",
        "input_count": len(source_list),
        "output_count": len(unique),
        "merges": merges,
        "ambiguous": ambiguous,
        "skipped": skipped,
        "generated_at": utc_timestamp(),
    }


def dedupe_key(source: CandidateSource) -> str:
    if source.doi:
        return f"doi:{normalize_doi(source.doi)}"
    if source.arxiv_id:
        return f"arxiv:{source.arxiv_id.strip().lower()}"
    if source.provider == "aminer" and source.source_id:
        return f"aminer:{source.source_id.strip().lower()}"
    if source.url and source.source_type not in {"web", "official_doc", "github_project"}:
        return f"url:{canonicalize_url(source.url)}"
    if source.title and source.year:
        return f"title-year:{normalize_title(source.title)}:{source.year}"
    if source.title and source.authors:
        return f"title-authors:{normalize_title(source.title)}:{','.join(normalize_author(author) for author in source.authors[:3])}"
    return normalize_title(source.title)


def find_fuzzy_duplicate(source: CandidateSource, existing: list[CandidateSource]) -> tuple[int | None, str, float]:
    source_title = normalize_title(source.title)
    if not source_title:
        return None, "", 0.0
    source_authors = {normalize_author(author) for author in source.authors if normalize_author(author)}
    for index, candidate in enumerate(existing):
        candidate_title = normalize_title(candidate.title)
        if not candidate_title:
            continue
        title_similarity = token_jaccard(source_title, candidate_title)
        year_close = bool(source.year and candidate.year and abs(source.year - candidate.year) <= 1)
        candidate_authors = {normalize_author(author) for author in candidate.authors if normalize_author(author)}
        author_overlap = bool(source_authors and candidate_authors and source_authors.intersection(candidate_authors))
        if title_similarity >= 0.97 and (year_close or author_overlap):
            return index, "normalized_title_with_year_or_author_overlap", round(title_similarity, 3)
        if title_similarity >= 0.86 and (year_close or author_overlap):
            return index, "ambiguous_fuzzy_title_match", round(title_similarity, 3)
    return None, "", 0.0


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def normalize_author(author: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", author.lower()).strip()


def normalize_doi(doi: str) -> str:
    return doi.strip().lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def canonicalize_url(url: str) -> str:
    return url.strip().lower().split("#", 1)[0].rstrip("/")


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def build_matrix_row(
    source: CandidateSource,
    *,
    topic: str,
    extraction: PaperExtraction | None = None,
    demo_fast: bool = False,
) -> LiteratureMatrixRow:
    score_breakdown = build_score_breakdown(source, topic=topic, extraction=extraction)
    relevance = score_breakdown["topic_relevance"]
    credibility = score_breakdown["overall_score"]
    extraction = extraction or PaperExtraction(
        source_id=source.source_id,
        missing_evidence=["extraction_not_run"],
        extraction_status="failed",
        extraction_basis=extraction_basis_for_source(source),
        extraction_method="none",
    )
    return LiteratureMatrixRow(
        paper_id=source.source_id,
        title=source.title,
        year=source.year,
        authors=", ".join(source.authors),
        venue=source.venue,
        source_channel=source.provider,
        source_type=source.source_type or infer_source_type(source),
        url=source.url,
        doi=source.doi,
        arxiv_id=source.arxiv_id,
        task=extraction.task,
        method=extraction.method,
        dataset=extraction.dataset,
        core_contribution=extraction.core_contribution,
        limitations=extraction.limitations,
        citation_value=infer_citation_value(source),
        suggested_section=extraction.suggested_section,
        relevance_score=relevance,
        credibility_score=credibility,
        read_priority=read_priority(relevance, credibility),
        notes="LLM extraction required for real mode; verify low-confidence rows." if not demo_fast else "Demo smoke extraction; not real research evidence.",
        evidence_snippets=extraction.evidence_snippets,
        confidence=extraction.confidence,
        missing_evidence=extraction.missing_evidence,
        extraction_status=extraction.extraction_status,
        extraction_basis=extraction.extraction_basis,
        extraction_method=extraction.extraction_method,
        demo_fast=demo_fast,
        quality_level="schema_smoke_only" if demo_fast else "evidence_matrix",
        score_breakdown=score_breakdown,
        priority_reason=priority_reason(score_breakdown),
        provenance=source.provenance,
    )


def validate_literature_matrix(matrix: list[LiteratureMatrixRow]) -> DiagnosticReport:
    issues: list[DiagnosticIssue] = []
    if not matrix:
        issues.append(
            DiagnosticIssue(
                type="missing_source_type",
                severity="high",
                message="The literature matrix has no sources.",
                repair_options=["provide_repair_plan"],
                missing=["paper", "web"],
            )
        )
        return DiagnosticReport(status="blocked", issues=issues, stage="matrix_validate", requires_openclaw_decision=True)
    source_types = {row.source_type for row in matrix}
    missing: list[str] = []
    if "paper" not in source_types:
        missing.append("paper")
    if missing:
        issues.append(
            DiagnosticIssue(
                type="missing_source_type",
                severity="medium",
                message="The matrix lacks one or more expected source types.",
                repair_options=["provide_repair_plan"],
                missing=missing,
            )
        )
    weak_metadata = sum(1 for row in matrix if not row.year or not row.authors or not row.venue)
    if weak_metadata:
        issues.append(
            DiagnosticIssue(
                type="weak_metadata",
                severity="medium",
                message=f"{weak_metadata} matrix row(s) lack year, authors, or venue metadata.",
                repair_options=["provide_repair_plan"],
            )
        )
    recent_count = sum(1 for row in matrix if row.year and row.year >= 2021)
    if recent_count == 0:
        issues.append(
            DiagnosticIssue(
                type="too_few_recent_sources",
                severity="medium",
                message="No recent sources were identified in the matrix.",
                repair_options=["provide_repair_plan"],
            )
        )
    failed_extractions = sum(1 for row in matrix if row.extraction_status == "failed")
    if failed_extractions:
        issues.append(
            DiagnosticIssue(
                type="llm_extraction_failures",
                severity="medium",
                message=f"{failed_extractions} matrix row(s) failed LLM extraction.",
                repair_options=["provide_repair_plan"],
                metric="failed_extractions",
                threshold="0",
            )
        )
    status = "blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok"
    return DiagnosticReport(
        status=status,
        issues=issues,
        stage="matrix_validate",
        metrics={"row_count": len(matrix), "failed_extractions": failed_extractions},
        requires_openclaw_decision=bool(issues),
    )


def repair_literature_matrix(
    *,
    topic: str,
    matrix: list[LiteratureMatrixRow],
    providers: list[LiteratureProvider],
    max_results: int = 40,
) -> list[LiteratureMatrixRow]:
    demo_fast = all(getattr(provider, "name", "") == "demo" for provider in providers)
    if not demo_fast:
        raise LiteratureResearchError(
            "Real-mode matrix repair requires an OpenClaw-authored repair_plan.json. "
            "Use `repair validate` and `repair execute`; worker-generated repair queries are out of scope."
        )
    existing = [
        CandidateSource(
            source_id=row.paper_id,
            title=row.title,
            authors=[author.strip() for author in row.authors.split(",") if author.strip()],
            year=row.year,
            venue=row.venue,
            url=row.url,
            doi=row.doi,
            arxiv_id=row.arxiv_id,
            provider=row.source_channel,
            source_type=row.source_type,
        )
        for row in matrix
    ]
    scope = build_research_scope(topic)
    repaired_sources = repair_seed_papers(scope, existing, providers=providers, max_results=max_results)
    rows: list[LiteratureMatrixRow] = []
    for source in repaired_sources[:max_results]:
        extraction, _trace = demo_extraction(source, topic=topic)
        rows.append(build_matrix_row(source, topic=topic, extraction=extraction, demo_fast=True))
    return rows


def score_relevance(source: CandidateSource, *, topic: str) -> float:
    topic_tokens = {token for token in re.findall(r"[a-z0-9]+", topic.lower()) if len(token) > 2}
    haystack = f"{source.title} {source.abstract}".lower()
    if not topic_tokens:
        return 0.5
    matched = sum(1 for token in topic_tokens if token in haystack)
    return round(min(1.0, 0.35 + 0.65 * matched / len(topic_tokens)), 3)


def score_credibility(source: CandidateSource) -> float:
    score = 0.35
    if source.year:
        score += 0.1
    if source.authors:
        score += 0.1
    if source.venue:
        score += 0.1
    if source.doi or source.arxiv_id or "arxiv.org" in source.url.lower():
        score += 0.15
    if source.citation_count > 0:
        score += min(0.2, source.citation_count / 500)
    if source.pdf:
        score += 0.05
    return round(min(1.0, score), 3)


def build_score_breakdown(source: CandidateSource, *, topic: str, extraction: PaperExtraction | None) -> dict[str, float]:
    topic_relevance = score_relevance(source, topic=topic)
    metadata_quality = score_metadata_quality(source)
    venue_signal = 0.8 if source.venue and source.source_type == "paper" else 0.45 if source.venue else 0.2
    citation_signal = min(1.0, source.citation_count / 500) if source.citation_count else 0.0
    fulltext_signal = 1.0 if source.content_text else 0.65 if source.pdf else 0.35 if source.abstract else 0.15
    extraction_confidence = extraction.confidence if extraction else 0.0
    providers = {provider for provider in source.provider.split("+") if provider}
    provider_agreement = 1.0 if len(providers) > 1 else 0.55 if providers else 0.0
    recency_signal = 0.9 if source.year and source.year >= 2021 else 0.6 if source.year and source.year >= 2015 else 0.35 if source.year else 0.1
    source_type_signal = {
        "paper": 0.85,
        "pdf": 0.75,
        "technical_report": 0.7,
        "official_doc": 0.65,
        "github_project": 0.55,
        "web": 0.4,
    }.get(source.source_type, 0.35)
    facet_relevance = 0.8 if any(candidate_signals(source).values()) else 0.35
    overall = (
        topic_relevance * 0.22
        + facet_relevance * 0.1
        + metadata_quality * 0.1
        + venue_signal * 0.08
        + citation_signal * 0.08
        + fulltext_signal * 0.12
        + extraction_confidence * 0.16
        + provider_agreement * 0.05
        + recency_signal * 0.05
        + source_type_signal * 0.04
    )
    return {
        "topic_relevance": round(topic_relevance, 3),
        "facet_relevance": round(facet_relevance, 3),
        "metadata_quality": round(metadata_quality, 3),
        "venue_signal": round(venue_signal, 3),
        "citation_signal": round(citation_signal, 3),
        "fulltext_signal": round(fulltext_signal, 3),
        "extraction_confidence": round(extraction_confidence, 3),
        "provider_agreement": round(provider_agreement, 3),
        "recency_signal": round(recency_signal, 3),
        "source_type_signal": round(source_type_signal, 3),
        "overall_score": round(min(1.0, overall), 3),
    }


def score_metadata_quality(source: CandidateSource) -> float:
    checks = [bool(source.title), bool(source.year), bool(source.authors), bool(source.venue), bool(source.doi or source.arxiv_id or source.url)]
    return sum(1 for check in checks if check) / len(checks)


def priority_reason(score_breakdown: dict[str, float]) -> str:
    strongest = sorted(score_breakdown.items(), key=lambda item: item[1], reverse=True)[:3]
    return ", ".join(f"{name}={value:.2f}" for name, value in strongest)


def read_priority(relevance: float, credibility: float) -> str:
    combined = relevance * 0.6 + credibility * 0.4
    if combined >= 0.78:
        return "high"
    if combined >= 0.58:
        return "medium"
    return "low"


def infer_citation_value(source: CandidateSource) -> str:
    text = f"{source.title} {source.abstract}".lower()
    if "benchmark" in text or "dataset" in text:
        return "Benchmark or dataset evidence candidate."
    if "survey" in text or "review" in text:
        return "Seed survey/background map candidate."
    if "framework" in text or "system" in text:
        return "System/framework evidence candidate."
    if source.citation_count >= 100:
        return "Highly cited background or representative source candidate."
    return "Candidate evidence; requires screening."


def suggest_section(source: CandidateSource) -> str:
    text = f"{source.title} {source.abstract}".lower()
    if "benchmark" in text or "evaluation" in text or "dataset" in text:
        return "Evaluation / Benchmarks"
    if "survey" in text or "review" in text:
        return "Background"
    if "application" in text or "case study" in text:
        return "Applications"
    if "limitation" in text or "risk" in text or "challenge" in text:
        return "Limitations / Open Problems"
    return "Core Methods"


def ensure_real_mode_llm_config() -> None:
    missing = [
        name
        for name in ("LITERATURE_LLM_BASE_URL", "LITERATURE_LLM_API_KEY", "LITERATURE_LLM_MODEL")
        if not clean_env(name)
    ]
    if missing:
        raise LiteratureResearchError(
            "Missing LLM environment variable(s): "
            + ", ".join(missing)
            + ". Real mode is LLM-only for extraction and cannot fall back to rule extraction."
        )


def extract_matrix_fields(
    sources: list[CandidateSource],
    *,
    topic: str,
    demo_fast: bool,
    output_dir: Path | None = None,
    checkpoint_every: int = 1,
) -> tuple[dict[str, PaperExtraction], dict[str, Any], list[dict[str, Any]]]:
    trace_events: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    extractions: dict[str, PaperExtraction] = {}
    extractor = None if demo_fast else LLMExtractor()
    emit_progress("llm.extract", "extraction planner ready", source_count=len(sources), demo_fast=demo_fast)
    for index, source in enumerate(sources, start=1):
        emit_progress(
            "llm.extract",
            "extracting source",
            index=index,
            total=len(sources),
            source_id=source.source_id,
            title=source.title[:120],
            demo_fast=demo_fast,
        )
        if demo_fast:
            extraction, trace = demo_extraction(source, topic=topic)
        else:
            assert extractor is not None
            extraction, trace = extractor.extract(source, topic=topic)
        extractions[source.source_id] = extraction
        trace_events.append(trace)
        emit_progress(
            "llm.extract",
            "source extraction finished",
            index=index,
            total=len(sources),
            source_id=source.source_id,
            status=extraction.extraction_status,
            confidence=extraction.confidence,
        )
        if extraction.extraction_status == "failed":
            failures.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "missing_evidence": extraction.missing_evidence,
                    "extraction_basis": extraction.extraction_basis,
                    "error": trace.get("error", ""),
                }
            )
        if output_dir is not None and checkpoint_every > 0 and (index % checkpoint_every == 0 or index == len(sources)):
            checkpoint_trace = {
                "demo_fast": demo_fast,
                "quality_level": "schema_smoke_only" if demo_fast else "llm_extraction_partial",
                "events": trace_events,
                "generated_at": utc_timestamp(),
            }
            checkpoint_paths = write_extraction_checkpoint(
                output_dir,
                sources=sources,
                extractions=extractions,
                extraction_trace=checkpoint_trace,
                extraction_failures=failures,
                topic=topic,
                demo_fast=demo_fast,
            )
            emit_progress(
                "llm.extract",
                "partial extraction checkpoint written",
                index=index,
                total=len(sources),
                extraction_count=len(extractions),
                checkpoint=checkpoint_paths["partial_literature_matrix_json"],
            )
    emit_progress("llm.extract", "extraction planner completed", source_count=len(sources), failure_count=len(failures))
    return extractions, {
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "llm_extraction",
        "events": trace_events,
        "generated_at": utc_timestamp(),
    }, failures


def demo_extraction(source: CandidateSource, *, topic: str) -> tuple[PaperExtraction, dict[str, Any]]:
    evidence_text, basis = extraction_input_for_source(source)
    snippet = make_evidence_snippet(source, evidence_text[:320] or source.title, content_type=basis)
    title = source.title or topic
    extraction = PaperExtraction(
        source_id=source.source_id,
        task=f"Screening task for {topic}",
        method="Deterministic demo extraction",
        dataset="Demo dataset signal" if "benchmark" in title.lower() else "",
        core_contribution=f"Demo smoke evidence for {title}",
        limitations="Demo artifact; not real evidence.",
        suggested_section="Background" if "survey" in title.lower() else "Methods",
        evidence_snippets=[snippet],
        confidence=0.5,
        missing_evidence=[],
        extraction_status="ok",
        extraction_basis=basis,
        extraction_method="demo_mock_llm",
        raw_response={"demo_fast": True},
    )
    trace = {
        "source_id": source.source_id,
        "title": source.title,
        "basis": basis,
        "status": "ok",
        "method": "demo_mock_llm",
        "demo_fast": True,
    }
    return extraction, trace


def build_extraction_prompt(source: CandidateSource, *, topic: str, evidence_text: str) -> str:
    return (
        "Topic:\n"
        f"{topic}\n\n"
        "Paper/source metadata:\n"
        + json.dumps(
            {
                "source_id": source.source_id,
                "title": source.title,
                "year": source.year,
                "authors": source.authors,
                "venue": source.venue,
                "url": source.url,
                "doi": source.doi,
                "arxiv_id": source.arxiv_id,
            },
            ensure_ascii=False,
        )
        + "\n\nEvidence:\n"
        + evidence_text[:12000]
        + "\n\nReturn JSON with exactly these keys: task, method, dataset, core_contribution, "
        "limitations, suggested_section, evidence_snippets, confidence, missing_evidence. "
        "Use empty strings or missing_evidence when evidence is insufficient. "
        "evidence_snippets must be an array of short objects with text and source_url."
    )


def extract_llm_message(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    if isinstance(payload.get("content"), str):
        return str(payload["content"])
    return json.dumps(payload, ensure_ascii=False)


def parse_llm_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM extraction response must be a JSON object.")
    return payload


def extraction_from_payload(source_id: str, payload: dict[str, Any], *, basis: str, method: str) -> PaperExtraction:
    missing_keys = sorted(REQUIRED_EXTRACTION_KEYS - set(payload))
    snippets = payload.get("evidence_snippets")
    if not isinstance(snippets, list):
        snippets = []
    missing = payload.get("missing_evidence")
    if not isinstance(missing, list):
        missing = []
    confidence = parse_float(payload.get("confidence"), default=0.0)
    status = "ok" if not missing_keys and (confidence > 0 or any(str(payload.get(key, "")).strip() for key in ("task", "method", "dataset", "core_contribution", "limitations"))) else "needs_review"
    if missing_keys:
        missing = [*missing, *[f"missing_key:{key}" for key in missing_keys]]
    return PaperExtraction(
        source_id=source_id,
        task=str(payload.get("task") or "").strip(),
        method=str(payload.get("method") or "").strip(),
        dataset=str(payload.get("dataset") or "").strip(),
        core_contribution=str(payload.get("core_contribution") or "").strip(),
        limitations=str(payload.get("limitations") or "").strip(),
        suggested_section=str(payload.get("suggested_section") or "").strip(),
        evidence_snippets=[snippet for snippet in snippets if isinstance(snippet, dict)],
        confidence=max(0.0, min(1.0, confidence)),
        missing_evidence=[str(item) for item in missing],
        extraction_status=status,
        extraction_basis=basis,
        extraction_method=method,
        raw_response=payload,
    )


def extraction_input_for_source(source: CandidateSource) -> tuple[str, str]:
    content = source.content_text.strip()
    if content:
        return content, extraction_basis_for_source(source)
    if source.abstract.strip():
        return source.abstract.strip(), "abstract" if source.provider == "aminer" else "snippet"
    metadata = " ".join(part for part in [source.title, source.venue, source.url] if part)
    return metadata, "metadata" if metadata.strip() else "none"


def extraction_basis_for_source(source: CandidateSource) -> str:
    content_type = source.content_type or classify_firecrawl_content(url=source.url, title=source.title, markdown=source.content_text)
    if content_type in {"pdf_markdown", "scraped_markdown", "official_doc_markdown", "github_project_markdown", "technical_report_markdown"}:
        return content_type
    if source.abstract.strip():
        return "abstract" if source.provider == "aminer" else "snippet"
    return "metadata"


def make_evidence_snippet(source: CandidateSource, text: str, *, content_type: str) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "content_id": content_id_for_source(source),
        "section": "",
        "heading": "",
        "text": text,
        "start_offset": None,
        "end_offset": None,
        "offsets_available": False,
        "source_url": source.url,
        "content_type": content_type,
    }


def fetch_fulltext_for_sources(
    sources: list[CandidateSource],
    *,
    providers: list[LiteratureProvider],
    demo_fast: bool,
    source_ids: list[str] | None = None,
    limit: int | None = None,
) -> tuple[list[CandidateSource], dict[str, Any]]:
    firecrawl_like = [provider for provider in providers if hasattr(provider, "scrape")]
    target_ids = set(source_ids or [])
    updated: list[CandidateSource] = []
    events: list[dict[str, Any]] = []
    processed = 0
    emit_progress(
        "fulltext.fetch",
        "fulltext planner ready",
        source_count=len(sources),
        provider_count=len(firecrawl_like),
        limit=limit,
        filtered_source_count=len(target_ids) if target_ids else 0,
    )
    for index, source in enumerate(sources, start=1):
        should_fetch = (not target_ids or source.source_id in target_ids) and should_fetch_fulltext(source)
        if limit is not None and processed >= limit:
            should_fetch = False
        if not should_fetch:
            emit_progress(
                "fulltext.fetch",
                "skipping source",
                index=index,
                total=len(sources),
                source_id=source.source_id,
                reason="not_required_or_limit_reached",
            )
            updated.append(source)
            continue
        if not firecrawl_like:
            events.append(
                {
                    "provider": "firecrawl",
                    "source_id": source.source_id,
                    "status": "skipped",
                    "failure_type": "provider_unavailable",
                    "url": source.pdf or source.url,
                }
            )
            updated.append(source)
            emit_progress(
                "fulltext.fetch",
                "skipping source no scrape provider",
                index=index,
                total=len(sources),
                source_id=source.source_id,
            )
            continue
        current = source
        for provider in firecrawl_like:
            emit_progress(
                "fulltext.fetch",
                "scraping source",
                index=index,
                total=len(sources),
                provider=getattr(provider, "name", ""),
                source_id=current.source_id,
                source_type=current.source_type,
            )
            scraped, event = provider.scrape(current)  # type: ignore[attr-defined]
            events.append(event)
            current = scraped
            emit_progress(
                "fulltext.fetch",
                "scrape provider returned",
                index=index,
                total=len(sources),
                provider=getattr(provider, "name", ""),
                source_id=current.source_id,
                status=event.get("status"),
                character_count=event.get("character_count"),
            )
            if scraped.content_text:
                break
        updated.append(current)
        processed += 1
    emit_progress("fulltext.fetch", "fulltext planner completed", processed=processed, event_count=len(events))
    return updated, {
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "fulltext_trace",
        "events": events,
        "generated_at": utc_timestamp(),
    }


def should_fetch_fulltext(source: CandidateSource) -> bool:
    if source.provider == "demo":
        return True
    if source.content_text:
        return False
    target_url = source.pdf or source.url
    if not target_url:
        return False
    if source.provider == "firecrawl":
        return True
    if source.pdf or source.arxiv_id or target_url.lower().endswith(".pdf"):
        return True
    if source.source_type in {"pdf", "technical_report", "official_doc", "github_project", "web"}:
        return True
    return False


def write_content_artifacts(output_dir: Path, sources: list[CandidateSource], *, demo_fast: bool) -> dict[str, Any]:
    content_dir = output_dir / "content"
    manifest_items: list[dict[str, Any]] = []
    for source in sources:
        content_type = source.content_type or classify_firecrawl_content(url=source.url, title=source.title, markdown=source.content_text)
        content_id = content_id_for_source(source)
        artifact_path = ""
        text = source.content_text.strip()
        if text:
            content_dir.mkdir(parents=True, exist_ok=True)
            artifact = content_dir / f"{content_id}.md"
            artifact.write_text(text, encoding="utf-8")
            artifact_path = str(artifact)
        manifest_items.append(
            {
                "source_id": source.source_id,
                "provider": source.provider,
                "url": source.url,
                "content_id": content_id,
                "content_type": content_type,
                "artifact_path": artifact_path,
                "status": "ok" if text else "metadata_only" if source.abstract or source.title else "empty",
                "basis": extraction_basis_for_source(source),
                "character_count": len(text),
                "demo_fast": demo_fast,
                "quality_level": "schema_smoke_only" if demo_fast else "content_manifest",
            }
        )
    return {
        "manifest": {
            "demo_fast": demo_fast,
            "quality_level": "schema_smoke_only" if demo_fast else "content_manifest",
            "items": manifest_items,
            "generated_at": utc_timestamp(),
        },
        "content_dir": str(content_dir),
    }


def build_fulltext_diagnostics(manifest: dict[str, Any], *, demo_fast: bool) -> DiagnosticReport:
    items = [item for item in manifest.get("items", []) if isinstance(item, dict)]
    metadata_only = [item for item in items if item.get("status") != "ok"]
    issues = []
    if metadata_only and not demo_fast:
        issues.append(
            DiagnosticIssue(
                type="fulltext_not_available",
                severity="medium",
                message=f"{len(metadata_only)} source(s) lack Firecrawl markdown/fulltext content.",
                repair_options=["provide_repair_plan"],
                affected_source_ids=[str(item.get("source_id")) for item in metadata_only],
            )
        )
    return DiagnosticReport(
        status="needs_review" if issues else "ok",
        issues=issues,
        stage="fulltext_fetch",
        metrics={"content_items": len(items), "metadata_only": len(metadata_only)},
        requires_openclaw_decision=bool(issues) and not demo_fast,
    )


def build_provider_status(providers: list[LiteratureProvider], *, trace: list[SearchTraceEvent], demo_fast: bool) -> dict[str, Any]:
    trace_by_provider: dict[str, list[SearchTraceEvent]] = {}
    for event in trace:
        trace_by_provider.setdefault(event.provider, []).append(event)
    statuses = {}
    for provider_name in sorted(SUPPORTED_PROVIDERS):
        events = trace_by_provider.get(provider_name, [])
        configured = any(getattr(provider, "name", "") == provider_name for provider in providers)
        statuses[provider_name] = {
            "configured": configured,
            "demo_fast": demo_fast,
            "capabilities": provider_capabilities(provider_name),
            "events": {
                "ok": sum(1 for event in events if event.status == "ok"),
                "error": sum(1 for event in events if event.status == "error"),
                "skipped": sum(1 for event in events if event.status == "skipped"),
            },
        }
    return {
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "provider_status",
        "providers": statuses,
        "generated_at": utc_timestamp(),
    }


def provider_capabilities(provider_name: str) -> dict[str, bool]:
    if provider_name == "aminer":
        return {
            "search": True,
            "detail": True,
            "references": True,
            "citations": False,
            "fulltext_links": True,
            "fulltext_content": False,
            "metadata_enrichment": True,
        }
    if provider_name == "firecrawl":
        return {
            "search": True,
            "detail": False,
            "references": False,
            "citations": False,
            "fulltext_links": True,
            "fulltext_content": True,
            "metadata_enrichment": False,
        }
    return {}


def collect_detail_trace(providers: list[LiteratureProvider]) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    relation_attempts: list[dict[str, Any]] = []
    authority_attempts: list[dict[str, Any]] = []
    for provider in providers:
        attempts.extend(getattr(provider, "detail_trace", []))
        relation_attempts.extend(getattr(provider, "relation_trace", []))
        authority_attempts.extend(getattr(provider, "authority_trace", []))
    return {
        "demo_fast": all(getattr(provider, "name", "") == "demo" for provider in providers),
        "quality_level": "detail_trace",
        "attempts": attempts,
        "relation_attempts": relation_attempts,
        "authority_attempts": authority_attempts,
        "generated_at": utc_timestamp(),
    }


def build_aminer_detail_diagnostics(detail_trace: dict[str, Any], *, demo_fast: bool) -> DiagnosticReport:
    attempts = [item for item in detail_trace.get("attempts", []) if isinstance(item, dict)]
    failed = [item for item in attempts if item.get("status") == "failed"]
    skipped = [item for item in attempts if item.get("status") == "skipped"]
    issues: list[DiagnosticIssue] = []
    if failed:
        issues.append(
            DiagnosticIssue(
                type="aminer_detail_failures",
                severity="medium",
                message=f"{len(failed)} AMiner detail enrichment call(s) failed.",
                repair_options=["provide_repair_plan", "accept_risk"],
                evidence=failed,
            )
        )
    return DiagnosticReport(
        status="needs_review" if issues else "ok",
        issues=issues,
        stage="aminer_detail",
        metrics={
            "total": len(attempts),
            "successful": sum(1 for item in attempts if item.get("status") == "ok"),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        requires_openclaw_decision=bool(issues) and not demo_fast,
    )


def build_gap_report(
    matrix: list[LiteratureMatrixRow],
    *,
    trace: list[SearchTraceEvent],
    extraction_failures: list[dict[str, Any]],
    demo_fast: bool,
) -> dict[str, Any]:
    provider_counts: dict[str, int] = {}
    source_type_counts: dict[str, int] = {}
    weak_metadata_ids: list[str] = []
    dataset_missing_ids: list[str] = []
    limitations_missing_ids: list[str] = []
    low_confidence_ids: list[str] = []
    for row in matrix:
        provider_counts[row.source_channel] = provider_counts.get(row.source_channel, 0) + 1
        source_type_counts[row.source_type] = source_type_counts.get(row.source_type, 0) + 1
        if not row.year or not row.authors or not row.venue:
            weak_metadata_ids.append(row.paper_id)
        if not row.dataset:
            dataset_missing_ids.append(row.paper_id)
        if not row.limitations:
            limitations_missing_ids.append(row.paper_id)
        if row.confidence < 0.45:
            low_confidence_ids.append(row.paper_id)
    gaps: list[dict[str, Any]] = []
    if extraction_failures:
        gaps.append(
            {
                "gap_id": "llm_extraction_failures",
                "type": "llm_extraction_failures",
                "count": len(extraction_failures),
                "affected_source_ids": [failure.get("source_id") for failure in extraction_failures],
                "candidate_actions": ["provide_repair_plan", "rerun_llm_extraction"],
            }
        )
    if not demo_fast and ("aminer" not in provider_counts or "firecrawl" not in provider_counts):
        gaps.append(
            {
                "gap_id": "provider_imbalance",
                "type": "provider_imbalance",
                "counts": provider_counts,
                "candidate_actions": ["provide_repair_plan", "rerun_provider_search", "accept_risk"],
            }
        )
    failed_searches = [asdict(event) for event in trace if event.status in {"error", "skipped"}]
    if failed_searches:
        gaps.append(
            {
                "gap_id": "provider_search_failures",
                "type": "provider_search_failures",
                "count": len(failed_searches),
                "evidence": failed_searches,
                "candidate_actions": ["rerun_provider_search", "accept_risk"],
            }
        )
    if weak_metadata_ids:
        gaps.append(
            {
                "gap_id": "metadata_completeness",
                "type": "metadata_completeness",
                "count": len(weak_metadata_ids),
                "affected_source_ids": weak_metadata_ids,
                "candidate_actions": ["enrich_metadata", "accept_risk"],
            }
        )
    if dataset_missing_ids:
        gaps.append(
            {
                "gap_id": "dataset_field_coverage",
                "type": "dataset_field_coverage",
                "count": len(dataset_missing_ids),
                "affected_source_ids": dataset_missing_ids,
                "candidate_actions": ["rerun_llm_extraction", "fetch_fulltext", "accept_risk"],
            }
        )
    if limitations_missing_ids:
        gaps.append(
            {
                "gap_id": "limitations_field_coverage",
                "type": "limitations_field_coverage",
                "count": len(limitations_missing_ids),
                "affected_source_ids": limitations_missing_ids,
                "candidate_actions": ["rerun_llm_extraction", "fetch_fulltext", "accept_risk"],
            }
        )
    if low_confidence_ids:
        gaps.append(
            {
                "gap_id": "low_extraction_confidence",
                "type": "llm_extraction_failures_or_low_confidence",
                "count": len(low_confidence_ids),
                "affected_source_ids": low_confidence_ids,
                "candidate_actions": ["fetch_fulltext", "rerun_llm_extraction", "accept_risk"],
            }
        )
    recent_count = sum(1 for row in matrix if row.year and row.year >= 2021)
    if matrix and recent_count == 0:
        gaps.append(
            {
                "gap_id": "recent_coverage",
                "type": "recent_foundational_coverage",
                "count": 0,
                "candidate_actions": ["provide_repair_plan", "accept_risk"],
            }
        )
    return {
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "matrix_gap_facts",
        "generated_at": utc_timestamp(),
        "metrics": {
            "row_count": len(matrix),
            "provider_counts": provider_counts,
            "source_type_counts": source_type_counts,
            "failed_extractions": len(extraction_failures),
            "weak_metadata": len(weak_metadata_ids),
            "dataset_missing": len(dataset_missing_ids),
            "limitations_missing": len(limitations_missing_ids),
            "low_confidence": len(low_confidence_ids),
            "recent_count": recent_count if matrix else 0,
        },
        "gaps": gaps,
    }


def build_citation_artifacts(
    seed_papers: list[CandidateSource],
    *,
    providers: list[LiteratureProvider] | None = None,
    demo_fast: bool,
    depth: int = 1,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    trace_events: list[dict[str, Any]] = []
    issues: list[DiagnosticIssue] = []
    providers = providers or []
    aminer = next((provider for provider in providers if hasattr(provider, "fetch_references")), None)
    emit_progress(
        "citation.expand",
        "citation planner ready",
        seed_count=len(seed_papers),
        provider_count=len(providers),
        depth=depth,
    )
    if not seed_papers:
        issues.append(
            DiagnosticIssue(
                type="missing_approved_seed_selection",
                severity="high",
                message="Citation expansion is blocked until OpenClaw provides approved seed papers.",
                repair_options=["provide_seed_selection"],
                blocking=True,
            )
        )
    if depth > 1:
        issues.append(
            DiagnosticIssue(
                type="citation_depth_limited",
                severity="medium",
                message="Citation expansion depth greater than 1 is not executed in this worker version.",
                repair_options=["accept_risk"],
                metric="citation_depth",
                threshold="1",
            )
        )
    for seed_index, seed in enumerate(seed_papers, start=1):
        emit_progress(
            "citation.expand",
            "processing seed",
            index=seed_index,
            total=len(seed_papers),
            source_id=seed.source_id,
            provider=seed.provider,
            title=seed.title[:120],
        )
        nodes.append(
            {
                "source_id": seed.source_id,
                "title": seed.title,
                "doi": seed.doi,
                "arxiv_id": seed.arxiv_id,
                "aminer_id": seed.source_id if seed.provider == "aminer" else "",
                "provider": seed.provider,
                "role": "seed",
            }
        )
        references: list[CandidateSource] = []
        if aminer is not None and seed.provider in {"aminer", "demo"}:
            references, trace_event = aminer.fetch_references(seed, limit=50) if hasattr(aminer, "fetch_references") else ([], {})  # type: ignore[attr-defined]
            trace_events.append(trace_event)
        else:
            references = [candidate_from_reference_payload(item, seed=seed) for item in extract_reference_candidates(seed)]
        if demo_fast and not references:
            references = [CandidateSource(source_id=f"{seed.source_id}-reference", title=f"Demo backward reference for {seed.title}", provider="demo", source_type="paper", raw={"demo_fast": True})]
            trace_events.append({"seed_source_id": seed.source_id, "provider": "demo", "status": "ok", "reference_count": len(references)})
        if not references and seed.provider == "aminer":
            issues.append(
                DiagnosticIssue(
                    type="empty_aminer_references",
                    severity="medium",
                    message="AMiner returned no backward references for a seed paper.",
                    repair_options=["accept_risk"],
                    affected_source_ids=[seed.source_id],
                )
            )
        emit_progress(
            "citation.expand",
            "seed references ready",
            index=seed_index,
            total=len(seed_papers),
            source_id=seed.source_id,
            reference_count=len(references),
        )
        for reference in references:
            ref_id = reference.source_id
            if not ref_id:
                continue
            node = {
                "source_id": ref_id,
                "title": reference.title,
                "doi": reference.doi,
                "arxiv_id": reference.arxiv_id,
                "aminer_id": reference.source_id if reference.provider == "aminer" else "",
                "provider": reference.provider or seed.provider,
                "role": "backward_reference",
            }
            nodes.append(node)
            edge = {
                "from_source_id": seed.source_id,
                "to_source_id": ref_id,
                "edge_type": "references",
                "provider": seed.provider,
                "provenance": reference.provenance,
            }
            edges.append(edge)
            candidates.append({**node, "introduced_by_edge": edge})
    emit_progress(
        "citation.expand",
        "citation planner completed",
        seed_count=len(seed_papers),
        node_count=len(nodes),
        edge_count=len(edges),
        issue_count=len(issues),
    )
    diagnostics = DiagnosticReport(
        status="blocked" if issues else "ok",
        issues=issues,
        stage="citation_expand",
        metrics={"seed_count": len(seed_papers), "node_count": len(nodes), "edge_count": len(edges)},
        requires_openclaw_decision=bool(issues) and not demo_fast,
    )
    return {
        "graph": {
            "demo_fast": demo_fast,
            "quality_level": "schema_smoke_only" if demo_fast else "citation_graph",
            "nodes": nodes,
            "edges": edges,
            "generated_at": utc_timestamp(),
        },
        "trace": {
            "demo_fast": demo_fast,
            "quality_level": "schema_smoke_only" if demo_fast else "citation_expansion_trace",
            "events": trace_events,
            "generated_at": utc_timestamp(),
        },
        "diagnostics": diagnostics,
        "candidates": {
            "demo_fast": demo_fast,
            "quality_level": "schema_smoke_only" if demo_fast else "citation_candidates",
            "count": len(candidates),
            "items": candidates,
            "generated_at": utc_timestamp(),
        },
    }


def extract_reference_candidates(seed: CandidateSource) -> list[dict[str, Any]]:
    raw_references: Any = None
    for key in ("references", "refs", "reference_papers", "ref_papers"):
        value = seed.raw.get(key)
        if isinstance(value, list):
            raw_references = value
            break
    if not isinstance(raw_references, list):
        return []
    references: list[dict[str, Any]] = []
    for item in raw_references:
        if not isinstance(item, dict):
            continue
        normalized = normalize_aminer_item(item)
        references.append(
            {
                "source_id": normalized.source_id,
                "title": normalized.title,
                "doi": normalized.doi,
                "arxiv_id": normalized.arxiv_id,
                "aminer_id": normalized.source_id,
                "provider": "aminer",
                "provenance": {"source": "aminer_detail_references"},
            }
        )
    return references


def candidate_from_reference_payload(item: dict[str, Any], *, seed: CandidateSource) -> CandidateSource:
    normalized = normalize_aminer_item(item)
    if not normalized.source_id and item.get("source_id"):
        normalized.source_id = str(item.get("source_id") or "")
    if not normalized.title and item.get("title"):
        normalized.title = str(item.get("title") or "")
    normalized.provider = normalized.provider or str(item.get("provider") or "aminer")
    normalized.provenance.append(
        {
            "introduced_by": "citation_expansion",
            "seed_source_id": seed.source_id,
            "edge_type": "references",
            "provider": seed.provider or normalized.provider,
        }
    )
    return normalized


def build_dedupe_diagnostics(dedupe_trace: dict[str, Any], *, demo_fast: bool) -> DiagnosticReport:
    skipped = dedupe_trace.get("skipped", [])
    ambiguous = dedupe_trace.get("ambiguous", [])
    issues = []
    if skipped:
        issues.append(
            DiagnosticIssue(
                type="dedupe_missing_identity",
                severity="medium",
                message=f"{len(skipped)} source(s) lacked enough identity fields for deduplication.",
                repair_options=["provide_repair_plan"],
            )
        )
    if ambiguous:
        issues.append(
            DiagnosticIssue(
                type="ambiguous_dedupe_matches",
                severity="medium",
                message=f"{len(ambiguous)} fuzzy duplicate match(es) require OpenClaw decision.",
                repair_options=["provide_repair_plan", "accept_risk"],
                evidence=[item for item in ambiguous if isinstance(item, dict)],
            )
        )
    return DiagnosticReport(
        status="needs_review" if issues else "ok",
        issues=issues,
        stage="deduplicate",
        metrics={"merge_count": len(dedupe_trace.get("merges", [])), "skipped_count": len(skipped), "ambiguous_count": len(ambiguous)},
        requires_openclaw_decision=bool(issues) and not demo_fast,
    )


def build_orchestration_summary(
    *,
    stage: str,
    diagnostics: list[DiagnosticReport],
    artifact_paths: dict[str, str],
    demo_fast: bool,
) -> dict[str, Any]:
    blocking = [
        issue
        for report in diagnostics
        for issue in report.issues
        if issue.blocking or issue.severity == "high" or report.status == "blocked"
    ]
    review = [issue for report in diagnostics for issue in report.issues if issue not in blocking]
    return {
        "stage": stage,
        "status": "blocked" if blocking else "needs_review" if review else "ok",
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "orchestration_facts",
        "blocking_issues": [asdict(issue) for issue in blocking],
        "review_items": [asdict(issue) for issue in review],
        "machine_readable_facts": {report.stage or f"diagnostic_{index}": report.metrics for index, report in enumerate(diagnostics)},
        "artifact_paths": artifact_paths,
        "next_available_worker_actions": ["repair validate", "repair execute"] if review or blocking else ["matrix validate"],
        "requires_openclaw_decision": any(report.requires_openclaw_decision for report in diagnostics),
        "requires_user_decision": any(report.requires_user_decision for report in diagnostics),
        "generated_at": utc_timestamp(),
    }


def update_orchestration_summary_path(path: Path, summary: dict[str, Any], output_paths: dict[str, str]) -> None:
    summary["artifact_paths"] = output_paths
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def write_stage_orchestration_summaries(output_dir: Path, reports: list[DiagnosticReport], *, output_paths: dict[str, str], demo_fast: bool) -> None:
    summary_dir = output_dir / "orchestration"
    summary_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        stage = report.stage or "stage"
        summary = build_orchestration_summary(stage=stage, diagnostics=[report], artifact_paths=output_paths, demo_fast=demo_fast)
        (summary_dir / f"{slugify_for_path(stage)}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def classify_firecrawl_content(*, url: str, title: str, markdown: str) -> str:
    text = f"{url} {title}".lower()
    if markdown and (text.endswith(".pdf") or ".pdf" in text):
        return "pdf_markdown"
    if markdown and "github.com" in text:
        return "github_project_markdown"
    if markdown and ("technical report" in text or "white paper" in text or "arxiv.org" in text):
        return "technical_report_markdown"
    if markdown and any(marker in text for marker in ("docs.", "/docs", "documentation", "official")):
        return "official_doc_markdown"
    if markdown:
        return "scraped_markdown"
    if text.endswith(".pdf") or ".pdf" in text:
        return "landing_page_markdown"
    return "search_snippet"


def content_id_for_source(source: CandidateSource) -> str:
    stable = source.url or source.source_id or source.title
    digest = hashlib.sha1(stable.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"content-{digest}"


def merge_duplicate_source(base: CandidateSource, duplicate: CandidateSource) -> CandidateSource:
    providers = sorted({part for provider in [base.provider, duplicate.provider] for part in provider.split("+") if part})
    merged_raw = {
        **base.raw,
        "merged_records": [
            *base.raw.get("merged_records", []),
            {
                "source_id": duplicate.source_id,
                "provider": duplicate.provider,
                "title": duplicate.title,
                "url": duplicate.url,
            },
        ],
        "duplicate_raw": duplicate.raw,
    }
    return CandidateSource(
        source_id=base.source_id or duplicate.source_id,
        title=base.title or duplicate.title,
        abstract=base.abstract or duplicate.abstract,
        authors=base.authors or duplicate.authors,
        year=base.year or duplicate.year,
        venue=base.venue or duplicate.venue,
        url=base.url or duplicate.url,
        pdf=base.pdf or duplicate.pdf,
        doi=base.doi or duplicate.doi,
        arxiv_id=base.arxiv_id or duplicate.arxiv_id,
        citation_count=max(base.citation_count, duplicate.citation_count),
        provider="+".join(providers),
        source_type=base.source_type if base.source_type == "paper" else duplicate.source_type or base.source_type,
        raw=merged_raw,
        content_text=base.content_text or duplicate.content_text,
        content_type=base.content_type or duplicate.content_type,
        provenance=merge_provenance(base, duplicate),
        signals={**base.signals, **duplicate.signals},
    )


def merge_provenance(base: CandidateSource, detail: CandidateSource) -> list[dict[str, Any]]:
    provenance = list(base.provenance) + list(detail.provenance)
    if base.provider:
        provenance.append({"provider": base.provider, "source_id": base.source_id})
    if detail.provider:
        provenance.append({"provider": detail.provider, "source_id": detail.source_id})
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in provenance:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def classify_http_failure(status_code: int | None) -> str:
    if status_code in {401, 403}:
        return "unauthorized" if status_code == 401 else "paid_access_denied"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code and status_code >= 500:
        return "http_error"
    return "http_error"


def parse_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_provider_authority(source: CandidateSource) -> dict[str, float]:
    raw = source.raw if isinstance(source.raw, dict) else {}
    author_scores: list[float] = []
    raw_payloads = authority_payloads(raw)
    for payload in raw_payloads:
        raw_authors = payload.get("authors")
        if isinstance(raw_authors, list):
            for author in raw_authors:
                if isinstance(author, dict):
                    author_scores.append(author_authority_from_payload(author))
        elif isinstance(raw_authors, dict):
            author_scores.append(author_authority_from_payload(raw_authors))
        raw_author = payload.get("author")
        if isinstance(raw_author, dict):
            author_scores.append(author_authority_from_payload(raw_author))
        if any(key in payload for key in ("author_authority", "author_score", "max_author_h_index")):
            author_scores.append(author_authority_from_payload(payload))
        if not source.authors:
            author_text = payload.get("author") or payload.get("authors")
            normalized_authors = normalize_author_text(author_text)
            if normalized_authors:
                source.authors = normalized_authors
    venue_payloads: list[dict[str, Any]] = []
    for payload in raw_payloads:
        venue_payload: dict[str, Any] = {}
        for key in ("venue_info", "venue", "journal", "conference", "publication", "metadata"):
            value = payload.get(key)
            if isinstance(value, dict):
                venue_payload.update(value)
            elif isinstance(value, str) and not source.venue:
                source.venue = value
        if venue_payload:
            venue_payloads.append(venue_payload)
        if not source.venue:
            for key in ("siteName", "publisher", "category", "journal", "venue"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    source.venue = value.strip()
                    break
    venue_scores = [venue_authority_from_payload(payload) for payload in [raw, *venue_payloads, *raw_payloads]]
    return {
        "author_authority": round(max([0.0, *author_scores]), 3),
        "venue_authority": round(max([0.0, *venue_scores]), 3),
    }


def authority_payloads(raw: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = [raw]
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        payloads.append(metadata)
    duplicate_raw = raw.get("duplicate_raw")
    if isinstance(duplicate_raw, dict):
        payloads.extend(authority_payloads(duplicate_raw))
    merged_records = raw.get("merged_records")
    if isinstance(merged_records, list):
        payloads.extend(item for item in merged_records if isinstance(item, dict))
    return payloads


def author_authority_from_payload(payload: dict[str, Any]) -> float:
    h_index = parse_float(payload.get("h_index") or payload.get("hindex") or payload.get("hIndex"), default=0.0)
    citations = parse_float(payload.get("n_citation") or payload.get("citation_count") or payload.get("citations"), default=0.0)
    publications = parse_float(payload.get("n_pubs") or payload.get("publication_count") or payload.get("pubs"), default=0.0)
    explicit = parse_float(payload.get("author_authority") or payload.get("authority_score") or payload.get("score"), default=-1.0)
    if explicit >= 0:
        return max(0.0, min(1.0, explicit if explicit <= 1 else explicit / 100))
    return round(min(1.0, h_index / 100 * 0.55 + citations / 10000 * 0.3 + publications / 300 * 0.15), 3)


def venue_authority_from_payload(payload: dict[str, Any]) -> float:
    if not payload:
        return 0.0
    explicit = parse_float(payload.get("venue_authority") or payload.get("authority_score") or payload.get("score"), default=-1.0)
    if explicit >= 0:
        return max(0.0, min(1.0, explicit if explicit <= 1 else explicit / 100))
    rank = str(payload.get("rank") or payload.get("ccf_rank") or payload.get("tier") or payload.get("level") or "").strip().upper()
    if rank in {"A*", "A", "Q1", "CORE A*", "CCF A"}:
        return 1.0
    if rank in {"B", "Q2", "CORE A", "CCF B"}:
        return 0.72
    if rank in {"C", "Q3", "CORE B", "CCF C"}:
        return 0.45
    citations = parse_float(payload.get("n_citation") or payload.get("citation_count") or payload.get("citations"), default=0.0)
    return round(min(1.0, citations / 50000), 3)


def authority_score_from_payload(payload: dict[str, Any], *, authority_type: str) -> float:
    data = payload.get("data") if isinstance(payload, dict) else None
    candidates: list[dict[str, Any]] = []
    if isinstance(data, list):
        candidates = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        candidates = [data]
        for key in ("items", "results", "authors", "venues"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
    elif isinstance(payload, dict):
        candidates = [payload]
    scorer = author_authority_from_payload if authority_type == "author" else venue_authority_from_payload
    return max([0.0, *[scorer(candidate) for candidate in candidates]])


def validate_repair_plan(plan: dict[str, Any]) -> DiagnosticReport:
    issues: list[DiagnosticIssue] = []
    for field_name in ("repair_run_id", "intent", "target_gap_ids", "actions", "merge_policy", "created_by"):
        if field_name not in plan:
            issues.append(
                DiagnosticIssue(
                    type="repair_plan_missing_field",
                    severity="high",
                    message=f"repair_plan.json is missing required field `{field_name}`.",
                    missing=[field_name],
                    repair_options=["provide_repair_plan"],
                    blocking=True,
                )
            )
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        issues.append(
            DiagnosticIssue(
                type="repair_plan_missing_actions",
                severity="high",
                message="repair_plan.json must include at least one action.",
                repair_options=["provide_repair_plan"],
                blocking=True,
            )
        )
        actions = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            issues.append(
                DiagnosticIssue(
                    type="repair_action_malformed",
                    severity="high",
                    message=f"Repair action at index {index} is not an object.",
                    repair_options=["provide_repair_plan"],
                    blocking=True,
                )
            )
            continue
        action_type = str(action.get("action_type") or "")
        action_id = str(action.get("action_id") or f"action_{index}")
        if action_type not in SUPPORTED_REPAIR_ACTIONS:
            issues.append(
                DiagnosticIssue(
                    type="unsupported_repair_action",
                    severity="high",
                    message=f"Repair action `{action_id}` uses unsupported action_type `{action_type}`.",
                    repair_options=["provide_repair_plan"],
                    affected_artifacts=[action_id],
                    blocking=True,
                )
            )
        providers = {str(provider).lower() for provider in action.get("providers", []) if str(provider).strip()}
        unknown = sorted(providers - SUPPORTED_PROVIDERS)
        if unknown:
            issues.append(
                DiagnosticIssue(
                    type="unsupported_repair_provider",
                    severity="high",
                    message=f"Repair action `{action_id}` targets providers outside AMiner plus Firecrawl.",
                    repair_options=["provide_repair_plan"],
                    missing=unknown,
                    affected_artifacts=[action_id],
                    blocking=True,
                )
            )
        if action_type == "run_provider_search" and not action.get("queries"):
            issues.append(
                DiagnosticIssue(
                    type="repair_action_missing_queries",
                    severity="high",
                    message=f"Repair action `{action_id}` must provide explicit queries; the worker will not invent repair queries.",
                    repair_options=["provide_repair_plan"],
                    affected_artifacts=[action_id],
                    blocking=True,
                )
            )
    return DiagnosticReport(
        status="blocked" if any(issue.severity == "high" for issue in issues) else "needs_review" if issues else "ok",
        issues=issues,
        stage="repair_validate",
        metrics={"action_count": len(actions)},
        requires_openclaw_decision=bool(issues),
    )


def execute_repair_plan(
    plan: dict[str, Any],
    *,
    topic: str,
    output_dir: Path,
    providers: list[LiteratureProvider],
    matrix: list[LiteratureMatrixRow] | None = None,
    max_results: int = 40,
    demo_fast: bool = False,
) -> dict[str, Any]:
    emit_progress(
        "repair.execute",
        "repair run started",
        topic=topic,
        output_dir=str(output_dir),
        action_count=len(plan.get("actions", [])) if isinstance(plan.get("actions"), list) else 0,
        provider_count=len(providers),
    )
    validation = validate_repair_plan(plan)
    if validation.status == "blocked":
        emit_progress("repair.execute", "repair validation blocked", issue_count=len(validation.issues))
        trace = build_repair_trace(plan, validation=validation, actions_executed=[], actions_skipped=[], failures=[asdict(issue) for issue in validation.issues])
        write_repair_outputs(output_dir, trace=trace, validation=validation)
        return {"status": validation.status, "repair_trace": trace, "validation": validation}

    before_sources = rows_to_sources(matrix or [])
    working_sources = list(before_sources)
    new_sources: list[CandidateSource] = []
    search_trace: list[SearchTraceEvent] = []
    fulltext_trace_events: list[dict[str, Any]] = []
    citation_trace_events: list[dict[str, Any]] = []
    introduced_source_ids: list[str] = []
    actions_executed: list[dict[str, Any]] = []
    actions_skipped: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    provider_by_name = {getattr(provider, "name", ""): provider for provider in providers}
    repair_run_id = str(plan.get("repair_run_id") or "")

    for index, action in enumerate(plan.get("actions", [])):
        action_id = str(action.get("action_id") or f"action_{index}")
        action_type = str(action.get("action_type") or "")
        emit_progress(
            "repair.execute",
            "starting repair action",
            index=index + 1,
            total=len(plan.get("actions", [])),
            action_id=action_id,
            action_type=action_type,
        )
        provider_names = [str(provider).lower() for provider in action.get("providers", []) if str(provider).strip()]
        if not provider_names:
            provider_names = sorted(provider_by_name) if demo_fast else sorted(name for name in provider_by_name if name in SUPPORTED_PROVIDERS)
        selected_providers = [provider_by_name[name] for name in provider_names if name in provider_by_name]
        if action_type == "run_provider_search":
            queries = [str(query) for query in action.get("queries", []) if str(query).strip()]
            if not queries:
                failures.append({"action_id": action_id, "reason": "missing_queries"})
                actions_skipped.append({"action_id": action_id, "action_type": action_type, "reason": "missing_queries"})
                continue
            for query in queries:
                for provider in selected_providers:
                    emit_progress("repair.search", "starting provider search", action_id=action_id, provider=getattr(provider, "name", ""), query=query)
                    sources, event = provider.search(query, limit=max(1, min(int(action.get("max_results") or max_results), 100)))
                    search_trace.append(event)
                    for source in sources:
                        source.provenance.append(
                            {
                                "repair_run_id": repair_run_id,
                                "introduced_by_gap_id": ",".join(str(gap_id) for gap_id in plan.get("target_gap_ids", [])),
                                "repair_action_id": action_id,
                            }
                        )
                    new_sources.extend(sources)
                    introduced_source_ids.extend(source.source_id for source in sources)
                    emit_progress("repair.search", "provider search completed", action_id=action_id, provider=event.provider, status=event.status, result_count=event.result_count)
            actions_executed.append({"action_id": action_id, "action_type": action_type, "queries": queries, "providers": provider_names})
            continue
        if action_type == "expand_citations":
            target_ids = set(str(item) for item in action.get("target_source_ids", []) if str(item).strip())
            citation_depth = int(action.get("citation_depth") or 1)
            targets = [source for source in working_sources if not target_ids or source.source_id in target_ids]
            if not targets:
                actions_skipped.append({"action_id": action_id, "action_type": action_type, "reason": "no_matching_target_sources"})
                continue
            aminer = next((provider for provider in selected_providers if hasattr(provider, "fetch_references")), None)
            if aminer is None:
                actions_skipped.append({"action_id": action_id, "action_type": action_type, "reason": "aminer_provider_unavailable"})
                emit_progress("repair.execute", "skipped citation action missing AMiner provider", action_id=action_id)
                continue
            for target in targets:
                emit_progress("repair.citation", "starting reference fetch", action_id=action_id, source_id=target.source_id)
                references, citation_event = aminer.fetch_references(target, limit=max(1, min(int(action.get("max_results") or max_results), 100)))  # type: ignore[attr-defined]
                citation_event["repair_action_id"] = action_id
                citation_event["citation_depth"] = citation_depth
                citation_trace_events.append(citation_event)
                for reference in references:
                    reference.provenance.append(
                        {
                            "repair_run_id": repair_run_id,
                            "introduced_by_gap_id": ",".join(str(gap_id) for gap_id in plan.get("target_gap_ids", [])),
                            "repair_action_id": action_id,
                            "introduced_by": "repair_expand_citations",
                        }
                    )
                new_sources.extend(references)
                introduced_source_ids.extend(reference.source_id for reference in references)
                emit_progress("repair.citation", "reference fetch completed", action_id=action_id, source_id=target.source_id, reference_count=len(references))
            actions_executed.append({"action_id": action_id, "action_type": action_type, "target_count": len(targets), "citation_depth": citation_depth})
            continue
        if action_type == "fetch_fulltext":
            target_ids = [str(item) for item in action.get("target_source_ids", []) if str(item).strip()]
            working_sources, fulltext_trace = fetch_fulltext_for_sources(
                [*working_sources, *new_sources],
                providers=selected_providers or providers,
                demo_fast=demo_fast,
                source_ids=target_ids,
                limit=int(action.get("max_results") or max_results),
            )
            new_sources = []
            fulltext_trace_events.extend(fulltext_trace.get("events", []))
            actions_executed.append({"action_id": action_id, "action_type": action_type, "target_source_ids": target_ids})
            emit_progress("repair.fulltext", "fulltext fetch completed", action_id=action_id, event_count=len(fulltext_trace.get("events", [])))
            continue
        if action_type == "enrich_metadata":
            target_ids = set(str(item) for item in action.get("target_source_ids", []) if str(item).strip())
            aminer = next((provider for provider in selected_providers if isinstance(provider, AMinerProvider)), None)
            if aminer is None:
                actions_skipped.append({"action_id": action_id, "action_type": action_type, "reason": "aminer_provider_unavailable"})
                continue
            enriched: list[CandidateSource] = []
            for source in [*working_sources, *new_sources]:
                if target_ids and source.source_id not in target_ids:
                    enriched.append(source)
                    continue
                emit_progress("repair.metadata", "starting detail enrichment", action_id=action_id, source_id=source.source_id)
                enriched.append(aminer.enrich_detail(source))
            working_sources = enriched
            new_sources = []
            actions_executed.append({"action_id": action_id, "action_type": action_type, "target_count": len(target_ids) or len(enriched)})
            continue
        if action_type == "rerun_llm_extraction":
            actions_executed.append({"action_id": action_id, "action_type": action_type, "note": "LLM extraction reruns during matrix rebuild."})
            emit_progress("repair.execute", "queued LLM extraction rerun for final rebuild", action_id=action_id)
            continue
        if action_type in {"merge_and_deduplicate", "rebuild_matrix"}:
            actions_executed.append({"action_id": action_id, "action_type": action_type, "note": "Applied during final repair merge/matrix rebuild."})
            emit_progress("repair.execute", "queued merge/rebuild for final pass", action_id=action_id, action_type=action_type)
            continue
        actions_skipped.append({"action_id": action_id, "action_type": action_type, "reason": "unsupported_action"})
        emit_progress("repair.execute", "skipped unsupported action", action_id=action_id, action_type=action_type)

    emit_progress("repair.execute", "deduplicating repair sources", source_count=len([*working_sources, *new_sources]))
    merged_sources, dedupe_trace = deduplicate_sources_with_trace([*working_sources, *new_sources])
    emit_progress("repair.execute", "dedupe completed", source_count=len(merged_sources))
    emit_progress("repair.execute", "extracting repaired matrix fields", source_count=len(merged_sources))
    extractions, extraction_trace, extraction_failures = extract_matrix_fields(
        merged_sources,
        topic=topic,
        demo_fast=demo_fast,
        output_dir=output_dir,
    )
    repaired_matrix = [
        build_matrix_row(source, topic=topic, extraction=extractions.get(source.source_id), demo_fast=demo_fast)
        for source in sorted(merged_sources, key=_candidate_sort_key)
    ][:max_results]
    matrix_diagnostics = validate_literature_matrix(repaired_matrix)
    emit_progress("repair.execute", "repaired matrix built", row_count=len(repaired_matrix), diagnostics_status=matrix_diagnostics.status)
    trace = build_repair_trace(
        plan,
        validation=validation,
        actions_executed=actions_executed,
        actions_skipped=actions_skipped,
        failures=failures,
        before_count=len(before_sources),
        after_count=len(repaired_matrix),
        new_source_ids=sorted(set(introduced_source_ids)),
        updated_source_ids=[row.paper_id for row in repaired_matrix],
        dedupe_merges=dedupe_trace.get("merges", []),
    )
    write_repair_outputs(
        output_dir,
        trace=trace,
        validation=validation,
        matrix=repaired_matrix,
        matrix_diagnostics=matrix_diagnostics,
        search_trace=search_trace,
        extraction_trace=extraction_trace,
        extraction_failures=extraction_failures,
        fulltext_trace={"events": fulltext_trace_events, "generated_at": utc_timestamp()},
        citation_trace={"events": citation_trace_events, "generated_at": utc_timestamp()},
    )
    emit_progress("repair.execute", "repair outputs written", output_dir=str(output_dir), status=matrix_diagnostics.status)
    return {
        "status": matrix_diagnostics.status,
        "repair_trace": trace,
        "validation": validation,
        "matrix": repaired_matrix,
        "matrix_diagnostics": matrix_diagnostics,
    }


def build_repair_trace(
    plan: dict[str, Any],
    *,
    validation: DiagnosticReport,
    actions_executed: list[dict[str, Any]],
    actions_skipped: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    before_count: int = 0,
    after_count: int = 0,
    new_source_ids: list[str] | None = None,
    updated_source_ids: list[str] | None = None,
    dedupe_merges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "repair_run_id": plan.get("repair_run_id", ""),
        "actions_executed": actions_executed,
        "actions_skipped": actions_skipped,
        "before_counts": {"matrix_rows": before_count},
        "after_counts": {"matrix_rows": after_count},
        "changed_artifacts": ["literature_matrix.json"] if after_count else [],
        "new_source_ids": new_source_ids or [],
        "updated_source_ids": updated_source_ids or [],
        "dedupe_merges": dedupe_merges or [],
        "failures": failures,
        "provenance": {
            "repair_run_id": plan.get("repair_run_id", ""),
            "target_gap_ids": plan.get("target_gap_ids", []),
            "created_by": plan.get("created_by", ""),
            "validation_status": validation.status,
        },
        "generated_at": utc_timestamp(),
    }


def write_repair_outputs(
    output_dir: Path,
    *,
    trace: dict[str, Any],
    validation: DiagnosticReport,
    matrix: list[LiteratureMatrixRow] | None = None,
    matrix_diagnostics: DiagnosticReport | None = None,
    search_trace: list[SearchTraceEvent] | None = None,
    extraction_trace: dict[str, Any] | None = None,
    extraction_failures: list[dict[str, Any]] | None = None,
    fulltext_trace: dict[str, Any] | None = None,
    citation_trace: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    emit_progress("repair.write", "writing repair artifacts", output_dir=str(output_dir), has_matrix=matrix is not None)
    (output_dir / "repair_trace.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "repair_diagnostics.json").write_text(json.dumps(asdict(validation), indent=2, ensure_ascii=False), encoding="utf-8")
    if matrix is not None:
        emit_progress("repair.write", "writing repaired matrix", row_count=len(matrix))
        (output_dir / "literature_matrix.json").write_text(
            json.dumps({"count": len(matrix), "items": [asdict(row) for row in matrix]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        write_matrix_csv(output_dir / "literature_matrix.csv", matrix)
        write_matrix_markdown(output_dir / "literature_matrix.md", topic="", matrix=matrix)
    if matrix_diagnostics is not None:
        (output_dir / "matrix_diagnostics.json").write_text(json.dumps(asdict(matrix_diagnostics), indent=2, ensure_ascii=False), encoding="utf-8")
    if search_trace is not None:
        (output_dir / "repair_search_trace.json").write_text(
            json.dumps({"events": [asdict(event) for event in search_trace]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if extraction_trace is not None:
        (output_dir / "llm_extraction_trace.json").write_text(json.dumps(extraction_trace, indent=2, ensure_ascii=False), encoding="utf-8")
    if extraction_failures is not None:
        (output_dir / "extraction_failures.json").write_text(
            json.dumps({"count": len(extraction_failures), "items": extraction_failures}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if fulltext_trace is not None:
        (output_dir / "fulltext_trace.json").write_text(json.dumps(fulltext_trace, indent=2, ensure_ascii=False), encoding="utf-8")
    if citation_trace is not None:
        (output_dir / "citation_expansion_trace.json").write_text(json.dumps(citation_trace, indent=2, ensure_ascii=False), encoding="utf-8")
    emit_progress("repair.write", "repair artifacts written", output_dir=str(output_dir))


def rows_to_sources(matrix: list[LiteratureMatrixRow]) -> list[CandidateSource]:
    return [
        CandidateSource(
            source_id=row.paper_id,
            title=row.title,
            authors=[author.strip() for author in row.authors.split(",") if author.strip()],
            year=row.year,
            venue=row.venue,
            url=row.url,
            doi=row.doi,
            arxiv_id=row.arxiv_id,
            provider=row.source_channel,
            source_type=row.source_type,
        )
        for row in matrix
    ]


def write_outputs(
    output_dir: Path,
    *,
    topic: str,
    scope: ResearchScope,
    scope_diagnostics: DiagnosticReport,
    seed_papers: list[CandidateSource],
    seed_diagnostics: DiagnosticReport,
    query_plan: QueryPlan,
    query_diagnostics: DiagnosticReport,
    matrix: list[LiteratureMatrixRow],
    matrix_diagnostics: DiagnosticReport,
    trace: list[SearchTraceEvent],
    provider_status: dict[str, Any] | None = None,
    detail_trace: dict[str, Any] | None = None,
    aminer_detail_diagnostics: DiagnosticReport | None = None,
    content_artifacts: dict[str, Any] | None = None,
    seed_candidate_artifact: dict[str, Any] | None = None,
    seed_selection_artifact: dict[str, Any] | None = None,
    extraction_trace: dict[str, Any] | None = None,
    extraction_failures: list[dict[str, Any]] | None = None,
    gap_report: dict[str, Any] | None = None,
    citation_artifacts: dict[str, Any] | None = None,
    dedupe_trace: dict[str, Any] | None = None,
    dedupe_diagnostics: DiagnosticReport | None = None,
    fulltext_diagnostics: DiagnosticReport | None = None,
    fulltext_trace: dict[str, Any] | None = None,
    orchestration_summary: dict[str, Any] | None = None,
    demo_fast: bool = False,
) -> dict[str, str]:
    emit_progress("artifacts.write", "preparing output paths", output_dir=str(output_dir))
    scope_json = output_dir / "research_scope.json"
    scope_diagnostics_json = output_dir / "research_scope_diagnostics.json"
    seed_json = output_dir / "seed_papers.json"
    seed_candidates_json = output_dir / "seed_candidates.json"
    seed_selection_json = output_dir / "seed_selection.json"
    seed_diagnostics_json = output_dir / "seed_papers_diagnostics.json"
    query_plan_json = output_dir / "query_plan.json"
    query_diagnostics_json = output_dir / "query_plan_diagnostics.json"
    matrix_json = output_dir / "literature_matrix.json"
    matrix_csv = output_dir / "literature_matrix.csv"
    matrix_md = output_dir / "literature_matrix.md"
    matrix_diagnostics_json = output_dir / "matrix_diagnostics.json"
    trace_json = output_dir / "search_trace.json"
    provider_status_json = output_dir / "provider_status.json"
    detail_trace_json = output_dir / "detail_trace.json"
    aminer_detail_diagnostics_json = output_dir / "aminer_detail_diagnostics.json"
    fulltext_manifest_json = output_dir / "fulltext_manifest.json"
    fulltext_diagnostics_json = output_dir / "fulltext_diagnostics.json"
    fulltext_trace_json = output_dir / "fulltext_trace.json"
    firecrawl_content_manifest_json = output_dir / "firecrawl_content_manifest.json"
    llm_extraction_trace_json = output_dir / "llm_extraction_trace.json"
    extraction_failures_json = output_dir / "extraction_failures.json"
    gap_report_json = output_dir / "gap_report.json"
    citation_graph_json = output_dir / "citation_graph.json"
    citation_expansion_trace_json = output_dir / "citation_expansion_trace.json"
    citation_diagnostics_json = output_dir / "citation_diagnostics.json"
    citation_candidates_json = output_dir / "citation_candidates.json"
    dedupe_trace_json = output_dir / "dedupe_trace.json"
    dedupe_diagnostics_json = output_dir / "dedupe_diagnostics.json"
    orchestration_summary_json = output_dir / "orchestration_summary.json"

    emit_progress("artifacts.write", "writing planning and seed artifacts")
    scope_json.write_text(json.dumps(asdict(scope), indent=2, ensure_ascii=False), encoding="utf-8")
    scope_diagnostics_json.write_text(json.dumps(asdict(scope_diagnostics), indent=2, ensure_ascii=False), encoding="utf-8")
    seed_json.write_text(
        json.dumps(
            {
                "topic": topic,
                "demo_fast": demo_fast,
                "quality_level": "schema_smoke_only" if demo_fast else "seed_candidates",
                "count": len(seed_papers),
                "items": [asdict(source) for source in seed_papers],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    seed_diagnostics_json.write_text(json.dumps(asdict(seed_diagnostics), indent=2, ensure_ascii=False), encoding="utf-8")
    seed_candidates_json.write_text(json.dumps(seed_candidate_artifact or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    seed_selection_json.write_text(json.dumps(seed_selection_artifact or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    query_plan_json.write_text(json.dumps(asdict(query_plan), indent=2, ensure_ascii=False), encoding="utf-8")
    query_diagnostics_json.write_text(json.dumps(asdict(query_diagnostics), indent=2, ensure_ascii=False), encoding="utf-8")
    emit_progress("artifacts.write", "writing matrix and search trace artifacts", row_count=len(matrix), trace_count=len(trace))
    matrix_payload = {
        "topic": topic,
        "demo_fast": demo_fast,
        "quality_level": "schema_smoke_only" if demo_fast else "evidence_matrix",
        "query_plan": asdict(query_plan),
        "count": len(matrix),
        "items": [asdict(row) for row in matrix],
    }
    matrix_json.write_text(json.dumps(matrix_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    matrix_diagnostics_json.write_text(json.dumps(asdict(matrix_diagnostics), indent=2, ensure_ascii=False), encoding="utf-8")
    trace_json.write_text(
        json.dumps(
            {"topic": topic, "demo_fast": demo_fast, "events": [asdict(event) for event in trace]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider_status_json.write_text(json.dumps(provider_status or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    detail_trace_json.write_text(json.dumps(detail_trace or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    emit_progress("artifacts.write", "writing enrichment and extraction artifacts")
    aminer_detail_diagnostics_json.write_text(
        json.dumps(asdict(aminer_detail_diagnostics) if aminer_detail_diagnostics else {}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    content_manifest = (content_artifacts or {}).get("manifest", {})
    fulltext_manifest_json.write_text(json.dumps(content_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    firecrawl_content_manifest_json.write_text(json.dumps(content_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    fulltext_diagnostics_json.write_text(json.dumps(asdict(fulltext_diagnostics) if fulltext_diagnostics else {}, indent=2, ensure_ascii=False), encoding="utf-8")
    fulltext_trace_json.write_text(json.dumps(fulltext_trace or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    llm_extraction_trace_json.write_text(json.dumps(extraction_trace or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    extraction_failures_json.write_text(
        json.dumps(
            {
                "demo_fast": demo_fast,
                "quality_level": "schema_smoke_only" if demo_fast else "llm_extraction_failures",
                "count": len(extraction_failures or []),
                "items": extraction_failures or [],
                "generated_at": utc_timestamp(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    gap_report_json.write_text(json.dumps(gap_report or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    citation_artifacts = citation_artifacts or {}
    citation_graph_json.write_text(json.dumps(citation_artifacts.get("graph", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    citation_expansion_trace_json.write_text(json.dumps(citation_artifacts.get("trace", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    citation_diagnostics = citation_artifacts.get("diagnostics")
    citation_diagnostics_json.write_text(
        json.dumps(asdict(citation_diagnostics) if isinstance(citation_diagnostics, DiagnosticReport) else citation_diagnostics or {}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    citation_candidates_json.write_text(json.dumps(citation_artifacts.get("candidates", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    dedupe_trace_json.write_text(json.dumps(dedupe_trace or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    dedupe_diagnostics_json.write_text(json.dumps(asdict(dedupe_diagnostics) if dedupe_diagnostics else {}, indent=2, ensure_ascii=False), encoding="utf-8")
    orchestration_summary_json.write_text(json.dumps(orchestration_summary or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    emit_progress("artifacts.write", "writing CSV and Markdown matrix", row_count=len(matrix))
    write_matrix_csv(matrix_csv, matrix)
    write_matrix_markdown(matrix_md, topic=topic, matrix=matrix)
    output_paths = {
        "research_scope_json": str(scope_json),
        "research_scope_diagnostics_json": str(scope_diagnostics_json),
        "seed_papers_json": str(seed_json),
        "seed_candidates_json": str(seed_candidates_json),
        "seed_selection_json": str(seed_selection_json),
        "seed_papers_diagnostics_json": str(seed_diagnostics_json),
        "query_plan_json": str(query_plan_json),
        "query_plan_diagnostics_json": str(query_diagnostics_json),
        "literature_matrix_json": str(matrix_json),
        "literature_matrix_csv": str(matrix_csv),
        "literature_matrix_md": str(matrix_md),
        "matrix_diagnostics_json": str(matrix_diagnostics_json),
        "search_trace_json": str(trace_json),
        "provider_status_json": str(provider_status_json),
        "detail_trace_json": str(detail_trace_json),
        "aminer_detail_diagnostics_json": str(aminer_detail_diagnostics_json),
        "fulltext_manifest_json": str(fulltext_manifest_json),
        "fulltext_diagnostics_json": str(fulltext_diagnostics_json),
        "fulltext_trace_json": str(fulltext_trace_json),
        "firecrawl_content_manifest_json": str(firecrawl_content_manifest_json),
        "llm_extraction_trace_json": str(llm_extraction_trace_json),
        "extraction_failures_json": str(extraction_failures_json),
        "gap_report_json": str(gap_report_json),
        "citation_graph_json": str(citation_graph_json),
        "citation_expansion_trace_json": str(citation_expansion_trace_json),
        "citation_diagnostics_json": str(citation_diagnostics_json),
        "citation_candidates_json": str(citation_candidates_json),
        "dedupe_trace_json": str(dedupe_trace_json),
        "dedupe_diagnostics_json": str(dedupe_diagnostics_json),
        "orchestration_summary_json": str(orchestration_summary_json),
    }
    stage_reports = [scope_diagnostics, seed_diagnostics, query_diagnostics, matrix_diagnostics]
    if isinstance(citation_diagnostics, DiagnosticReport):
        stage_reports.append(citation_diagnostics)
    stage_reports.extend(report for report in [aminer_detail_diagnostics, fulltext_diagnostics, dedupe_diagnostics] if report is not None)
    emit_progress("artifacts.write", "writing orchestration summaries", report_count=len(stage_reports))
    write_stage_orchestration_summaries(output_dir, stage_reports, output_paths=output_paths, demo_fast=demo_fast)
    emit_progress("artifacts.write", "final artifacts written", artifact_count=len(output_paths))
    return output_paths


def write_extraction_checkpoint(
    output_dir: Path,
    *,
    sources: list[CandidateSource],
    extractions: dict[str, PaperExtraction],
    extraction_trace: dict[str, Any],
    extraction_failures: list[dict[str, Any]],
    topic: str,
    demo_fast: bool,
) -> dict[str, str]:
    extracted_sources = [source for source in sorted(sources, key=_candidate_sort_key) if source.source_id in extractions]
    checkpoint_matrix = [
        build_matrix_row(source, topic=topic, extraction=extractions.get(source.source_id), demo_fast=demo_fast)
        for source in extracted_sources
    ]
    checkpoint = {
        "topic": topic,
        "demo_fast": demo_fast,
        "source_count": len(sources),
        "extraction_count": len(extractions),
        "failure_count": len(extraction_failures),
        "generated_at": utc_timestamp(),
        "matrix": [asdict(row) for row in checkpoint_matrix],
        "extractions": {source_id: asdict(extraction) for source_id, extraction in extractions.items()},
        "trace": extraction_trace,
        "failures": extraction_failures,
    }
    checkpoint_json = output_dir / "partial_literature_matrix.json"
    checkpoint_csv = output_dir / "partial_literature_matrix.csv"
    checkpoint_md = output_dir / "partial_literature_matrix.md"
    checkpoint_state = output_dir / "partial_extraction_checkpoint.json"
    checkpoint_json.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    write_matrix_csv(checkpoint_csv, checkpoint_matrix)
    write_matrix_markdown(checkpoint_md, topic=topic, matrix=checkpoint_matrix)
    checkpoint_state.write_text(
        json.dumps(
            {
                "topic": topic,
                "demo_fast": demo_fast,
                "source_count": len(sources),
                "extraction_count": len(extractions),
                "failure_count": len(extraction_failures),
                "generated_at": checkpoint["generated_at"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "partial_literature_matrix_json": str(checkpoint_json),
        "partial_literature_matrix_csv": str(checkpoint_csv),
        "partial_literature_matrix_md": str(checkpoint_md),
        "partial_extraction_checkpoint_json": str(checkpoint_state),
    }


def write_matrix_csv(path: Path, matrix: list[LiteratureMatrixRow]) -> None:
    fields = list(LiteratureMatrixRow.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in matrix:
            writer.writerow(asdict(row))


def write_matrix_markdown(path: Path, *, topic: str, matrix: list[LiteratureMatrixRow]) -> None:
    lines = [
        f"# Literature Matrix: {topic}",
        "",
        "| Priority | Year | Title | Venue | Citation Value | Suggested Section |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in matrix:
        title = row.title.replace("|", "\\|")
        venue = row.venue.replace("|", "\\|")
        citation_value = row.citation_value.replace("|", "\\|")
        section = row.suggested_section.replace("|", "\\|")
        lines.append(f"| {row.read_priority} | {row.year or ''} | {title} | {venue} | {citation_value} | {section} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_aminer_item(item: dict[str, Any]) -> CandidateSource:
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    source = CandidateSource(
        source_id=str(item.get("id") or item.get("_id") or item.get("paper_id") or item.get("aminer_id") or item.get("url") or item.get("title") or "").strip(),
        title=str(item.get("title") or item.get("name") or "").strip(),
        abstract=str(item.get("abstract") or item.get("abstract_zh") or "").strip(),
        authors=normalize_authors(authors),
        year=parse_year(item.get("year")),
        venue=str(item.get("venue") or item.get("venue_name") or item.get("raw") or "").strip(),
        url=str(item.get("url") or "").strip(),
        pdf=str(item.get("pdf") or "").strip(),
        doi=str(item.get("doi") or "").strip(),
        arxiv_id=extract_arxiv_id(str(item.get("url") or item.get("pdf") or "")),
        citation_count=parse_int(item.get("n_citation") or item.get("citation_count") or item.get("citations")),
        provider="aminer",
        source_type="paper",
        raw=item,
        content_type="abstract" if item.get("abstract") or item.get("abstract_zh") else "metadata",
    )
    return source


def normalize_firecrawl_item(item: dict[str, Any]) -> CandidateSource:
    url = str(item.get("url") or item.get("metadata", {}).get("url") or "").strip()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    markdown = str(item.get("markdown") or item.get("content") or "").strip()
    snippet = str(item.get("description") or item.get("snippet") or metadata.get("description") or "").strip()
    title = str(item.get("title") or metadata.get("title") or url).strip()
    author_text = item.get("author") or item.get("authors") or metadata.get("author") or metadata.get("authors")
    authors = normalize_author_text(author_text)
    venue = str(
        item.get("venue")
        or item.get("journal")
        or item.get("conference")
        or item.get("category")
        or metadata.get("venue")
        or metadata.get("journal")
        or metadata.get("conference")
        or metadata.get("publisher")
        or metadata.get("siteName")
        or "Firecrawl research search"
    ).strip()
    content_type = classify_firecrawl_content(url=url, title=title, markdown=markdown)
    source = CandidateSource(
        source_id=url or str(item.get("title") or "").strip(),
        title=title,
        abstract=snippet,
        authors=authors,
        year=infer_year_from_text(" ".join([str(item.get("date") or ""), str(item.get("publishedDate") or ""), url, snippet[:500], markdown[:500]])),
        venue=venue,
        url=url,
        pdf=url if url.lower().endswith(".pdf") else "",
        doi=extract_doi(" ".join([snippet, markdown])),
        arxiv_id=extract_arxiv_id(url),
        citation_count=0,
        provider="firecrawl",
        source_type="web",
        raw=item,
        content_text=markdown,
        content_type=content_type,
    )
    source.source_type = infer_source_type(source)
    return source


def infer_source_type(source: CandidateSource) -> str:
    text = f"{source.title} {source.venue} {source.url}".lower()
    if source.provider == "aminer" or source.doi or source.arxiv_id:
        return "paper"
    if text.endswith(".pdf") or ".pdf" in text or source.pdf:
        return "pdf"
    if "github.com" in text:
        return "github_project"
    if any(domain in text for domain in ("docs.", "/docs", "documentation", "official")):
        return "official_doc"
    if "technical report" in text or "white paper" in text or "arxiv.org" in text:
        return "technical_report"
    return "web"


def merge_candidate_detail(base: CandidateSource, detail: CandidateSource) -> CandidateSource:
    return CandidateSource(
        source_id=base.source_id or detail.source_id,
        title=base.title or detail.title,
        abstract=base.abstract or detail.abstract,
        authors=base.authors or detail.authors,
        year=base.year or detail.year,
        venue=base.venue or detail.venue,
        url=base.url or detail.url,
        pdf=base.pdf or detail.pdf,
        doi=base.doi or detail.doi,
        arxiv_id=base.arxiv_id or detail.arxiv_id,
        citation_count=base.citation_count or detail.citation_count,
        provider=base.provider or detail.provider,
        source_type=base.source_type or detail.source_type,
        raw={**detail.raw, **base.raw, "detail_enriched": bool(detail.raw)},
        content_text=base.content_text or detail.content_text,
        content_type=base.content_type or detail.content_type,
        provenance=merge_provenance(base, detail),
        signals={**detail.signals, **base.signals},
    )


def safe_request_params(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"authorization", "token", "api_key", "apikey", "key"}
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in blocked:
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def normalize_authors(authors: list[Any]) -> list[str]:
    normalized: list[str] = []
    for author in authors:
        if isinstance(author, dict):
            name = str(author.get("name") or author.get("name_zh") or "").strip()
        else:
            name = str(author or "").strip()
        if name:
            normalized.append(name)
    return normalized


def normalize_author_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return normalize_authors(value)
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;]|\band\b", value) if part.strip()]
    return []


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "papers", "results", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def _extract_detail_item(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("paper", "item", "result", "detail"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
        return data
    if isinstance(payload.get("paper"), dict):
        return payload["paper"]
    return {}


def _extract_firecrawl_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        web = data.get("web")
        if isinstance(web, list):
            return [item for item in web if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _extract_relation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    candidates: list[Any] = []
    if isinstance(data, dict):
        for key in ("references", "refs", "papers", "items", "results", "result"):
            value = data.get(key)
            if isinstance(value, list):
                candidates = value
                break
    elif isinstance(data, list):
        candidates = data
    if not candidates:
        for key in ("references", "refs", "papers", "items", "results", "result"):
            value = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(value, list):
                candidates = value
                break
    return [item for item in candidates if isinstance(item, dict)]


def extract_firecrawl_markdown(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("markdown", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return value.strip()
        scrape = data.get("scrape")
        if isinstance(scrape, dict):
            value = scrape.get("markdown") or scrape.get("content")
            if isinstance(value, str):
                return value.strip()
    for key in ("markdown", "content"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, str):
            return value.strip()
    return ""


def summarize_markdown_for_snippet(markdown: str, *, limit: int = 700) -> str:
    cleaned = re.sub(r"\s+", " ", re.sub(r"[#*_`>\[\]()]|!\[[^\]]*\]\([^)]*\)", " ", markdown)).strip()
    return cleaned[:limit]


def _candidate_sort_key(source: CandidateSource) -> tuple[float, int, int]:
    return (-score_credibility(source), -(source.year or 0), -source.citation_count)


def parse_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def infer_year_from_text(text: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if not match:
        return None
    return parse_year(match.group(0))


def extract_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def extract_arxiv_id(text: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf|html)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""
