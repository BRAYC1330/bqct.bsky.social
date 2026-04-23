import os
import logging
import httpx
import time
import config
import parsers
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

_trend_cache = None
_trend_cache_time = 0
_trend_cache_ttl = 300

async def get_trending_topics_raw(client: httpx.AsyncClient) -> list:
    global _trend_cache, _trend_cache_time
    now = time.time()
    if _trend_cache is not None and now - _trend_cache_time < _trend_cache_ttl:
        return _trend_cache
    try:
        r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en", timeout=config.SEARCH_TIMEOUT)
        if r.status_code != 200:
            return []
        _trend_cache = parsers.parse_trends(r.json())
        _trend_cache_time = now
        if config.RAW_DEBUG:
            import json
            logger.info(f"=== RAW-TRENDS ===\n{json.dumps(_trend_cache, ensure_ascii=False, indent=2)}\n=== END ===")
        return _trend_cache
    except Exception as e:
        logger.error(f"[SEARCH] Trend fetch failed: {e}")
        return []

def clean_search_results(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, list):
        return " ".join([r.get("title", "") + " " + r.get("content", "")[:150] for r in raw])
    return str(raw)[:500]

async def fetch_tavily(client: httpx.AsyncClient, query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY:
        return ""
    url = "https://api.tavily.com/search"
    headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": True}
    if time_range:
        payload["time_range"] = time_range
    try:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return clean_search_results(r.json().get("results", []))
    except Exception as e:
        logger.error(f"[tavily] Error: {e}")
        return ""

async def fetch_chainbase(client: httpx.AsyncClient, query: str) -> str:
    return ""
