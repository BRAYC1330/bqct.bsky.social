import httpx
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
import config
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

async def request_with_retry(client, method, url, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            r = await client.request(method, url, **kwargs)
            if r.status_code == 429:
                retry_after = int(r.headers.get("retry-after", 2 ** attempt))
                import asyncio, random
                delay = retry_after + random.uniform(0, 1)
                await asyncio.sleep(delay)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            import asyncio, random
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
            continue

async def login_with_cache(client: httpx.AsyncClient, handle: str, password: str) -> None:
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    logger.info(f"POST {url}")
    try:
        r = await client.post(url, json={"identifier": handle, "password": password})
        r.raise_for_status()
        sess = r.json()
        client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
        logger.debug("Session created and attached")
    except httpx.HTTPStatusError as e:
        logger.error(f"Login failed: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Login request failed: {e}")
        raise

async def post_root(client: httpx.AsyncClient, bot_did: str, text: str):
    url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
    logger.info(f"POST {url}")
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await request_with_retry(client, "POST", url, json=body)
    return r.json()

async def post_reply(client: httpx.AsyncClient, bot_did: str, text: str, root_uri: str, root_cid: str, parent_uri: str, parent_cid: str):
    url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
    logger.info(f"POST {url}")
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await request_with_retry(client, "POST", url, json=body)
    return r.json()

async def _extract_clean_url_content(url: str) -> Optional[str]:
    logger.info(f"Fetching URL content: {url}")
    try:
        from trafilatura import extract as trafilatura_extract
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                content = trafilatura_extract(r.text, include_tables=False, include_comments=False, output_format="txt")
                return content if content else None
    except Exception as e:
        logger.warning(f"Failed to fetch URL {url}: {e}")
    return None

def _extract_embed_full(embed: Optional[Dict]) -> tuple:
    parts, alts = [], []
    if not embed:
        return "", []
    embed_type = embed.get("$type", "")
    if embed_type == "app.bsky.embed.images":
        for i, img in enumerate(embed.get("images", []), 1):
            alt = img.get("alt", "").strip()
            if alt:
                parts.append(f"[Image {i}: {alt}]")
                alts.append(f"Image {i}: {alt}")
            else:
                parts.append(f"[Image {i}]")
    elif embed_type == "app.bsky.embed.external":
        ext = embed.get("external", {})
        title = ext.get("title", "").strip()
        desc = ext.get("description", "").strip()
        uri = ext.get("uri", "").strip()
        if title:
            parts.append(f"[Link: {title}]")
        if desc:
            parts.append(f"[Desc: {desc}]")
        if uri and not uri.startswith("https://bsky.app"):
            parts.append(f"[URL: {uri}]")
    elif embed_type == "app.bsky.embed.record":
        rec = embed.get("record", {})
        if rec.get("$type") == "app.bsky.feed.post":
            val = rec.get("value", {})
            quote_text = val.get("text", "")
            quote_author = rec.get("author", {}).get("handle", "")
            if quote_text:
                parts.append(f"[Quote @{quote_author}: {quote_text}]")
    return " ".join(p for p in parts if p), alts

async def _parse_thread_nodes(node, parent_uri=None, client=None, token=None, link_cache=None, all_nodes=None):
    if not node or not isinstance(node, dict):
        return
    if node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return
    post = node.get("post", {})
    record = post.get("record", {})
    if not record:
        return
    node_uri = post.get("uri", "")
    author = post.get("author", {})
    did = author.get("did", "")
    handle = author.get("handle", did.split(":")[-1] if ":" in did else "unknown")
    txt = record.get("text", "")
    embed = record.get("embed")
    alts = []
    link_hints = []
    if embed and isinstance(embed, dict):
        embed_text, embed_alts = _extract_embed_full(embed)
        if embed_text:
            link_hints.append(f"[Embed: {embed_text}]")
        if embed_alts:
            alts.extend(embed_alts)
        if embed.get("$type") == "app.bsky.embed.external":
            ext_uri = embed.get("external", {}).get("uri", "").strip()
            if ext_uri and ext_uri not in link_cache:
                clean = await _extract_clean_url_content(ext_uri)
                link_cache[ext_uri] = clean
                if clean:
                    link_hints.append(f"[Page content from {ext_uri}]: {clean}")
    urls = URL_PATTERN.findall(txt)
    for url in urls:
        if url not in link_cache:
            clean = await _extract_clean_url_content(url)
            link_cache[url] = clean
            if clean:
                link_hints.append(f"[Linked content from {url}]: {clean}")
    all_nodes.append({
        "uri": node_uri,
        "parent_uri": parent_uri,
        "did": did,
        "handle": handle,
        "text": txt,
        "alts": alts,
        "link_hints": link_hints,
        "is_root": (parent_uri is None)
    })
    for reply_node in node.get("replies", []):
        if isinstance(reply_node, dict):
            await _parse_thread_nodes(reply_node, node_uri, client, token, link_cache, all_nodes)

async def fetch_thread_chain(client: httpx.AsyncClient, uri: str):
    url = "https://bsky.social/xrpc/app.bsky.feed.getPostThread"
    logger.info(f"GET {url} (uri={uri})")
    try:
        r = await request_with_retry(client, "GET", url, params={"uri": uri, "depth": 100, "parentHeight": 100})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning(f"Thread fetch failed: {e}")
        return None
    try:
        data = r.json()
    except ValueError as e:
        logger.warning(f"Invalid JSON in thread response: {e}")
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
    all_nodes = []
    link_cache = {}
    token = client.headers.get("Authorization", "").replace("Bearer ", "")
    await _parse_thread_nodes(thread, None, client, token, link_cache, all_nodes)
    all_texts = [p.get("text", "") for p in all_nodes]
    full_thread_text = " ".join(all_texts)
    logger.info(f"THREAD_CHAIN: root_uri={root_uri} | posts_count={len(all_nodes)}")
    for p in all_nodes:
        logger.info(f"THREAD_POST: handle={p.get('handle')} | text={p.get('text')} | uri={p.get('uri')}")
        if p.get("link_hints"):
            for hint in p["link_hints"]:
                logger.info(f"LINK_HINT: {hint}")
        if p.get("alts"):
            for alt in p["alts"]:
                logger.info(f"ALT: {alt}")
    return {
        "root_uri": root_uri, 
        "root_cid": root_cid, 
        "root_text": root_text,
        "parent_cid": parent_cid, 
        "cid": post.get("cid", ""),
        "all_texts": all_texts, 
        "full_text": full_thread_text,
        "chain": all_nodes
    }

async def fetch_notifications(client: httpx.AsyncClient, limit: int = 100, seen_at: str = None):
    url = "https://bsky.social/xrpc/app.bsky.notification.listNotifications"
    logger.info(f"GET {url}")
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    try:
        r = await request_with_retry(client, "GET", url, params=params, timeout=15.0)
        return r.json().get("notifications", [])
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        logger.warning(f"Notifications fetch failed: {e}")
        return []