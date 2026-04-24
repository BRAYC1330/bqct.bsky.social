import os
import hashlib
import subprocess
import logging
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def count_graphemes(text: str) -> int: return len(text) if text else 0
def hash_to_slot(value: str, slot_count: int) -> int: return int(hashlib.sha256(value.encode()).hexdigest(), 16) % slot_count
def update_github_secret(key: str, value: str) -> None:
    if not value or not key: return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat: return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try: subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e: logger.error(f"[utils] Secret update failed: {e}")

def _get_active_digest_uri() -> str: return os.environ.get("ACTIVE_DIGEST_URI", "").strip()

async def process_reply(client, llm, task, max_chars=240, suffix="", temperature=0.7, search_data="", link_content=""):
    import state
    import generator
    import bsky

    uri = task["uri"]
    user_text = task["text"]
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return

    root_uri = chain.get("root_uri", task.get("parent_uri", uri))
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    root_thread = chain.get("root_text", "")[:200]
    full_thread_text = chain.get("full_text", "")
    current_hash = hashlib.sha256(full_thread_text.encode()).hexdigest()

    cached_mem, stored_hash = state.load_context(root_uri)

    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] THREAD_HASH_CURRENT: {current_hash}")
        logger.info(f"[DEBUG-OWNER] THREAD_HASH_STORED: {stored_hash or 'NONE'}")
        
    if stored_hash == current_hash and cached_mem:
        final_context = cached_mem
        if config.DEBUG_OWNER: logger.info("[DEBUG-OWNER] CACHE_STATUS: HIT")
    else:
        final_context = generator.update_context_memory(llm, full_thread_text)
        state.save_context(root_uri, final_context, current_hash)
        if config.DEBUG_OWNER: logger.info("[DEBUG-OWNER] CACHE_STATUS: MISS")

    combined_search = search_data
    if link_content:
        combined_search = f"{search_data}\n\n[EXTRACTED_LINKS]\n{link_content}" if search_data else f"[EXTRACTED_LINKS]\n{link_content}"

    if config.DEBUG_OWNER:
        embeds = chain.get("embeds", {})
        if embeds.get("links"):
            for l in embeds["links"]: logger.info(f"[DEBUG-OWNER] EMBED_LINK: URL='{l['url']}' | Title='{l['title']}' | Desc='{l['desc']}'")
        if embeds.get("reposts"):
            for r in embeds["reposts"]: logger.info(f"[DEBUG-OWNER] EMBED_REPOST: Author='{r['author']}' | Text='{r['text']}' | URI='...{r['uri'][-15:]}'")
        logger.info(f"[DEBUG-OWNER] RAW_THREAD: {full_thread_text[:300]}{'...' if len(full_thread_text)>300 else ''}")
        logger.info(f"[DEBUG-OWNER] CONTEXT: [MEMORY] {final_context[:100] if final_context else 'None'} | [ROOT_THREAD] {root_thread[:100]} | [SEARCH] {combined_search[:100] if combined_search else 'None'}")
        logger.info(f"[DEBUG-OWNER] PRIORITY: [SEARCH] > [ROOT_THREAD] > [MEMORY]")

    reply = generator.get_reply(llm, final_context, root_thread, combined_search, user_text)

    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] MODEL_RAW: '{reply}' ({len(reply)} chars)")

    reply = reply.strip()
    max_body = 240 - len(suffix)

    if len(reply) > max_body:
        logger.warning(f"[utils] Reply too long ({len(reply)} > {max_body}). Skipped to preserve format.")
        return

    await bsky.post_reply(client, config.BOT_DID, reply + suffix, root_uri, root_cid, uri, parent_cid)