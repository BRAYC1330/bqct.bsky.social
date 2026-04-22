import httpx
import datetime
import logging
import json
import pathlib
import os
import tempfile
from typing import Optional
import config
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
BASE_URL = "https://bsky.social"
API_URL = "https://api.bsky.app"
SESSION_FILE = pathlib.Path("/tmp/bsky_session.json")
TIMEOUT = httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT)
def get_client():
    logger.debug("[get_client] Creating async client")
    transport = httpx.AsyncHTTPTransport(retries=3)
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, transport=transport)
async def login(client, handle, password):
    logger.debug(f"[login] Attempting login for {handle}")
    r = await client.post("/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password}, timeout=TIMEOUT)
    r.raise_for_status()
    token = r.json()['accessJwt']
    client.headers["Authorization"] = f"Bearer {token}"
    logger.info(f"[login] Success")
    return client.headers["Authorization"]
async def refresh_session(client, refresh_jwt: str):
    try:
        logger.debug("[refresh_session] Refreshing token")
        r = await client.post("/xrpc/com.atproto.server.refreshSession", headers={"Authorization": f"Bearer {refresh_jwt}"}, timeout=TIMEOUT)
        r.raise_for_status()
        token = r.json()['accessJwt']
        client.headers["Authorization"] = f"Bearer {token}"
        logger.debug("[refresh_session] Token refreshed")
        return token
    except Exception as e:
        logger.warning(f"[refresh_session] Failed: {e}")
        return None
async def login_with_cache(client, handle, password):
    logger.debug("[login_with_cache] Checking session cache")
    if SESSION_FILE.exists():
        try:
            os.chmod(SESSION_FILE, 0o600)
            with open(SESSION_FILE) as f:
                session = json.load(f)
            access_jwt = session.get('accessJwt')
            refresh_jwt = session.get('refreshJwt')
            if access_jwt:
                client.headers["Authorization"] = f"Bearer {access_jwt}"
                test = await client.get("/xrpc/com.atproto.server.getSession", timeout=10)
                if test.status_code == 200:
                    logger.debug("[login_with_cache] Cached session valid")
                    return client.headers["Authorization"]
            if refresh_jwt:
                new_token = await refresh_session(client, refresh_jwt)
                if new_token:
                    with tempfile.NamedTemporaryFile('w', dir='/tmp', delete=False, suffix='.tmp') as tf:
                        json.dump({"accessJwt": new_token.replace("Bearer ", ""), "refreshJwt": refresh_jwt}, tf)
                        tf.flush()
                        os.fsync(tf.fileno())
                        temp_name = tf.name
                    os.replace(temp_name, SESSION_FILE)
                    os.chmod(SESSION_FILE, 0o600)
                    logger.debug("[login_with_cache] Session refreshed via refresh token")
                    return client.headers["Authorization"]
        except Exception as e:
            logger.warning(f"[login_with_cache] Cache read failed: {e}")
    logger.info("[login_with_cache] Creating new session")
    r = await client.post("/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password}, timeout=TIMEOUT)
    r.raise_for_status()
    result = r.json()
    access_jwt = result['accessJwt']
    refresh_jwt = result.get('refreshJwt', '')
    client.headers["Authorization"] = f"Bearer {access_jwt}"
    with tempfile.NamedTemporaryFile('w', dir='/tmp', delete=False, suffix='.tmp') as tf:
        session_data = {"accessJwt": access_jwt}
        if refresh_jwt:
            session_data["refreshJwt"] = refresh_jwt
        json.dump(session_data, tf)
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name
    os.replace(temp_name, SESSION_FILE)
    os.chmod(SESSION_FILE, 0o600)
    logger.info("[login_with_cache] New session created and cached")
    return client.headers["Authorization"]
async def get_record(client, uri: str):
    logger.debug(f"[get_record] Fetching {uri[:50]}...")
    if not uri.startswith("at://"):
        return None
    parts = uri.split("/")
    if len(parts) < 5:
        return None
    r = await client.get("/xrpc/com.atproto.repo.getRecord", params={"repo": parts[2], "collection": parts[3], "rkey": parts[4]}, timeout=TIMEOUT)
    if r.status_code == 200:
        logger.debug(f"[get_record] Success")
        return r.json()
    logger.warning(f"[get_record] Failed: {r.status_code}")
    return None
async def get_thread_raw(client, root_uri: str):
    logger.debug(f"[get_thread_raw] Fetching thread for {root_uri[:40]}...")
    r = await client.get(f"{API_URL}/xrpc/app.bsky.feed.getPostThread?uri={root_uri}&depth=100", timeout=60)
    if r.status_code == 200:
        logger.debug(f"[get_thread_raw] Success")
        return r.json()
    logger.warning(f"[get_thread_raw] Failed: {r.status_code}")
    return None
async def fetch_thread_chain(client, target_uri: str):
    logger.debug(f"[fetch_thread_chain] Fetching chain for {target_uri[:40]}...")
    r = await client.get(f"{API_URL}/xrpc/app.bsky.feed.getPostThread?uri={target_uri}&depth=0&parentHeight=100", timeout=30)
    if r.status_code != 200:
        logger.warning(f"[fetch_thread_chain] API error: {r.status_code}")
        return None
    chain = []
    current = r.json().get("thread", {})
    while current:
        post = current.get("post")
        if post:
            post_type = post.get("$type", "")
            if post_type in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
                break
            chain.append(post)
            current = current.get("parent")
    chain.reverse()
    if not chain:
        logger.debug(f"[fetch_thread_chain] Empty chain")
        return None
    logger.debug(f"[fetch_thread_chain] Chain length: {len(chain)}")
    return {
        "root_uri": chain[0].get("uri"), "root_cid": chain[0].get("cid"),
        "root_text": chain[0].get("record", {}).get("text", ""),
        "root_handle": chain[0].get("author", {}).get("handle", ""),
        "parent_uri": target_uri, "parent_cid": chain[-1].get("cid"), "chain": chain
    }
async def post_record(client, bot_did, text, reply_obj=None, facets=None):
    logger.debug(f"[post_record] Creating record | text_preview={text[:100]}... | len={len(text)} | bot_did={bot_did[:20]}...")
    created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": created_at}
    if reply_obj:
        record["reply"] = reply_obj
    if facets:
        record["facets"] = facets
    r = await client.post("/xrpc/com.atproto.repo.createRecord", json={"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}, timeout=TIMEOUT)
    if r.status_code != 200:
        logger.error(f"[post_record] API error {r.status_code}: {r.text[:200]}")
        r.raise_for_status()
    logger.info(f"[post_record] Record created: {r.json().get('uri', 'N/A')[:40]}...")
    return r.json()
async def post_reply(client, bot_did, text, root_uri, root_cid, parent_uri, parent_cid):
    logger.debug(f"[post_reply] Posting reply to {parent_uri[:40]}...")
    if not root_uri or not parent_uri:
        raise ValueError("Missing required URI for reply")
    reply_obj = {"root": {"uri": root_uri, "cid": root_cid or parent_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    return await post_record(client, bot_did, text, reply_obj)
async def post_root(client, bot_did, text, facets=None):
    logger.debug(f"[post_root] Posting root message | text_preview={text[:100]}...")
    return await post_record(client, bot_did, text, facets=facets)
async def like_post(client, bot_did, subject_uri, subject_cid):
    logger.debug(f"[like_post] Liking {subject_uri[:40]}...")
    created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    r = await client.post("/xrpc/com.atproto.repo.createRecord", json={
        "repo": bot_did, "collection": "app.bsky.feed.like",
        "record": {"$type": "app.bsky.feed.like", "subject": {"uri": subject_uri, "cid": subject_cid}, "createdAt": created_at}
    }, timeout=TIMEOUT)
    r.raise_for_status()
    logger.info(f"[like_post] Like created")
    return r.json()
