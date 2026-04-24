import asyncio
import hashlib
import os
import subprocess
import logging
from httpx import AsyncClient, HTTPStatusError, Timeout
import config
import parser as ctx_parser
import state
import generator
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def count_graphemes(text: str) -> int:
    return len(text) if text else 0

async def with_retry(func, max_attempts: int = 3, backoff: float = 1.5):
    for attempt in range(max_attempts):
        try:
            return await func()
        except HTTPStatusError as e:
            if e.response.status_code in [429, 502, 503, 504] and attempt < max_attempts - 1:
                await asyncio.sleep(3 * (backoff ** attempt))
                continue
            raise
        except Exception:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1 * (backoff ** attempt))
                continue
            raise

def hash_to_slot(value: str, slot_count: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % slot_count

def get_async_client(timeout: float = 30.0) -> AsyncClient:
    return AsyncClient(timeout=Timeout(timeout, connect=config.CONNECT_TIMEOUT))

def update_github_secret(key: str, value: str) -> None:
    if not value or not key:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat:
        return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e:
        logger.error(f"[utils] Secret update failed: {e}")

async def process_reply(client, llm, task, max_chars=280, suffix="", temperature=0.7, search_data=""):
    uri = task["uri"]
    user_text = task["text"]
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    memory = state.load_context(root_uri)
    root_thread = f"Root: {chain.get('root_text', '')[:200]}"
    final_ctx = ctx_parser.prepare_context(memory, root_thread, search_data, user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=max_chars, temperature=temperature)
    if count_graphemes(reply) > 293:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=260, temperature=temperature)
    if count_graphemes(reply) > 293:
        return
    reply = reply.strip() + suffix
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    if root_uri != os.environ.get("ACTIVE_DIGEST_URI", "").strip():
        state.save_context(root_uri, generator.update_summary(llm, memory, user_text, reply))