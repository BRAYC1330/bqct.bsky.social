import os
import logging
import parser
import bsky
import generator
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

_processed_cache = set()

async def process_digest_community(client, llm, digest_uri, digest_text):
    if digest_uri in _processed_cache:
        return
    _processed_cache.add(digest_uri)

    thread = await bsky.get_thread_raw(client, digest_uri)
    if not thread:
        return
    nodes = await parser.parse_thread(thread, "", client)
    comments = [n for n in nodes if not n.get("is_root") and n.get("did") != config.BOT_DID]
    if not comments:
        return
    comments = comments[:config.COMMUNITY_MAX_COMMENTS]

    digest_ctx = os.getenv("CONTEXT_DIGEST", "No digest context.")
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-COMMENTS-RECEIVED ===\n{[{'handle': c['handle'], 'text': c['text'], 'uri': c['uri'][:30]} for c in comments]}\n=== END ===")

    plan = await generator.generate_community_plan(llm, digest_ctx, comments)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-COMMUNITY-PLAN ===\n{plan}\n=== END ===")

    lc, rc = 0, 0
    for uri in plan.get("likes", []):
        if lc >= config.COMMUNITY_MAX_LIKES:
            break
        try:
            c = next((x for x in comments if x["uri"] == uri), None)
            if c:
                await bsky.like_post(client, config.BOT_DID, uri, c.get("cid", ""))
                lc += 1
        except Exception:
            pass
    for rp in plan.get("replies", []):
        if rc >= config.COMMUNITY_MAX_REPLIES:
            break
        uri, txt = rp.get("uri"), rp.get("text", "")
        if not uri or not txt:
            continue
        try:
            c = next((x for x in comments if x["uri"] == uri), None)
            if c:
                await bsky.post_reply(client, config.BOT_DID, txt[:config.COMMUNITY_MAX_REPLY_CHARS], digest_uri, "", uri, c.get("cid", ""))
                rc += 1
        except Exception:
            pass
    logger.info(f"[COMMUNITY] Done: {lc} likes, {rc} replies")
