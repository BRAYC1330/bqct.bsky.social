import os
import sys
import asyncio
import json
import logging
import subprocess
import config
import tempfile
import bsky
import utils
from datetime import datetime, timezone
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
LAST_PROCESSED = os.getenv("LAST_PROCESSED", "").strip()
def is_empty(value):
    return not value or value.strip().lower() in ("", "{}", "null", "none")
def update_secret_via_gh(key, value):
    if not value: return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", os.environ["GITHUB_REPOSITORY"]]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": os.environ["PAT"]}, check=True)
        logger.info(f"[secret_update] {key} updated immediately")
    except Exception as e:
        logger.error(f"[secret_update] Failed to update {key}: {e}")
async def fetch_all_notifications(client, since: str):
    all_notifs = []
    seen_uris = set()
    cursor = None
    limit = getattr(config, "NOTIF_LIMIT", 100)
    logger.info(f"[CHECK] Starting pagination since {since} with limit {limit}")
    for attempt in range(5):
        try:
            while True:
                params = {"limit": limit}
                if cursor:
                    params["cursor"] = cursor
                r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
                if r.status_code != 200:
                    r.raise_for_status()
                data = r.json()
                batch = data.get("notifications", [])
                if not batch:
                    break
                for n in batch:
                    uri = n.get("uri")
                    if uri and uri not in seen_uris:
                        all_notifs.append(n)
                        seen_uris.add(uri)
                oldest_in_batch = batch[-1].get("indexedAt", "")
                if oldest_in_batch <= since:
                    break
                cursor = data.get("cursor")
                if not cursor:
                    break
            logger.info(f"[CHECK] Retrieved {len(all_notifs)} notifications")
            return all_notifs
        except Exception as e:
            wait = min(30, 2 ** attempt)
            logger.warning(f"[CHECK] Error: {e}, retrying in {wait}s")
            await asyncio.sleep(wait)
    return None
async def main():
    logger.info("[main] Starting notification check")
    if not all([config.BOT_HANDLE, config.BOT_PASSWORD, config.OWNER_DID, config.PAT, config.GITHUB_REPOSITORY]):
        logger.critical("[main] Missing required environment variables")
        sys.exit(1)
    github_output = os.getenv("GITHUB_OUTPUT", "")
    if is_empty(LAST_PROCESSED):
        logger.warning("[main] LAST_PROCESSED is empty, setting initial value")
        initial = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        update_secret_via_gh("LAST_PROCESSED", initial)
        if github_output:
            with open(github_output, "a") as f:
                f.write(f"last_processed={initial}\n")
        sys.exit(0)
    logger.info(f"[main] Checking notifications since {LAST_PROCESSED}")
    async with bsky.get_client() as client:
        try:
            await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
            notifications = await fetch_all_notifications(client, LAST_PROCESSED)
            if notifications is None:
                logger.warning("[main] API unavailable after retries, skipping")
                sys.exit(0)
            latest_idx = LAST_PROCESSED
            relevant = []
            for n in notifications:
                idx = n.get("indexedAt", "")
                author_did = n.get("author", {}).get("did", "")
                if idx > latest_idx:
                    latest_idx = idx
                if idx <= LAST_PROCESSED:
                    continue
                if author_did != config.OWNER_DID:
                    continue
                txt = (n.get("record", {}).get("text") or "").strip()
                uri = n.get("uri", "")
                has_search = "!c" in txt.lower() or "!t" in txt.lower()
                search_type = "chainbase" if "!c" in txt.lower() else ("tavily" if "!t" in txt.lower() else None)
                relevant.append({"uri": uri, "text": txt, "has_search": has_search, "search_type": search_type})
            update_secret_via_gh("LAST_PROCESSED", latest_idx)
            if github_output:
                with open(github_output, "a") as f:
                    f.write(f"last_processed={latest_idx}\n")
            if relevant:
                logger.info(f"[main] Found {len(relevant)} relevant notifications:")
                for i, r in enumerate(relevant):
                    logger.info(f"  [{i+1}] URI: {r['uri'][:40]}... | Text: {r['text'][:120]} | search: {r['has_search']}")
                if github_output:
                    with open(github_output, "a") as f:
                        f.write("has_work=true\n")
                with tempfile.NamedTemporaryFile('w', dir='.', delete=False, suffix='.tmp') as tf:
                    json.dump({"items": relevant}, tf)
                    tf.flush()
                    os.fsync(tf.fileno())
                    temp_name = tf.name
                os.replace(temp_name, "work_data.json")
            elif notifications:
                logger.info("[main] No new relevant notifications")
        except Exception as e:
            logger.critical(f"[main] Check failed: {e}")
            sys.exit(1)
    logger.info("[main] Check completed")
if __name__ == "__main__":
    asyncio.run(main())
