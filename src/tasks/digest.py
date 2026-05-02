import logging
import config
import bsky
import search
import build_content

logger = logging.getLogger(__name__)

async def run(client, llm, task_type="digest_mini") -> str | None:
    trends = await search.get_trending_topics_raw()
    if not trends: return None

    final_post = await build_content.build_digest(llm, trends, task_type, max_total=300)
    if not final_post: return None

    try:
        resp = await bsky.post_root(client, config.BOT_DID, final_post)
        return resp.get("uri")
    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")
        return None