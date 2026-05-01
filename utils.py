import re
import logging
import httpx
import asyncio
from typing import Any, Optional
import config
import bsky
logger = logging.getLogger(__name__)
def is_english(text: str) -> bool:
    if not text or not config.ENGLISH_ONLY_SEARCH:
        return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= config.ENGLISH_ASCII_RATIO
def clean_for_llm(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'[\s\n]*Qwen(\s*\|\s*(Tavily|Chainbase|Chainbase TOPS))?\s*[\s\n]*$', '', text, flags=re.I | re.MULTILINE)
    text = re.sub(r'[\U0001F300-\U0001F9FF\U0000FE00-\U0000FE0F\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U00002600-\U000026FF\U00002700-\U000027BF\U0001F1E0-\U0001F1FF]+', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'@\S+', '', text)
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
def count_chars(text: str) -> int:
    return len(text) if text else 0
def truncate_response(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_dot = truncated.rfind(".")
    if last_dot != -1 and last_dot > max_length * 0.5:
        return truncated[:last_dot+1]
    return truncated.rstrip() + "."
def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text:
        return 0
    if llm:
        try:
            return len(llm.tokenize(text.encode("utf-8")))
        except Exception:
            pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))
async def _format_thread_for_llm(chain: dict, owner_did: str, bot_did: str, client: httpx.AsyncClient, max_recent: int = 20) -> str:
    if not chain:
        return ""
    root = clean_for_llm(chain.get("root_text", ""))
    posts = chain.get("chain", [])
    recent_posts = posts[-max_recent:] if len(posts) > max_recent else posts
    dialogue = []
    seen_hashes = set()
    seen_hashes.add(hash(root))
    fetch_tasks = []
    post_metadata = []
    for post in recent_posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        raw_text = rec.get("text", "")
        text = clean_for_llm(raw_text)
        if not text:
            continue
        post_hash = hash(text)
        if post_hash in seen_hashes:
            continue
        seen_hashes.add(post_hash)
        embed = rec.get("embed")
        embed_txt = bsky._extract_embed_text(embed)
        if embed_txt:
            text += f" [EMBED: {embed_txt}]"
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', raw_text)
        if urls:
            for u in urls:
                fetch_tasks.append(u)
        prefix = "A:" if did == bot_did else "Q:"
        post_metadata.append({"prefix": prefix, "text": text, "url_count": len(urls)})
    if fetch_tasks:
        semaphore = asyncio.Semaphore(3)
        async def fetch_with_limit(url):
            async with semaphore:
                return await bsky._fetch_url_content(client, url)
        results = await asyncio.gather(*[fetch_with_limit(u) for u in fetch_tasks], return_exceptions=True)
        result_iter = iter(r if isinstance(r, str) and r else "" for r in results)
        for meta in post_metadata:
            for _ in range(meta["url_count"]):
                content = next(result_iter)
                if content:
                    meta["text"] += f" [LINK: {content}]"
    for meta in post_metadata:
        dialogue.append(f"{meta['prefix']} {meta['text']}")
    parts = [f"[ROOT]\n{root}"]
    if dialogue:
        parts.append(f"[RECENT]\n" + "\n".join(dialogue))
    return "\n".join(parts)