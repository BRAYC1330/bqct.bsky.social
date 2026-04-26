import os
import json
import asyncio
import logging
import httpx
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Callable, Awaitable, TypedDict, Optional
import config
import bsky
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

ALLOWED_TASK_TYPES = {"digest_mini", "digest_full", "digest_comment", "owner_command"}

class TaskDict(TypedDict, total=False):
    type: str
    uri: str
    text: str
    author_did: str
    parent_uri: str

async def main() -> None:
    start_time = time.monotonic()
    logger.info("[main] === START ===")
    tasks_json = os.environ.get("TASKS_JSON", "[]")
    try:
        tasks: List[TaskDict] = json.loads(tasks_json)
    except json.JSONDecodeError as e:
        logger.error(f"[main] Invalid TASKS_JSON: {e}")
        return
    logger.info(f"[main] Loaded {len(tasks)} tasks")
    if not tasks:
        logger.warning("[main] Task list empty")
        return

    metrics = {
        "total_tasks": len(tasks),
        "success": 0,
        "failed": 0,
        "model_load_time": 0.0,
        "execution_time": 0.0
    }
    new_digest_uri = ""

    limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    client = httpx.AsyncClient(limits=limits, timeout=timeout)

    llm_cache: Optional[Any] = None
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)

        needs_llm = any(t.get("type") in ALLOWED_TASK_TYPES for t in tasks)
        if needs_llm:
            import generator
            model_start = time.monotonic()
            try:
                llm_cache = generator.get_model()
            except OSError as e:
                logger.error(f"[main] Model load failed: {e}")
                return
            metrics["model_load_time"] = round(time.monotonic() - model_start, 2)
            if not llm_cache:
                logger.error("[main] Model load failed, skipping remaining tasks")
                return

        import digest
        import community
        import owner

        handlers: Dict[str, Callable[[TaskDict], Awaitable[Any]]] = {
            "digest_mini": lambda t: digest.run(client, llm_cache, "digest_mini"),
            "digest_full": lambda t: digest.run(client, llm_cache, "digest_full"),
            "digest_comment": lambda t: community.process(client, llm_cache, t),
            "owner_command": lambda t: owner.process(client, llm_cache, t)
        }

        exec_start = time.monotonic()
        for idx, task in enumerate(tasks):
            t_type = task.get("type", "UNKNOWN")
            if t_type not in ALLOWED_TASK_TYPES:
                logger.warning(f"[main] Rejected unknown task type: {t_type}")
                metrics["failed"] += 1
                continue
            logger.debug(f"[main] Processing task #{idx}: {t_type}")
            handler = handlers.get(t_type)
            if handler:
                try:
                    result = await handler(task)
                    if t_type.startswith("digest_") and result:
                        new_digest_uri = result
                    metrics["success"] += 1
                except httpx.HTTPStatusError as e:
                    logger.error(f"[main] HTTP error for task {t_type}: {e.response.status_code}")
                    metrics["failed"] += 1
                except (httpx.RequestError, RuntimeError, ValueError) as e:
                    logger.error(f"[main] Task {t_type} execution failed: {e}")
                    metrics["failed"] += 1
        metrics["execution_time"] = round(time.monotonic() - exec_start, 2)
    except httpx.RequestError as e:
        logger.error(f"[main] Global network request failed: {e}")
        metrics["failed"] = metrics["total_tasks"]
    finally:
        await client.aclose()

    total_time = round(time.monotonic() - start_time, 2)
    logger.info(f"[main] Metrics: {metrics['success']} ok, {metrics['failed']} fail, {total_time}s total")

    out_path = os.getenv("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"new_digest_uri={new_digest_uri}\n")

    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())