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

        llm_types = {"digest_mini", "digest_full", "digest_comment", "owner_command"}
        needs_llm = any(t.get("type") in llm_types for t in tasks)
        if needs_llm:
            import generator
            llm_cache = generator.get_model()
            if not llm_cache:
                logger.error("[main] Model load failed, skipping remaining tasks")
                return

        import digest
        import community
        import owner

        handlers = {
            "digest_mini": lambda t: digest.run(client, llm_cache, "digest_mini"),
            "digest_full": lambda t: digest.run(client, llm_cache, "digest_full"),
            "digest_comment": lambda t: community.process(client, llm_cache, t),
            "owner_command": lambda t: owner.process(client, llm_cache, t)
        }

        for idx, task in enumerate(tasks):
            t_type = task.get("type", "UNKNOWN")
            logger.debug(f"[main] Processing task #{idx}: {t_type}")
            handler = handlers.get(t_type)
            if handler:
                await handler(task)
            else:
                logger.warning(f"[main] Unknown type: {t_type}")
    finally:
        await client.aclose()
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())