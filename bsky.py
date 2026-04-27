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
        except Exception:
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
    r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 0, "parentHeight": 100})
    if r.status_code != 200:
        logger.warning(f"[bsky] Thread fetch failed: {r.status_code}")
        return None
    data = r.json()
    thread = data.get("thread", {})
    chain = []
    current = thread
    while current and isinstance(current, dict):
        post = current.get("post")
        if post:
            chain.append(post)
        current = current.get("parent")
    chain = list(reversed(chain))
    if not chain:
        return None
    root = chain[0]
    target = chain[-1]
    root_uri = root.get("uri")
    root_cid = root.get("cid")
    root_text = root.get("record", {}).get("text", "")
    target_cid = target.get("cid")
    logger.info(f"THREAD_CHAIN: root_uri={root_uri} | posts_count={len(chain)}")
    for p in chain:
        rec = p.get("record", {})
        author = p.get("author", {})
        text = rec.get("text", "")
        logger.info(f"THREAD_POST: handle={author.get('handle')} | text={text} | uri={p.get('uri')}")
    return {
        "root_uri": root_uri,
        "root_cid": root_cid,
        "root_text": root_text,
        "parent_cid": target_cid,
        "chain": chain
    }
async def fetch_notifications(client, limit=100, seen_at=None):
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    try:
        r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
        r.raise_for_status()
        return r.json().get("notifications", [])
    except Exception as e:
        logger.warning(f"[bsky] Notifications fetch failed: {e}")
        return []
def _extract_embed_text(embed):
    texts = []
    if not embed: return ""
    et = embed.get("$type", "")
    if et == "app.bsky.embed.images":
        for img in embed.get("images", []):
            if img.get("alt"): texts.append(img["alt"])
    elif et == "app.bsky.embed.external":
        ext = embed.get("external", {})
        if ext.get("title"): texts.append(ext["title"])
        if ext.get("description"): texts.append(ext["description"])
    elif et == "app.bsky.embed.record":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"): texts.append(val["text"])
    elif et == "app.bsky.embed.recordWithMedia":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"): texts.append(val["text"])
        med = embed.get("media", {})
        if med.get("$type") == "app.bsky.embed.images":
            for img in med.get("images", []):
                if img.get("alt"): texts.append(img["alt"])
    return " ".join(texts)
async def _fetch_url_content(client, url):
    try:
        from trafilatura import extract as trafilatura_extract
        parsed = httpx.URL(url)
        if parsed.netloc not in config.ALLOWED_LINK_DOMAINS: return ""
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 200:
            txt = trafilatura_extract(r.text, include_tables=False, include_comments=False, output_format="txt")
            if txt: return txt[:config.MAX_LINK_CONTENT_SIZE]
    except Exception:
        pass
    return ""