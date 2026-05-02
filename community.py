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
        return
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
    root_uri = chain.get("root_uri", parent_uri)
    if parent_uri != root_uri:
        return
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        return
    parent_ctx = chain.get("root_text", "")
    clean_query = utils.clean_for_llm(user_text)
    ext_prompt = generator.get_prompt(
        "community_ext_keyword",
        query=clean_query,
        context=parent_ctx[:300]
    )
    kw = generator.get_answer(llm, "", ext_prompt, max_chars=20, temperature=0.1).strip().strip("'\"")
    has_data = False
    sig = ""
    max_body = config.RESPONSE_MAX_CHARS
    if kw.upper() == "SOCIAL":
        sig = build_content.get_signature("none", False)
        max_body = config.RESPONSE_MAX_CHARS - len(sig)
        reply_prompt = generator.get_prompt(
            "community_social_reply",
            reaction=user_text,
            max_chars=max_body
        )
    else:
        search_data = await search.fetch_chainbase(kw) if kw else ""
        has_data = bool(search_data) and kw.lower() in search_data.lower()
        sig = build_content.get_signature("chainbase", has_data)
        max_body = config.RESPONSE_MAX_CHARS - len(sig)
        if has_data:
            reply_prompt = generator.get_prompt(
                "community_with_search",
                keyword=kw,
                search_data=search_data[:1500],
                context=parent_ctx[:300],
                query=clean_query,
                max_chars=max_body
            )
        else:
            reply_prompt = generator.get_prompt(
                "community_no_search",
                keyword=kw,
                max_chars=max_body
            )
    reply = generator.get_answer(llm, "", reply_prompt, max_chars=max_body, temperature=0.3)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Keyword: {kw} | Match: {has_data} | Replied to {uri[:40]}...")