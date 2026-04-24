import asyncio
import hashlib
import re
import logging
import html
import httpx
from httpx import HTTPStatusError
import config
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

def sanitize_prompt(text: str) -> str:
    if not text:
        return ""
    injection_patterns = [
        r'(?i)ignore\s+(previous|all)\s+instructions',
        r'(?i)system\s*(override|prompt|instruction)',
        r'(?i)forget\s+all\s+rules',
        r'(?i)you\s+are\s+now\s+',
        r'(?i)from\s+now\s+on\s+',
        r'(?i)disregard\s+(the\s+)?(above|previous)',
        r'(?i)new\s+instruction[s]?:',
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, '[BLOCKED]', text, flags=re.I)
    text = html.escape(text)
    text = re.sub(r'\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'[`\'"\\<>]', '', text)
    return text.strip()

def sanitize_for_prompt(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[{}`\\]', '', text)
    text = text.replace('"', '\\"').replace("'", "\\'")
    return text.strip()

def is_valid_length(text: str, max_len: int = 300) -> bool:
    return len(text) <= max_len

def summarize_search_for_context(search_data: str, max_chars: int = 100) -> str:
    if not search_data:
        return ""
    parts = search_data.split(" | ")
    if parts:
        clean = re.sub(r'^[^\w\s]*', '', parts[0])
        return clean[:max_chars]
    return re.sub(r'[|{}]', '', search_data)[:max_chars]

def update_summary(memory: str, user_query: str, reply: str) -> str:
    if not memory:
        return f"Q: {user_query[:100]} -> A: {reply[:100]}"
    return memory[-200:] + f" | Q: {user_query[:50]} -> A: {reply[:50]}"

def format_fallback_topics(topics: list) -> str:
    if not topics:
        return ""
    return ", ".join(topics)

async def fetch_url_content(url: str) -> str:
    if not TRAFILATURA_AVAILABLE:
        return ""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            content = trafilatura.extract(r.text)
            if content:
                return re.sub(r'\s+', ' ', content.strip())[:400]
            return ""
    except Exception:
        return ""

async def with_retry(func, max_attempts: int = None, backoff: float = None):
    if max_attempts is None:
        max_attempts = config.HTTP_MAX_RETRIES
    if backoff is None:
        backoff = config.HTTP_BACKOFF
    for attempt in range(max_attempts):
        try:
            return await func()
        except HTTPStatusError as e:
            if e.response.status_code in [429, 502, 503, 504] and attempt < max_attempts - 1:
                await asyncio.sleep(3 * (backoff ** attempt))
                continue
            raise
        except Exception:
            if attempt < max_attempts - 1:
                await asyncio.sleep(1 * (backoff ** attempt))
                continue
            raise

def hash_to_slot(value: str, slot_count: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % slot_count