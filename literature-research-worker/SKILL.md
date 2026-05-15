---
name: literature-research-worker
description: Independent research skill for literature search, diagnostics, repair, and literature matrix construction.
metadata:
  openclaw:
    os: ["darwin", "linux", "win32"]
    requires:
      bins: ["uv"]
      env: ["FIRECRAWL_API_KEY", "AMINER_SEARCH_API_TOKEN", "LITERATURE_LLM_BASE_URL", "LITERATURE_LLM_API_KEY", "LITERATURE_LLM_MODEL"]
    envVars:
      - name: FIRECRAWL_API_KEY
        required: true
        description: Firecrawl API key for web, PDF, GitHub, official docs, and technical report search.
      - name: AMINER_SEARCH_API_TOKEN
        required: true
        description: AMiner token for scholarly paper search and metadata enrichment.
      - name: FIRECRAWL_BASE_URL
        required: false
        description: Optional Firecrawl base URL. Defaults to https://api.firecrawl.dev.
      - name: AMINER_SEARCH_API_BASE_URL
        required: false
        description: Optional AMiner-backed search base URL. Defaults to https://agentic-search.aminer.cn.
      - name: AMINER_SEARCH_API_ENDPOINT
        required: false
        description: Optional AMiner-backed search endpoint. Defaults to /paper/search.
      - name: AMINER_SEARCH_MODEL
        required: false
        description: Optional AMiner search model name. Defaults to glm-4.5.
      - name: AMINER_DETAIL_URL
        required: false
        description: Optional AMiner paper detail endpoint.
      - name: AMINER_RELATION_URL
        required: false
        description: Optional AMiner paper relation endpoint for backward references.
      - name: AMINER_AUTHOR_URL
        required: false
        description: Optional AMiner author authority endpoint used by seed selection scoring.
      - name: AMINER_VENUE_URL
        required: false
        description: Optional AMiner venue/journal authority endpoint used by seed selection scoring.
      - name: LITERATURE_LLM_BASE_URL
        required: true
        description: OpenAI-compatible LLM base URL for real-mode paper extraction.
      - name: LITERATURE_LLM_API_KEY
        required: true
        description: OpenAI-compatible LLM API key for real-mode paper extraction.
      - name: LITERATURE_LLM_MODEL
        required: true
        description: LLM model name for real-mode paper extraction.
      - name: LITERATURE_LLM_ENDPOINT
        required: false
        description: Optional LLM chat-completions endpoint. Defaults to /v1/chat/completions.
    primaryEnv: AMINER_SEARCH_API_TOKEN
    install:
      - id: uv
        kind: uv
        label: Install uv
---

# Task Context

Operate as a standalone literature research worker.

Do not write the final survey, do not evaluate a draft, and do not assume any downstream workflow integration.
Your job is to turn a topic or research question into a reproducible literature matrix and search trace.
OpenClaw controls the research workflow; scripts provide deterministic execution, diagnostics, repair actions, and rerunnable stage artifacts.

# Goals

- Scope the literature search from the provided topic in demo-fast/bootstrap mode.
- Consume OpenClaw-authored scope and query plans in real mode.
- Search AMiner for scholarly papers when configured.
- Search Firecrawl for research web/PDF/project documentation when configured.
- Normalize and deduplicate candidate sources.
- Use LLM-only extraction in real mode and deterministic mock extraction only in `--demo-fast`.
- Export the literature matrix in JSON, CSV, and Markdown.
- Export the search trace so the run can be audited and repeated.
- Rank seed candidates with auditable signal, venue/journal, author, citation,
  recency, fulltext, and metadata score components.

# Primary Command

Run from a copied skill folder. Store artifacts in a workspace run folder whose name includes the run time; do not write outputs directly into the skill folder:

```powershell
$runDir = "../literature-runs/$(Get-Date -Format 'yyyyMMdd-HHmmss')-literature"
uv run python scripts/research_skill.py matrix build --scope-file "$runDir/research_scope.json" --query-plan "$runDir/query_plan.json" --output-dir "$runDir"
```

If `$runDir/literature_matrix.json` already exists, `matrix build` refuses to overwrite it by default. Inspect the existing diagnostics first. Only rerun with `--force-overwrite` after you are sure replacing the artifacts is the right move; the command will back up existing matrix artifacts into `_artifact_backups/<timestamp>/` first.

Repository development path. This still uses the self-contained code inside the skill folder:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache-local"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/run_literature_search.py --topic "<topic>" --scope-file "<runDir>/research_scope.json" --query-plan "<runDir>/query_plan.json"
```

Do not pass API keys on the command line. Use process environment variables or OpenClaw skill env injection for `FIRECRAWL_API_KEY`, `AMINER_SEARCH_API_TOKEN`, and `LITERATURE_LLM_API_KEY`. For the LLM base URL, use the provider origin such as `https://api.deepseek.com`; the script appends `/v1/chat/completions` and normalizes an accidental duplicate `/v1` path.

Portable OpenClaw workspace:

```powershell
uv run python .cmdop/skills/literature-research-worker/scripts/run_literature_search.py --topic "<topic>"
```

Deterministic smoke mode:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache-local"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/run_literature_search.py --topic "<topic>" --demo-fast
```

# Stage Commands

Prefer the staged CLI when OpenClaw needs to review or repair intermediate artifacts:

```bash
$runDir = "literature-runs/$(Get-Date -Format 'yyyyMMdd-HHmmss')-literature"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py scope build --topic "<topic>" --output "$runDir/research_scope.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py scope validate --scope-file "$runDir/research_scope.json" --output "$runDir/research_scope_diagnostics.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py seed discover --scope-file "$runDir/research_scope.json" --output "$runDir/seed_papers.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py seed validate --scope-file "$runDir/research_scope.json" --seed-file "$runDir/seed_papers.json" --output "$runDir/seed_papers_diagnostics.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py query build --scope-file "$runDir/research_scope.json" --seed-file "$runDir/seed_papers.json" --output "$runDir/query_plan.json" --demo-fast
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py query validate --scope-file "$runDir/research_scope.json" --query-plan "$runDir/query_plan.json" --output "$runDir/query_plan_diagnostics.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py matrix build --scope-file "$runDir/research_scope.json" --query-plan "$runDir/query_plan.json" --output-dir "$runDir"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py matrix validate --matrix-file "$runDir/literature_matrix.json" --output "$runDir/matrix_diagnostics.json"
```

## Long-Run Supervision

Real matrix builds now write partial checkpoints during extraction:

- `partial_extraction_checkpoint.json`
- `partial_literature_matrix.json`
- `partial_literature_matrix.csv`
- `partial_literature_matrix.md`

If a run is interrupted or OpenClaw compacts context, stop the process tree and inspect the partial artifacts instead of launching another matrix build in the same `runDir`. If there is no new `[literature-progress]` output for several minutes, report the current stage and active process tree; do not blind-retry.

Repair commands are deterministic and consume an OpenClaw-authored `repair_plan.json`:

```powershell
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py repair validate --repair-plan "$runDir/repair_plan.json" --output "$runDir/repair_diagnostics.json"
uv run --project skills/literature-research-worker python skills/literature-research-worker/scripts/research_skill.py repair execute --repair-plan "$runDir/repair_plan.json" --topic "<topic>" --matrix-file "$runDir/literature_matrix.json" --output-dir "$runDir"
```

Seed selection policies may include:

```json
{
  "max_seeds": 8,
  "min_objective_score": 0.45,
  "required_signals": ["survey_or_review", "benchmark_or_dataset"],
  "venue_weights": {"Journal of Agent Research": 0.2},
  "author_weights": {"Ada Lovelace": 0.2},
  "preferred_venues": ["NeurIPS", "ICML"],
  "preferred_authors": ["Grace Hopper"],
  "signal_weights": {"survey_or_review": 0.18}
}
```

# Inputs

Required:
- `--topic <topic>`

Optional:
- `--output-dir <path>`; defaults to a workspace-level `literature-runs/YYYYMMDD-HHMMSS-<topic>` directory
- `--channels aminer,firecrawl`
- `--max-results <n>`
- `--max-queries <n>`
- `--scrape-markdown`
- `--demo-fast`

# Provider Configuration

Default real provider mode uses both AMiner and Firecrawl, so it requires both
`AMINER_SEARCH_API_TOKEN` and `FIRECRAWL_API_KEY`.
If provider keys are unavailable, use `--demo-fast`; do not treat demo-fast output as real research.

AMiner search:
- `AMINER_SEARCH_API_BASE_URL`, default `https://agentic-search.aminer.cn`
- `AMINER_SEARCH_API_ENDPOINT`, default `/paper/search`
- `AMINER_SEARCH_API_TOKEN`
- `AMINER_SEARCH_MODEL`, default `glm-4.5`

Firecrawl:
- `FIRECRAWL_API_KEY`
- `FIRECRAWL_BASE_URL`, default `https://api.firecrawl.dev`

Firecrawl requests use official v2 object-style parameters:

```json
{
  "sources": [{ "type": "web" }],
  "categories": [{ "type": "research" }, { "type": "pdf" }]
}
```

# Expected Artifacts

The output directory contains:

- `research_scope.json`
- `research_scope_diagnostics.json`
- `seed_papers.json`
- `seed_candidates.json`
- `seed_selection.json`
- `seed_papers_diagnostics.json`
- `query_plan.json`
- `query_plan_diagnostics.json`
- `literature_matrix.json`
- `literature_matrix.csv`
- `literature_matrix.md`
- `matrix_diagnostics.json`
- `search_trace.json`
- `provider_status.json`
- `detail_trace.json`
- `aminer_detail_diagnostics.json`
- `fulltext_manifest.json`
- `fulltext_diagnostics.json`
- `fulltext_trace.json`
- `firecrawl_content_manifest.json`
- `llm_extraction_trace.json`
- `extraction_failures.json`
- `gap_report.json`
- `citation_graph.json`
- `citation_expansion_trace.json`
- `citation_diagnostics.json`
- `citation_candidates.json`
- `dedupe_trace.json`
- `dedupe_diagnostics.json`
- `orchestration_summary.json`

The scripts refuse to write artifacts inside the skill folder. Use a timestamped workspace directory such as `literature-runs/20260514-153012-literature`.

Diagnostic files use:

```json
{
  "status": "ok | needs_review | blocked | failed",
  "issues": [
    {
      "type": "issue_type",
      "severity": "low | medium | high",
      "message": "Human-readable diagnostic.",
      "repair_options": ["repair_action"],
      "missing": []
    }
  ]
}
```

# Literature Matrix Fields

Each matrix row contains:

- `paper_id`
- `title`
- `year`
- `authors`
- `venue`
- `source_channel`
- `source_type`
- `url`
- `doi`
- `arxiv_id`
- `task`
- `method`
- `dataset`
- `core_contribution`
- `limitations`
- `citation_value`
- `suggested_section`
- `relevance_score`
- `credibility_score`
- `read_priority`
- `notes`
- `evidence_snippets`
- `confidence`
- `missing_evidence`
- `extraction_status`
- `extraction_basis`
- `extraction_method`
- `score_breakdown`
- `priority_reason`
- `provenance`

# Boundaries

Real mode uses LLM-only extraction and refuses to fabricate matrix extraction
fields when LLM configuration is missing. `--demo-fast` uses deterministic mock
extraction and marks artifacts as `schema_smoke_only`; do not treat those rows
as real evidence.

Taxonomy, draft writing, post-writing repair, and providers outside AMiner plus
Firecrawl are out of scope for this worker contract.

Initial `source_type` values are `paper`, `web`, `technical_report`, `github_project`, `official_doc`, and `pdf`.

OpenClaw should review diagnostics and decide whether to ask the user, run a repair command, or continue to the next stage. The scripts should not make final research-quality judgments beyond deterministic validation and scoring.

Do not present `--demo-fast` outputs as real research.

# Distribution Notes

This skill is a text-based OpenClaw skill folder package. It does not ship binaries.

Use `uv` as the official runtime and dependency manager. Do not use a system `pip` fallback in the official workflow.

The copied skill folder includes a skill-local `pyproject.toml`, `scripts/`, and `references/`.
Run commands from the copied skill root with `uv run python scripts/research_skill.py ...`.
The runtime code required by the entrypoints lives under this skill folder; entrypoint scripts must not import repository modules such as `jingdong_claw` or shared bootstrap helpers.

See:
- `references/provider_docs.md`
- `references/matrix_schema.md`
