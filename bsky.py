import logging
import asyncio
import random
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import config
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def request_with_retry(client, method, url, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            r = await client.request(method, url, **kwargs)
            if r.status_code == 429:
                retry_after = int(r.headers.get("retry-after", 2 ** attempt))
                delay = retry_after + random.uniform(0, 1)
                await asyncio.sleep(delay)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
            continue

async def login_with_cache(client: httpx.AsyncClient, handle: str, password: str) -> None:
    try:
        r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
        r.raise_for_status()
        sess = r.json()
        client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
        logger.debug("[bsky] Session created and attached")
    except httpx.HTTPStatusError as e:
        logger.error(f"[bsky] Login failed: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"[bsky] Login request failed: {e}")
        raise

async def post_root(client: httpx.AsyncClient, bot_did: str, text: str) -> Dict[str, Any]:
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await request_with_retry(client, "POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    return r.json()

async def post_reply(client: httpx.AsyncClient, bot_did: str, text: str, root_uri: str, root_cid: str, parent_uri: str, parent_cid: str) -> Dict[str, Any]:
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await request_with_retry(client, "POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    return r.json()

def iter_thread_posts(node):
    if not node or not isinstance(node, dict):
        return
    if node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return
    post = node.get("post", {})
    record = post.get("record", {})
    text = record.get("text") if record else post.get("value", {}).get("text")
    if text:
        yield {
            "uri": post.get("uri", ""),
            "cid": post.get("cid", ""),
            "handle": post.get("author", {}).get("handle", ""),
            "text": text,
            "is_root": False
        }
    for reply_node in node.get("replies", []):
        yield from iter_thread_posts(reply_node)

async def fetch_thread_chain(client: httpx.AsyncClient, uri: str) -> Optional[Dict[str, Any]]:
    try:
        r = await request_with_retry(client, "GET", "https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 10})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning(f"[bsky] Thread fetch failed: {e}")
        return None
    try:
        data = r.json()
    except ValueError as e:
        logger.warning(f"[bsky] Invalid JSON in thread response: {e}")
        return None

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

    all_posts = list(iter_thread_posts(thread))
    all_texts = [p.get("text", "") for p in all_posts]
    full_thread_text = " ".join(all_texts)

    embeds: Dict[str, List[Dict[str, Any]]] = {"links": [], "reposts": []}
    raw_embed = post.get("embed", {})
    if raw_embed:
        if raw_embed.get("$type") == "app.bsky.embed.external#view":
            ext = raw_embed.get("external", {})
            embeds["links"].append({"url": ext.get("uri"), "title": ext.get("title"), "desc": ext.get("description", "")})
        elif raw_embed.get("$type") == "app.bsky.embed.record#view":
            rec = raw_embed.get("record", {})
            if rec.get("$type") == "app.bsky.embed.record#viewRecord":
                val = rec.get("value", {})
                embeds["reposts"].append({"author": rec.get("author", {}).get("handle"), "text": val.get("text", ""), "uri": rec.get("uri")})
    return {
        "root_uri": root_uri, "root_cid": root_cid, "root_text": root_text,
        "parent_cid": parent_cid, "embeds": embeds,
        "all_texts": all_texts, "full_text": full_thread_text
    }

async def fetch_notifications(client: httpx.AsyncClient, limit: int = 100, seen_at: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    try:
        r = await request_with_retry(client, "GET", "https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15.0)
        return r.json().get("notifications", [])
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        logger.warning(f"[bsky] Notifications fetch failed: {e}")
        return []