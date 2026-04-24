import logging
import hashlib
import generator
import search
import utils
import config
import bsky
import state
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    if not task.get("parent_uri"):
        logger.warning("[community] Missing parent_uri")
        return
        
    user_text = task["text"]
    uri = task["uri"]
    
    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] USER_QUERY: {user_text}")
    
    keyword = generator.extract_chainbase_keyword(llm, user_text)
    search_data = await search.fetch_chainbase(keyword)
    
    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] SEARCH_QUERY: !c → keyword='{keyword}'")
        logger.info(f"[DEBUG-OWNER] SEARCH_RAW: {search_data[:200]}{'...' if len(search_data)>200 else ''} ({len(search_data)} chars)")
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return

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
        if config.DEBUG_OWNER:
            logger.info("[DEBUG-OWNER] CACHE_STATUS: HIT")
    else:
        final_context = generator.update_context_memory(llm, full_thread_text)
        state.save_context(root_uri, final_context, current_hash)
        if config.DEBUG_OWNER:
            logger.info("[DEBUG-OWNER] CACHE_STATUS: MISS")

    combined_search = search_data

    if config.DEBUG_OWNER:
        embeds = chain.get("embeds", {})
        if embeds.get("links"):
            for l in embeds["links"]:
                logger.info(f"[DEBUG-OWNER] EMBED_LINK: URL='{l['url']}' | Title='{l['title']}' | Desc='{l['desc']}'")
        if embeds.get("reposts"):
            for r in embeds["reposts"]:
                logger.info(f"[DEBUG-OWNER] EMBED_REPOST: Author='{r['author']}' | Text='{r['text']}' | URI='...{r['uri'][-15:]}'")
        logger.info(f"[DEBUG-OWNER] RAW_THREAD: {full_thread_text[:300]}{'...' if len(full_thread_text)>300 else ''}")
        logger.info(f"[DEBUG-OWNER] CONTEXT: [MEMORY] {final_context[:100] if final_context else 'None'} | [ROOT_THREAD] {root_thread[:100]} | [SEARCH] {combined_search[:100] if combined_search else 'None'}")
        logger.info(f"[DEBUG-OWNER] PRIORITY: [SEARCH] > [ROOT_THREAD] > [MEMORY]")

    reply = generator.get_reply(llm, final_context, root_thread, combined_search, user_text)

    if config.DEBUG_OWNER:
        logger.info(f"[DEBUG-OWNER] MODEL_RAW: '{reply}' ({len(reply)} chars)")

    reply = reply.strip()
    suffix = "\n\nQwen | Chainbase" if search_data else "\n\nQwen"
    max_body = 240 - len(suffix)

    if len(reply) > max_body:
        logger.warning(f"[community] Reply too long ({len(reply)} > {max_body}). Skipped to preserve format.")
        return

    await bsky.post_reply(client, config.BOT_DID, reply + suffix, root_uri, root_cid, uri, parent_cid)