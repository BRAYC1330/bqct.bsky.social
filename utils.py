import os
import re
import hashlib
import subprocess
import logging
import asyncio
import random
import httpx
from typing import Any, Optional
import config
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

def count_graphemes(text: str) -> int:
    return len(text) if text else 0

def sanitize_input(text: str, max_len: int = 2000) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text

def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text:
        return 0
    if llm is not None:
        try:
            return len(llm.tokenize(text.encode("utf-8")))
        except Exception:
            pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))

def validate_and_fix_output(text: str) -> str:
    if not text:
        return "Invalid response."
    text = text.strip()
    prefixes_to_remove = ["Answer:", "Here is", "Sure,", "Of course", "Based on"]
    for p in prefixes_to_remove:
        if text.startswith(p):
            text = text[len(p):].strip().lstrip(": ")
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) > 2:
        text = " ".join(sentences[:2])
        if not any(text.endswith(c) for c in ".!?"):
            text += "."
    elif not any(text.endswith(c) for c in ".!?"):
        text += "."
    if len(text) > 300:
        last_dot = text[:299].rfind(".")
        text = text[:last_dot+1] if last_dot != -1 else text[:297] + "..."
    return text

def get_slot(value: str, slot_count: int = None) -> int:
    count = slot_count if slot_count is not None else config.CONTEXT_SLOT_COUNT
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % count

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

async def request_with_retry(client, method, url, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            r = await client.request(method, url, **kwargs)
            if r.status_code == 429:
                retry_after = int(r.headers.get("retry-after", 2 ** attempt))
                delay = retry_after + random.uniform(0, 1)
                await asyncio.sleep(delay)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
            continue

def iter_thread_posts(node):
    if not node or not isinstance(node, dict):
        return
    if node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return
    post = node.get("post", {})
    record = post.get("record", {})
    text = record.get("text") if record else post.get("value", {}).get("text")
    if text:
        yield {
            "uri": post.get("uri", ""),
            "cid": post.get("cid", ""),
            "handle": post.get("author", {}).get("handle", ""),
            "text": text,
            "is_root": False
        }
    for reply_node in node.get("replies", []):
        yield from iter_thread_posts(reply_node)

async def process_reply(client, llm, task, max_chars=240, suffix="", temperature=0.7, search_data="", link_content=""):
    import state
    import generator
    import bsky
    uri = task["uri"]
    user_text = sanitize_input(task["text"])
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    root_thread = sanitize_input(chain.get("root_text", ""))
    full_thread_text = sanitize_input(chain.get("full_text", ""), max_len=4000)
    current_hash = hashlib.sha256(full_thread_text.encode()).hexdigest()
    cached_mem, stored_hash = state.load_context(root_uri)
    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] THREAD_HASH_CURRENT: {current_hash}")
        logger.info(f"[DEBUG-OWNER] THREAD_HASH_STORED: {stored_hash or 'NONE'}")
    if stored_hash == current_hash and cached_mem:
        final_context = cached_mem
        if config.DEBUG_OWNER:
            logger.info("[DEBUG-OWNER] CACHE_STATUS: HIT")
    else:
        final_context = generator.update_context_memory(llm, full_thread_text)
        state.save_context(root_uri, final_context, current_hash)
        if config.DEBUG_OWNER:
            logger.info("[DEBUG-OWNER] CACHE_STATUS: MISS")
    combined_search = sanitize_input(search_data)
    if link_content:
        combined_search = f"{combined_search}\n\n[EXTRACTED_LINKS]\n{sanitize_input(link_content)}" if combined_search else f"[EXTRACTED_LINKS]\n{sanitize_input(link_content)}"
    reply = generator.get_reply(llm, final_context, root_thread, combined_search, user_text)
    reply = validate_and_fix_output(reply)
    max_body = max_chars - len(suffix)
    if count_tokens(reply, llm) > int(max_body * config.TOKEN_TO_CHAR_RATIO):
        reply = reply[:max_body].rsplit(" ", 1)[0] + "."
    if len(reply) > max_body:
        reply = reply[:max_body].rsplit(".", 1)[0] + "." if "." in reply[:max_body] else reply[:max_body-3] + "..."
    await bsky.post_reply(client, config.BOT_DID, reply + suffix, root_uri, root_cid, uri, parent_cid)