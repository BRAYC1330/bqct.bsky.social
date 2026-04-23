import os
import logging
import config
import bsky
import generator
import search
import state
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return

    root_uri = chain["root_uri"]
    root_cid = chain["root_cid"]
    parent_cid = chain.get("parent_cid", "")
    active_digest = os.environ.get("ACTIVE_DIGEST_URI", "").strip()
    root_thread = f"Root: {chain['root_text'][:200]}"

    if root_uri == active_digest:
        memory = state.load_digest_context()
    else:
        memory = state.load_thread_context(root_uri)

    search_query, time_range = "", ""
    search_data = ""
    if "!t" in user_text.lower() or "!c" in user_text.lower():
        clean = user_text.replace("!t", "").replace("!c", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean)
        if search_query:
            search_data = await (search.fetch_chainbase(client, search_query) if "!c" in user_text.lower() else search.fetch_tavily(client, search_query, time_range))

    final_ctx = state.merge_contexts(memory, root_thread, search_data, user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=280, temperature=0.7)
    if len(reply) > 300:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=240, temperature=0.7)
    if len(reply) > 300:
        return

    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    if root_uri != active_digest:
        await state.save_thread_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    logger.info(f"[owner] Replied to {uri[:40]}...")