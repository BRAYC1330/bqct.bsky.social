import os
import logging
import config
import bsky
import generator
import search
import state
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_query, time_range = "", ""
    if do_search:
        clean_text = user_text.replace("!t", "").replace("!c", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean_text)
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    memory = state.load_thread_context(root_uri)
    search_data = ""
    if do_search and search_query:
        if "!c" in user_text.lower():
            search_data = await search.fetch_chainbase(client, search_query)
        else:
            search_data = await search.fetch_tavily(client, search_query, time_range)
    root_thread = f"Root: {chain.get('root_text', '')[:200]}"
    final_ctx = state.merge_contexts(memory, root_thread, search_data, user_text)
    
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=280, temperature=0.7)
    if len(reply) > 300:
        logger.warning(f"[owner] Reply too long ({len(reply)}), regenerating...")
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=240, temperature=0.7)
    if len(reply) > 300:
        logger.error(f"[owner] Reply still too long, skipping post")
        return
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    await state.save_thread_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    logger.info(f"[owner] Replied to {uri[:40]}...")
