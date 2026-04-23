import asyncio
import hashlib
import re
import logging
from httpx import HTTPStatusError

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
        msg = record.getMessage() if hasattr(record, 'getMessage') else str(record.msg)
        for pattern in self.SECRET_PATTERNS:
            msg = re.sub(pattern, self.REPLACEMENT, msg, flags=re.IGNORECASE)
        record.msg = msg
        record.args = None
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
    return len(text) if text else 0

async def with_retry(func, max_attempts: int = 3, backoff: float = 1.5):
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
