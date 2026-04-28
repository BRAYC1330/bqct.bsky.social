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
    text = re.sub(r'[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U00002600-\U000026FF\U00002700-\U000027BF]+', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n', text)
    return text.strip()
def count_graphemes(text: str) -> int:
    return len(text) if text else 0
def sanitize_input(text: str, max_len: int = 2000, for_prompt: bool = False) -> str:
    if not text: return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    if for_prompt:
        text = re.sub(r'[\[\]{}<>|\\^`]', '', text)
    return text[:max_len] if len(text) > max_len else text
def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text: return 0
    if llm:
        try: return len(llm.tokenize(text.encode("utf-8")))
        except: pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))
def validate_and_fix_output(text: str) -> str:
    if not text: return "Invalid response."
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) > 2: text = " ".join(sentences[:2])
    if not any(text.endswith(c) for c in ".!?"): text += "."
    if len(text) > 300:
        last_dot = text[:299].rfind(".")
        text = text[:last_dot+1] if last_dot != -1 else text[:297] + "..."
    return text
def validate_post_content(text: str, max_graphemes: int = 300, max_tokens: Optional[int] = None, llm: Optional[Any] = None) -> tuple:
    if max_tokens and llm and count_tokens(text, llm) > max_tokens:
        words = text.split()
        out, current = [], 0
        for w in words:
            t = count_tokens(w + " ", llm)
            if current + t > max_tokens: break
            out.append(w)
            current += t
        text = " ".join(out)
        if not text.endswith(('.', '!', '?')): text += "."
    grapheme_count = count_graphemes(text)
    if grapheme_count <= max_graphemes: return True, text
    truncated = text[:max_graphemes]
    last_period = truncated.rfind('.')
    if last_period >= int(max_graphemes * 0.7):
        truncated = truncated[:last_period + 1]
    else:
        last_space = truncated.rfind(' ')
        if last_space >= int(max_graphemes * 0.7):
            truncated = truncated[:last_space].rstrip('.,;:') + '.'
        else:
            truncated = truncated[:int(max_graphemes * 0.7)].rstrip('.,;: ') + '.'
    return count_graphemes(truncated) <= max_graphemes, truncated
async def _format_thread_for_llm(chain: dict, owner_did: str, bot_did: str, client: httpx.AsyncClient, max_recent: int = 20) -> str:
    if not chain: return ""
    root = clean_for_llm(chain.get("root_text", ""))
    posts = chain.get("chain", [])
    recent_posts = posts[-max_recent:] if len(posts) > max_recent else posts
    dialogue = []
    seen_hashes = set()
    root_hash = hash(root)
    seen_hashes.add(root_hash)
    for post in recent_posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        text = clean_for_llm(rec.get("text", ""))
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
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        for u in urls:
            content = await bsky._fetch_url_content(client, u)
            if content: text += f" [LINK: {content}]"
        if did == owner_did: prefix = "Q:"
        elif did == bot_did: prefix = "A:"
        else: prefix = "@user:"
        dialogue.append(f"{prefix} {text}")
    parts = [f"[ROOT]\n{root}"]
    if dialogue:
        parts.append(f"[RECENT]\n" + "\n".join(dialogue))
    return "\n".join(parts)