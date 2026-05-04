import os
import pathlib
import yaml
import logging
import re
from llama_cpp import Llama
import config
logger = logging.getLogger(__name__)
PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts = yaml.safe_load(f)
def get_model():
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
def load_prompt(key, **kwargs):
    template = _prompts.get(key, "")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"[generator] Missing prompt key: {e}")
        return template
def extract_search_intent(llm, thread_context: str, user_query: str) -> tuple:
    prompt = load_prompt("tavily_intent", query=user_query)
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
    except Exception:
        return user_query, ""
def extract_chainbase_keyword(llm, text: str) -> str:
    prompt = load_prompt("chainbase_keyword", text=text)
    try:
        raw = llm(prompt, max_tokens=10, temperature=0.1)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        raw = raw.strip()
        if "KEYWORD:" in raw.upper():
            raw = raw.split("KEYWORD:")[-1].strip()
        return re.sub(r'[^\w\s]', '', raw).split()[0] if raw else ""
    except Exception:
        return ""
def classify_intent(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("intent_check", message=message, root_topic=root_topic)
    try:
        raw = llm(prompt, max_tokens=5, temperature=0.1)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        cls = raw.strip().upper()
        return "SUBSTANTIVE" if "SUBSTANTIVE" in cls else "CASUAL"
    except Exception:
        return "SUBSTANTIVE"
def regenerate_keyword(llm, original: str, query: str, root_topic: str) -> str:
    prompt = load_prompt("keyword_regenerate", original=original, query=query, root_topic=root_topic)
    try:
        raw = llm(prompt, max_tokens=15, temperature=0.3)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        kw = raw.strip().split()[0] if raw.strip() else ""
        return re.sub(r'[^\w]', '', kw)
    except Exception:
        return ""
def get_answer(llm, context: str, user_query: str, max_chars: int = 280, temperature: float = 0.5, prompt_key: str = "community_reply") -> str:
    prompt_skeleton = load_prompt(prompt_key, query=user_query, max_chars=max_chars, context=context)
    logger.info(f"\033[93m=== [PROMPT] ===\033[0m")
    logger.info(prompt_skeleton)
    logger.info(f"\033[93m=== [PROMPT] END ===\033[0m")
    full_prompt = f"{context}\n{prompt_skeleton}"
    output = llm(full_prompt, max_tokens=220, temperature=temperature)
    raw_text = output.get("choices", [{}])[0].get("text", "")
    return raw_text.strip()