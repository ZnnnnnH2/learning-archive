import os

vars = [
    "LITERATURE_LLM_BASE_URL",
    "LITERATURE_LLM_API_KEY",
    "LITERATURE_LLM_MODEL",
    "AMINER_SEARCH_API_TOKEN",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_BASE_URL",
]
for v in vars:
    val = os.environ.get(v)
    status = "SET" if val and val.strip() else "MISSING"
    print(f"{v}={status}")
