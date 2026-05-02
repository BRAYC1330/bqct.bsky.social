import logging
import config
import bsky
import search
import build_content
import utils
logger = logging.getLogger(__name__)
async def run(client, llm, task_type="digest_mini") -> str | None:
    trends = await search.get_trending_topics_raw()
    logger.info(f"[DIGEST] PARSED_TRENDS_COUNT: {len(trends)}")
    if not trends:
        logger.warning("[DIGEST] No trends fetched")
        return None
    logger.info("=== MODEL GENERATION (DIGEST) ===")
    final_post = await build_content.build_digest(llm, trends, task_type, max_total=config.RESPONSE_MAX_CHARS)
    if not final_post:
        logger.warning("[DIGEST] Build failed or empty")
        return None
    if config.RAW_DEBUG:
        logger.info(f"=== MODEL CONTEXT (DIGEST) ===\n{final_post}")
        logger.info(f"[TOKENS] {utils.count_tokens(final_post, llm)} / {config.MODEL_N_CTX}")
    try:
        resp = await bsky.post_root(client, config.BOT_DID, final_post)
        logger.info(f"[DIGEST] Posted {task_type}")
        return resp.get("uri")
    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")
        return None