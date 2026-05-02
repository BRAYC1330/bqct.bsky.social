import logging
from src.state import settings as config

logger = logging.getLogger(__name__)

def _clean_tavily_content(text):
    if not text: return ""
    import re
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_#~`>]', '', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    return ' '.join(text.split()).strip()

async def fetch(query, time_range=""):
    import httpx
    if not config.TAVILY_API_KEY: return ""
    try:
        payload = {
            "query": query,
            "include_answer": "basic",
            "search_depth": "basic",
            "max_results": 5,
            "include_raw_content": "text",
            "exclude_domains": ["youtube.com"],
            "api_key": config.TAVILY_API_KEY
        }
        if time_range in ("day", "week", "month", "year"):
            payload["time_range"] = time_range
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            if r.status_code == 200:
                data = r.json()
                answer = data.get("answer", "")
                results = data.get("results", [])
                parts = []
                if answer:
                    clean_answer = _clean_tavily_content(answer)
                    if clean_answer: parts.append(f"[SUMMARY] {clean_answer}")
                for res in results[:5]:
                    title = res.get("title", "").strip()
                    content = _clean_tavily_content(res.get("content", ""))
                    if len(content) > 1600: content = content[:1600].rsplit(' ', 1)[0] + "..."
                    if title and content: parts.append(f"• {title}: {content}")
                    elif content: parts.append(f"• {content}")
                return "\n".join(parts)
    except Exception:
        pass
    return ""
