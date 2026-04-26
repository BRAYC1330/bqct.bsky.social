import logging
from typing import List, Dict, Any
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def is_english_text(text: str) -> bool:
    if not text: return False
    return sum(1 for c in text if ord(c) < 128) / len(text) > 0.7

def parse_trending_items(items: Any) -> List[Dict]:
    if not isinstance(items, list):
        items = items.get("items", []) if isinstance(items, dict) else []
    eng = [i for i in items if is_english_text(i.get("keyword", "")) and is_english_text(i.get("summary", ""))]
    eng.sort(key=lambda x: x.get("score", 0), reverse=True)
    return eng[:10]

def parse_search_results(data: Any) -> List[Dict]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        raw = data.get("items")
        items = raw if isinstance(raw, list) else [data]
    else:
        return []

    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kw = item.get("keyword", "")
        summary = item.get("summary", "")
        if is_english_text(kw) and is_english_text(summary):
            valid.append(item)
            
    valid.sort(key=lambda x: x.get("score", 0), reverse=True)
    return valid[:6]

def format_chainbase_results(items: List[Dict]) -> str:
    lines = []
    for item in items:
        kw = item.get("keyword", "Unknown")
        summary = item.get("summary", "")
        lines.append(f"{kw}: {summary}")
    return "\n\n".join(lines)