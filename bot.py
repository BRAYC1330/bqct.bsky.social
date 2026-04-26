import os
import json
import asyncio
import logging
import httpx
from typing import Dict, List, Any, Callable, Awaitable, TypedDict, Optional
import config
import bsky
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

class TaskDict(TypedDict, total=False):
    type: str
    uri: str
    text: str
    author_did: str
    parent_uri: str

async def main() -> None:
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

    limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0)
    client = httpx.AsyncClient(limits=limits, timeout=timeout)

    llm_cache: Optional[Any] = None
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)

        llm_types = {"digest_mini", "digest_full", "digest_comment", "owner_command"}
        needs_llm = any(t.get("type") in llm_types for t in tasks)
        if needs_llm:
            import generator
            try:
                llm_cache = generator.get_model()
            except OSError as e:
                logger.error(f"[main] Model load failed: {e}")
                return
            if not llm_cache:
                logger.error("[main] Model load failed, skipping remaining tasks")
                return

        import digest
        import community
        import owner

        handlers: Dict[str, Callable[[TaskDict], Awaitable[None]]] = {
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
                try:
                    await handler(task)
                except httpx.HTTPStatusError as e:
                    logger.error(f"[main] HTTP error for task {t_type}: {e.response.status_code}")
                except (httpx.RequestError, RuntimeError, ValueError) as e:
                    logger.error(f"[main] Task {t_type} execution failed: {e}")
            else:
                logger.warning(f"[main] Unknown type: {t_type}")
    except httpx.RequestError as e:
        logger.error(f"[main] Global network request failed: {e}")
    finally:
        await client.aclose()
    logger.info("[main] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())