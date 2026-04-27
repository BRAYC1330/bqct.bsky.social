import os
import logging
import httpx
import json
import config
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def is_english_text(text: str) -> bool:
    if not text:
        return False
    return sum(1 for c in text if ord(c) < 128) / len(text) > 0.7

async def get_trending_topics_raw() -> list:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
            r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en", timeout=config.SEARCH_TIMEOUT)
            if r.status_code != 200:
                return []
            data = r.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            eng = [i for i in items if is_english_text(i.get('keyword', '')) and is_english_text(i.get('summary', ''))]
            eng.sort(key=lambda x: x.get('score', 0), reverse=True)
            if config.RAW_DEBUG:
                logger.info(f"=== RAW-TRENDS ===\n{json.dumps(eng[:10], ensure_ascii=False, indent=2)}\n=== END ===")
            return eng[:10]
    except Exception as e:
        logger.error(f"Trend fetch failed: {e}")
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
        logger.error(f"Tavily error: {e}")
        return ""

async def fetch_chainbase(query: str) -> str:
    if not query:
        return ""
    logger.info(f"Fetching Chainbase for: {query}")
    url = f"https://api.chainbase.com/tops/v1/tool/search-narrative-candidates?keyword={query}"
    try:
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning(f"Chainbase status: {r.status_code}")
                return ""
            raw_data = r.json()
            if config.RAW_DEBUG:
                logger.info(f"CHAINBASE_RAW_RESPONSE:\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}")
            items = raw_data.get("items", [])
            eng_items = [i for i in items if is_english_text(i.get("keyword", "")) and is_english_text(i.get("summary", ""))]
            eng_items.sort(key=lambda x: x.get("score", 0), reverse=True)
            if not eng_items:
                logger.warning("No English results from Chainbase")
                return ""
            lines = []
            for item in eng_items[:5]:
                kw = item.get("keyword", "")
                score = item.get("score", 0)
                summary = item.get("summary", "")
                lines.append(f"{kw} [Score: {int(score)}]: {summary}")
            result = "\n\n".join(lines)
            logger.info(f"Chainbase results length: {len(result)}")
            return result
    except Exception as e:
        logger.error(f"Chainbase fetch failed: {e}")
        return ""