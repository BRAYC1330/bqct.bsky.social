import re
import logging
logger = logging.getLogger(__name__)

def merge_contexts(memory: str, root_thread: str, search_ str, user_query: str, recent_messages: list = None) -> str:
    parts = []
    if memory:
        parts.append(f"[MEMORY]\n{memory}")
    if recent_messages:
        parts.append(f"[RECENT]\n" + "\n".join(recent_messages[-5:]))
    if root_thread:
        parts.append(f"[ROOT]\n{root_thread}")
    if search_
        parts.append(f"[SEARCH]\n{search_data}")
    if user_query:
        parts.append(f"[QUERY]\n{user_query}")
    return "\n".join(parts)

def format_search_summary(search_ str, max_chars: int = 100) -> str:
    if not search_
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

def compress_thread_context(llm, raw_parts: list, max_total_chars: int = 3500) -> str:
    full_text = " ".join(raw_parts)
    if len(full_text) <= max_total_chars:
        return full_text.strip()
    chunks = [full_text[i:i+2000] for i in range(0, len(full_text), 2000)]
    summaries = []
    for chunk in chunks:
        prompt = f"Summarize this text in 100-150 characters. Keep only core facts and context.\nText: {chunk[:1500]}\nSummary:"
        try:
            res = llm(prompt, max_tokens=100, temperature=0.1)
            summaries.append(res["choices"][0]["text"].strip())
        except:
            summaries.append(chunk[:150])
    merged = " ".join(summaries)
    return merged.strip()[:max_total_chars]