import os
import json
import asyncio
import logging
import httpx
import config
import generator
import bsky
import community
import owner
import digest
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    logger.info("[main] === START ===")
    
    if not os.path.exists("work_data.json"):
        logger.error("[main] work_data.json NOT FOUND")
        return
    logger.info("[main] work_data.json found, loading...")
    
    with open("work_data.json") as f:
        data = json.load(f)
    tasks = data.get("tasks", [])
    logger.info(f"[main] Tasks loaded: {tasks}")
    
    if not tasks:
        logger.warning("[main] Tasks list is EMPTY")
        return
    
    llm = generator.get_model()
    if not llm:
        logger.error("[main] Failed to load model")
        return
    
    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        
        for idx, task in enumerate(tasks):
            t_type = task.get("type", "UNKNOWN")
            uri = task.get("uri", "N/A")[:40]
            logger.info(f"[main] Processing task #{idx}: type={t_type}, uri={uri}")
            
            if t_type in ("digest_mini", "digest_full"):
                logger.info(f"[main] Calling digest.run({t_type})")
                result = await digest.run(client, llm, t_type)
                logger.info(f"[main] digest.run returned: {result}")
            elif t_type == "digest_comment":
                logger.info("[main] Calling community.process")
                await community.process(client, llm, task)
            elif t_type == "owner_command":
                logger.info("[main] Calling owner.process")
                await owner.process(client, llm, task)
            else:
                logger.warning(f"[main] Unknown task type: {t_type}")
    finally:
        await client.aclose()
    
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
