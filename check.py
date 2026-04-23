import os
import sys
import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
import config
import bsky
import parsers
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def update_secret(key: str, value: str, pat: str, repo: str):
    if not value or not repo or not pat:
        return
    proc = await asyncio.create_subprocess_exec(
        "gh", "secret", "set", key, "--body", value, "--repo", repo,
        env={**os.environ, "GH_TOKEN": pat},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

def _check_timer(last_key: str, interval_sec: int) -> bool:
    last_str = os.getenv(last_key, "").strip()
    if not last_str:
        logger.debug(f"[timer] {last_key} is empty. Returning due=True")
        return True
    try:
        last_dt = datetime.fromisoformat(last_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - last_dt).total_seconds()
        is_due = delta >= interval_sec
        logger.info(f"[timer] {last_key} delta={delta:.0f}s, due={is_due}")
        return is_due
    except Exception as e:
        logger.error(f"[timer] {last_key} parse error: {e}. Returning due=True")
        return True

async def run():
    last_processed = os.getenv("LAST_PROCESSED", "").strip()
    tasks = []
    now_utc = datetime.now(timezone.utc).isoformat()
    owner_count = 0
    digest_comment_count = 0

    async with httpx.AsyncClient(timeout=30) as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        params = {"limit": 100}
        if last_processed and last_processed not in ("{}", "null", "none"):
            params["seen_at"] = last_processed

        r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
        r.raise_for_status()
        notifs = parsers.parse_notifications(r.json())
        total_notifs = len(notifs)

        active_uri = os.getenv("ACTIVE_DIGEST_URI", "").strip()
        for n in notifs:
            if n["indexed_at"] <= last_processed:
                continue
            if n["reason"] not in ("reply", "mention"):
                continue
            if active_uri and n["parent_uri"] and active_uri in n["parent_uri"]:
                tasks.append({"type": "digest_comment", "uri": n["uri"], "text": n["text"], "author_did": n["author_did"], "parent_uri": n["parent_uri"]})
                digest_comment_count += 1
            elif n["author_did"] == config.OWNER_DID:
                tasks.append({"type": "owner_command", "uri": n["uri"], "text": n["text"], "author_did": n["author_did"]})
                owner_count += 1

    digest_task_type = "none"
    pat = os.environ.get("PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if _check_timer("LAST_MINI_DIGEST", 4 * 3600):
        tasks.append({"type": "digest_mini"})
        digest_task_type = "digest_mini"
        await update_secret("LAST_MINI_DIGEST", now_utc, pat, repo)
        logger.info("[TIMER] LAST_MINI_DIGEST reset successfully (pre-emptive).")
    elif _check_timer("LAST_FULL_DIGEST", 2 * 3600):
        tasks.append({"type": "digest_full"})
        digest_task_type = "digest_full"
        await update_secret("LAST_FULL_DIGEST", now_utc, pat, repo)
        logger.info("[TIMER] LAST_FULL_DIGEST reset successfully (pre-emptive).")

    def _write_work_data():
        with open("work_data.json", "w") as f:
            json.dump({"tasks": tasks}, f)
    await asyncio.to_thread(_write_work_data)

    await update_secret("LAST_PROCESSED", now_utc, pat, repo)
    relevant = owner_count + digest_comment_count
    logger.info(f"[checker] Received {total_notifs} notifs. Relevant: {relevant} (Owner: {owner_count}, Digest comments: {digest_comment_count}, Digest task: {digest_task_type}). Total queued: {len(tasks)}. LAST_PROCESSED updated.")
    out_path = os.getenv("GITHUB_OUTPUT")
    if out_path:
        def _write_output():
            with open(out_path, "a") as f:
                f.write(f"status={'true' if tasks else 'false'}\n")
                f.write(f"last_processed={now_utc}\n")
        await asyncio.to_thread(_write_output)
    if not tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())
