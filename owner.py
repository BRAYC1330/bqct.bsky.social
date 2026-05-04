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

    logger.info(f"{C_CYAN}=== [INPUT] ==={C_RESET}")
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

    clean_query = utils.clean_for_llm(user_text)
    root_text = utils.clean_for_llm(chain.get("root_text", ""))
    clean_search = utils.clean_for_llm(search_data) if search_data else ""

    posts = chain.get("chain", [])[-5:]
    history_lines = []
    for post in posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        text = utils.clean_for_llm(rec.get("text", ""))
        if not text: continue
        if did == config.OWNER_DID: prefix = "OWNER:"
        elif did == config.BOT_DID: prefix = "BOT:"
        else: prefix = "USER:"
        history_lines.append(f"{prefix} {text}")
    history_block = "\n".join(history_lines) if history_lines else "No history."

    model_ctx = (
        f"[QUERY]\n{clean_query}\n"
        f"[CONVERSATION]\n"
        f"[ROOT]\n{root_text}\n"
        f"[HISTORY]\n{history_block}\n"
        f"[SEARCH]\n{clean_search if clean_search else 'No external data'}"
    )

    logger.info(f"{C_GREEN}=== [CONTEXT] ==={C_RESET}")
    logger.info(f"{C_CYAN}[QUERY]\n{clean_query}{C_RESET}")
    logger.info(f"{C_GREEN}[CONVERSATION]{C_RESET}")
    logger.info(f"{C_YELLOW}[ROOT]\n{root_text}{C_RESET}")
    logger.info(f"{C_YELLOW}[HISTORY]\n{history_block}{C_RESET}")
    logger.info(f"{C_MAGENTA}[SEARCH]\n{clean_search if clean_search else 'No external data'}{C_RESET}")
    logger.info(f"{C_GREEN}=== [CONTEXT] END ==={C_RESET}")

    sig = build_content._get_signature(source, bool(search_data))
    max_total = 300

    raw = generator.get_answer(llm, model_ctx, clean_query, max_chars=max_total-len(sig), temperature=0.5, prompt_key="owner_reply")
    reply = utils.format_reply(raw, sig, max_total)

    logger.info(f"{C_MAGENTA}=== [OUTPUT] ==={C_RESET}")
    logger.info(f"Raw: {reply}")
    logger.info(f"{C_MAGENTA}=== [OUTPUT] END ==={C_RESET}")

    facets = utils.generate_facets(reply)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid, facets)
    logger.info(f"[owner] Replied to {uri[:40]}... | Final length: {len(reply)}")