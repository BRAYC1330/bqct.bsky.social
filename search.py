import os
import logging
import httpx
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_trending_topics_raw() -> list:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en", timeout=30)
            if r.status_code != 200:
                return []
            data = r.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            eng = [i for i in items if i.get("keyword") and i.get("summary")]
            eng.sort(key=lambda x: x.get("score", 0), reverse=True)
            return eng[:10]
    except Exception as e:
        logger.error(f"[SEARCH] Trend fetch failed: {e}")
        return []

def clean_search_results(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, list):
        return " ".join([r.get("title", "") + " " + r.get("content", "")[:150] for r in raw])
    return str(raw)[:500]

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY:
        return ""
    url = "https://api.tavily.com/search"
    headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": True}
    if time_range:
        payload["time_range"] = time_range
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            return clean_search_results(r.json().get("results", []))
    except Exception as e:
        logger.error(f"[tavily] Error: {e}")
        return ""

async def fetch_chainbase(query: str) -> str:
    return ""
