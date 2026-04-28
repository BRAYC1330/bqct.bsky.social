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
    parent_cid = chain.get("parent_cid", "")
    try:
        r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 1})
        if r.status_code == 200:
            replies = r.json().get("thread", {}).get("replies", [])
            for rep in replies:
                post = rep.get("post", {})
                if post.get("author", {}).get("did") == config.BOT_DID:
                    return
    except Exception as e:
        logger.warning(f"[community] Reply check failed: {e}")
    kw = generator.extract_chainbase_keyword(llm, user_text)
    search_data = ""
    source = ""
    if kw:
        logger.info(f"\033[36m[CHAINBASE KEYWORD GENERATED] {kw}\033[0m")
        search_data = await search.fetch_chainbase(client, kw)
        source = "chainbase"
    if not search_data:
        reply = build_content.get_no_data_response(kw or "query")
        await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
        return
    clean_query = utils.clean_for_llm(user_text)
    clean_search = utils.clean_for_llm(search_data)
    minimal_ctx = f"Q: {clean_query}\nA: {clean_search}"
    reply = await build_content.build_reply(llm, minimal_ctx, clean_query, search_data, source, max_total=300)
    await bsky.post_reply(client, config.BOT_DID, reply, root_uri, root_cid, uri, parent_cid)
    logger.info(f"[community] Replied to {uri[:40]}...")