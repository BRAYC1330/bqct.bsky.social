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
        return None
    logger.info(f"[DIGEST] PARSED_TRENDS_COUNT: {len(trends)}")
    logger.info(f"[{task_type.upper()} DIGEST INPUT] current_rank: {trends[0].get('current_rank')} | keyword: {trends[0].get('keyword')}")
    final_post = await build_content.build_digest(llm, trends, task_type, max_total=300)
    return final_post