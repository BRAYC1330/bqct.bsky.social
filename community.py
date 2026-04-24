import os
import asyncio
import logging
import config
import bsky
import generator
import search
import memory
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    logger.info(f"[community] Task received: source_uri={uri[:40]} | User: '{user_text[:100]}'")
    
    if not parent_uri:
        logger.warning(f"[community] No parent_uri for {uri[:40]}, skipping")
        return

    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        logger.error(f"[community] Failed to fetch thread chain for {uri[:40]}")
        return

    root_uri = chain["root_uri"]
    root_cid = chain["root_cid"]
    target_uri = chain.get("target_uri", uri)
    target_cid = chain.get("target_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    logger.info(f"[community] Reply targeting: target_uri={target_uri[:40]} target_cid={target_cid[:20]} | root_uri={root_uri[:40]}")
    
    root_thread = f"Root: {chain['root_text'][:200]}"

    mem = memory.merge_contexts("", root_thread, "", user_text)
    search_data = ""
    clean = user_text.strip()

    logger.info(f"[COMMUNITY:SEARCH] Input: '{clean}' | Context preview: {root_thread[:100]}...")
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
                logger.info(f"[CONTEXT:SEARCH_DATA] -> {search_data}")
                break
        await asyncio.sleep(0.3)

    final_ctx = memory.merge_contexts(mem, root_thread, search_data, user_text)
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=290, temperature=0.7).strip() + "\n\nQwen"
    
    if len(reply) > 295:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=260, temperature=0.7).strip() + "\n\nQwen"
    if len(reply) > 295:
        logger.warning(f"[community] Reply too long: {len(reply)} chars, skipping")
        return

    logger.info(f"[community] Sending reply: source_cid={uri[:20]} | reply_to_cid={target_cid[:20]} | root_cid={root_cid[:20]}")
    logger.info(f"[community] Reply preview: {reply[:80]}...")

    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, target_uri, target_cid)
    logger.info(f"[community] Reply sent successfully to {target_uri[:40]}")