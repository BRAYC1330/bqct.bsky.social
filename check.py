import os
import sys
import json
import logging
import httpx
import config
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_client():
    return httpx.AsyncClient(timeout=30)

def check_timer(last_processed: str, interval_hours: int) -> bool:
    from datetime import datetime, timezone, timedelta
    if not last_processed:
        return True
    try:
        last = datetime.fromisoformat(last_processed.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - last) >= timedelta(hours=interval_hours)
    except Exception:
        return True

async def update_secret(key: str, value: str, pat: str, repo: str):
    if not value:
        return
    import subprocess
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    env = {**os.environ, "GH_TOKEN": pat}
    subprocess.run(cmd, env=env, check=True, capture_output=True)

async def main():
    client = await get_client()
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        last_processed = os.environ.get("LAST_PROCESSED", "").strip()
        active_digest_uri = os.environ.get("ACTIVE_DIGEST_URI", "").strip()
        last_mini = os.environ.get("LAST_MINI_DIGEST", "").strip()
        last_full = os.environ.get("LAST_FULL_DIGEST", "").strip()
        mini_due = check_timer(last_mini, 4)
        full_due = check_timer(last_full, 2) if last_full else True
        if full_due and not active_digest_uri:
            logger.warning("LAST_FULL_DIGEST is empty. Returning due=True")
            await update_secret("LAST_FULL_DIGEST", "init", os.environ["PAT"], os.environ["GITHUB_REPOSITORY"])
            logger.info("TIMER LAST_FULL_DIGEST reset successfully (pre-emptive).")
        tasks = []
        if active_digest_uri:
            if mini_due:
                tasks.append({"type": "mini", "uri": active_digest_uri})
            if full_due:
                tasks.append({"type": "full", "uri": active_digest_uri})
        with open("work_data.json", "w") as f:
            json.dump({"tasks": tasks}, f)
        logger.info(f"Relevant: 0 (Owner: 0, Digest comments: 0, Digest task: {tasks[0]['type'] if tasks else 'none'}). Total queued: {len(tasks)}. LAST_PROCESSED updated.")
        await update_secret("LAST_PROCESSED", json.dumps({"ts": str(__import__("datetime").datetime.now(__import__("datetime").timezone.utc))}), os.environ["PAT"], os.environ["GITHUB_REPOSITORY"])
        print(f"::set-output name=status::{'true' if tasks else 'false'}")
        if tasks:
            print(f"::set-output name=last_processed::{json.dumps({'ts': str(__import__('datetime').datetime.now(__import__('datetime').timezone.utc))})}")
    finally:
        await client.aclose()

if __name__ == "__main__":
    __import__("asyncio").run(main())
