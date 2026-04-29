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
    
    try:
        r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 1})
        if r.status_code == 200:
            replies = r.json().get("thread", {}).get("replies", [])
            for rep in replies:
                post = rep.get("post", {})
                if post.get("author", {}).get("did") == config.BOT_DID:
                    logger.info(f"[community] Bot already replied to {uri[:40]}... Skipping.")
                    return
    except Exception as e:
        logger.warning(f"[community] Reply check failed: {e}")
    
    kw = generator.extract_chainbase_keyword(llm, user_text)
    search_data = ""
    source = ""
    if kw:
        logger.info(f"\033[36m[CHAINBASE KEYWORD GENERATED] {kw}\033[0m")
        search_data = await search.fetch_chainbase(kw)
        source = "chainbase"
    
    if not search_data:
        reply = build_content.get_no_data_response(kw or "query")
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
        logger.info(f"[community] No-data reply sent for '{kw}'")
        return
    
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data)
    minimal_ctx = f"Q: {clean_query}\n\nA: {clean_search}"
    logger.info(f"\033[32m=== MODEL CONTEXT (COMMUNITY) ===\033[0m\n{minimal_ctx}")
    logger.info(f"\033[33m[TOKENS] {utils.count_tokens(minimal_ctx, llm)} / {config.MODEL_N_CTX}\033[0m")
    
    logger.info(f"\033[33m=== MODEL GENERATION (COMMUNITY) ===\033[0m")
    sig = build_content._get_signature(source, True)
    max_body = 300 - len(sig)
    reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_body, temperature=0.5)
    if utils.count_graphemes(reply) > max_body:
        truncated = reply[:max_body]
        last_dot = truncated.rfind(".")
        reply = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
    reply = reply.strip() + sig
    
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")