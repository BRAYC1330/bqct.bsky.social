import httpx
import logging
import re
import json
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def clean_query(query: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'\s*[!|/][tc]\s*', ' ', query)).strip()

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
        logger.error(f"[SEARCH] Trend fetch failed: {e}")
        return []

async def tavily_search(query: str, time_range: str = None, topic: str = None) -> str:
    if not config.TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY not set"
    try:
        payload = {"query": clean_query(query), "search_depth": "basic", "max_results": 3, "include_answer": True, "include_raw_content": "text"}
        if time_range and str(time_range).lower() in ["day", "week", "month", "year", "d", "w", "m", "y"]:
            payload["time_range"] = str(time_range).lower()
        if topic and str(topic).lower() in ["news", "finance"]:
            payload["topic"] = str(topic).lower()
        headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
            r = await client.post("https://api.tavily.com/search", json=payload, headers=headers, timeout=config.SEARCH_TIMEOUT)
            if r.status_code != 200:
                return f"Error: Tavily {r.status_code}"
            raw = r.json()
            if config.RAW_DEBUG:
                logger.info(f"=== RAW-SEARCH-TAVILY ===\n{json.dumps(raw, ensure_ascii=False, indent=2)}\n=== END ===")
            if "results" not in raw:
                return "Error: Invalid format"
            return json.dumps(raw, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"

async def chainbase_search(query: str) -> str:
    try:
        clean_q = clean_query(query)
        url = f"https://api.chainbase.com/tops/v1/tool/search-narrative-candidates?keyword={clean_q}" if clean_q else "https://api.chainbase.com/tops/v1/tool/list-trending-topics?language=en"
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)) as client:
            r = await client.get(url, timeout=config.SEARCH_TIMEOUT)
            if r.status_code != 200:
                return ""
            data = r.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            eng = [i for i in items if is_english_text(i.get('keyword', '')) and is_english_text(i.get('summary', ''))]
            eng.sort(key=lambda x: x.get('score', 0), reverse=True)
            if config.RAW_DEBUG:
                logger.info(f"=== RAW-SEARCH-CHAINBASE ===\n{json.dumps(eng[:10], ensure_ascii=False, indent=2)}\n=== END ===")
            return json.dumps(eng[:10], ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"

def is_search_result_valid(result, search_type: str) -> bool:
    if not result:
        return False
    if "Error" in str(result):
        return False
    try:
        data = json.loads(result) if isinstance(result, str) else result
        if search_type == "tavily":
            return isinstance(data, dict) and "results" in data and len(data["results"]) > 0
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return len(str(result)) > 50

SEARCH_PROVIDERS = {"tavily": {"func": tavily_search, "supports": ["time_range", "topic"]}, "chainbase": {"func": chainbase_search, "supports": []}}
