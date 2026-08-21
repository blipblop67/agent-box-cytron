"""
Tavily's search API - built specifically for feeding LLMs/agents, so results
come back as clean extracted content rather than raw HTML to scrape. Chosen
over wrapping a general search engine directly for that reason, and it has a
genuinely free tier (no credit card) that fits this hub's "approachable to
someone learning" bar as well as OpenRouter/Ollama do for the LLM side.
"""
import httpx

API_URL = "https://api.tavily.com/search"


class WebSearchError(Exception):
    pass


def search(api_key: str, query: str, max_results: int = 5) -> list[dict]:
    try:
        resp = httpx.post(
            API_URL,
            json={"api_key": api_key, "query": query, "max_results": max_results, "include_answer": False},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise WebSearchError("The Tavily API key on the Settings page looks invalid") from exc
        raise WebSearchError(f"Web search failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise WebSearchError(f"Couldn't reach Tavily: {exc}") from exc

    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in data.get("results", [])
    ]
