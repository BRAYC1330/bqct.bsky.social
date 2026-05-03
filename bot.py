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
                final_post = await digest.run(llm, actual_type)
                if final_post:
                    try:
                        resp = await bsky.post_root(client, config.BOT_DID, final_post)
                        uri = resp.get("uri", "")
                        logger.info(f"[DIGEST] Posted {actual_type} | URI: {uri[:40]}... | Length: {len(final_post)}")
                        state["digest_uri"] = uri
                        state["digest_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        results.append({"type": task_type, "status": "ok", "uri": uri})
                    except Exception as e:
                        logger.error(f"[DIGEST] Post failed: {e}")
                        results.append({"type": task_type, "status": "fail", "reason": "post_error"})
                else:
                    logger.warning(f"[DIGEST] Generation failed for {actual_type}, skipping this run")
                    results.append({"type": task_type, "status": "skip", "reason": "generation_failed"})
            else:
                logger.warning(f"[bot] Unknown task type: {task_type}")
                results.append({"type": task_type, "status": "skipped"})
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a") as f:
                f.write(f"state_json={json.dumps(state, ensure_ascii=False)}\n")
                f.write(f"results={json.dumps(results, ensure_ascii=False)}\n")
                f.write(f"new_digest_uri={state.get('digest_uri', '')}\n")
                f.write(f"sched_type={state.get('digest_type', '')}\n")
        logger.info(f"[bot] Completed {len(results)} tasks")
    finally:
        await client.aclose()
        if llm and hasattr(llm, 'close'):
            llm.close()
if __name__ == "__main__":
    asyncio.run(main())