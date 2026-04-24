import logging
import re
from typing import List, Dict, Optional, Set
import httpx
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

logger = logging.getLogger(__name__)

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
            parts.append(f"[Desc: {desc[:150]}]")
        if uri and not uri.startswith("https://bsky.app"):
            parts.append(f"[URL: {uri}]")
    elif embed_type == "app.bsky.embed.record":
        rec = embed.get("record", {})
        rec_type = rec.get("$type", "")
        if rec_type == "app.bsky.feed.post":
            val = rec.get("value", {})
            quote_text = val.get("text", "")[:150]
            quote_author = rec.get("author", {}).get("handle", "")
            if quote_text:
                parts.append(f"[Quote @{quote_author}: {quote_text}]")
        elif rec.get("title"):
            parts.append(f"[Record: {rec.get('title')}]")
    elif embed_type == "app.bsky.embed.video":
        video = embed.get("video", {})
        alt = video.get("alt", "").strip()
        if alt:
            parts.append(f"[Video: {alt}]")
            alts.append(f"Video: {alt}")
        else:
            parts.append("[Video]")
    elif embed_type == "app.bsky.embed.recordWithMedia":
        media = embed.get("media", {})
        record = embed.get("record", {})
        media_text, media_alts = _extract_embed_full(media)
        record_text, _ = _extract_embed_full({"$type": "app.bsky.embed.record", "record": record})
        if media_text:
            parts.append(media_text)
            alts.extend(media_alts)
        if record_text:
            parts.append(record_text)
    return " ".join(p for p in parts if p), alts

async def _extract_clean_url_content(url: str) -> Optional[str]:
    if not TRAFILATURA_AVAILABLE:
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                content = trafilatura.extract(r.text, include_tables=False, include_comments=False, output_format="txt")
                if content:
                    return content[:400].strip()
    except Exception:
        pass
    return None

def _extract_urls_from_text(text: str) -> List[str]:
    return re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)

async def _parse_thread_nodes(node, parent_uri, client, token, quoted_cache, link_cache, all_nodes):
    if not node or node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return
    post = node.get("post", {})
    record = post.get("record", {})
    if not record:
        return
    node_uri = post.get("uri")
    author = post.get("author", {})
    did = author.get("did", "")
    handle = author.get("handle", did.split(":")[-1] if ":" in did else "unknown")
    txt = record.get("text", "")
    embed = record.get("embed")
    alts = []
    link_hints = []
    
    if embed and isinstance(embed, dict):
        etype = embed.get("$type", "")
        if etype in ["app.bsky.embed.record", "app.bsky.embed.recordWithMedia"]:
            rec_ref = embed.get("record", {})
            if rec_ref and rec_ref.get("uri") and rec_ref["uri"] not in quoted_cache:
                parts = rec_ref["uri"].split("/")
                if len(parts) >= 5:
                    try:
                        q = await client.get(
                            "https://bsky.social/xrpc/com.atproto.repo.getRecord",
                            params={"repo": parts[2], "collection": parts[3], "rkey": parts[4]},
                            headers={"Authorization": f"Bearer {token}"}
                        )
                        if q.status_code == 200:
                            quoted_cache[rec_ref["uri"]] = q.json().get("value", {}).get("text", "")[:200]
                    except:
                        pass
            if rec_ref.get("uri") in quoted_cache:
                q_author = rec_ref["uri"].split("/")[2]
                txt = f"{txt}\n[Quote @{q_author}: {quoted_cache[rec_ref['uri']]}]"
            if etype == "app.bsky.embed.recordWithMedia":
                media = embed.get("media", {})
                if media and media.get("$type") == "app.bsky.embed.images":
                    for img in media.get("images", []):
                        if isinstance(img, dict) and img.get("alt"):
                            alts.append(f"@{handle} image: {img['alt']}")
        elif etype == "app.bsky.embed.images":
            for img in embed.get("images", []):
                if isinstance(img, dict) and img.get("alt"):
                    alts.append(f"@{handle} image: {img['alt']}")
        elif etype == "app.bsky.embed.external":
            ext = embed.get("external", {})
            title = ext.get("title", "").strip()
            desc = ext.get("description", "").strip()
            uri = ext.get("uri", "").strip()
            if title:
                link_hints.append(f"[Embed Link: {title}]")
            if desc:
                link_hints.append(f"[Desc: {desc[:150]}]")
            if uri and uri not in link_cache:
                clean = await _extract_clean_url_content(uri)
                if clean:
                    link_cache[uri] = clean
                    link_hints.append(f"[Page content: {clean}]")
                else:
                    link_cache[uri] = "[Page fetch failed]"
    
    for url in _extract_urls_from_text(txt):
        if url not in link_cache:
            clean = await _extract_clean_url_content(url)
            if clean:
                link_cache[url] = clean
                link_hints.append(f"[Linked page: {clean}]")
            else:
                link_cache[url] = "[Fetch failed]"
    
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
            await _parse_thread_nodes(reply_node, node_uri, client, token, quoted_cache, link_cache, all_nodes)

async def parse_thread_full(raw_response: dict, client: httpx.AsyncClient, token: str) -> dict:
    all_nodes = []
    quoted_cache = {}
    link_cache = {}
    thread = raw_response.get("thread", {})
    await _parse_thread_nodes(thread, None, client, token, quoted_cache, link_cache, all_nodes)
    texts = [n["text"] for n in all_nodes if n["text"]]
    links = list(set(l for n in all_nodes for l in n.get("link_hints", []) if l.startswith("[URL:") or l.startswith("[Linked")))
    return {"texts": texts, "links": links, "nodes": all_nodes}