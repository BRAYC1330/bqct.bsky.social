import os
import asyncio
import logging
import config
import bsky
import generator
import search
import state
import memory
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
        mem = state.load_digest_context()
    else:
        mem = state.load_thread_context(root_uri)

    search_data = ""
    fallback_topics = []

    if "!c" in user_text.lower():
        clean = user_text.replace("!c", "").strip()
        keywords = generator.extract_chainbase_keywords_multi(llm, clean)

        for kw in keywords:
            raw_items = await search.fetch_chainbase_raw(client, kw)
            if raw_items:
                filtered = generator.filter_search_results_by_intent(llm, clean, raw_items)
                if filtered:
                    search_data = " | ".join([
                        f"{config.TREND_EMOJIS.get(it.get('rank_status','same'),'')} {it['keyword']} [{it['score']}]: {it['summary'][:120]}"
                        for it in filtered[:2]
                    ])
                    break
                else:
                    for item in raw_items[:2]:
                        fb = f"{item['keyword']} ({config.TREND_EMOJIS.get(item.get('rank_status','same'),'')})"
                        if fb not in fallback_topics:
                            fallback_topics.append(fb)
            await asyncio.sleep(0.5)

    elif "!t" in user_text.lower():
        clean = user_text.replace("!t", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean)
        if search_query:
            search_data = await search.fetch_tavily(client, search_query, time_range)

    final_ctx = memory.merge_contexts(mem, root_thread, search_data, user_text)
    fallback_str = memory.format_fallback_topics(fallback_topics)

    reply = generator.get_answer(llm, final_ctx, user_text, search_data, fallback_str, max_chars=270, temperature=0.7).strip() + "\n\nQwen"
    if len(reply) > 295:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, fallback_str, max_chars=240, temperature=0.7).strip() + "\n\nQwen"
    if len(reply) > 295:
        return

    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)

    if root_uri != active_digest:
        search_summary = memory.format_search_summary(search_data)
        new_mem = memory.update_and_truncate(mem, user_text, reply, search_summary)
        await state.save_thread_context(root_uri, new_mem)

    logger.info(f"[owner] Replied to {uri[:40]}...")