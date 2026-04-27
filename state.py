import os
import hashlib
import subprocess
import logging
import config
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def _slot(tid: str) -> int:
    return int(hashlib.sha256(tid.encode()).hexdigest(), 16) % config.CONTEXT_SLOT_COUNT

def load_context(thread_id: str) -> str:
    slot = _slot(thread_id)
    return os.getenv(f"CONTEXT_{slot}", "") or ""

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
    if search_
        parts.append(f"[SEARCH]\n{search_data}")
    if user_query:
        parts.append(f"[QUERY]\n{user_query}")
    final = "\n".join(parts)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-FINAL-CONTEXT ===\n{final}\n=== END ===")
    return final