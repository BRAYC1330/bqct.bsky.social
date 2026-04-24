import os
import json
import logging
import httpx
from datetime import datetime, timezone
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def login_with_cache(client, handle, password):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            with open(session_path) as f:
                sess = json.load(f)
            client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
            logger.debug("[bsky] Session loaded from cache")
            return
        except Exception:
            pass
    r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    with open(session_path, "w") as f:
        json.dump(sess, f)
    logger.debug("[bsky] New session created")

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
        logger.warning(f"[bsky] Thread fetch failed: {r.status_code}")
        return None
    data = r.json()
    thread = data.get("thread", {})
    post = thread.get("post", {})
    record = post.get("record", {})
    reply_ref = record.get("reply", {})
    root_ref = reply_ref.get("root", {}) if reply_ref else {}
    parent_ref = reply_ref.get("parent", {}) if reply_ref else {}
    root_uri = root_ref.get("uri") if root_ref.get("uri") else uri
    root_cid = root_ref.get("cid") if root_ref.get("cid") else post.get("cid", "")
    root_text = record.get("text", "") if root_uri == uri else ""
    parent_cid = parent_ref.get("cid", "") if parent_ref else ""

    embeds = {"links": [], "reposts": []}
    raw_embed = post.get("embed", {})
    if raw_embed:
        if raw_embed.get("$type") == "app.bsky.embed.external#view":
            ext = raw_embed.get("external", {})
            embeds["links"].append({"url": ext.get("uri"), "title": ext.get("title"), "desc": ext.get("description", "")[:150]})
        elif raw_embed.get("$type") == "app.bsky.embed.record#view":
            rec = raw_embed.get("record", {})
            if rec.get("$type") == "app.bsky.embed.record#viewRecord":
                val = rec.get("value", {})
                embeds["reposts"].append({
                    "author": rec.get("author", {}).get("handle"),
                    "text": val.get("text", "")[:150],
                    "uri": rec.get("uri")
                })

    return {"root_uri": root_uri, "root_cid": root_cid, "root_text": root_text, "parent_cid": parent_cid, "embeds": embeds}

async def fetch_notifications(client, limit=100, seen_at=None):
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("notifications", [])