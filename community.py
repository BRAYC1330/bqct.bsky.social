import os
import logging
import re
import config
import bsky
import generator
import search
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[community] Missing parent_uri for {uri}")
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", parent_uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    keyword = generator.extract_chainbase_keyword(llm, user_text)
    search_data = ""
    if keyword:
        search_data = await search.fetch_chainbase(keyword)
    thread_context = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    final_ctx = thread_context
    if search_data:
        final_ctx += f"\n\n[SEARCH]\n{search_data}"
    reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=280, temperature=0.3)
    if utils.count_graphemes(reply) > 293:
        logger.warning(f"[community] Reply too long ({utils.count_graphemes(reply)}), regenerating...")
        reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=260, temperature=0.3)
    if utils.count_graphemes(reply) > 293:
        logger.error(f"[community] Reply still too long, skipping post")
        return
    await bsky.post_reply(client, config.BOT_DID, reply.strip(), root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")