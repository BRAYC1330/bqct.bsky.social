import asyncio
import hashlib
import re
import logging
from httpx import HTTPStatusError
import config

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
