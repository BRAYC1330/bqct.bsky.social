import os
import logging
import httpx
import time
import json
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
    logger.info(f"[SEARCH:TAVILY] Query: '{query}' | Time: {time_range or 'any'}")
    if not config.TAVILY_API_KEY:
        logger.warning("[SEARCH:TAVILY] API key not set")
        return ""
    try:
        payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": True}
        if time_range:
            payload["time_range"] = time_range
        logger.info(f"[SEARCH:TAVILY] Request payload: {json.dumps(payload)}")
        r = await client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"}, json=payload)
        r.raise_for_status()
        result = clean_search_results(r.json().get("results", []))
        logger.info(f"[SEARCH:TAVILY] Response: {len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"[SEARCH:TAVILY] Error: {e}")
        return ""

async def fetch_chainbase_raw(client: httpx.AsyncClient, keyword: str) -> list:
    logger.info(f"[SEARCH:CHAINBASE] Keyword query: '{keyword}'")
    try:
        safe_kw = httpx.URL(keyword).raw_path.decode()
        url = f"https://api.chainbase.com/tops/v1/tool/search-narrative-candidates?keyword={safe_kw}"
        logger.info(f"[SEARCH:CHAINBASE] Request URL: {url}")
        r = await client.get(url, timeout=config.SEARCH_TIMEOUT)
        if r.status_code != 200:
            logger.warning(f"[SEARCH:CHAINBASE] HTTP {r.status_code}")
            return []
        data = r.json()
        items = data.get("items", [])
        result = [
            {
                "id": str(item.get("id", "")),
                "keyword": item.get("keyword", ""),
                "summary": item.get("summary", ""),
                "score": int(item.get("score", 0)),
                "rank_status": item.get("rank_status", "same")
            }
            for item in items[:5]
        ]
        logger.info(f"[SEARCH:CHAINBASE] Response: {len(result)} items")
        return result
    except Exception as e:
        logger.error(f"[SEARCH:CHAINBASE] Error: {e}")
        return []

async def fetch_chainbase(client: httpx.AsyncClient, keyword: str) -> str:
    items = await fetch_chainbase_raw(client, keyword)
    if not items:
        return ""
    lines = []
    for item in items[:3]:
        kw = item.get("keyword", "")
        summary = item.get("summary", "")
        score = item.get("score", 0)
        rank = item.get("rank_status", "same")
        emoji = config.TREND_EMOJIS.get(rank, "")
        lines.append(f"{emoji} {kw} [{score}]: {summary[:150]}")
    return " | ".join(lines)