import os
import pathlib
import yaml
import logging
import re
from typing import Optional, Tuple, Any, Dict
from llama_cpp import Llama
import config
logger = logging.getLogger(__name__)
PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts: Dict[str, str] = yaml.safe_load(f)
def get_prompt(name: str, **kwargs) -> str:
    template = _prompts.get(name, "")
    if not template:
        logger.warning(f"[generator] Prompt '{name}' not found")
        return ""
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"[generator] Missing prompt key {e} in '{name}'")
        return template
def get_model() -> Optional[Llama]:
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[generator] Model not found: {model_path}")
        return None
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=config.MODEL_N_CTX,
            n_gpu_layers=0,
            n_threads=config.MODEL_N_THREADS,
            n_batch=512,
            verbose=False
        )
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None
def extract_search_intent(llm: Llama, thread_context: str, user_query: str) -> Tuple[str, str]:
    prompt = get_prompt("tavily_intent", thread_context=thread_context, user_query=user_query)
    try:
        raw = llm(prompt, max_tokens=60, temperature=0.1)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip().strip('"')
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"):
                time_range = ""
            return query, time_range
        return user_query, ""
    except Exception as e:
        logger.warning(f"[generator] extract_search_intent failed: {e}")
        return user_query, ""
def extract_chainbase_keyword(llm: Llama, text: str) -> str:
    prompt = get_prompt("chainbase_keyword", text=text)
    try:
        raw = llm(prompt, max_tokens=10, temperature=0.1)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        raw = raw.strip()
        if "KEYWORD:" in raw.upper():
            raw = raw.split("KEYWORD:")[-1].strip()
        cleaned = re.sub(r'[^\w\s]', '', raw)
        return cleaned.split()[0] if cleaned else ""
    except Exception as e:
        logger.warning(f"[generator] extract_chainbase_keyword failed: {e}")
        return ""
def get_answer(
    llm: Llama,
    context: str,
    user_query: str,
    max_chars: int = 280,
    temperature: float = 0.5
) -> str:
    prompt = get_prompt("reply", context=context, query=user_query, max_chars=max_chars)
    try:
        output = llm(prompt, max_tokens=150, temperature=temperature)
        raw_text = output.get("choices", [{}])[0].get("text", "")
        raw_text = raw_text.strip()
        for prefix in ("A: ", "A:", "Q: ", "Q:"):
            if raw_text.startswith(prefix):
                raw_text = raw_text[len(prefix):]
                break
        logger.info(f"[LLM] RAW_REPLY_OUTPUT: {raw_text}")
        return raw_text.strip()
    except Exception as e:
        logger.error(f"[generator] get_answer failed: {e}")
        return ""