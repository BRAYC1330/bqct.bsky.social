import os
import logging
import config
import utils
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

HASH_MARKER = "HASH:"
MEM_MARKER = "|MEM:"

def load_context(thread_id: str) -> tuple:
    slot = utils.get_slot(thread_id)
    val = os.getenv(f"CONTEXT_{slot}", "").strip()
    if not val:
        return "", None
    if val.startswith(HASH_MARKER) and MEM_MARKER in val:
        try:
            parts = val.split(MEM_MARKER, 1)
            if len(parts) == 2:
                h = parts[0].replace(HASH_MARKER, "").strip()
                m = parts[1].strip()
                return m, h
        except Exception:
            pass
    return val, None

def save_context(thread_id: str, context: str, thread_hash: str):
    slot = utils.get_slot(thread_id)
    payload = f"{HASH_MARKER}{thread_hash}{MEM_MARKER}{context}"
    utils.update_github_secret(f"CONTEXT_{slot}", payload)
    logger.debug(f"[state] Context saved for {thread_id[-10:]}")