import logging
from src.state import settings as config
from src.clients import chainbase, httpx_base
from src.content import builder

logger = logging.getLogger(__name__)

async def run(client, llm, task_type="digest_mini"):
    trends = await chainbase.get_trending()
    if not trends: return None
    final_post = await builder.build_digest(llm, trends, task_type, max_total=300)
    if not final_post: return None
    try:
        resp = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json={
            "repo": config.BOT_DID,
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": final_post,
                "createdAt": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
            }
        })
        resp.raise_for_status()
        return resp.json().get("uri")
    except Exception:
        return None
