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
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_query, time_range, search_data = "", "", ""
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            search_query = generator.extract_chainbase_keyword(llm, clean_text)
            if search_query:
                search_data = await search.fetch_chainbase(search_query)
        else:
            search_query, time_range = generator.extract_search_intent(llm, "", clean_text)
            if search_query:
                search_data = await search.fetch_tavily(search_query, time_range)
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    thread_context = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    final_ctx = thread_context
    if search_data:
        final_ctx += f"\n\n[SEARCH]\n{search_data}"
    reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=280, temperature=0.3)
    if utils.count_graphemes(reply) > 300:
        logger.warning(f"[owner] Reply too long ({utils.count_graphemes(reply)}), regenerating...")
        reply = generator.get_answer(llm, final_ctx, user_text, "", max_chars=240, temperature=0.3)
    if utils.count_graphemes(reply) > 300:
        logger.error(f"[owner] Reply still too long, skipping post")
        return
    await bsky.post_reply(client, config.BOT_DID, reply.strip(), root_uri, root_cid, uri, parent_cid)
    logger.info(f"[owner] Replied to {uri[:40]}...")