import logging
import re
import config
import utils
logger = logging.getLogger(__name__)
def _clean_tavily_content(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_#~`>]', '', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    result = ' '.join(text.split())
    return result.strip()
async def get_trending_topics_raw():
    try:
        import httpx
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics", params={"language": "en"})
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
            trends = filtered[:10]
            logger.info(f"\033[36m=== PARSED TRENDS (RAW) ===\033[0m")
            for t in trends:
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
        payload = {
            "query": query,
            "include_answer": "basic",
            "search_depth": "basic",
            "max_results": 5,
            "include_raw_content": "text",
            "exclude_domains": ["youtube.com"],
            "api_key": config.TAVILY_API_KEY
        }
        if time_range in ("day", "week", "month", "year"):
            payload["time_range"] = time_range
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.post("https://api.tavily.com/search", json=payload)
            if r.status_code == 200:
                data = r.json()
                answer = data.get("answer", "")
                results = data.get("results", [])
                parts = []
                if answer:
                    clean_answer = _clean_tavily_content(answer)
                    if clean_answer:
                        parts.append(f"[SUMMARY] {clean_answer}")
                for res in results[:5]:
                    title = res.get("title", "").strip()
                    content = _clean_tavily_content(res.get("content", ""))
                    if len(content) > 1600:
                        content = content[:1600].rsplit(' ', 1)[0] + "..."
                    if title and content:
                        parts.append(f"• {title}: {content}")
                    elif content:
                        parts.append(f"• {content}")
                final_output = "\n".join(parts)
                logger.info(f"\033[32m[TAVILY PARSED CONTEXT]\n{final_output}\033[0m")
                return final_output
    except Exception as e:
        logger.warning(f"[search] Tavily error: {e}")
        return ""
async def fetch_chainbase(keyword: str) -> str:
    try:
        import httpx
        url = "https://api.chainbase.com/tops/v1/tool/search-narrative-candidates"
        params = {"keyword": keyword}
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(url, params=params)
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
                if not kw or not sm: continue
                if not utils.is_english(sm): continue
                dedup_key = (kw.lower(), sm[:50].lower())
                if dedup_key in seen: continue
                seen.add(dedup_key)
                valid_items.append((kw, sm))
                if len(valid_items) >= 5: break
            if not valid_items:
                logger.warning(f"[search] Chainbase returned 0 valid English results for '{keyword}'")
                return ""
            formatted_lines = [f"{kw}: {sm}" for kw, sm in valid_items]
            output = "\n".join(formatted_lines)
            logger.info(f"\033[36m=== CHAINBASE CONTEXT (MODEL INPUT) ===\033[0m\n{output}")
            return output
    except Exception as e:
        logger.warning(f"[search] Chainbase error: {e}")
        return ""