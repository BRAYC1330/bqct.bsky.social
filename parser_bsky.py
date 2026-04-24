import logging
from typing import List, Dict, Optional
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def flatten_thread(thread_node: Dict, parent_uri: Optional[str] = None, out: Optional[List[Dict]] = None) -> List[Dict]:
    if out is None:
        out = []
    if not thread_node or thread_node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return out
    post = thread_node.get("post", {})
    record = post.get("record", {})
    if not record:
        return out
    out.append({
        "uri": post.get("uri", ""),
        "cid": post.get("cid", ""),
        "handle": post.get("author", {}).get("handle", ""),
        "text": record.get("text", ""),
        "is_root": parent_uri is None
    })
    for reply_node in thread_node.get("replies", []):
        if isinstance(reply_node, dict):
            flatten_thread(reply_node, post.get("uri", ""), out)
    return out

async def parse_thread(thread_data: Dict, root_uri: str = "") -> List[Dict]:
    return flatten_thread(thread_data.get("thread", {}))

async def parse_digest_thread(thread_data: Dict) -> Dict:
    nodes = flatten_thread(thread_data.get("thread", {}))
    root = next((n for n in nodes if n.get("is_root")), {"uri": "", "cid": "", "text": ""})
    comments = [n for n in nodes if not n.get("is_root") and n.get("uri") != root["uri"]]
    return {"uri": root["uri"], "cid": root["cid"], "text": root["text"], "comments": comments}