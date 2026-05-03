import logging
import re
import config
import bsky
import generator
import search
import utils
import build_content
logger = logging.getLogger(__name__)
COLOR_BLUE = "\033[94m"
COLOR_GREEN = "\033[92m"
COLOR_RESET = "\033[0m"
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
            logger.info(f"{COLOR_BLUE}[owner] Keyword:{COLOR_RESET} '{kw}'")
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
                res_count = search_data.count("\n") + 1 if search_data else 0
                logger.info(f"{COLOR_GREEN}[owner] Chainbase results:{COLOR_RESET} {res_count}")
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            logger.info(f"{COLOR_BLUE}[owner] Intent:{COLOR_RESET} '{q}' | Time: '{t}'")
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
                res_count = search_data.count("\n") + 1 if search_data else 0
                logger.info(f"{COLOR_GREEN}[owner] Tavily results:{COLOR_RESET} {res_count}")
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return
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
    reply = await build_content.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, parent_uri, parent_cid)
    logger.info(f"[owner] Replied to {uri[:40]}... | Final length: {len(reply)}")