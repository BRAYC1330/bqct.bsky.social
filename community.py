import logging
import time
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)
async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[community] Missing parent_uri for {uri}")
        return
    start_total = time.monotonic()
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", parent_uri)
    if parent_uri != root_uri:
        logger.info(f"[community] Nested reply, skipping.")
        return
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        logger.error(f"[community] Missing cid for {uri}")
        return
    t_kw_start = time.monotonic()
    kw = generator.extract_chainbase_keyword(llm, user_text)
    t_kw_end = time.monotonic()
    logger.info(f"[community] Keyword: '{kw}' (extracted in {t_kw_end - t_kw_start:.2f}s)")
    search_data = ""
    source = ""
    if kw:
        t_search_start = time.monotonic()
        search_data = await search.fetch_chainbase(kw)
        t_search_end = time.monotonic()
        res_count = search_data.count("\n") + 1 if search_data else 0
        logger.info(f"[community] Chainbase results: {res_count} (fetched in {t_search_end - t_search_start:.2f}s)")
        source = "chainbase"
    if not search_data:
        reply = build_content.get_no_data_response(kw or "query")
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
        return
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data)
    minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
    sig = build_content._get_signature(source, True)
    max_body = 300 - len(sig)
    t_gen_start = time.monotonic()
    reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    t_gen_end = time.monotonic()
    pre_len = len(reply)
    logger.info(f"[community] Generation time: {t_gen_end - t_gen_start:.2f}s | Raw length: {pre_len}")
    truncation_info = "none"
    if utils.count_graphemes(reply) > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        if last_dot != -1:
            reply = truncated[:last_dot+1]
            truncation_info = f"cut at dot (pos {last_dot})"
        else:
            reply = truncated.rstrip() + "."
            truncation_info = "hard cut at max_body"
        logger.info(f"[community] Truncated: {pre_len} -> {len(reply)} ({truncation_info})")
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    total_time = time.monotonic() - start_total
    logger.info(f"[community] Replied to {uri[:40]}... | Total time: {total_time:.2f}s | Final length: {len(reply)}")