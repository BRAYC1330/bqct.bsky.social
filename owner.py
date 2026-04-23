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
    do_search = "!c" in user_text.lower() or "!t" in user_text.lower()
    search_type = "chainbase" if "!c" in user_text.lower() else ("tavily" if "!t" in user_text.lower() else None)
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    memory = state.load_context(root_uri)
    search_data = ""
    if do_search and search_type:
        params = generator.extract_search_params(llm, "", user_text)
        provider = search.SEARCH_PROVIDERS.get(search_type)
        if provider:
            raw = await provider["func"](params.get("query", ""), **{k: v for k, v in params.items() if k in provider["supports"] and v})
            if search.is_search_result_valid(raw, search_type):
                search_data = search.clean_search_results(raw, search_type)
    root_thread = f"Root: {chain.get('root_text', '')[:200]}"
    final_ctx = state.merge_contexts(memory, root_thread, search_data, user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, config.RESPONSE_MAX_CHARS)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    if root_uri != os.environ.get("ACTIVE_DIGEST_URI", "").strip():
        state.save_context(root_uri, generator.update_summary(llm, memory, user_text, reply))
    logger.info(f"[owner] Replied to {uri[:40]}...")
