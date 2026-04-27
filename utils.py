import re
import hashlib
import logging
from typing import Any, Optional
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
def count_graphemes(text: str) -> int:
    if not text:
        return 0
    return len(text)
def sanitize_input(text: str, max_len: int = 2000, for_prompt: bool = False) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    if for_prompt:
        text = re.sub(r'[\[\]{}<>|\\^`]', '', text)
    if len(text) > max_len:
        text = text[:max_len]
    return text
def count_tokens(text: str, llm: Optional[Any] = None) -> int:
    if not text:
        return 0
    if llm is not None:
        try:
            return len(llm.tokenize(text.encode("utf-8")))
        except Exception:
            pass
    return max(1, int(len(text) * config.TOKEN_TO_CHAR_RATIO))
def validate_and_fix_output(text: str) -> str:
    if not text:
        return "Invalid response."
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) > 2:
        text = " ".join(sentences[:2])
    if not any(text.endswith(c) for c in ".!?"):
        text += "."
    elif not any(text.endswith(c) for c in ".!?"):
        text += "."
    if len(text) > 300:
        last_dot = text[:299].rfind(".")
        text = text[:last_dot+1] if last_dot != -1 else text[:297] + "..."
    return text
def validate_post_content(text: str, max_graphemes: int = 300, max_tokens: Optional[int] = None, llm: Optional[Any] = None) -> tuple:
    if max_tokens and llm and count_tokens(text, llm) > max_tokens:
        words = text.split()
        out = []
        current = 0
        for w in words:
            t = count_tokens(w + " ", llm)
            if current + t > max_tokens:
                break
            out.append(w)
            current += t
        text = " ".join(out)
        if not text.endswith(('.', '!', '?')):
            text += "."
    grapheme_count = count_graphemes(text)
    if grapheme_count <= max_graphemes:
        return True, text
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
def get_slot(value: str, slot_count: int = None) -> int:
    count = slot_count if slot_count is not None else config.CONTEXT_SLOT_COUNT
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % count
def _clean_user_text(text: str) -> str:
    text = text.replace("!t", "").replace("!c", "").strip()
    text = re.sub(r'\s+', ' ', text)
    return text
def _clean_bot_signature(text: str) -> str:
    text = re.sub(r'\s*\|\s*(Qwen|Tavily|Chainbase)(\s*\|\s*(Tavily|Chainbase|Qwen))*\s*$', '', text, flags=re.I)
    return text.strip()
def _format_handle(handle: str, owner_did: str, author_did: str) -> str:
    if author_did == owner_did:
        return "@owner"
    if "bsky.app" in handle or handle.endswith(".social"):
        return "@user"
    return f"@{handle.split('.')[0]}"
def _clean_thread_for_llm(chain: dict, owner_did: str, max_recent: int = 12) -> str:
    if not chain:
        return ""
    root = chain.get("root_text", "").strip()
    root_clean = re.sub(r'(!t|!c)', '', root, flags=re.I)
    root_clean = re.sub(r'\s*\|\s*(Qwen|Tavily|Chainbase).*$', '', root_clean, flags=re.I).strip()
    lines = [f"Root: {root_clean[:200]}"]
    posts = chain.get("chain", [])
    recent = posts[-max_recent:] if len(posts) > max_recent else posts
    for post in recent:
        rec = post.get("record", {})
        author = post.get("author", {})
        handle = author.get("handle", "")
        author_did = author.get("did", "")
        p_text = rec.get("text", "")
        p_text = _clean_user_text(p_text)
        p_text = _clean_bot_signature(p_text)
        embed = rec.get("embed")
        if embed:
            embed_type = embed.get("$type", "")
            if embed_type == "app.bsky.embed.external":
                ext = embed.get("external", {})
                if ext.get("title"):
                    p_text += f" [Link: {ext['title']}]"
        role = _format_handle(handle, owner_did, author_did)
        lines.append(f"{role}: {p_text}")
    return "\n".join(lines)