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
    clean_root = utils.clean_for_llm(root_text)
    clean_query = utils.clean_for_llm(user_text)

    intent = generator.classify_intent(llm, user_text, clean_root)
    logger.info(f"{C_CYAN}=== [INPUT] ==={C_RESET}")
    logger.info(f"Query: {user_text[:150]}")
    logger.info(f"Intent: {intent}")

    if intent == "CASUAL":
        sig = build_content.SIG_DEFAULT
        max_total = 300
        ctx = f"[ROOT]\n{clean_root}"
        raw = generator.get_answer(llm, ctx, user_text, max_chars=max_total-len(sig), temperature=0.7, prompt_key="casual_reply")
        reply = utils.format_reply(raw, sig)
        facets = utils.generate_facets(reply)
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid, facets)
        logger.info(f"[community] Casual reply to {uri[:40]}...")
        return

    kw = generator.extract_chainbase_keyword(llm, user_text)
    logger.info(f"Initial keyword: {kw}")
    search_data = ""
    source = ""
    attempts = 0
    max_attempts = 3
    while attempts < max_attempts and not search_data and kw:
        attempts += 1
        logger.info(f"[community] Chainbase attempt {attempts}/{max_attempts} with keyword: {kw}")
        search_data = await search.fetch_chainbase(kw)
        if search_data:
            source = "chainbase"
            logger.info(f"Search results: {search_data.count(chr(10)) + 1}")
            break
        if attempts < max_attempts:
            kw = generator.regenerate_keyword(llm, kw, clean_query, clean_root)
            logger.info(f"Regenerated keyword: {kw}")

    logger.info(f"{C_CYAN}=== [INPUT] END ==={C_RESET}")
    sig = build_content._get_signature(source, bool(search_data))
    max_total = 300

    if not search_data:
        dyor_text = f"No data found for '{kw}'. Try rephrasing or DYOR."
        reply = utils.format_reply(dyor_text, build_content.SIG_DEFAULT, max_total)
    else:
        clean_search = utils.clean_for_llm(search_data)
        logger.info(f"{C_GREEN}=== [CONTEXT] ==={C_RESET}")
        logger.info(f"{C_CYAN}[QUERY]\n{clean_query}{C_RESET}")
        logger.info(f"{C_YELLOW}[ROOT]\n{clean_root}{C_RESET}")
        logger.info(f"{C_MAGENTA}[SEARCH]\n{clean_search}{C_RESET}")
        logger.info(f"{C_GREEN}=== [CONTEXT] END ==={C_RESET}")
        minimal_ctx = f"[ROOT]\n{clean_root}\n[SEARCH]\n{clean_search}"
        raw = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_total-len(sig), temperature=0.5, prompt_key="community_reply")
        reply = utils.format_reply(raw, sig, max_total)

    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid, facets)
    logger.info(f"{C_MAGENTA}=== [OUTPUT] ==={C_RESET}")
    logger.info(f"Raw: {reply}")
    logger.info(f"{C_MAGENTA}=== [OUTPUT] END ==={C_RESET}")
    logger.info(f"[community] Replied to {uri[:40]}... | Final length: {len(reply)}")