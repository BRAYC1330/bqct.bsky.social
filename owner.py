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
        raw_preview = json.dumps(chain_raw['raw'], indent=2, ensure_ascii=False)[:8000]
        logger.info(f"=== OWNER-RAW-API-RESPONSE ===\n{raw_preview}\n=== END ===")

    token = chain_raw.get("access_jwt", "")
    allowed_handles = {config.BOT_HANDLE, "brayc1330.bsky.social"}
    thread_content = await parsers.parse_thread_full(chain_raw["raw"], client, token, allowed_handles)
    all_nodes = thread_content.get("nodes", [])
    
    filtered_nodes = [n for n in all_nodes if n.get("handle") in allowed_handles]
    recent_messages = [n["text"] for n in filtered_nodes[-4:] if n.get("text")]
    
    root_node = next((n for n in filtered_nodes if n.get("is_root")), None)
    root_embed_text = ""
    if root_node:
        root_record = chain_raw["raw"].get("thread", {}).get("post", {}).get("record", {})
        embed = root_record.get("embed", {})
        if embed:
            embed_text, _ = parsers._extract_embed_full(embed)
            if embed_text:
                root_embed_text = f" {embed_text}"
    
    root_thread = f"{root_node['text']}{root_embed_text}" if root_node else ""
    
    middle_messages = [n["text"] for n in filtered_nodes[1:-4] if n.get("text")] if len(filtered_nodes) > 5 else []
    
    link_texts = []
    link_tasks = [utils.fetch_url_content(url) for url in thread_content["links"][:5]]
    results = await asyncio.gather(*link_tasks)
    link_texts = [r for r in results if r]

    combined_raw = recent_messages + ([root_thread] if root_thread else []) + middle_messages + link_texts
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-RAW-THREAD ===\nuri={uri}\ntexts_count={len(combined_raw)}\nlinks={thread_content['links']}\ncombined_raw_len={len(' '.join(combined_raw))}\ncombined_raw_preview={' '.join(combined_raw)[:800]}")

    compressed_root = memory.compress_thread_context(llm, combined_raw)
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-COMPRESSED-ROOT ===\n{compressed_root}\n=== END ===")

    root_uri = chain_raw["root_uri"]
    root_cid = chain_raw["root_cid"]
    target_uri = chain_raw.get("target_uri", uri)
    target_cid = chain_raw.get("target_cid", "")
    parent_uri = chain_raw["parent_uri"]
    parent_cid = chain_raw["parent_cid"]
    active_digest = os.environ.get("ACTIVE_DIGEST_URI", "").strip()

    if root_uri == active_digest:
        mem = state.load_digest_context()
    else:
        mem = state.load_thread_context(root_uri)

    search_data = ""
    is_c = "!c" in user_text.lower()
    is_t = "!t" in user_text.lower()
    
    if is_c:
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
        clean = user_text.replace("!t", "").strip()
        search_query, time_range = generator.extract_search_intent(llm, "", clean)
        if search_query:
            search_data = await search.fetch_tavily(client, search_query, time_range)

    suffix = "\n\nQwen"
    if (is_c or is_t) and search_data:
        suffix = f"\n\nQwen | {'Chainbase' if is_c else 'Tavily'}"

    budget = 300 - len(suffix)
    final_ctx = memory.merge_contexts(mem, compressed_root, search_data, user_text, recent_messages)
    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-FINAL-CTX ===\n{final_ctx}\n=== END ===")
    
    reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=budget, temperature=0.7).strip() + suffix
    if len(reply) > 298:
        reply = generator.get_answer(llm, final_ctx, user_text, search_data, max_chars=budget - 10, temperature=0.7).strip() + suffix
    if len(reply) > 298:
        return

    if config.RAW_DEBUG:
        logger.info(f"=== OWNER-REPLY ===\n{reply}\n=== END ===")
    
    logger.info(f"[owner] Reply context: target_uri={target_uri[:40]} target_cid={target_cid[:20]} root_uri={root_uri[:40]}")
    logger.info(f"[owner] Reply generated: {reply[:100]}...")

    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, target_uri, target_cid)
    if root_uri != active_digest:
        search_summary = memory.format_search_summary(search_data)
        new_mem = memory.update_and_truncate(mem, user_text, reply, search_summary)
        await state.save_thread_context(root_uri, new_mem)
    logger.info(f"[owner] Replied to {target_uri[:40]}...")