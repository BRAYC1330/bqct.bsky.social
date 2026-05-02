import logging
import re
import httpx
from typing import List, Dict, Any
import config
import utils

logger = logging.getLogger(__name__)


def _clean_tavily_content(text: str) -> str:
    """Clean Tavily search result content.
    
    Args:
        text: Raw text from Tavily API
        
    Returns:
        Cleaned text with markdown and links removed
    """
    if not text:
        return ""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Remove markdown links
    text = re.sub(r'[*_#~`>]', '', text)  # Remove markdown formatting
    text = re.sub(r'\s*\n\s*', '\n', text)  # Normalize whitespace
    result = ' '.join(text.split())
    return result.strip()
async def get_trending_topics_raw() -> List[Dict[str, Any]]:
    """Fetch trending topics from Chainbase API.
    
    Returns:
        List of filtered and sorted trending topic dictionaries
    """
    try:
        async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
            r = await client.get(
                "https://api.chainbase.com/tops/v1/tool/list-trending-topics",
                params={"language": "en"}
            )
            if r.status_code != 200:
                logger.warning(f"[search] Chainbase trending failed: {r.status_code}")
                return []
            
            data = r.json()
            raw_items = data.get("items", [])
            
            # Filter for English content only
            filtered = [t for t in raw_items if utils.is_english(t.get("summary", ""))]
            
            # Sort by current_rank and take top 10
            trends = sorted(filtered, key=lambda x: x.get("current_rank", 999))[:10]
            
            logger.info("=== PARSED TRENDS (RAW) ===")
            for t in trends:
                kw = t.get("keyword", "?")
                sc = t.get("score")
                rs = t.get("rank_status", "same")
                cr = t.get("current_rank", "?")
                logger.info(f"• {kw} | score:{sc} | rank:{rs} | rank_pos:{cr}")
            logger.info("=== END PARSED TRENDS ===")
            
            return trends
    except httpx.RequestError as e:
        logger.error(f"[search] Trending fetch network error: {e}")
        return []
    except Exception as e:
        logger.error(f"[search] Trending fetch error: {e}")
        return []


async def fetch_tavily(query: str, time_range: str = "") -> str:
    """Fetch search results from Tavily API.
    
    Args:
        query: Search query string
        time_range: Optional time filter (day/week/month/year)
        
    Returns:
        Formatted search results or empty string on failure
    """
    if not config.TAVILY_API_KEY:
        logger.debug("[search] Tavily API key not configured")
        return ""
    
    try:
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
                logger.info(f"[TAVILY PARSED CONTEXT]\n{final_output}")
                return final_output
    except httpx.RequestError as e:
        logger.warning(f"[search] Tavily network error: {e}")
    except Exception as e:
        logger.warning(f"[search] Tavily error: {e}")
    return ""
async def fetch_chainbase(keyword: str) -> str:
    """Fetch narrative candidates from Chainbase API.
    
    Args:
        keyword: Search keyword
        
    Returns:
        Formatted search results or empty string on failure
    """
    try:
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
                logger.warning("[search] Chainbase unexpected data format")
                return ""
            
            seen: set = set()
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
                logger.warning(f"[search] Chainbase returned 0 valid English results for '{keyword}'")
                return ""
            
            formatted_lines = [f"{kw}: {sm}" for kw, sm in valid_items]
            output = "\n".join(formatted_lines)
            logger.info(f"=== CHAINBASE CONTEXT (MODEL INPUT) ===\n{output}")
            return output
    except httpx.RequestError as e:
        logger.warning(f"[search] Chainbase network error: {e}")
        return ""
    except Exception as e:
        logger.warning(f"[search] Chainbase error: {e}")
        return ""