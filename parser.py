import re
import logging
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def sanitize_for_prompt(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[{}`\\]', '', text)
    text = text.replace('"', '\\"').replace("'", "\\'")
    return text.strip()

def prepare_context(memory: str, root_thread: str, search_data: str, user_query: str) -> str:
    parts = []
    if memory:
        parts.append(f"[MEMORY]\n{memory}")
    if root_thread:
        parts.append(f"[ROOT_THREAD]\n{root_thread}")
    if search_data:
        parts.append(f"[SEARCH]\n{search_data}")
    if user_query:
        parts.append(f"[QUERY]\n{user_query}")
    return "\n".join(parts)

def trim_for_llm(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(' ', 1)[0] + "..."