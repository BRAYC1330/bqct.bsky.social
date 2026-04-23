import os
import hashlib
import asyncio
import json
import logging
import shlex
import re
import config
from logging_config import setup_logging

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
    safe_memory = shlex.quote(memory[:250])
    safe_repo = shlex.quote(repo)
    safe_slot = shlex.quote(f"CONTEXT_{slot}")
    proc = await asyncio.create_subprocess_exec(
        "gh", "secret", "set", safe_slot, "--body", safe_memory, "--repo", safe_repo,
        env={**os.environ, "GH_TOKEN": pat},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

def load_digest_context() -> str:
    raw = os.environ.get("CONTEXT_DIGEST", "")
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            parts = []
            for item in data:
                kw = item.get("keyword", "")
                summary = item.get("summary", "")
                score = item.get("score", 0)
                parts.append(f"{kw} (score: {score}): {summary}")
            return "\n".join(parts)
        return ""
    except json.JSONDecodeError:
        return ""

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
    return "\n".join(parts)
