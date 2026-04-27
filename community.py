import os
import logging
import config
import bsky
import generator
import state
import utils
import search
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"Missing parent_uri for {uri}")
        return

    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data = ""
    suffix = ""

    if do_search:
        clean_text = user_text.replace("!t", "").replace("!c", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean_text)
        if search_query:
            if "!c" in user_text.lower():
                search_data = await search.fetch_chainbase(search_query)
                suffix = "\n\nQwen | Chainbase"
            else:
                search_data = await search.fetch_tavily(search_query, time_range)
                suffix = "\n\nQwen | Tavily"
            logger.info(f"Search triggered | query={search_query} | results_len={len(search_data)}")

    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return

    root_uri = chain.get("root_uri", parent_uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")

    memory = state.load_context(root_uri)
    root_thread = chain.get("root_text", "")

    ctx_parts = []
    if memory:
        ctx_parts.append(f"[MEMORY]\n{memory}")
    if root_thread:
        ctx_parts.append(f"[ROOT_THREAD]\n{root_thread}")
    if search_data:
        ctx_parts.append(f"[SEARCH]\n{search_data}")
    ctx_parts.append(f"[USER]\n{user_text}")
    final_ctx = "\n\n".join(ctx_parts)

    if config.RAW_DEBUG:
        logger.info(f"=== FINAL CONTEXT ===\n{final_ctx}\n=== END ===")

    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=280, temperature=0.7)
    if utils.count_graphemes(reply) > 293:
        logger.warning(f"Reply too long ({utils.count_graphemes(reply)}), regenerating...")
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=240, temperature=0.7)

    if utils.count_graphemes(reply) > 293:
        logger.error("Reply still too long, skipping post")
        return

    final_reply = reply.strip() + suffix
    await bsky.post_reply(client, config.BOT_DID, final_reply, root_uri, root_cid, uri, parent_cid)

    if root_uri != os.environ.get("ACTIVE_DIGEST_URI", "").strip():
        state.save_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    logger.info(f"Replied to {uri[:40]}...")