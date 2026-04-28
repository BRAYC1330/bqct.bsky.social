import logging
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_trending_topics_raw():
    try:
        import httpx
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get("https://api.chainbase.com/v1/trending/topics", headers={"Authorization": f"Bearer {config.PAT}"})
            if r.status_code != 200:
                logger.warning(f"[search] Chainbase trending failed: {r.status_code}")
                return []
            data = r.json()
            trends = data.get("data", [])
            logger.info(f"\033[36m=== PARSED TRENDS (RAW) ===\033[0m")
            for t in trends[:10]:
                kw = t.get("keyword", "?")
                sc = t.get("score")
                rs = t.get("rank_status", "same")
                sm = t.get("summary", "")
                logger.info(f"\033[36m• {kw} | score:{sc} | rank:{rs} | {sm}\033[0m")
            logger.info(f"\033[36m=== END PARSED TRENDS ===\033[0m")
            return trends
    except Exception as e:
        logger.error(f"[search] Trending fetch error: {e}")
        return []

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY: return ""
    try:
        import httpx
        payload = {"query": query, "max_results": 3, "include_answer": True}
        if time_range in ("day", "week", "month", "year"):
            payload["time_range"] = time_range
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.post("https://api.tavily.com/search", json={**payload, "api_key": config.TAVILY_API_KEY})
            if r.status_code == 200:
                results = r.json().get("results", [])
                return "\n".join([f"- {res.get('content', '')}" for res in results[:3]])
    except Exception as e:
        logger.warning(f"[search] Tavily error: {e}")
    return ""

async def fetch_chainbase(keyword: str) -> str:
    try:
        import httpx
        url = "https://api.chainbase.com/tops/v1/tool/search-narrative-candidates"
        params = {"keyword": keyword}
        headers = {"Authorization": f"Bearer {config.PAT}"}
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                logger.warning(f"[search] Chainbase fetch failed: status={r.status_code}")
                return ""
            data = r.json()
            items = data.get("data", data.get("items", []))
            if not isinstance(items, list):
                logger.warning(f"[search] Chainbase unexpected data format")
                return ""
            if not items:
                logger.warning(f"[search] Chainbase returned 0 results for '{keyword}'")
                return ""
            formatted_lines = []
            for item in items[:5]:
                kw = item.get("keyword", item.get("narrative", ""))
                sm = item.get("summary", item.get("description", ""))
                if kw and sm:
                    formatted_lines.append(f"{kw}: {sm}")
            if not formatted_lines:
                logger.warning(f"[search] Chainbase no valid keyword/summary pairs for '{keyword}'")
                return ""
            output = "\n\n".join(formatted_lines)
            logger.info(f"\033[36m=== CHAINBASE CONTEXT (MODEL INPUT) ===\033[0m\n{output}")
            return output
    except Exception as e:
        logger.warning(f"[search] Chainbase error: {e}")
    return ""