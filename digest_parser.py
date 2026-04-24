import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

def _flatten(node, parent_uri=None, out=None):
    if out is None: out = []
    if not node or node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]: return out
    post = node.get("post", {})
    rec = post.get("record", {})
    if not rec: return out
    out.append({"uri": post.get("uri", ""), "cid": post.get("cid", ""), "handle": post.get("author", {}).get("handle", ""), "text": rec.get("text", ""), "is_root": parent_uri is None})
    for r in node.get("replies", []):
        if isinstance(r, dict): _flatten(r, post.get("uri", ""), out)
    return out

async def parse_digest_thread(thread_data: Dict) -> Dict:
    nodes = _flatten(thread_data.get("thread", {}))
    root = next((n for n in nodes if n.get("is_root")), {"uri": "", "cid": "", "text": ""})
    comments = [n for n in nodes if not n.get("is_root") and n.get("uri") != root["uri"]]
    return {"uri": root["uri"], "cid": root["cid"], "text": root["text"], "comments": comments}
