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

_rl_queue, _rl_max, _rl_win = deque(), 10, 60

def check_rate_limit() -> bool:
    now = time()
    while _rl_queue and _rl_queue[0] < now - _rl_win:
        _rl_queue.popleft()
    if len(_rl_queue) >= _rl_max:
        return False
    _rl_queue.append(now)
    return True

async def main():
    logger.info("[main] === START ===")
    if not os.path.exists("work_data.json"):
        return
    def _load():
        with open("work_data.json") as f:
            return json.load(f)
    data = await asyncio.to_thread(_load)
    tasks = data.get("tasks", [])
    if not tasks:
        return

    llm = generator.get_model()
    if not llm:
        return

    async with httpx.AsyncClient(timeout=30) as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        for idx, task in enumerate(tasks):
            if not check_rate_limit():
                await asyncio.sleep(1)
                continue
            t_type = task.get("type", "UNKNOWN")
            uri = task.get("uri", "N/A")[:40]
            logger.info(f"[main] Task #{idx}: type={t_type}, uri={uri}")
            if t_type in ("digest_mini", "digest_full"):
                await digest.run(client, llm, t_type)
            elif t_type == "digest_comment":
                await community.process(client, llm, task)
            elif t_type == "owner_command":
                await owner.process(client, llm, task)
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())