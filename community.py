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
    sig = build_content._get_signature(source, bool(search_data))
    max_body = 300 - len(sig)
    clean_query = utils.clean_for_llm(user_text)
    topic_ref = kw if kw else clean_query[:50]
    if not search_data:
        prompt = (f"User asked about '{topic_ref}'. No current data found. "
                  f"Reply naturally in English (max {max_body} chars). Be friendly, concise. "
                  f"NEVER use phrases like 'I'm sorry', 'I didn't understand', or 'provide more context'. "
                  f"Just say the info isn't available right now and suggest rephrasing or DYOR. "
                  f"Start directly with the answer.")
        reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.5)
    else:
        clean_search = utils.clean_for_llm(search_data)
        minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
        reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")