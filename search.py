import logging
import config
import utils
logger = logging.getLogger(__name__)
async def get_trending_topics_raw(client):
    try:
        r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics", params={"language": "en"}, timeout=config.SEARCH_TIMEOUT)
        if r.status_code != 200:
            logger.warning(f"[search] Chainbase trending failed: {r.status_code}")
            return []
        data = r.json()
        trends = data.get("data", [])
        filtered = []
        for t in trends:
            sm = t.get("summary", "")
            if utils.is_english(sm):
                filtered.append(t)
        return filtered[:10]
    except Exception as e:
        logger.error(f"[search] Trending fetch error: {e}")
        return []
async def fetch_tavily(client, query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY: return ""
    try:
        payload = {"query": query, "max_results": 3, "include_answer": True}
        if time_range in ("day", "week", "month", "year"):
            payload["time_range"] = time_range
        r = await client.post("https://api.tavily.com/search", json={**payload, "api_key": config.TAVILY_API_KEY}, timeout=config.SEARCH_TIMEOUT)
        if r.status_code == 200:
            results = r.json().get("results", [])
            valid = [f"- {res.get('content', '')}" for res in results[:3] if utils.is_english(res.get('content', ''))]
            return "\n".join(valid)
    except Exception as e:
        logger.warning(f"[search] Tavily error: {e}")
        return ""
async def fetch_chainbase(client, keyword: str) -> str:
    try:
        url = "https://api.chainbase.com/tops/v1/tool/search-narrative-candidates"
        params = {"keyword": keyword}
        r = await client.get(url, params=params, timeout=config.SEARCH_TIMEOUT)
        if r.status_code != 200:
            logger.warning(f"[search] Chainbase fetch failed: status={r.status_code}")
            return ""
        data = r.json()
        items = data.get("data", data.get("items", []))
        if not isinstance(items, list):
            logger.warning(f"[search] Chainbase unexpected data format")
            return ""
        seen = set()
        valid_items = []
        for item in items:
            kw = str(item.get("keyword") or item.get("narrative") or "").strip()
            sm = str(item.get("summary") or item.get("description") or "").strip()
            if not kw or not sm:
                continue
            if not utils.is_english(sm):
                continue
            dedup_key = (kw.lower(), sm[:50].lower())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            valid_items.append((kw, sm))
            if len(valid_items) >= 5:
                break
        if not valid_items:
            return ""
        formatted_lines = [f"{kw}: {sm}" for kw, sm in valid_items]
        return "\n".join(formatted_lines)
    except Exception as e:
        logger.warning(f"[search] Chainbase error: {e}")
        return ""