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
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

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
        logger.debug(f"[timer] {last_key} delta={delta:.0f}s, due={is_due}")
        return is_due
    except Exception as e:
        logger.warning(f"[timer] {last_key} parse error: {e}. Returning due=True")
        return True

async def run():
    last_processed = os.getenv("LAST_PROCESSED", "").strip()
    tasks = []
    now_utc = datetime.now(timezone.utc).isoformat()
    owner_count = 0
    digest_comment_count = 0
    clear_mini = os.getenv("CLEAR_MINI", "false").lower() == "true"
    clear_full = os.getenv("CLEAR_FULL", "false").lower() == "true"
    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        notifs = await bsky.fetch_notifications(client, limit=100, seen_at=last_processed)
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
        digest_task_type = "mini"
        if not clear_mini:
            utils.update_github_secret("LAST_MINI_DIGEST", now_utc)
            logger.debug("[TIMER] LAST_MINI_DIGEST reset")
        else:
            logger.debug("[TIMER] LAST_MINI_DIGEST update skipped (clear flag active)")
    elif _check_timer("LAST_FULL_DIGEST", 2 * 3600):
        tasks.append({"type": "digest_full"})
        digest_task_type = "full"
        if not clear_full:
            utils.update_github_secret("LAST_FULL_DIGEST", now_utc)
            logger.debug("[TIMER] LAST_FULL_DIGEST reset")
        else:
            logger.debug("[TIMER] LAST_FULL_DIGEST update skipped (clear flag active)")
    tasks_json = json.dumps(tasks, ensure_ascii=False)
    out_path = os.getenv("GITHUB_OUTPUT")
    has_tasks = len(tasks) > 0
    if out_path:
        with open(out_path, "a") as f:
            f.write(f"status={'true' if has_tasks else 'false'}\n")
            f.write(f"tasks={tasks_json}\n")
            f.write(f"last_processed={now_utc}\n")
    logger.info(f"[checker] Tasks: {len(tasks)} (Owner: {owner_count}, Community: {digest_comment_count}, Digest: {digest_task_type})")
    if not has_tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())