import os
import sys
import json
import asyncio
import logging
import subprocess
import httpx
from datetime import datetime, timezone
import config
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def update_secret(key, value):
    if not value: return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat: return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
        logger.info(f"[checker] Secret {key} updated successfully.")
    except Exception as e:
        logger.error(f"[checker] Secret update failed: {e}")

def _check_timer(last_key: str, interval_sec: int) -> bool:
    last_str = os.getenv(last_key, "").strip()
    if not last_str:
        logger.warning(f"[timer] {last_key} is empty. Returning due=True")
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

    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        params = {"limit": 100}
        if last_processed and last_processed not in ("{}", "null", "none"):
            params["seen_at"] = last_processed

        r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
        r.raise_for_status()
        notifs = r.json().get("notifications", [])
        total_notifs = len(notifs)

        active_uri = os.getenv("ACTIVE_DIGEST_URI", "").strip()
        for n in notifs:
            idx = n.get("indexedAt", "")
            if idx <= last_processed:
                continue
            reason = n.get("reason", "")
            if reason not in ("reply", "mention"):
                continue
            author_did = n.get("author", {}).get("did", "")
            text = (n.get("record", {}).get("text") or "").strip()
            uri = n.get("uri", "")
            record = n.get("record", {})
            parent_uri = record.get("reply", {}).get("parent", {}).get("uri", "") if isinstance(record, dict) else ""

            if active_uri and parent_uri and active_uri in parent_uri:
                tasks.append({"type": "digest_comment", "uri": uri, "text": text, "author_did": author_did, "parent_uri": parent_uri})
                digest_comment_count += 1
            elif author_did == config.OWNER_DID:
                tasks.append({"type": "owner_command", "uri": uri, "text": text, "author_did": author_did})
                owner_count += 1
    finally:
        await client.aclose()

    digest_task_type = "none"
    if _check_timer("LAST_MINI_DIGEST", 4 * 3600):
        tasks.append({"type": "digest_mini"})
        digest_task_type = "digest_mini"
        update_secret("LAST_MINI_DIGEST", now_utc)
        logger.info("[TIMER] LAST_MINI_DIGEST reset successfully (pre-emptive).")
    elif _check_timer("LAST_FULL_DIGEST", 2 * 3600):
        tasks.append({"type": "digest_full"})
        digest_task_type = "digest_full"
        update_secret("LAST_FULL_DIGEST", now_utc)
        logger.info("[TIMER] LAST_FULL_DIGEST reset successfully (pre-emptive).")

    with open("work_data.json", "w") as f:
        json.dump({"tasks": tasks}, f)

    update_secret("LAST_PROCESSED", now_utc)
    relevant = owner_count + digest_comment_count
    logger.info(f"[checker] Received {total_notifs} notifs. Relevant: {relevant} (Owner: {owner_count}, Digest comments: {digest_comment_count}, Digest task: {digest_task_type}). Total queued: {len(tasks)}. LAST_PROCESSED updated.")
    out_path = os.getenv("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a") as f:
            f.write(f"status={'true' if tasks else 'false'}\n")
            f.write(f"last_processed={now_utc}\n")
    if not tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())
