import os
import sys
import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
import config
import bsky
import utils
import owner
import community
import digest
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    tasks_raw = os.getenv("TASKS", "[]").strip()
    state_raw = os.getenv("STATE_JSON", "{}").strip()
    
    try:
        tasks = json.loads(tasks_raw) if tasks_raw else []
        state = json.loads(state_raw) if state_raw else {}
    except json.JSONDecodeError as e:
        logger.error(f"[bot] Failed to parse input: {e}")
        sys.exit(1)
    
    client = httpx.AsyncClient(timeout=60)
    llm = None
    
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        from generator import get_model
        llm = get_model()
        if not llm:
            logger.error("[bot] Model failed to load")
            sys.exit(1)
        
        results = []
        for task in tasks:
            task_type = task.get("type")
            logger.info(f"[bot] Processing task: {task_type}")
            
            if task_type == "owner_command":
                result = await owner.process(client, llm, task)
                results.append({"type": "owner_command", "status": "ok" if result else "fail"})
                
            elif task_type == "digest_comment":
                result = await community.process(client, llm, task)
                results.append({"type": "digest_comment", "status": "ok" if result else "fail"})
                
            elif task_type in ("digest_mini", "digest_full"):
                actual_type = task_type.replace("digest_", "")
                digest_result = await digest.run(llm, actual_type)
                
                if digest_result.get("status") == "ok":
                    logger.info("[bot] Digest posted successfully, clearing pending")
                    state.pop("digest_pending_type", None)
                    state["digest_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    state["digest_retry_count"] = 0
                    if actual_type:
                        state["digest_type"] = actual_type
                elif digest_result.get("downgrade_next"):
                    logger.warning("[bot] Digest failed, downgrading next to mini")
                    state.pop("digest_pending_type", None)
                    state["digest_type"] = "mini"
                    state["digest_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    state["digest_retry_count"] = 0
                else:
                    logger.info("[bot] Digest failed, keeping pending for retry")
                    state["digest_retry_count"] = state.get("digest_retry_count", 0) + 1
                
                results.append({"type": task_type, "status": digest_result.get("status", "unknown")})
            else:
                logger.warning(f"[bot] Unknown task type: {task_type}")
                results.append({"type": task_type, "status": "skipped"})
        
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a") as f:
                f.write(f"state_json={json.dumps(state, ensure_ascii=False)}\n")
                f.write(f"results={json.dumps(results, ensure_ascii=False)}\n")
        
        logger.info(f"[bot] Completed {len(results)} tasks")
        
    finally:
        await client.aclose()
        if llm and hasattr(llm, 'close'):
            llm.close()

if __name__ == "__main__":
    asyncio.run(main())
