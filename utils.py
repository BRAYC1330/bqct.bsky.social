import re
import logging
import httpx
from typing import Any, Optional
import config
import bsky
logger = logging.getLogger(__name__)

def is_english(text: str) -> bool:
    if not text or not config.ENGLISH_ONLY_SEARCH: return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= config.ENGLISH_ASCII_RATIO

def clean_for_llm(text: str) -> str:
    if not text: return ""
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'[\s\n]*Qwen(\s*\|\s*(Tavily|Chainbase|Chainbase TOPS))?\s*[\s\n]*$', '', text, flags=re.I | re.MULTILINE)
    text = re.sub(r'[\U0001F100-\U0001F1FF\U0001F200-\U0001F2FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U0000FE00-\U0000FE0F\u2000-\u206F\u2190-\u21FF\u2B00-\u2BFF]+', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://[^\s<>"{}|\\^`\[\]]+', '', text)
    text = re.sub(r'[*_#~`>|]', '', text)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n', text)
    text = re.sub(r'\.\s*\+\s*[A-Z][a-z]+\.\s*\+\s*[A-Z][a-z]+', '', text)
    text = re.sub(r'(Be Well\.?\s*)+', '', text, flags=re.I)
    text = re.sub(r'(White House\.?\s*)+', '', text, flags=re.I)
    return text.strip()

def format_reply(text: str, sig: str, max_total: int = 300) -> str:
    max_body = max_total - len(sig)
    if count_graphemes(text) > max_body:
        truncated = text[:max_body]
        last_dot = truncated.rfind(".")
        text = truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip() + "."
    return text.strip() + sig

def generate_facets(text: str) -> list:
    facets = []
    for pattern, ftype, key in [
        (r'#([a-zA-Z0-9_]+)', 'app.bsky.richtext.facet#tag', 'tag'),
        (r'\$([a-zA-Z0-9]+)', 'app.bsky.richtext.facet#link', 'uri')
    ]:
        for m in re.finditer(pattern, text):
            bs = len(text[:m.start()].encode('utf-8'))
            be = len(text[:m.end()].encode('utf-8'))
            if ftype.endswith('tag'): val = m.group(1)
            else: val = f"https://dexscreener.com/search?q={m.group(1)}"
            facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": ftype, key: val}]})
    return facets

def count_graphemes(text: str) -> int:
    return len(text) if text else 0

def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text: return 0
    if llm:
        try: return len(llm.tokenize(text.encode("utf-8")))
        except: pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))