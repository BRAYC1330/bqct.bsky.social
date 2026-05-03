import re
import logging
import httpx
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
def generate_facets(text: str) -> list:
    facets = []
    for pattern, ftype, key in [
        (r'#([a-zA-Z0-9_]+)', 'app.bsky.richtext.facet#tag', 'tag'),
        (r'\$([a-zA-Z0-9]+)', 'app.bsky.richtext.facet#link', 'uri')
    ]:
        for m in re.finditer(pattern, text):
            bs = len(text[:m.start()].encode('utf-8'))
            be = len(text[:m.end()].encode('utf-8'))
            val = m.group(1) if ftype.endswith('tag') else f"https://dexscreener.com/search?q={m.group(0)}"
            facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": ftype, key: val}]})
    return facets
def count_graphemes(text: str) -> int:
    return len(text) if text else 0
def truncate_to_sentence(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    dot = cut.rfind(".")
    return cut[:dot+1] if dot != -1 else cut.rstrip() + "."
def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text:
        return 0
    if llm:
        try:
            return len(llm.tokenize(text.encode("utf-8")))
        except:
            pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))
async def _format_thread_for_llm(chain: dict, owner_did: str, bot_did: str, client: httpx.AsyncClient, max_recent: int = 5) -> str:
    if not chain:
        return ""
    root = clean_for_llm(chain.get("root_text", ""))
    posts = chain.get("chain", [])
    recent_posts = posts[-max_recent:] if len(posts) > max_recent else posts
    dialogue = []
    seen_hashes = set()
    seen_hashes.add(hash(root))
    for post in recent_posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        raw_text = rec.get("text", "")
        text = clean_for_llm(raw_text)
        if not text or hash(text) in seen_hashes:
            continue
        seen_hashes.add(hash(text))
        embed = rec.get("embed")
        embed_txt = bsky._extract_embed_text(embed)
        if embed_txt:
            text += f" [EMBED: {embed_txt}]"
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', raw_text)
        for u in urls:
            content = await bsky._fetch_url_content(client, u)
            if content:
                text += f" [LINK: {content[:900]}]"
        if did == owner_did:
            prefix = "OWNER:"
        elif did == bot_did:
            prefix = "BOT:"
        else:
            prefix = "USER:"
        dialogue.append(f"{prefix} {text}")
    parts = [f"[ROOT]\n{root}"]
    if dialogue:
        parts.append(f"[RECENT]\n" + "\n".join(dialogue))
    return "\n".join(parts)