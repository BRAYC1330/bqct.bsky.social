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
from collections import deque
from time import time
setup_logging()
logger = logging.getLogger(__name__)

_rate_limit_queue = deque()
_rate_limit_max = 10
_rate_limit_window = 60

def check_rate_limit() -> bool:
    now = time()
    while _rate_limit_queue and _rate_limit_queue[0] < now - _rate_limit_window:
        _rate_limit_queue.popleft()
    if len(_rate_limit_queue) >= _rate_limit_max:
        return False
    _rate_limit_queue.append(now)
    return True

async def main():
    logger.info("[main] === START ===")
    
    if not os.path.exists("work_data.json"):
        logger.error("[main] work_data.json NOT FOUND")
        return
    logger.info("[main] work_data.json found, loading...")
    
    def _load_work_data():
        with open("work_data.json") as f:
            return json.load(f)
    data = await asyncio.to_thread(_load_work_data)
    tasks = data.get("tasks", [])
    logger.info(f"[main] Tasks loaded: {tasks}")
    
    if not tasks:
        logger.warning("[main] Tasks list is EMPTY")
        return
    
    llm = generator.get_model()
    if not llm:
        logger.error("[main] Failed to load model")
        return
    
    async with httpx.AsyncClient(timeout=30) as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        
        for idx, task in enumerate(tasks):
            if not check_rate_limit():
                logger.warning("[main] Rate limit exceeded, skipping task")
                await asyncio.sleep(1)
                continue
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
    
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
