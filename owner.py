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
    logger.info("=== [INPUT] ===")
    logger.info(f"Query: {user_text[:150]}")
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text)
            logger.info(f"Command: !c | Keyword: {kw}")
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
                logger.info(f"Search results: {search_data.count(chr(10)) + 1 if search_data else 0}")
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            logger.info(f"Command: !t | Intent: {q} | Time: {t}")
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
                logger.info(f"Search results: {search_data.count(chr(10)) + 1 if search_data else 0}")
    logger.info("=== [INPUT] END ===")
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
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data) if search_data else ""
    logger.info("=== [CONTEXT] ===")
    logger.info(f"Priority 1 (Query): {clean_query}")
    logger.info(f"Priority 2 (Thread): {thread_ctx[:200]}...")
    logger.info(f"Priority 3 (Search): {clean_search[:200] if clean_search else 'None'}...")
    logger.info("=== [CONTEXT] END ===")
    sig = build_content._get_signature(source, bool(search_data))
    max_body = 300 - len(sig)
    model_context = f"[QUERY]\n{clean_query}\n[THREAD]\n{thread_ctx}\n[SEARCH]\n{clean_search if clean_search else 'No external data'}"
    reply = generator.get_answer(llm, model_context, "", max_chars=max_body, temperature=0.5)
    logger.info("=== [OUTPUT] ===")
    logger.info(f"Raw: {reply}")
    pre_len = utils.count_graphemes(reply)
    if pre_len > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
        logger.info(f"Truncated: {pre_len} -> {len(reply)}")
    reply = reply.strip() + sig
    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid, facets)
    logger.info("=== [OUTPUT] END ===")
    logger.info(f"[owner] Replied to {uri[:40]}... | Final length: {len(reply)}")