import logging
import httpx
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_trending_topics_raw() -> list:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
            r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en", timeout=config.SEARCH_TIMEOUT)
            logger.info(f"[search] Chainbase trends raw status: {r.status_code}")
            if r.status_code != 200: return []
            from parser_chainbase import parse_trending_items
            return parse_trending_items(r.json())
    except Exception as e:
        logger.error(f"[search] Trend fetch failed: {e}")
        return []

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY: return ""
    url = "https://api.tavily.com/search"
    headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": "text"}
    if time_range and time_range.lower() in ("day", "week", "month", "year"):
        payload["time_range"] = time_range.lower()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            logger.info(f"[search] Tavily raw response status: {r.status_code}")
            r.raise_for_status()
            from parser_tavily import clean_search_results
            return clean_search_results(r.json().get("results", []))
    except Exception as e:
        logger.error(f"[search] Tavily error: {e}")
        return ""

async def fetch_chainbase(query: str) -> str:
    if not query: return ""
    try:
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            url = f"https://api.chainbase.com/tops/v1/tool/search-narrative-candidates?keyword={query}"
            r = await client.get(url, timeout=config.SEARCH_TIMEOUT)
            logger.info(f"[search] Chainbase search raw response status: {r.status_code}")
            if r.status_code != 200: return ""
            from parser_chainbase import format_chainbase_results, parse_search_results
            items = parse_search_results(r.json())
            return format_chainbase_results(items)
    except Exception as e:
        logger.error(f"[search] Chainbase error: {e}")
        return ""