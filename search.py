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
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(f"https://api.chainbase.com/v1/search?q={keyword}", headers={"Authorization": f"Bearer {config.PAT}"})
            if r.status_code == 200:
                data = r.json()
                results = data.get("data", [])
                if not results: return ""
                formatted = []
                for res in results:
                    kw = res.get("keyword", "")
                    summary = res.get("summary", "")
                    formatted.append(f"KEYWORD: {kw}\nSUMMARY: {summary}")
                output = "\n\n".join(formatted)
                logger.info(f"\033[36m=== CHAINBASE CONTEXT (MODEL INPUT) ===\033[0m\n{output}")
                return output
    except Exception as e:
        logger.warning(f"[search] Chainbase error: {e}")
    return ""