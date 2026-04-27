import httpx
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Optional
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

async def fetch_thread_chain(client: httpx.AsyncClient, uri: str):
    url = "https://bsky.social/xrpc/app.bsky.feed.getPostThread"
    logger.info(f"GET {url} (uri={uri})")
    try:
        r = await request_with_retry(client, "GET", url, params={"uri": uri, "depth": 0, "parentHeight": 100})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning(f"Thread fetch failed: {e}")
        return None
    try:
        data = r.json()
    except ValueError as e:
        logger.warning(f"Invalid JSON in thread response: {e}")
        return None
    
    chain = []
    current = data.get("thread", {})
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
    parent_cid = target.get("cid")
    
    logger.info(f"THREAD_CHAIN: root_uri={root_uri} | posts_count={len(chain)}")
    for p in chain:
        rec = p.get("record", {})
        author = p.get("author", {})
        text = rec.get("text", "")
        embed = rec.get("embed")
        embed_text, alts = _extract_embed_full(embed) if embed else ("", "")
        urls = URL_PATTERN.findall(text)
        logger.info(f"THREAD_POST: handle={author.get('handle')} | text={text} | uri={p.get('uri')}")
        if embed_text:
            logger.info(f"EMBED: {embed_text}")
        if alts:
            for alt in alts:
                logger.info(f"ALT: {alt}")
        for url in urls:
            logger.info(f"URL_FOUND: {url}")
            clean = await _extract_clean_url_content(url)
            if clean:
                logger.info(f"LINK_CONTENT from {url}:\n{clean}")
    
    return {
        "root_uri": root_uri,
        "root_cid": root_cid,
        "root_text": root_text,
        "parent_cid": parent_cid,
        "chain": chain
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