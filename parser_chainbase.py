import logging
from typing import List, Dict, Any
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def is_english_text(text: str) -> tuple[bool, float]:
    if not text:
        return False, 0.0
    ascii_count = sum(1 for c in text if ord(c) < 128)
    ratio = ascii_count / len(text)
    return ratio > 0.7, ratio

def parse_trending_items(items: Any) -> List[Dict]:
    if not isinstance(items, list):
        items = items.get("items", []) if isinstance(items, dict) else []
    eng = []
    for i in items:
        kw_ok, kw_ratio = is_english_text(i.get("keyword", ""))
        sum_ok, sum_ratio = is_english_text(i.get("summary", ""))
        if kw_ok and sum_ok:
            eng.append(i)
        else:
            logger.debug(f"Filtered item: keyword_ratio={kw_ratio:.2f}, summary_ratio={sum_ratio:.2f}")
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
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        kw = item.get("keyword", "")
        summary = item.get("summary", "")
        kw_ok, kw_ratio = is_english_text(kw)
        sum_ok, sum_ratio = is_english_text(summary)
        if kw_ok and sum_ok:
            valid.append(item)
        else:
            logger.debug(f"Item {idx} filtered: keyword='{kw[:20]}...' ratio={kw_ratio:.2f}, summary_ratio={sum_ratio:.2f}, score={item.get('score', 'N/A')}")
            
    valid.sort(key=lambda x: x.get("score", 0), reverse=True)
    logger.debug(f"parse_search_results: {len(valid)}/{len(items)} items passed filter, sorted by score")
    return valid[:6]

def format_chainbase_results(items: List[Dict]) -> str:
    lines = []
    for item in items:
        kw = item.get("keyword", "Unknown")
        summary = item.get("summary", "")
        lines.append(f"{kw}: {summary}")
    return "\n\n".join(lines)