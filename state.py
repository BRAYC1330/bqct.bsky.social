import os
import hashlib
import subprocess
import logging
import config
import re
import json
import utils
from logging_config import setup_logging

logger = logging.getLogger(__name__)

def update_github_secret(key: str, value: str) -> None:
    if not re.match(r'^[A-Z0-9_]+$', key):
        logger.error(f"[state] Invalid secret key format: {key}")
        return
    if not value:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat:
        return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e:
        logger.error(f"[state] Secret update failed: {e}")

def _slot(tid: str) -> int:
    return int(hashlib.sha256(tid.encode()).hexdigest(), 16) % config.CONTEXT_SLOT_COUNT

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

def save_context(thread_id: str, memory: str):
    slot = _slot(thread_id)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat or not memory:
        return
    cmd = ["gh", "secret", "set", f"CONTEXT_{slot}", "--body", memory[:250], "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e:
        logger.error(f"[CTX] Save failed: {e}")

def merge_contexts(memory: str, root_thread: str, search_data: str, user_query: str) -> str:
    parts = []
    if memory:
        parts.append(f"[MEMORY]\n{memory}")
    if root_thread:
        parts.append(f"[ROOT_THREAD]\n{root_thread}")
    if search_data:
        parts.append(f"[SEARCH]\n{search_data}")
    if user_query:
        parts.append(f"[QUERY]\n{user_query}")
    final = "\n".join(parts)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-FINAL-CONTEXT ===\n{final}\n=== END ===")
    return final
