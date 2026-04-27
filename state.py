import os
import re
import logging
import json
import subprocess
import config
import utils

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
    update_github_secret(f"CONTEXT_{slot}", payload)
    logger.debug(f"[state] Context saved for {thread_id[-10:]}")

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
