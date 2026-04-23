import os
import json
import logging
import httpx
from datetime import datetime, timezone
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_client():
    return httpx.AsyncClient(timeout=30)

async def login_with_cache(client, handle, password):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            with open(session_path) as f:
                sess = json.load(f)
            client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
            logger.info("[bsky] Session loaded from cache")
            return
        except:
            pass
    r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    with open(session_path, "w") as f:
        json.dump(sess, f)
    logger.info("[bsky] New session created and cached")

async def post_root(client, bot_did, text):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

async def post_reply(client, bot_did, text, root_uri, root_cid, parent_uri, parent_cid):
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

async def fetch_thread_chain(client, uri):
    r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 0})
    if r.status_code != 200:
        logger.warning(f"[bsky] [get_thread_raw] Failed: {r.status_code}")
        return None
    data = r.json()
    thread = data.get("thread", {})
    post = thread.get("post", {})
    record = post.get("record", {})
    author = post.get("author", {})
    return {
        "root_uri": uri,
        "root_cid": post.get("cid", ""),
        "root_text": record.get("text", ""),
        "parent_cid": record.get("reply", {}).get("parent", {}).get("cid", "") if record.get("reply") else "",
        "chain": [{"record": record, "author": author}]
    }
