import logging
import re
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
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data = ""
    source = ""
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text)
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_uri = uri
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        logger.error(f"[owner] Missing cid for {uri}")
        return
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    if search_data:
        search_data = utils.clean_for_llm(search_data)
    sig = build_content._get_signature(source, bool(search_data))
    max_body = 300 - len(sig)
    ctx = f"[SEARCH]\n{search_data}\n{thread_ctx}" if search_data else thread_ctx
    reply = generator.get_answer(llm, ctx, user_text, max_chars=max_body, temperature=0.5)
    if utils.count_graphemes(reply) > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
    reply = reply.strip() + sig
    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid, facets=facets)
    logger.info(f"[owner] Replied to {uri[:40]}...")