import os
import json
import asyncio
import logging
import httpx
import config
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    logger.info("[main] === START ===")
    if not os.path.exists("work_data.json"):
        logger.error("[main] work_data.json NOT FOUND")
        return
    with open("work_data.json") as f:
        data = json.load(f)
    tasks = data.get("tasks", [])
    logger.info(f"[main] Loaded {len(tasks)} tasks")
    if not tasks:
        logger.warning("[main] Task list empty")
        return

    client = httpx.AsyncClient(timeout=30)
    llm_cache = None
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        for idx, task in enumerate(tasks):
            t_type = task.get("type", "UNKNOWN")
            logger.debug(f"[main] Processing task #{idx}: {t_type}")
            if t_type in ("digest_mini", "digest_full", "digest_comment", "owner_command"):
                if llm_cache is None:
                    import generator
                    llm_cache = generator.get_model()
                    if not llm_cache:
                        logger.error("[main] Model load failed, skipping remaining tasks")
                        break
                llm = llm_cache
                if t_type in ("digest_mini", "digest_full"):
                    import digest
                    await digest.run(client, llm, t_type)
                elif t_type == "digest_comment":
                    import community
                    await community.process(client, llm, task)
                elif t_type == "owner_command":
                    import owner
                    await owner.process(client, llm, task)
            else:
                logger.warning(f"[main] Unknown type: {t_type}")
    finally:
        await client.aclose()
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())