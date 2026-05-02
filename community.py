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
    sig = ""
    max_body = 300
    reply = ""
    if kw and kw.upper() == "SOCIAL":
        sig = build_content._get_signature("none", False)
        max_body = 300 - len(sig)
        reply_prompt = (f"User reacted: '{user_text}' on a crypto post. "
                        f"Reply with a brief, warm acknowledgment. "
                        f"PROVIDE ONLY THE DIRECT REPLY. NO questions, NO sign-offs, NO greetings, NO hashtags. "
                        f"This is a standalone, final response. Max {max_body} chars.")
        reply = generator.get_answer(llm, "", reply_prompt, max_chars=max_body, temperature=0.3)
    else:
        search_data = ""
        source = ""
        if kw:
            search_data = await search.fetch_chainbase(kw)
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
        reply_prompt = (f"Search data for '{kw}':\n{clean_search[:1500]}\n"
                        f"Post context: {chain.get('root_text', '')[:300]}\n"
                        f"User query: {clean_query}\n"
                        f"Answer concisely using ONLY the provided data and context. "
                        f"PROVIDE ONLY THE DIRECT ANSWER. NO questions, NO sign-offs, NO greetings, NO hashtags. "
                        f"This is a standalone, final response. Max {max_body} chars. Start directly.")
        reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    reply = reply.strip() + sig
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")