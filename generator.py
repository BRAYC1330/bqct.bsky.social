import os
import pathlib
import yaml
import logging
import re
from typing import Optional
from llama_cpp import Llama
import config
from utils import sanitize_prompt
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts = yaml.safe_load(f)

_model_cache: Optional[Llama] = None

def _run_llm(llm, prompt: str, max_tokens: int = 150, temperature: float = 0.7) -> str:
    try:
        out = llm(prompt, max_tokens=max_tokens, temperature=temperature)
        return out["choices"][0]["text"].strip()
    except Exception:
        return ""

def get_model() -> Optional[Llama]:
    global _model_cache
    if _model_cache is not None:
        logger.debug("[generator] Using cached model instance")
        return _model_cache
    
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[generator] Model file not found: {model_path}")
        return None
    
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=config.MODEL_N_CTX,
            n_gpu_layers=0,
            n_threads=config.MODEL_N_THREADS,
            n_batch=1024,
            n_ubatch=1024,
            mmap=True,
            mlock=True,
            verbose=False,
        )
        _model_cache = llm
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None

def extract_search_intent(llm, context: str, user_query: str) -> tuple:
    prompt = _prompts["extract_search_intent"].format(context=sanitize_prompt(context), user_text=sanitize_prompt(user_query))
    try:
        raw = _run_llm(llm, prompt, max_tokens=60, temperature=0.1)
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip()
            time_range = t_part.strip().lower()
            return query, time_range if time_range in ("day", "week", "month", "year") else ""
    except:
        pass
    return user_query, ""

def extract_chainbase_keywords_multi(llm, user_query: str) -> list:
    prompt = _prompts["extract_chainbase_keywords"].format(user_query=sanitize_prompt(user_query))
    try:
        raw = _run_llm(llm, prompt, max_tokens=40, temperature=0.1).upper()
        candidates = [re.sub(r'[^A-Z0-9\-]', '', k.strip()) for k in raw.split(",")[:3]]
        return [k for k in candidates if k and 2 <= len(k) <= 20]
    except:
        return []

def filter_search_results_by_intent(llm, intent_query: str, results: list) -> list:
    if not results:
        return []
    summaries = "\n".join([f"- {r.get('keyword','')}: {r.get('summary','')[:100]}" for r in results[:5]])
    prompt = _prompts["filter_results_by_intent"].format(intent_query=sanitize_prompt(intent_query), summaries=summaries)
    try:
        raw = _run_llm(llm, prompt, max_tokens=30, temperature=0.1).upper()
        if "NONE" in raw:
            return []
        keep_ids = set(re.findall(r'[A-Z0-9\-]+', raw))
        return [r for r in results if r.get("id") in keep_ids or any(kw in r.get("keyword","").upper() for kw in keep_ids)]
    except:
        return results[:2]

def get_answer(llm, context: str, user_query: str, search_data: str = "", fallback_topics: str = "", max_chars: int = 270, temperature: float = 0.7) -> str:
    if fallback_topics and not search_
        prompt = _prompts["get_answer_fallback"].format(fallback_topics=fallback_topics, max_chars=max_chars)
    else:
        prompt = _prompts["get_answer_standard"].format(
            context=sanitize_prompt(context),
            user_query=sanitize_prompt(user_query),
            search_data=sanitize_prompt(search_data) if search_data else "N/A",
            max_chars=max_chars
        )
    return _run_llm(llm, prompt, max_tokens=150, temperature=temperature)
