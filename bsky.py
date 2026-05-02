import os
import json
import logging
import httpx
import base64
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import config
import utils

logger = logging.getLogger(__name__)

SESSION_PATH = "session.json"


def _is_jwt_expired(token: str) -> bool:
    """Check if JWT token is expired."""
    try:
        payload = token.split('.')[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        exp = decoded.get('exp')
        if exp:
            return time.time() >= exp
        return False
    except Exception as e:
        logger.warning(f"[bsky] JWT decode failed: {e}")
        return True
async def login_with_cache(client: httpx.AsyncClient, handle: str, password: str) -> None:
    """Login to Bluesky, using cached session if valid.
    
    Args:
        client: HTTP client with authorization headers
        handle: Bot handle/username
        password: Bot password
        
    Note: Session caching stores JWT tokens - consider security implications.
    """
    if os.path.exists(SESSION_PATH):
        try:
            with open(SESSION_PATH) as f:
                sess = json.load(f)
            if not _is_jwt_expired(sess.get('accessJwt', '')):
                client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
                logger.info("[bsky] Session loaded from cache")
                return
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[bsky] Cache read failed: {e}")
        except Exception as e:
            logger.warning(f"[bsky] Unexpected cache error: {e}")
    
    try:
        r = await client.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": password}
        )
        r.raise_for_status()
        sess = r.json()
        client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
        
        # Security note: Consider not persisting JWT tokens to disk
        with open(SESSION_PATH, "w") as f:
            json.dump(sess, f)
        logger.info("[bsky] New session created and cached")
    except httpx.HTTPStatusError as e:
        logger.error(f"[bsky] Login HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"[bsky] Login request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"[bsky] Unexpected login error: {e}")
        raise
async def post_root(client: httpx.AsyncClient, bot_did: str, text: str) -> Dict[str, Any]:
    """Create a root post on Bluesky.
    
    Args:
        client: Authenticated HTTP client
        bot_did: Bot's DID identifier
        text: Post text content
        
    Returns:
        Response JSON from createRecord API
    """
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "facets": utils.build_ticker_facets(text),
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    try:
        r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[bsky] post_root HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"[bsky] post_root request failed: {e}")
        raise


async def post_reply(
    client: httpx.AsyncClient,
    bot_did: str,
    text: str,
    root_uri: str,
    root_cid: str,
    parent_uri: str,
    parent_cid: str
) -> Dict[str, Any]:
    """Create a reply post on Bluesky.
    
    Args:
        client: Authenticated HTTP client
        bot_did: Bot's DID identifier
        text: Reply text content
        root_uri: Root post URI
        root_cid: Root post CID
        parent_uri: Parent post URI
        parent_cid: Parent post CID
        
    Returns:
        Response JSON from createRecord API
    """
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "facets": utils.build_ticker_facets(text),
        "reply": reply,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    try:
        r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[bsky] post_reply HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"[bsky] post_reply request failed: {e}")
        raise
async def fetch_thread_chain(client: httpx.AsyncClient, uri: str) -> Optional[Dict[str, Any]]:
    """Fetch a thread chain from Bluesky.
    
    Args:
        client: Authenticated HTTP client
        uri: Post URI to fetch
        
    Returns:
        Dictionary with root_uri, root_cid, chain, etc. or None on failure
    """
    try:
        r = await client.get(
            "https://bsky.social/xrpc/app.bsky.feed.getPostThread",
            params={"uri": uri, "depth": 0, "parentHeight": 100}
        )
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
        parent_cid_ref = parent_ref.get("cid", "") if parent_ref else ""
        
        chain: List[Dict[str, Any]] = []
        current = thread
        while current and isinstance(current, dict):
            p = current.get("post")
            if p:
                chain.append(p)
            current = current.get("parent")
        chain = list(reversed(chain))
        
        return {
            "root_uri": root_uri,
            "root_cid": root_cid,
            "root_text": root_text,
            "parent_cid": parent_cid_ref,
            "cid": post.get("cid", ""),
            "chain": chain
        }
    except httpx.RequestError as e:
        logger.error(f"[bsky] fetch_thread_chain request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"[bsky] fetch_thread_chain unexpected error: {e}")
        return None


async def fetch_notifications(
    client: httpx.AsyncClient,
    limit: int = 100,
    seen_at: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch notifications from Bluesky.
    
    Args:
        client: Authenticated HTTP client
        limit: Maximum number of notifications to fetch
        seen_at: ISO timestamp for filtering already-seen notifications
        
    Returns:
        List of notification dictionaries
    """
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    
    try:
        r = await client.get(
            "https://bsky.social/xrpc/app.bsky.notification.listNotifications",
            params=params,
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("notifications", [])
    except httpx.HTTPStatusError as e:
        logger.warning(f"[bsky] Notifications HTTP error: {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.warning(f"[bsky] Notifications fetch failed: {e}")
        return []
    except Exception as e:
        logger.warning(f"[bsky] Notifications unexpected error: {e}")
        return []
async def _fetch_url_content(client: httpx.AsyncClient, url: str) -> str:
    """Fetch and extract content from a URL.
    
    Args:
        client: HTTP client
        url: URL to fetch
        
    Returns:
        Extracted text content or empty string on failure
    """
    try:
        from trafilatura import extract as trafilatura_extract
        
        parsed = httpx.URL(url)
        if parsed.netloc not in config.ALLOWED_LINK_DOMAINS:
            return ""
        
        r = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=config.REQUEST_TIMEOUT
        )
        if r.status_code == 200:
            txt = trafilatura_extract(
                r.text,
                include_tables=False,
                include_comments=False,
                output_format="txt"
            )
            if txt:
                return txt[:config.MAX_LINK_CONTENT_SIZE]
    except ImportError:
        logger.warning("[bsky] trafilatura not installed, skipping link extraction")
    except httpx.RequestError as e:
        logger.warning(f"[bsky] Link fetch request failed: {e}")
    except Exception as e:
        logger.warning(f"[bsky] Link extraction error: {e}")
    return ""