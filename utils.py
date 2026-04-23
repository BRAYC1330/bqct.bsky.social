import asyncio
import hashlib
import re
import json
import logging
import datetime
import email.utils
from httpx import HTTPStatusError
from typing import Optional, Dict, List
logger = logging.getLogger(__name__)

class SecretFilter(logging.Filter):
    SECRET_PATTERNS = [
        r'Bearer\s+[A-Za-z0-9\-_\.]+',
        r'password["\']?\s*[:=]\s*["\']?[^"\',\s}]+',
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\',\s}]+',
        r'PAT["\']?\s*[:=]\s*["\']?[^"\',\s}]+',
        r'did:[^"\',\s}]+',
    ]
    REPLACEMENT = "[REDACTED]"
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self.SECRET_PATTERNS:
                record.msg = re.sub(pattern, self.REPLACEMENT, record.msg, flags=re.IGNORECASE)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(re.sub(p, self.REPLACEMENT, str(a), flags=re.IGNORECASE) if isinstance(a, str) else a for p in [None] for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = {k: re.sub(p, self.REPLACEMENT, str(v), flags=re.IGNORECASE) if isinstance(v, str) else v for k, v in record.args.items() for p in [None]}
        return True

def sanitize_for_prompt(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[{}`\\]', '', text)
    text = text.replace('"', '\\"').replace("'", "\\'")
    return text.strip()

def count_graphemes(text: str) -> int:
    if not text:
        return 0
    text = re.sub(r'\u200d', '', text)
    text = re.sub(r'[\uFE00-\uFE0F\u1F3FB-\u1F3FF]', '', text)
    graphemes = re.findall(r'\X', text, re.UNICODE)
    return len(graphemes)

def flatten_thread(node, parent_uri=None, out=None):
    if out is None:
        out = []
    if not node or node.get("$type") in ["app.bsky.feed.defs#notFoundPost", "app.bsky.feed.defs#blockedPost"]:
        return out
    post = node.get("post", {})
    rec = post.get("record", {})
    if not rec:
        return out
    out.append({
        "uri": post.get("uri", ""),
        "cid": post.get("cid", ""),
        "handle": post.get("author", {}).get("handle", ""),
        "text": rec.get("text", ""),
        "is_root": parent_uri is None
    })
    for r in node.get("replies", []):
        if isinstance(r, dict):
            flatten_thread(r, post.get("uri", ""), out)
    return out

def extract_embed_full(embed: Optional[Dict]) -> tuple:
    parts, alts = [], []
    if not embed:
        return "", []
    etype = embed.get("$type", "")
    if etype == "app.bsky.embed.images":
        for i, img in enumerate(embed.get("images", []), 1):
            alt = img.get("alt", "").strip()
            parts.append(f"[Image {i}: {alt}]" if alt else f"[Image {i}]")
            if alt:
                alts.append(f"Image {i}: {alt}")
    elif etype == "app.bsky.embed.external":
        ext = embed.get("external", {})
        title, desc, uri = ext.get("title", "").strip(), ext.get("description", "").strip(), ext.get("uri", "").strip()
        if title:
            parts.append(f"[Link: {title}]")
        if desc:
            parts.append(f"[Desc: {desc[:150]}]")
        if uri and not uri.startswith("https://bsky.app"):
            parts.append(f"[URL: {uri}]")
    elif etype == "app.bsky.embed.record":
        rec = embed.get("record", {})
        if rec.get("$type") == "app.bsky.feed.post":
            val = rec.get("value", {})
            quote_text = val.get("text", "")[:150]
            quote_author = rec.get("author", {}).get("handle", "")
            if quote_text:
                parts.append(f"[Quote @{quote_author}: {quote_text}]")
        elif rec.get("title"):
            parts.append(f"[Record: {rec.get('title')}]")
    elif etype == "app.bsky.embed.video":
        alt = embed.get("video", {}).get("alt", "").strip()
        parts.append(f"[Video: {alt}]" if alt else "[Video]")
        if alt:
            alts.append(f"Video: {alt}")
    elif etype == "app.bsky.embed.recordWithMedia":
        media = embed.get("media", {})
        record = embed.get("record", {})
        m_text, m_alts = extract_embed_full(media)
        r_text, _ = extract_embed_full({"$type": "app.bsky.embed.record", "record": record})
        if m_text:
            parts.append(m_text)
            alts.extend(m_alts)
        if r_text:
            parts.append(r_text)
    return " ".join(p for p in parts if p), alts

async def with_retry(func, max_attempts: int = 3, backoff: float = 1.5):
    for attempt in range(max_attempts):
        try:
            return await func()
        except HTTPStatusError as e:
            if e.response.status_code in [429, 502, 503, 504] and attempt < max_attempts - 1:
                retry_header = e.response.headers.get("retry-after")
                wait_time = None
                if retry_header:
                    try:
                        wait_time = int(retry_header)
                    except ValueError:
                        try:
                            parsed_time = email.utils.parsedate_to_datetime(retry_header)
                            wait_time = max(0, (parsed_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
                        except Exception:
                            pass
                if wait_time is None:
                    wait_time = 5 * (backoff ** attempt)
                await asyncio.sleep(wait_time)
                continue
            raise
        except Exception as e:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1 * (backoff ** attempt))
                continue
            raise

def hash_to_slot(value: str, slot_count: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % slot_count
