import os
import pathlib
import yaml
import logging
import re
import html
from llama_cpp import Llama
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts = yaml.safe_load(f)

SYSTEM_PROMPT = _prompts["system"]
SUMMARIZE_SYSTEM = _prompts["summarize"]
QUERY_REFINE_SYSTEM = _prompts["query_refine"]
DIGEST_GENERATE = _prompts["digest_generate"]
DIGEST_REFINE_SYSTEM = _prompts["digest_refine"]
COMMUNITY_SYSTEM = _prompts["community"]

def _sanitize_input(text: str) -> str:
    if not text:
        return ""
    injection_patterns = [
        r'(?i)ignore\s+(previous|all)\s+instructions',
        r'(?i)system\s*(override|prompt|instruction)',
        r'(?i)forget\s+all\s+rules',
        r'(?i)you\s+are\s+now\s+',
        r'(?i)from\s+now\s+on\s+',
        r'(?i)disregard\s+(the\s+)?(above|previous)',
        r'(?i)new\s+instruction[s]?:',
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, '[BLOCKED]', text, flags=re.I)
    text = html.escape(text)
    text = re.sub(r'\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'[`\'"\\<>]', '', text)
    return text.strip()

def get_model():
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        return None
    try:
        llm = Llama(model_path=model_path, n_ctx=config.MODEL_N_CTX, n_gpu_layers=0, n_threads=config.MODEL_N_THREADS, n_batch=512, verbose=False)
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None

def extract_search_intent(llm, context: str, user_query: str) -> tuple:
    prompt = f"""Extract search query and time filter.
Rules:
- If time is a search filter, use: day, week, month, year.
- If time is part of the question itself, use: none.
- Return ONLY: QUERY: <text> | TIME: <day/week/month/year/none>
Context: {_sanitize_input(context)}
User: "{_sanitize_input(user_query)}"
Output:"""
    try:
        raw = llm(prompt, max_tokens=60, temperature=0.1)
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip()
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"):
                time_range = ""
            return query, time_range
        return user_query, ""
    except:
        return user_query, ""

def extract_chainbase_keywords_multi(llm, user_query: str) -> list:
    prompt = f"""Generate 3 search keywords for crypto narrative API, priority order.
Rules:
- First: compound query combining main topics (e.g. "AI BTC", "quantum bitcoin")
- Second: simplified compound (e.g. "BTC quantum")
- Third: core ticker only (e.g. "BTC", "ETH")
- Return ONLY comma-separated uppercase keywords: KEY1,KEY2,KEY3
- Max 20 chars per keyword, letters/numbers/hyphens only.
Query: "{_sanitize_input(user_query)}"
Keywords:"""
    try:
        raw = llm(prompt, max_tokens=40, temperature=0.1)["choices"][0]["text"].strip().upper()
        candidates = [re.sub(r'[^A-Z0-9\-]', '', k.strip()) for k in raw.split(",")[:3]]
        return [k for k in candidates if k and 2 <= len(k) <= 20]
    except:
        return []

def filter_search_results_by_intent(llm, intent_query: str, results: list) -> list:
    if not results:
        return []
    summaries = "\n".join([f"- {r.get('keyword','')}: {r.get('summary','')[:100]}" for r in results[:5]])
    prompt = f"""Filter results by relevance to query. Keep only items mentioning or related to core topic.
Query: "{_sanitize_input(intent_query)}"
Results:
{summaries}
Return ONLY comma-separated IDs of relevant items, or NONE if all irrelevant.
Relevant IDs:"""
    try:
        raw = llm(prompt, max_tokens=30, temperature=0.1)["choices"][0]["text"].strip().upper()
        if "NONE" in raw:
            return []
        keep_ids = set(re.findall(r'[A-Z0-9\-]+', raw))
        return [r for r in results if r.get("id") in keep_ids or any(kw in r.get("keyword","").upper() for kw in keep_ids)]
    except:
        return results[:2]

def summarize_search_for_context(search_data: str, max_chars: int = 100) -> str:
    if not search_data:
        return ""
    parts = search_data.split(" | ")
    if parts:
        clean = re.sub(r'^[^\w\s]*', '', parts[0])
        return clean[:max_chars]
    return re.sub(r'[|{}]', '', search_data)[:max_chars]

def get_answer(llm, context: str, user_query: str, search_data: str = "", fallback_topics: str = "", max_chars: int = 270, temperature: float = 0.7) -> str:
    fallback_rule = ""
    if fallback_topics and not search_data:
        fallback_rule = f"\n- [FALLBACK] is active: Acknowledge lack of direct info. State what is currently trending: {fallback_topics}. Ask to clarify which topic to explore."
    prompt = f"""Reply in 1-2 short conversational sentences.
Context: {_sanitize_input(context)}
Query: {_sanitize_input(user_query)}
Search: {_sanitize_input(search_data) if search_data else "N/A"}
Rules:
- Max {max_chars} characters including spaces and emojis.
- NO lists, bullets, headers, or digest format.
- Speak naturally like in a direct chat.
- No hashtags, no links, no markdown.
{fallback_rule}
- Be helpful and direct.
Reply:"""
    return llm(prompt, max_tokens=150, temperature=temperature)["choices"][0]["text"].strip()

def update_summary(llm, memory: str, user_query: str, reply: str) -> str:
    if not memory:
        return f"Q: {user_query[:100]} -> A: {reply[:100]}"
    return memory[-200:] + f" | Q: {user_query[:50]} -> A: {reply[:50]}"