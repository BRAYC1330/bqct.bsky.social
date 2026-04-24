import re
import logging
logger = logging.getLogger(__name__)

def merge_contexts(memory: str, root_thread: str, search_data: str, user_query: str) -> str:
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

def format_search_summary(search_data: str, max_chars: int = 100) -> str:
    if not search_data:
        return ""
    parts = search_data.split(" | ")
    if parts:
        clean = re.sub(r'^[^\w\s]*', '', parts[0])
        return clean[:max_chars]
    return re.sub(r'[|{}]', '', search_data)[:max_chars]

def format_fallback_topics(topics: list) -> str:
    if not topics:
        return ""
    return ", ".join(topics)

def update_and_truncate(memory: str, user_query: str, reply: str, search_summary: str = "", max_len: int = 250) -> str:
    base = memory[-200:] if memory else ""
    new_entry = f" | Q: {user_query[:40]} -> A: {reply[:40]}"
    if search_summary:
        new_entry += f" | S: {search_summary[:50]}"
    combined = base + new_entry
    return combined[-max_len:]