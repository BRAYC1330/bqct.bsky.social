import asyncio
import hashlib
import os
import subprocess
import logging
import config
import generator
import state
import bsky
import parser as ctx_parser
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def count_graphemes(text: str) -> int:
    return len(text) if text else 0

def hash_to_slot(value: str, slot_count: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % slot_count

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

def _get_active_digest_uri() -> str:
    return os.environ.get("ACTIVE_DIGEST_URI", "").strip()

async def process_reply(client, llm, task, max_chars=240, suffix="", temperature=0.7, search_data="", link_content=""):
    uri = task["uri"]
    user_text = task["text"]
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    
    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    memory = state.load_context(root_uri)
    root_thread = chain.get("root_text", "")[:200]
    
    combined_search = search_data
    if link_content:
        combined_search = f"{search_data}\n\n[EXTRACTED_LINKS]\n{link_content}" if search_data else f"[EXTRACTED_LINKS]\n{link_content}"
    
    reply = generator.get_reply(llm, memory, root_thread, combined_search, user_text)
    
    if count_graphemes(reply) > 240:
        reply = reply[:240].rsplit(" ", 1)[0] + "..."
    
    reply = reply.strip() + suffix
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    
    if root_uri != _get_active_digest_uri():
        history = f"Root: {root_thread} | Query: {user_text} | Search: {combined_search[:300]} | Reply: {reply}"
        state.save_context(root_uri, llm, history)