# Provider Configuration

The skill has two real providers and one deterministic smoke provider.

## Real Provider Mode

Default real search mode uses both providers and requires:

- `FIRECRAWL_API_KEY`
- `AMINER_SEARCH_API_TOKEN`
- `LITERATURE_LLM_BASE_URL`
- `LITERATURE_LLM_API_KEY`
- `LITERATURE_LLM_MODEL`

AMiner is the primary scholarly paper discovery and metadata provider.
Firecrawl supplements web, PDF, GitHub project, official documentation, and technical report evidence.
The LLM endpoint is used only for extraction into matrix fields; no rule-based
real-mode extraction fallback is provided.

## AMiner

Environment variables:

- `AMINER_SEARCH_API_TOKEN`, required for AMiner search and detail enrichment
- `AMINER_SEARCH_API_BASE_URL`, optional, default `https://agentic-search.aminer.cn`
- `AMINER_SEARCH_API_ENDPOINT`, optional, default `/paper/search`
- `AMINER_SEARCH_MODEL`, optional, default `glm-4.5`
- `AMINER_DETAIL_URL`, optional, default `https://datacenter.aminer.cn/gateway/open_platform/api/paper/detail`
- `AMINER_RELATION_URL`, optional, default `https://datacenter.aminer.cn/gateway/open_platform/api/paper/relation`
- `AMINER_AUTHOR_URL`, optional author authority endpoint for seed scoring
- `AMINER_VENUE_URL`, optional venue/journal authority endpoint for seed scoring

The search request records safe request parameters in `search_trace.json`.
Authorization headers and tokens are never written to the trace.
Detail enrichment writes `detail_trace.json` and `aminer_detail_diagnostics.json`.
Backward reference expansion writes `citation_graph.json`,
`citation_expansion_trace.json`, `citation_diagnostics.json`, and
`citation_candidates.json`.
If `AMINER_AUTHOR_URL` or `AMINER_VENUE_URL` is configured, seed scoring also
records authority lookup attempts in `detail_trace.json` under
`authority_attempts`.

For OpenClaw skill development, declare this variable in the skill metadata and
configure both provider credentials through the OpenClaw skill env contract. Do
not rely on `PATH`; it is only for executable lookup and is not read as a
provider credential.

## Firecrawl

Environment variables:

- `FIRECRAWL_API_KEY`, required for real mode
- `FIRECRAWL_BASE_URL`, optional, default `https://api.firecrawl.dev`

Firecrawl v2 requests use object-style `sources` and `categories`:

```json
{
  "sources": [{ "type": "web" }],
  "categories": [{ "type": "research" }, { "type": "pdf" }]
}
```

Firecrawl metadata fields such as `author`, `authors`, `siteName`,
`publisher`, and `journal` are normalized into seed candidate author and venue
signals when present.

## Demo-Fast Mode

`--demo-fast` uses deterministic mocked sources and does not require provider keys or network access.
All artifacts produced in this mode include `demo_fast: true` and
`quality_level: "schema_smoke_only"`.
Do not present `--demo-fast` output as real literature research.
