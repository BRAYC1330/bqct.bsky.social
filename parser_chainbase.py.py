import logging
from typing import List, Dict, Any
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def is_english_text(text: str) -> bool:
    if not text:
        return False
    return sum(1 for c in text if ord(c) < 128) / len(text) > 0.7

def parse_trending_items(items: Any) -> List[Dict]:
    if not isinstance(items, list):
        items = items.get("items", []) if isinstance(items, dict) else []
    eng = [i for i in items if is_english_text(i.get("keyword", "")) and is_english_text(i.get("summary", ""))]
    eng.sort(key=lambda x: x.get("score", 0), reverse=True)
    return eng[:10]

def parse_search_results(data: Any) -> List[Dict]:
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    if not isinstance(items, list):
        return []
    eng = [i for i in items if is_english_text(i.get("keyword", "")) and is_english_text(i.get("summary", ""))]
    return sorted(eng, key=lambda x: x.get("score", 0), reverse=True)[:6]

def format_chainbase_results(items: List[Dict]) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        kw = item.get("keyword", "Unknown")
        score = item.get("score", 0)
        rank = item.get("current_rank", "N/A")
        status = item.get("rank_status", "same")
        summary = item.get("summary", "")[:200]
        lines.append(f"{i}. {kw} (Score: {score:.1f} | Rank: {rank} | Trend: {status})\nSummary: {summary}")
    return "\n\n".join(lines)

def parse_digest_context(items: List[Dict], limit: int = 6) -> List[Dict]:
    result = []
    for item in items[:limit]:
        result.append({
            "id": item.get("id", ""),
            "keyword": item.get("keyword", ""),
            "summary": item.get("summary", ""),
            "score": item.get("score", 0),
            "rank_status": item.get("rank_status", "same"),
            "is_new": item.get("is_new", False)
        })
    return result