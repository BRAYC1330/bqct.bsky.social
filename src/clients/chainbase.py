import logging
from src.state import settings as config
from src.content import sanitizer

logger = logging.getLogger(__name__)

async def get_trending():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics", params={"language": "en"})
            if r.status_code != 200: return []
            data = r.json()
            raw_items = data.get("items", [])
            filtered = [t for t in raw_items if sanitizer.is_english(t.get("summary", ""))]
            trends = sorted(filtered, key=lambda x: x.get("current_rank", 999))[:10]
            return trends
    except Exception:
        return []

async def fetch_narrative(keyword):
    import httpx
    try:
        url = "https://api.chainbase.com/tops/v1/tool/search-narrative-candidates"
        params = {"keyword": keyword}
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200: return ""
            data = r.json()
            items = data.get("data", data.get("items", []))
            if not isinstance(items, list): return ""
            seen = set()
            valid_items = []
            for item in items:
                kw = str(item.get("keyword") or item.get("narrative") or "").strip()
                sm = str(item.get("summary") or item.get("description") or "").strip()
                if not kw or not sm: continue
                if not sanitizer.is_english(sm): continue
                dedup_key = (kw.lower(), sm[:50].lower())
                if dedup_key in seen: continue
                seen.add(dedup_key)
                valid_items.append((kw, sm))
                if len(valid_items) >= 5: break
            if not valid_items: return ""
            return "\n".join([f"{kw}: {sm}" for kw, sm in valid_items])
    except Exception:
        return ""
