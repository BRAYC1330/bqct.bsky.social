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
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    root_text = chain.get("root_text", "")
    parent_ctx = root_text
    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', root_text)
    if urls:
        try:
            link_content = await bsky._fetch_url_content(client, urls[0])
            if link_content and len(link_content) > 50:
                parent_ctx += f"\n\n[LINK EXPANSION]: {link_content[:1200]}"
        except Exception as e:
            logger.warning(f"[owner] Link fetch failed: {e}")
    clean_query = utils.clean_for_llm(user_text)
    kw = generator.extract_chainbase_keyword(llm, user_text)
    logger.info(f"[owner] Extracted keyword: {kw}")
    search_data = ""
    source = ""
    if kw:
        search_data = await search.fetch_chainbase(kw)
        source = "chainbase"
    sig = build_content._get_signature(source, bool(search_data))
    max_body = 300 - len(sig)
    if search_data:
        clean_search = utils.clean_for_llm(search_data)
        minimal_ctx = f"[ROOT CONTEXT]\n{parent_ctx[:400]}\n\n[SEARCH]\n{clean_search}\n\n[USER QUERY]\n{clean_query}"
        reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    else:
        ctx = f"[ROOT CONTEXT]\n{parent_ctx[:3000]}\n\n[USER QUERY]\n{clean_query}"
        reply = generator.get_answer(llm, ctx, clean_query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, root_cid)
    logger.info(f"[owner] Replied to {uri[:40]}...")
