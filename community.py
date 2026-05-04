import logging
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
    root_text = chain.get("root_text", "")
    kw = generator.extract_chainbase_keyword(llm, user_text)
    logger.info(f"{C_CYAN}=== [INPUT] ==={C_RESET}")
    logger.info(f"Query: {user_text[:150]}")
    logger.info(f"Keyword: {kw}")
    search_data = ""
    source = ""
    if kw:
        search_data = await search.fetch_chainbase(kw)
        source = "chainbase"
        logger.info(f"Search results: {search_data.count(chr(10)) + 1 if search_data else 0}")
    logger.info(f"{C_CYAN}=== [INPUT] END ==={C_RESET}")
    if not search_data:
        reply = build_content.get_no_data_response(kw or "query")
        facets = utils.generate_facets(reply)
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid, facets)
        return
    clean_query = utils.clean_for_llm(user_text)
    clean_root = utils.clean_for_llm(root_text)
    clean_search = utils.clean_for_llm(search_data)
    logger.info(f"{C_GREEN}=== [CONTEXT] ==={C_RESET}")
    logger.info(f"[QUERY] {clean_query}")
    logger.info(f"[ROOT] {clean_root}")
    logger.info(f"[SEARCH] {clean_search}")
    logger.info(f"{C_GREEN}=== [CONTEXT] END ==={C_RESET}")
    sig = build_content._get_signature(source, True)
    max_body = 300 - len(sig)
    minimal_ctx = f"[QUERY]\n{clean_query}\n[ROOT]\n{clean_root}\n[SEARCH]\n{clean_search}"
    reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    logger.info(f"{C_MAGENTA}=== [OUTPUT] ==={C_RESET}")
    logger.info(f"Raw: {reply}")
    pre_len = utils.count_graphemes(reply)
    if pre_len > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
        logger.info(f"Truncated: {pre_len} -> {len(reply)}")
    reply = reply.strip() + sig
    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid, facets)
    logger.info(f"{C_MAGENTA}=== [OUTPUT] END ==={C_RESET}")
    logger.info(f"[community] Replied to {uri[:40]}... | Final length: {len(reply)}")