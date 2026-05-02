import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from src.state import settings as config
from src.state import logging_config
from src.state import github_io
from src.clients import bsky, httpx_base

logging_config.setup_logging()
logger = logging.getLogger(__name__)

async def run():
    state = github_io.load_state()
    seen_at = state.get("seen_at", "").strip()
    digest_uri = state.get("digest_uri", "").strip()
    last_digest_time_str = state.get("digest_time", "").strip()
    last_digest_type = state.get("digest_type", "mini").strip()
    tasks = []
    now_utc = datetime.now(timezone.utc)
    now_utc_str = now_utc.isoformat().replace("+00:00", "Z")
    owner_count = 0
    digest_comment_count = 0
    if not seen_at: seen_at = now_utc_str
    client = httpx_base.get_client()
    try:
        await bsky.login_with_cache(config.BOT_HANDLE, config.BOT_PASSWORD)
        notifs = await bsky.fetch_notifications(client, limit=100, seen_at=seen_at)
        for n in notifs:
            idx = n.get("indexedAt", "")
            if idx <= seen_at: continue
            reason = n.get("reason", "")
            if reason not in ("reply", "mention"): continue
            author_did = n.get("author", {}).get("did", "")
            text = (n.get("record", {}).get("text") or "").strip()
            uri = n.get("uri", "")
            record = n.get("record", {})
            reply_data = record.get("reply", {}) if isinstance(record, dict) else {}
            parent_uri = reply_data.get("parent", {}).get("uri", "")
            root_uri = reply_data.get("root", {}).get("uri", "")
            if digest_uri and root_uri == digest_uri:
                if parent_uri and parent_uri.startswith(f"at://{config.BOT_DID}/"): continue
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
            if last_dt.tzinfo is None: last_dt = last_dt.replace(tzinfo=timezone.utc)
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
    state["seen_at"] = now_utc_str
    tasks_json = json.dumps(tasks, ensure_ascii=False)
    has_tasks = len(tasks) > 0
    github_io.write_output("status", "true" if has_tasks else "false")
    github_io.write_output("tasks", tasks_json)
    github_io.save_state(state)
    if not has_tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())
