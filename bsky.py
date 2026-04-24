import os
import json
import logging
import httpx
import time
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import config
import parsers

logger = logging.getLogger(__name__)
_session_key = None

def _get_fernet_key() -> Fernet:
    global _session_key
    if _session_key is None:
        key = os.environ.get("SESSION_KEY", Fernet.generate_key().decode())
        _session_key = Fernet(key.encode() if isinstance(key, str) else key)
    return _session_key

async def login_with_cache(client: httpx.AsyncClient, handle: str, password: str):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            os.chmod(session_path, 0o600)
            with open(session_path, "rb") as f:
                encrypted = f.read()
            fernet = _get_fernet_key()
            decrypted = fernet.decrypt(encrypted)
            sess = json.loads(decrypted.decode())
            if time.time() < sess.get("expires_at", 0):
                client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
                return
        except Exception:
            pass
    r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    sess["expires_at"] = time.time() + 3600
    encrypted = _get_fernet_key().encrypt(json.dumps(sess).encode())
    with open(session_path, "wb") as f:
        f.write(encrypted)
    os.chmod(session_path, 0o600)

async def post_root(client: httpx.AsyncClient, bot_did: str, text: str):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

async def post_reply(client: httpx.AsyncClient, bot_did: str, text: str, root_uri: str, root_cid: str, parent_uri: str, parent_cid: str):
    reply_ref = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply_ref}
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

async def fetch_thread_chain(client: httpx.AsyncClient, uri: str):
    r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 10, "parentHeight": 10})
    r.raise_for_status()
    thread = r.json().get("thread", {})
    root = _find_root(thread)
    target = _find_target(thread, uri)
    parent = _get_parent(thread, uri)
    return {
        "root_uri": root.get("uri", ""),
        "root_cid": root.get("cid", ""),
        "root_text": root.get("record", {}).get("text", ""),
        "target_uri": uri,
        "target_cid": target.get("cid", "") if target else "",
        "parent_uri": parent.get("uri", "") if parent else "",
        "parent_cid": parent.get("cid", "") if parent else ""
    }

def _find_root(node: dict) -> dict:
    if not node or "post" not in node:
        return {}
    parent = node.get("parent", {})
    if parent and "post" in parent:
        return _find_root(parent)
    return node.get("post", {})

def _find_target(node: dict, target_uri: str) -> dict:
    if not node or "post" not in node:
        return {}
    post = node.get("post", {})
    if post.get("uri") == target_uri:
        return post
    for reply in node.get("replies", []):
        if isinstance(reply, dict):
            found = _find_target(reply, target_uri)
            if found.get("uri"):
                return found
    return {}

def _get_parent(node: dict, target_uri: str) -> dict:
    if not node or "post" not in node:
        return {}
    post = node.get("post", {})
    if post.get("uri") == target_uri:
        parent = node.get("parent", {})
        if parent and "post" in parent:
            return parent["post"]
    for reply in node.get("replies", []):
        if isinstance(reply, dict):
            found = _get_parent(reply, target_uri)
            if found.get("uri"):
                return found
    return {}
