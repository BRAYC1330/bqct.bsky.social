import logging
import re
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)
C_CYAN, C_GREEN, C_YELLOW, C_MAGENTA, C_RESET = "\033[96m", "\033[92m", "\033[93m", "\033[95m", "\033[0m"
async def process(client, llm, task):
    uri = task["uri"]
    user_text = task["text"]
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    search_data = ""
    source = ""
    search_query_sent = ""
    logger.info(f"{C_CYAN}=== [INPUT] ==={C_RESET}")
    logger.info(f"Query: {user_text[:150]}")
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        logger.info(f"Commands removed: !c/!t -> '{clean_text[:100]}'")
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text)
            logger.info(f"Command: !c | Keyword: {kw}")
            if kw:
                search_query_sent = kw
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
                logger.info(f"Search query sent: {search_query_sent}")
                logger.info(f"Search results: {search_data.count(chr(10)) + 1 if search_data else 0}")
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            logger.info(f"Command: !t | Intent: {q} | Time: {t}")
            if q:
                search_query_sent = f"{q} | time:{t or 'none'}"
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
                logger.info(f"Search query sent: {search_query_sent}")
                logger.info(f"Search results: {search_data.count(chr(10)) + 1 if search_data else 0}")
    logger.info(f"{C_CYAN}=== [INPUT] END ==={C_RESET}")
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_uri = uri
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        logger.error(f"[owner] Missing cid for {uri}")
        return
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client, max_recent=5)
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data) if search_data else ""
    logger.info(f"{C_GREEN}=== [CONTEXT] ==={C_RESET}")
    logger.info(f"Priority 1 (Query): {clean_query}")
    logger.info(f"Priority 2 (Thread):\n{thread_ctx}")
    logger.info(f"Priority 3 (Search):\n{clean_search if clean_search else 'None'}")
    logger.info(f"{C_GREEN}=== [CONTEXT] END ==={C_RESET}")
    sig = build_content._get_signature(source, bool(search_data))
    max_body = 300 - len(sig)
    model_ctx = f"[QUERY]\n{clean_query}\n[THREAD]\n{thread_ctx}\n[SEARCH]\n{clean_search if clean_search else 'No external data'}"
    reply = generator.get_answer(llm, model_ctx, clean_query, max_chars=max_body, temperature=0.5)
    logger.info(f"{C_MAGENTA}=== [OUTPUT] ==={C_RESET}")
    logger.info(f"Raw: {reply}")
    reply = utils.truncate_reply(reply, max_body)
    reply = reply.strip() + sig
    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid, facets)
    logger.info(f"Posted: {reply}")
    logger.info(f"Facets: {len(facets) if facets else 0}")
    logger.info(f"{C_MAGENTA}=== [OUTPUT] END ==={C_RESET}")
    logger.info(f"[owner] Replied to {uri[:40]}... | Final length: {len(reply)}")