import logging
import httpx
import json
import config
from logging_config import setup_logging
from copy import deepcopy

setup_logging()
logger = logging.getLogger(__name__)

NOISE_FIELDS = {
    "id", "tweet_urls", "authors", "analysis_time", 
    "snapshot_time", "first_tweet_time", "is_manual", "is_new"
}

def _clean_json_log(data):
    if isinstance(data, dict):
        return {k: _clean_json_log(v) for k, v in data.items() if k not in NOISE_FIELDS}
    elif isinstance(data, list):
        return [_clean_json_log(item) for item in data]
    return data

async def get_trending_topics_raw() -> list:
    url = "https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en"
    logger.info(f"URL: {url}")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
            r = await client.get(url, timeout=config.SEARCH_TIMEOUT)
            logger.info(f"Chainbase status: {r.status_code}")
            if r.status_code != 200:
                return []
            raw_data = r.json()
            if config.RAW_DEBUG:
                logger.debug(f"Chainbase body: {json.dumps(_clean_json_log(raw_data), ensure_ascii=False)}")
            from parser_chainbase import parse_trending_items
            return parse_trending_items(raw_data)
    except Exception as e:
        logger.error(f"Trend fetch failed: {e}")
        return []

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY:
        return ""
    url = "https://api.tavily.com/search"
    logger.info(f"URL: {url}")
    headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": "text"}
    if time_range and time_range.lower() in ("day", "week", "month", "year"):
        payload["time_range"] = time_range.lower()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            logger.info(f"Tavily status: {r.status_code}")
            if config.RAW_DEBUG:
                logger.debug(f"Tavily body: {json.dumps(r.json(), ensure_ascii=False)}")
            r.raise_for_status()
            from parser_tavily import clean_search_results
            results = r.json().get("results", [])
            logger.info(f"Tavily results count: {len(results)}")
            return clean_search_results(results)
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return ""

async def fetch_chainbase(query: str) -> str:
    if not query:
        logger.info(f"Chainbase skipped: empty keyword")
        return ""
    try:
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            url = f"https://api.chainbase.com/tops/v1/tool/search-narrative-candidates?keyword={query}"
            logger.info(f"URL: {url}")
            r = await client.get(url, timeout=config.SEARCH_TIMEOUT)
            logger.info(f"Chainbase Search status: {r.status_code}")
            if r.status_code != 200:
                logger.info(f"CHAINBASE_RAW_RESPONSE: {r.text}")
                return ""
            raw_data = r.json()
            logger.info(f"CHAINBASE_RAW_RESPONSE: {json.dumps(raw_data, ensure_ascii=False)}")
            if config.RAW_DEBUG:
                logger.debug(f"Chainbase Search body (cleaned): {json.dumps(_clean_json_log(raw_data), ensure_ascii=False)}")
            from parser_chainbase import format_chainbase_results, parse_search_results
            items = parse_search_results(raw_data)
            logger.info(f"Chainbase Search results count: {len(items)}")
            if items:
                preview = " | ".join([f"{i.get('keyword')}: {i.get('summary', '')[:50]}..." for i in items[:2]])
                logger.info(f"CHAINBASE_PARSED_PREVIEW: {preview}")
            search_text = format_chainbase_results(items)
            if config.RAW_DEBUG:
                logger.info(f"Chainbase context passed to model:\n{search_text}")
            return search_text
    except Exception as e:
        logger.error(f"Chainbase error: {e}")
        return ""