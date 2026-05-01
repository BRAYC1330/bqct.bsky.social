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
    parent_ctx = chain.get("root_text", "")
    clean_query = utils.clean_for_llm(user_text)
    kw = generator.extract_chainbase_keyword(llm, user_text)
    logger.info(f"[community] Keyword: {kw}")
    search_data = ""
    if kw:
        search_data = await search.fetch_chainbase(kw)
    sig = build_content._get_signature("chainbase", bool(search_data))
    max_body = 300 - len(sig)
    if search_
        prompt = (f"Search results: {search_data[:1500]}\n"
                  f"Post context: {parent_ctx[:300]}\n"
                  f"User query: {clean_query}\n\n"
                  f"Answer using ONLY relevant info from results and context. "
                  f"Ignore unrelated trends. Be concise, factual. Max {max_body} chars. Start directly.")
    else:
        prompt = (f"User commented: \"{user_text}\" on a post about: {parent_ctx[:200]}\n"
                  f"Reply with a brief, warm acknowledgment. "
                  f"CRITICAL: FINAL reply only. NO questions. NO invitations. NO hashtags, EVER. "
                  f"NO links, NO markdown. Max {max_body} chars.")
    reply = generator.get_answer(llm, "", prompt, max_chars=max_body, temperature=0.3)
    reply = reply.replace('#', '').strip()
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")