import logging
from typing import List, Dict, Optional, TypedDict

class PostNode(TypedDict):
    uri: str
    cid: str
    handle: str
    text: str
    is_root: bool

class NotificationItem(TypedDict):
    uri: str
    reason: str
    author_did: str
    text: str
    indexed_at: str
    parent_uri: str

class TrendItem(TypedDict):
    id: str
    keyword: str
    summary: str
    score: int
    rank_status: str

logger = logging.getLogger(__name__)

def flatten_thread_nodes(node: Dict, parent_uri: Optional[str] = None, out: Optional[List[PostNode]] = None) -> List[PostNode]:
    if out is None:
        out = []
    if not node or node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return out
    post = node.get("post", {})
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
    for reply_node in node.get("replies", []):
        if isinstance(reply_node, dict):
            flatten_thread_nodes(reply_node, post.get("uri", ""), out)
    return out

def parse_thread(thread_data: Dict) -> Dict:
    nodes = flatten_thread_nodes(thread_data.get("thread", {}))
    root = next((n for n in nodes if n.get("is_root")), {"uri": "", "cid": "", "text": ""})
    comments = [n for n in nodes if not n.get("is_root") and n.get("uri") != root["uri"]]
    return {"uri": root["uri"], "cid": root["cid"], "text": root["text"], "comments": comments, "nodes": nodes}

def parse_notifications(raw_json: Dict) -> List[NotificationItem]:
    items = []
    for n in raw_json.get("notifications", []):
        record = n.get("record", {})
        parent_uri = ""
        if isinstance(record, dict) and "reply" in record:
            parent_uri = record.get("reply", {}).get("parent", {}).get("uri", "")
        items.append({
            "uri": n.get("uri", ""),
            "reason": n.get("reason", ""),
            "author_did": n.get("author", {}).get("did", ""),
            "text": (record.get("text") or "").strip(),
            "indexed_at": n.get("indexedAt", ""),
            "parent_uri": parent_uri
        })
    return items

def parse_trends(raw_json: Dict) -> List[TrendItem]:
    items = raw_json.get("items", []) if isinstance(raw_json, dict) else []
    result = []
    for i in items:
        keyword = i.get("keyword", "")
        summary = i.get("summary", "")
        if len(keyword) > 0 and sum(1 for c in keyword if ord(c) < 128) / len(keyword) > 0.7:
            result.append({
                "id": str(i.get("id", "")),
                "keyword": keyword,
                "summary": summary,
                "score": int(i.get("score", 0)),
                "rank_status": i.get("rank_status", "same")
            })
    result.sort(key=lambda x: x["score"], reverse=True)
    return result

def extract_text_from_html(html_content: str, max_length: int = 400) -> str:
    import re
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_length]
