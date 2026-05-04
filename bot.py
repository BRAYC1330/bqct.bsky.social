import os
import sys
import json
import asyncio
import logging
import httpx
from functools import partial
import config
import bsky
import generator
import community
import owner
import digest
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    tasks_json = os.getenv("TASKS_JSON", "[]")
    try: tasks = json.loads(tasks_json)
    except json.JSONDecodeError: tasks = []
    if not tasks:
        logger.info("[MAIN] No tasks.")
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a") as f:
                f.write("status=false\nall_ok=true\n")
        return
        
    logger.info(f"[MAIN] Loaded {len(tasks)} tasks")
    client = httpx.AsyncClient(timeout=30)
    llm = generator.get_model()
    if not llm:
        logger.error("[MAIN] Model load failed. Exiting.")
        sys.exit(1)
        
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        handlers = {
            "digest_mini": partial(digest.run, client, llm, "digest_mini"),
            "digest_full": partial(digest.run, client, llm, "digest_full"),
            "digest_comment": partial(community.process, client, llm),
            "owner_command": partial(owner.process, client, llm)
        }
        ok, fail = 0, 0
        for task in tasks:
            task_type = task.get("type", "")
            handler = handlers.get(task_type)
            if not handler:
                logger.warning(f"[MAIN] Unknown task type: {task_type}")
                fail += 1
                continue
            try:
                await handler(task) if task_type in ("digest_comment", "owner_command") else await handler()
                ok += 1
            except Exception as e:
                logger.error(f"[MAIN] Task {task_type} failed: {e}")
                fail += 1
                
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a") as f:
                f.write(f"status={'true' if ok > 0 else 'false'}\n")
                f.write(f"all_ok={'true' if fail == 0 else 'false'}\n")
        logger.info(f"[MAIN] Metrics: {ok} ok, {fail} fail")
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())