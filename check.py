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

async def run():
    last_processed_raw = os.getenv("LAST_PROCESSED", "{}").strip()
    try:
        state = json.loads(last_processed_raw) if last_processed_raw else {}
    except json.JSONDecodeError:
        state = {}

    seen_at = state.get("seen_at", "").strip()
    digest_uri = state.get("digest_uri", "").strip()
    last_digest_time_str = state.get("digest_time", "").strip()
    last_digest_type = state.get("digest_type", "mini").strip()

    tasks = []
    now_utc = datetime.now(timezone.utc)
    now_utc_str = now_utc.isoformat().replace("+00:00", "Z")
    owner_count = 0
    digest_comment_count = 0

    if not seen_at:
        seen_at = now_utc_str

    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        notifs = await bsky.fetch_notifications(client, limit=100, seen_at=seen_at)
        for n in notifs:
            idx = n.get("indexedAt", "")
            if idx <= seen_at:
                continue
            reason = n.get("reason", "")
            if reason not in ("reply", "mention"):
                continue
            author_did = n.get("author", {}).get("did", "")
            text = (n.get("record", {}).get("text") or "").strip()
            uri = n.get("uri", "")
            record = n.get("record", {})
            
            reply_data = record.get("reply", {}) if isinstance(record, dict) else {}
            parent_uri = reply_data.get("parent", {}).get("uri", "")
            root_uri = reply_data.get("root", {}).get("uri", "")
            
            if digest_uri and root_uri == digest_uri:
                tasks.append({"type": "digest_comment", "uri": uri, "text": text, "author_did": author_did, "parent_uri": parent_uri})
                digest_comment_count += 1
                continue

            if author_did == config.OWNER_DID:
                tasks.append({"type": "owner_command", "uri": uri, "text": text, "author_did": author_did})
                owner_count += 1
    finally:
        await client.aclose()

    scheduled_type = None
    if last_digest_time_str:
        try:
            last_dt = datetime.fromisoformat(last_digest_time_str.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now_utc - last_dt).total_seconds() >= 2 * 3600:
                scheduled_type = "full" if last_digest_type == "mini" else "mini"
        except Exception:
            scheduled_type = "mini"
    else:
        scheduled_type = "mini"

    if scheduled_type:
        tasks.append({"type": f"digest_{scheduled_type}"})
        state["digest_type"] = scheduled_type
        state["digest_time"] = now_utc_str
        logger.info(f"[TIMER] Digest scheduled: {scheduled_type}")

    state["seen_at"] = now_utc_str
    tasks_json = json.dumps(tasks, ensure_ascii=False)
    out_path = os.getenv("GITHUB_OUTPUT")
    has_tasks = len(tasks) > 0
    if out_path:
        with open(out_path, "a") as f:
            f.write(f"status={'true' if has_tasks else 'false'}\n")
            f.write(f"tasks={tasks_json}\n")
            f.write(f"state_json={json.dumps(state, ensure_ascii=False)}\n")

    logger.info(f"[checker] Tasks: {len(tasks)} (Owner: {owner_count}, Community: {digest_comment_count}, Digest: {scheduled_type or 'none'})")
    if not has_tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())