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
                res_count = search_data.count("\n") + 1 if search_data else 0
                logger.info(f"Search results: {res_count}")
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            logger.info(f"Command: !t | Intent: {q} | Time: {t}")
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
                res_count = search_data.count("\n") + 1 if search_data else 0
                logger.info(f"Search results: {res_count}")
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
    if search_data:
        search_data = utils.clean_for_llm(search_data)
    clean_query = utils.clean_for_llm(user_text)
    clean_thread = utils.clean_for_llm(thread_ctx) if thread_ctx else ""
    logger.info("=== [CONTEXT] ===")
    logger.info(f"Priority 1 (Query): {clean_query}")
    logger.info(f"Priority 2 (Thread/Root): {clean_thread[:200]}...")
    logger.info(f"Priority 3 (Search): {search_data[:200] if search_data else 'None'}...")
    logger.info("=== [CONTEXT] END ===")
    reply = await build_content.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    logger.info("=== [OUTPUT] ===")
    logger.info(f"Raw: {reply}")
    logger.info("=== [OUTPUT] END ===")
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
    logger.info(f"[owner] Replied to {uri[:40]}... | Final length: {len(reply)}")