import logging
from typing import Any
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def clean_search_results(raw: Any) -> str:
    if not raw: return ""
    if isinstance(raw, list):
        return " ".join([r.get("title", "") + " " + r.get("content", "") for r in raw])
    return str(raw)

def validate_response(data: dict) -> bool:
    if not isinstance(data, dict): return False
    if "results" not in data: return False
    results = data.get("results", [])
    return isinstance(results, list) and len(results) > 0