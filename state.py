import os
import logging
import json
import config
import utils
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def load_context(thread_id: str) -> tuple:
    slot = utils.get_slot(thread_id)
    val = os.getenv(f"CONTEXT_{slot}", "").strip()
    if not val:
        return "", None
    try:
        data = json.loads(val)
        if isinstance(data, dict) and "h" in data and "m" in data:
            return data["m"], data["h"]
    except Exception:
        pass
    return val, None

def save_context(thread_id: str, context: str, thread_hash: str):
    slot = utils.get_slot(thread_id)
    payload = json.dumps({"h": thread_hash, "m": context}, ensure_ascii=False)
    utils.update_github_secret(f"CONTEXT_{slot}", payload)
    logger.debug(f"[state] Context saved for {thread_id[-10:]}")