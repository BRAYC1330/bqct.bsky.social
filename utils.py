import re
import logging
import asyncio
from typing import Any, Optional
import config
logger = logging.getLogger(__name__)
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,10}[A-Z0-9]*|[A-Z0-9]*[A-Z]{1,10})\b')
CLEAN_COMMANDS = re.compile(r'(!t|!c)', re.I)
CLEAN_SIGNATURE = re.compile(r'[\s\n]*Qwen(\s*\|\s*(Tavily|Chainbase|Chainbase TOPS))?\s*[\s\n]*$', re.I | re.MULTILINE)
CLEAN_EMOJIS = re.compile(r'[\U0001F300-\U0001F9FF\U0000FE00-\U0000FE0F\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U00002600-\U000026FF\U00002700-\U000027BF\U0001F1E0-\U0001F1FF]+')
CLEAN_MARKDOWN_LINKS = re.compile(r'!\[[^\]]*\]\([^)]*\)')
CLEAN_LINKS = re.compile(r'\[([^\]]+)\]\([^)]+\)')
CLEAN_MENTIONS = re.compile(r'@\S+')
CLEAN_URLS = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
CLEAN_MARKDOWN = re.compile(r'[*_#~`>|]')
CLEAN_PARENS = re.compile(r'\([^)]*\)')
CLEAN_CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
CLEAN_SPACES = re.compile(r'\s{2,}')
CLEAN_NEWLINES = re.compile(r'\n{3,}')
CLEAN_ARTIFACTS = re.compile(r'\.\s*\+\s*[A-Z][a-z]+\.\s*\+\s*[A-Z][a-z]+')
CLEAN_BE_WELL = re.compile(r'(Be Well\.?\s*)+', re.I)
CLEAN_WHITE_HOUSE = re.compile(r'(White House\.?\s*)+', re.I)
def is_english(text: str) -> bool:
    if not text or not config.ENGLISH_ONLY_SEARCH:
        return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= config.ENGLISH_ASCII_RATIO
def clean_for_llm(text: str) -> str:
    if not text:
        return ""
    text = CLEAN_COMMANDS.sub('', text)
    text = CLEAN_SIGNATURE.sub('', text)
    text = CLEAN_EMOJIS.sub('', text)
    text = CLEAN_MARKDOWN_LINKS.sub('', text)
    text = CLEAN_LINKS.sub(r'\1', text)
    text = CLEAN_MENTIONS.sub('', text)
    text = CLEAN_URLS.sub('', text)
    text = CLEAN_MARKDOWN.sub('', text)
    text = CLEAN_PARENS.sub('', text)
    text = CLEAN_CTRL.sub(' ', text)
    text = CLEAN_SPACES.sub(' ', text)
    text = CLEAN_NEWLINES.sub('\n', text)
    text = CLEAN_ARTIFACTS.sub('', text)
    text = CLEAN_BE_WELL.sub('', text)
    text = CLEAN_WHITE_HOUSE.sub('', text)
    return text.strip()
def count_chars(text: str) -> int:
    return len(text) if text else 0
def truncate_response(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text.strip()
    truncated = text[:max_length]
    idx = truncated.rfind(".")
    if idx != -1 and idx > max_length * 0.5:
        return truncated[:idx+1].strip()
    return text[:max_length].rsplit(" ", 1)[0].rstrip() + "."
def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text:
        return 0
    if llm:
        try:
            return len(llm.tokenize(text.encode("utf-8")))
        except Exception:
            pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))
def build_ticker_facets(text: str) -> list:
    facets = []
    for match in TICKER_PATTERN.finditer(text):
        symbol = match.group(1).lower()
        byte_start = len(text[:match.start()].encode('utf-8'))
        byte_end = len(text[:match.end()].encode('utf-8'))
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": f"https://www.coingecko.com/en/coins/{symbol}"
            }]
        })
    return facets
def extract_embed_text(embed):
    texts = []
    if not embed:
        return ""
    et = embed.get("$type", "")
    if et == "app.bsky.embed.images":
        for img in embed.get("images", []):
            if img.get("alt"):
                texts.append(img["alt"])
    elif et == "app.bsky.embed.external":
        ext = embed.get("external", {})
        if ext.get("title"):
            texts.append(ext["title"])
        if ext.get("description"):
            texts.append(ext["description"])
    elif et == "app.bsky.embed.record":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"):
            texts.append(val["text"])
    elif et == "app.bsky.embed.recordWithMedia":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"):
            texts.append(val["text"])
        med = embed.get("media", {})
        if med.get("$type") == "app.bsky.embed.images":
            for img in med.get("images", []):
                if img.get("alt"):
                    texts.append(img["alt"])
    return " ".join(texts)
async def _format_thread_for_llm(chain: dict, owner_did: str, bot_did: str, client, max_recent: int = 20) -> str:
    if not chain:
        return ""
    import bsky
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
        embed_txt = extract_embed_text(embed)
        if embed_txt:
            text += f" [EMBED: {embed_txt}]"
        urls = CLEAN_URLS.findall(raw_text)
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