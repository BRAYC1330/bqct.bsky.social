import os
import hashlib
import asyncio
import json
import logging
import re
import config
from logging_config import setup_logging
from utils import update_github_secret
setup_logging()
logger = logging.getLogger(__name__)

def _validate_input(value: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_\-\.:@/]+$', value))

def _slot(tid: str) -> int:
    if not _validate_input(tid):
        raise ValueError("Invalid thread_id")
    return int(hashlib.sha256(tid.encode()).hexdigest(), 16) % config.CONTEXT_SLOT_COUNT

def load_thread_context(thread_id: str) -> str:
    if not _validate_input(thread_id):
        return ""
    slot = _slot(thread_id)
    return os.getenv(f"CONTEXT_{slot}", "") or ""

async def save_thread_context(thread_id: str, memory: str):
    if not _validate_input(thread_id) or not _validate_input(memory):
        return
    slot = _slot(thread_id)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat or not memory:
        return
    await update_github_secret(f"CONTEXT_{slot}", memory, pat, repo)

def load_digest_context() -> str:
    raw = os.environ.get("CONTEXT_DIGEST", "")
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return "\n".join(f"{i.get('keyword', '')} (score: {i.get('score', 0)}): {i.get('summary', '')}" for i in data)
        return ""
    except json.JSONDecodeError:
        return ""