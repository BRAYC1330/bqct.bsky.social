import logging
import re
import config
import bsky
import generator
import search
import utils
import build_content
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

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
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
        else:
            q, t = generator.extract_search_intent(llm, "", clean_text)
            if q:
                search_data = await search.fetch_tavily(q, t)
                source = "tavily"
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    logger.info(f"\033[32m=== MODEL CONTEXT (OWNER) ===\033[0m\n{thread_ctx}")
    logger.info(f"\033[33m[TOKENS] {utils.count_tokens(thread_ctx, llm)} / {config.MODEL_N_CTX}\033[0m")
    
    logger.info(f"\033[33m=== MODEL GENERATION (OWNER) ===\033[0m")
    if search_
        search_data = utils.clean_for_llm(search_data)
    reply = await build_content.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[owner] Replied to {uri[:40]}...")