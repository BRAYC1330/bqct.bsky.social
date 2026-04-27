import re
import hashlib
import logging
import unicodedata
from typing import Any, Optional
import config
from logging_config import setup_logging
import regex

setup_logging()
logger = logging.getLogger(__name__)

def count_graphemes(text: str) -> int:
    if not text:
        return 0
    return len(regex.findall(r'\X', text))

def sanitize_input(text: str, max_len: int = 2000, for_prompt: bool = False) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
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
    text = text.strip()
    prefixes_to_remove = ["Answer:", "Here is", "Sure,", "Of course", "Based on"]
    for p in prefixes_to_remove:
        if text.startswith(p):
            text = text[len(p):].strip().lstrip(": ")
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

def validate_post_content(text: str, max_graphemes: int = 300, max_tokens: Optional[int] = None, llm: Optional[Any] = None) -> tuple[bool, str]:
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