import re
import json
import logging
from typing import Dict, Optional, TypedDict
from llama_cpp import Llama
import config
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

class SearchParams(TypedDict, total=False):
    query: str
    time_range: Optional[str]
    topic: Optional[str]

def get_model():
    return Llama(model_path=config.MODEL_PATH, n_ctx=config.MODEL_N_CTX, n_threads=config.MODEL_N_THREADS, verbose=False)

def _extract_text(response) -> str:
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        c = response.get("choices", [])
        if c and isinstance(c[0], dict):
            return c[0].get("text", "").strip()
    return ""

def extract_search_params(llm, context: str, user_text: str) -> SearchParams:
    prompt = config.QUERY_REFINE_SYSTEM.replace("{{context}}", context).replace("{{user_text}}", user_text)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-SEARCH-PARAM-PROMPT ===\n{prompt}\n=== END ===")
    res = llm(prompt, max_tokens=80, temperature=0.2)
    raw = _extract_text(res)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-SEARCH-PARAM-OUTPUT ===\n{raw}\n=== END ===")
    try:
        p = json.loads(raw)
        p["query"] = p.get("query", user_text)
        for k in ["time_range", "topic"]:
            p[k] = p[k] if p.get(k) not in [None, "null", "none"] else None
        return p
    except Exception:
        return {"query": user_text, "time_range": None, "topic": None}

def get_answer(llm, context: str, user_text: str, search_data: str, max_chars: int) -> str:
    sig = "Qwen"
    prompt = f"{config.SYSTEM_PROMPT}\nConstraint: <{max_chars} chars.\n\n{context}\n\nAnswer:"
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-LLM-PROMPT ===\n{prompt}\n=== END ===")
    res = llm(prompt, max_tokens=max(int(max_chars * 0.8), 100), temperature=config.TEMPERATURE)
    raw = _extract_text(res)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-LLM-OUTPUT ===\n{raw}\n=== END ===")
    reply = raw.split("\n")[0]
    target = max_chars - len(sig) - 2
    if len(reply) > target:
        w = reply.split()
        reply = " ".join(x for x in w if len(" ".join(w[:w.index(x) + 1])) <= target)
    return f"{reply}\n\n{sig}"

def update_summary(llm, memory: str, user_text: str, reply: str) -> str:
    prompt = f"{config.SUMMARIZE_SYSTEM}\nQ: {user_text}\nA: {reply}\nSummary:"
    return utils.sanitize_for_prompt(_extract_text(llm(prompt, max_tokens=50, temperature=0.3)))

def generate_digest(llm, keyword: str, summary: str, max_desc_chars: int) -> str:
    prompt = config.DIGEST_REFINE_SYSTEM.format(keyword=keyword, summary=summary, max_desc_chars=max(20, max_desc_chars))
    raw = _extract_text(llm(prompt, max_tokens=min(max_desc_chars + 10, 100), temperature=0.3)).split("\n")[0]
    return raw[:max_desc_chars]

async def generate_community_plan(llm, digest_ctx: str, comments: list) -> dict:
    c_str = "\n".join([f"@{c['handle']}: {c['text']}" for c in comments])
    prompt = f"{config.COMMUNITY_SYSTEM}\n[DIGEST_CONTEXT]\n{digest_ctx}\n\n[COMMENTS]\n{c_str}\nJSON:"
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-COMMUNITY-PROMPT ===\n{prompt}\n=== END ===")
    res = llm(prompt, max_tokens=300, temperature=0.3)
    raw = _extract_text(res)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-COMMUNITY-OUTPUT ===\n{raw}\n=== END ===")
    try:
        return json.loads(raw)
    except Exception:
        return {"likes": [], "replies": []}
