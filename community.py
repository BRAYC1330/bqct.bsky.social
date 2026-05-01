import logging
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
    kw = generator.extract_chainbase_keyword(llm, user_text)
    logger.info(f"[community] Extracted keyword: {kw}")
    search_data = ""
    source = ""
    if kw:
        search_data = await search.fetch_chainbase(kw)
        source = "chainbase"
    if not search_
        reply = await build_content.build_no_data_reply(llm, kw or "query")
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
        return
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data)
    minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
    sig = build_content._get_signature(source, True)
    max_body = 300 - len(sig)
    reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")