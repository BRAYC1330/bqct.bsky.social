import os
import asyncio
import logging
import json
import config
import bsky
import generator
import search
import memory
import state
import parsers
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    chain_raw = await bsky.fetch_thread_chain(client, uri)
    if not chain_raw:
        return

    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-RAW-API-RESPONSE ===\n{json.dumps(chain_raw['raw'], indent=2, ensure_ascii=False)[:8000]}\n=== END ===")

    token = chain_raw.get("access_jwt", "")
    thread_content = await parsers.parse_thread_full(chain_raw["raw"], client, token)
    all_texts = thread_content["texts"]
    link_texts = []
    
    link_tasks = [utils.fetch_url_content(url) for url in thread_content["links"][:5]]
    results = await asyncio.gather(*link_tasks)
    link_texts = [r for r in results if r]

    combined_raw = all_texts + link_texts
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-RAW-THREAD ===\nuri={uri}\ntexts_count={len(all_texts)}\nlinks={thread_content['links']}\ncombined_raw_len={len(' '.join(combined_raw))}\ncombined_raw_preview={' '.join(combined_raw)[:800]}")

    root_thread = memory.compress_thread_context(llm, combined_raw)
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-COMPRESSED-ROOT ===\n{root_thread}\n=== END ===")

    root_uri = chain_raw["root_uri"]
    root_cid = chain_raw["root_cid"]
    parent_uri = chain_raw["parent_uri"]
    parent_cid = chain_raw["parent_cid"]
    active_digest = os.environ.get("ACTIVE_DIGEST_URI", "").strip()

    if root_uri == active_digest:
        mem = state.load_digest_context()
    else:
        mem = state.load_thread_context(root_uri)

    search_data = ""
    suffix = "\n\nQwen"
    is_c = "!c" in user_text.lower()
    is_t = "!t" in user_text.lower()

    if is_c:
        suffix = "\n\nQwen | Chainbase"
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
            await asyncio.sleep(0.3)
    elif is_t:
        suffix = "\n\nQwen | Tavily"
        clean = user_text.replace("!t", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean)
        if search_query:
            search_data = await search.fetch_tavily(client, search_query, time_range)

    budget = 300 - len(suffix)
    final_ctx = memory.merge_contexts(mem, root_thread, search_data, user_text)
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-FINAL-CTX ===\n{final_ctx}\n=== END ===")
    
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=budget, temperature=0.7).strip() + suffix
    if len(reply) > 298:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=budget - 10, temperature=0.7).strip() + suffix
    if len(reply) > 298:
        return

    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-REPLY ===\n{reply}\n=== END ===")

    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
    if root_uri != active_digest:
        search_summary = memory.format_search_summary(search_data)
        new_mem = memory.update_and_truncate(mem, user_text, reply, search_summary)
        await state.save_thread_context(root_uri, new_mem)
    logger.info(f"[owner] Replied to {uri[:40]}...")