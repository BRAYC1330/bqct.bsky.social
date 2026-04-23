import os
import json
import asyncio
import logging
import config
import generator
import bsky
import community
import owner
import news
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    logger.info("[main] === START ===")
    if not os.path.exists("work_data.json"):
        logger.warning("[main] No work_data.json found. Exiting.")
        return
    with open("work_data.json") as f:
        data = json.load(f)
    tasks = data.get("tasks", [])
    if not tasks:
        logger.info("[main] No tasks. Exiting.")
        return

    llm = generator.get_model()
    async with bsky.get_client() as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        for task in tasks:
            t_type = task.get("type", "")
            if t_type in ("digest_mini", "digest_full"):
                await news.run(client, llm)
            elif t_type == "digest_comment":
                await community.process(client, llm, task)
            elif t_type == "owner_command":
                await owner.process(client, llm, task)
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
