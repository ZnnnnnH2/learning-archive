# Literature Matrix Schema

The skill writes a unified literature matrix for papers, web sources, technical reports, GitHub projects, official documentation, and PDFs.

## Matrix Artifacts

- `literature_matrix.json`
- `literature_matrix.csv`
- `literature_matrix.md`
- `llm_extraction_trace.json`
- `extraction_failures.json`
- `fulltext_manifest.json`
- `fulltext_trace.json`
- `firecrawl_content_manifest.json`
- `provider_status.json`
- `aminer_detail_diagnostics.json`
- `seed_candidates.json`
- `seed_selection.json`
- `gap_report.json`
- `citation_graph.json`
- `citation_expansion_trace.json`
- `citation_diagnostics.json`
- `citation_candidates.json`
- `dedupe_trace.json`
- `orchestration_summary.json`

Top-level JSON fields:

- `topic`
- `demo_fast`
- `query_plan`
- `count`
- `items`

Each row contains:

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
- `demo_fast`
- `quality_level`
- `score_breakdown`
- `priority_reason`
- `provenance`

Initial `source_type` values:

- `paper`
- `web`
- `technical_report`
- `github_project`
- `official_doc`
- `pdf`

## Diagnostics

Diagnostics use:

```json
{
  "status": "ok",
  "issues": [
    {
      "type": "issue_type",
      "severity": "medium",
      "message": "Human-readable diagnostic.",
      "repair_options": ["repair_action"],
      "missing": []
    }
  ]
}
```

`status` may be `ok`, `needs_review`, `blocked`, or `failed`.

Real-mode extraction fields come from the configured LLM only. Demo-fast rows
use deterministic mock extraction and are marked as `schema_smoke_only`.

`seed_candidates.json` includes `score_breakdown` with:

- `base_signal_score`
- `venue_weight`
- `author_weight`
- `citation_weight`
- `recency_weight`
- `fulltext_weight`
- `metadata_penalty`
- `ranking_score`
- `objective_score`

OpenClaw can provide `venue_weights`, `author_weights`, `preferred_venues`,
`preferred_authors`, and `signal_weights` in `seed_selection_policy.json`.
`ranking_score` is the unbounded ordering score so venue/author boosts are not
lost when `objective_score` reaches 1.0. `objective_score` remains a normalized
0-1 value for threshold checks such as `min_objective_score`.

## Search Trace

`search_trace.json` records:

- `provider`
- `query`
- `endpoint`
- `status`
- `result_count`
- `elapsed_seconds`
- `error`
- `request_params`
- `normalization_path`

`request_params` must not include API keys, tokens, or Authorization headers.
