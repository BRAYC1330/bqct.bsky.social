import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import json
import asyncio
import logging
import time
from src.state import settings as config
from src.state import logging_config
from src.state import github_io
from src.clients import bsky, httpx_base
from src.llm import loader as llm_loader
from src.core import router

logging_config.setup_logging()
logger = logging.getLogger(__name__)

async def run():
    start_time = time.monotonic()
    tasks_json = os.environ.get("TASKS_JSON", "[]")
    try:
        tasks = json.loads(tasks_json)
    except json.JSONDecodeError:
        return
    if not tasks: return
    metrics = {"total_tasks": len(tasks), "success": 0, "failed": 0, "model_load_time": 0.0, "execution_time": 0.0}
    new_digest_uri = ""
    client = httpx_base.get_client()
    llm_cache = None
    try:
        await bsky.login_with_cache(config.BOT_HANDLE, config.BOT_PASSWORD)
        needs_llm = any(t.get("type") in router.ALLOWED_TASK_TYPES for t in tasks)
        if needs_llm:
            model_start = time.monotonic()
            llm_cache = llm_loader.load()
            metrics["model_load_time"] = round(time.monotonic() - model_start, 2)
            if not llm_cache: return
        exec_start = time.monotonic()
        for idx, task in enumerate(tasks):
            t_type = task.get("type", "UNKNOWN")
            if t_type not in router.ALLOWED_TASK_TYPES:
                metrics["failed"] += 1
                continue
            handler = router.get_handler(t_type)
            if handler:
                try:
                    result = await handler(task, client, llm_cache)
                    if t_type.startswith("digest_") and result: new_digest_uri = result
                    metrics["success"] += 1
                except Exception:
                    metrics["failed"] += 1
        metrics["execution_time"] = round(time.monotonic() - exec_start, 2)
    except Exception:
        metrics["failed"] = metrics["total_tasks"]
    finally:
        await client.aclose()
    total_time = round(time.monotonic() - start_time, 2)
    github_io.write_output("new_digest_uri", new_digest_uri)
    github_io.write_output("metrics", json.dumps(metrics))

if __name__ == "__main__":
    asyncio.run(run())
