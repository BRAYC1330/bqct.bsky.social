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

_session_cache = {}
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
            expires_at = sess.get("expires_at", 0)
            if time.time() < expires_at:
                client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
                logger.info("[bsky] Session loaded from cache")
                return
        except Exception:
            pass
    r = await client.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password}
    )
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    sess["expires_at"] = time.time() + 3600
    fernet = _get_fernet_key()
    encrypted = fernet.encrypt(json.dumps(sess).encode())
    with open(session_path, "wb") as f:
        f.write(encrypted)
    os.chmod(session_path, 0o600)
    logger.info("[bsky] New session created and cached")

async def post_root(client: httpx.AsyncClient, bot_did: str, text: str):
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    body = {
        "repo": bot_did,
        "collection": "app.bsky.feed.post",
        "record": record
    }
    r = await client.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        json=body
    )
    r.raise_for_status()
    return r.json()

async def post_reply(client: httpx.AsyncClient, bot_did: str, text: str, root_uri: str, root_cid: str, parent_uri: str, parent_cid: str):
    reply = {
        "root": {"uri": root_uri, "cid": root_cid},
        "parent": {"uri": parent_uri, "cid": parent_cid}
    }
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "reply": reply
    }
    body = {
        "repo": bot_did,
        "collection": "app.bsky.feed.post",
        "record": record
    }
    r = await client.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        json=body
    )
    r.raise_for_status()
    return r.json()

async def fetch_thread_chain(client: httpx.AsyncClient, uri: str):
    r = await client.get(
        "https://bsky.social/xrpc/app.bsky.feed.getPostThread",
        params={"uri": uri, "depth": 0}
    )
    if r.status_code != 200:
        logger.warning(f"[bsky] get_thread_raw failed: {r.status_code}")
        return None
    data = r.json()
    parsed = parsers.parse_thread(data)
    return {
        "root_uri": parsed["uri"],
        "root_cid": parsed["cid"],
        "root_text": parsed["text"],
        "parent_cid": "",
        "chain": parsed["nodes"]
    }
