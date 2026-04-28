import logging
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
    parent_uri = task.get("parent_uri", "")
    if not parent_uri:
        logger.warning(f"[community] Missing parent_uri for {uri}")
        return
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return
    
    root_uri = chain.get("root_uri", parent_uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("parent_cid", "")
    
    kw = generator.extract_chainbase_keyword(llm, user_text)
    search_data = ""
    source = ""
    if kw:
        logger.info(f"\033[36m[CHAINBASE KEYWORD GENERATED] {kw}\033[0m")
        search_data = await search.fetch_chainbase(kw)
        source = "chainbase"
    
    thread_ctx = await utils._format_thread_for_llm(chain, config.OWNER_DID, config.BOT_DID, client)
    logger.info(f"\033[32m=== MODEL CONTEXT (COMMUNITY) ===\033[0m\n{thread_ctx}")
    logger.info(f"\033[33m[TOKENS] {utils.count_tokens(thread_ctx, llm)} / {config.MODEL_N_CTX}\033[0m")
    
    logger.info(f"\033[33m=== MODEL GENERATION (COMMUNITY) ===\033[0m")
    reply = await build_content.build_reply(llm, thread_ctx, user_text, search_data, source, max_total=300)
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")