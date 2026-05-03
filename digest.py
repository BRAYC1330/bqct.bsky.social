import logging
import config
import bsky
import search
import build_content
logger = logging.getLogger(__name__)
async def run(llm, task_type: str):
    trends = await search.get_trending_topics_raw()
    if not trends:
        logger.warning("[DIGEST] No trends fetched")
        return {"status": "fail", "reason": "no_trends"}
    logger.info(f"[DIGEST] PARSED_TRENDS_COUNT: {len(trends)}")
    logger.info(f"[FULL DIGEST INPUT] current_rank: {trends[0].get('current_rank')} | keyword: {trends[0].get('keyword')}")
    
    final_post = None
    for attempt in range(3):
        logger.info(f"[MODEL GENERATION (DIGEST)] Attempt {attempt + 1}/3")
        final_post = await build_content.build_digest(llm, trends, task_type, max_total=300, retry_count=attempt)
        if final_post:
            break
        logger.warning(f"[DIGEST] Attempt {attempt + 1} failed or too long")
        
    if not final_post:
        logger.error("[DIGEST] Failed after 3 attempts. Skipping post.")
        return {"status": "fail", "reason": "length_retry_exhausted", "downgrade_next": True}
        
    try:
        await bsky.post_root(config.BOT_DID, final_post)
        logger.info(f"[DIGEST] Posted successfully | Length: {len(final_post)}")
        return {"status": "ok", "digest_type": task_type}
    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")
        return {"status": "fail", "reason": "post_error"}