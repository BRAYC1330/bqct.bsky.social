import os
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta
import config
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def _extract_texts(node):
    texts = []
    if not node or not isinstance(node, dict): return texts
    post = node.get("post", {})
    if not post: return texts
    record = post.get("record", {})
    if record and record.get("text"):
        texts.append(record["text"])
    elif post.get("value", {}).get("text"):
        texts.append(post["value"]["text"])
    for r in node.get("replies", []):
        texts.extend(_extract_texts(r))
    return texts

async def login_with_cache(client, handle, password):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            with open(session_path) as f:
                sess = json.load(f)
            if sess.get("expiresAt"):
                exp = datetime.fromisoformat(sess["expiresAt"].replace("Z", "+00:00"))
                if exp < datetime.now(timezone.utc) - timedelta(minutes=5):
                    os.remove(session_path)
                    return await login_with_cache(client, handle, password)
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
    r = await utils.request_with_retry(client, "POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    return r.json()

async def post_reply(client, bot_did, text, root_uri, root_cid, parent_uri, parent_cid):
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await utils.request_with_retry(client, "POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    return r.json()

async def fetch_thread_chain(client, uri):
    r = await utils.request_with_retry(client, "GET", "https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 10})
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
    all_texts = _extract_texts(thread)
    full_thread_text = " ".join(all_texts)
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
                embeds["reposts"].append({"author": rec.get("author", {}).get("handle"), "text": val.get("text", "")[:150], "uri": rec.get("uri")})
    return {
        "root_uri": root_uri, "root_cid": root_cid, "root_text": root_text,
        "parent_cid": parent_cid, "embeds": embeds,
        "all_texts": all_texts, "full_text": full_thread_text
    }

async def fetch_notifications(client, limit=100, seen_at=None):
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    r = await utils.request_with_retry(client, "GET", "https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
    return r.json().get("notifications", [])