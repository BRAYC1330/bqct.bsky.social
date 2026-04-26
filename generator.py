import os
import sys
import pathlib
import yaml
import logging
import re
from llama_cpp import Llama
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
try:
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        _prompts = yaml.safe_load(f)
    if not isinstance(_prompts, dict) or "digest_refine" not in _prompts:
        logger.error(f"[generator] Invalid prompts.yaml at {PROMPTS_PATH}")
        sys.exit(1)
    logger.info(f"[generator] Prompts loaded: {PROMPTS_PATH} | Version: {_prompts.get('version', 'unknown')}")
except Exception as e:
    logger.error(f"[generator] Failed to load prompts: {e}")
    sys.exit(1)

def get_model():
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[generator] Model not found: {model_path}")
        return None
    try:
        llm = Llama(model_path=model_path, n_ctx=config.MODEL_N_CTX, n_gpu_layers=0, n_threads=config.MODEL_N_THREADS, n_batch=512, verbose=False)
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None

def clean_artifacts(text: str) -> str:
    text = re.sub(r'\s*\[score:\s*\d+\]\s*:', ':', text)
    text = re.sub(r'\s*\[\d+\s*characters?\]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'^\[ROOT\]\s*@[^\s]+:\s*', '', text)
    text = re.sub(r'^\[[A-Z_]+\]\s*', '', text)
    return text.strip()

def _extract_text(response) -> str:
    if isinstance(response, str): return response.strip()
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices and isinstance(choices[0], dict): return choices[0].get("text", "").strip()
    return ""

def extract_tavily_intent(llm, query: str) -> tuple:
    prompt = _prompts["tavily_intent"].format(query=query)
    logger.info(f"=== TAVILY_PROMPT ===\n{prompt}\n=== END_TAVILY_PROMPT ===")
    try:
        raw = llm(prompt, max_tokens=config.TAVILY_MAX_TOKENS, temperature=0.1)
        logger.info(f"[generator] RAW_TAVILY_INTENT_OUTPUT: {raw}")
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query_out = q_part.replace("QUERY:", "").strip()
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"): time_range = ""
            return query_out, time_range
        return query, ""
    except Exception: return query, ""

def extract_chainbase_keyword(llm, text: str) -> str:
    prompt = _prompts["chainbase_keyword"].format(text=text)
    logger.info(f"=== KEYWORD_PROMPT ===\n{prompt}\n=== END_KEYWORD_PROMPT ===")
    try:
        raw = llm(prompt, max_tokens=config.KEYWORD_MAX_TOKENS, temperature=0.1)
        logger.info(f"[generator] RAW_KEYWORD_OUTPUT: {raw}")
        keyword = raw.strip().split("\n")[0].replace("KEYWORD:", "").strip().strip('"')
        keyword = re.sub(r'[^a-zA-Z0-9\s]', '', keyword).strip()
        words = keyword.split()
        if not words: return text[:30]
        final_keyword = " ".join(words[:3])
        if len(final_keyword) > 50: return " ".join(text.split()[:3])
        return final_keyword
    except Exception: return text[:30]

def get_reply(llm, memory: str, root_thread: str, search_data: str, query: str) -> str:
    prompt = _prompts["reply"].format(memory=memory or "None", root_thread=root_thread or "None", search_data=search_data or "None", query=query)
    logger.info(f"[generator] REPLY_PROMPT_VERSION: {_prompts.get('version', 'unknown')}")
    logger.info(f"=== REPLY_PROMPT ===\n{prompt}\n=== END_REPLY_PROMPT ===")
    try:
        raw = llm(prompt, max_tokens=config.REPLY_MAX_TOKENS, temperature=0.7)
        logger.info(f"[generator] RAW_REPLY_OUTPUT: {raw}")
        return _extract_text(raw).strip()
    except Exception as e:
        logger.error(f"[generator] get_reply failed: {e}")
        return "Error generating reply."

def generate_digest(llm, keyword: str, summary: str, max_chars: int) -> str:
    target_chars = max(20, max_chars - 10)
    prompt = _prompts["digest_refine"].format(keyword=keyword, summary=summary, max_desc_chars=target_chars)
    logger.info(f"[generator] DIGEST_PROMPT_VERSION: {_prompts.get('version', 'unknown')}")
    logger.info(f"=== DIGEST_PROMPT ===\n{prompt}\n=== END_DIGEST_PROMPT ===")
    try:
        raw = llm(prompt, max_tokens=min(target_chars + 50, config.DIGEST_MAX_TOKENS), temperature=0.3)
        logger.info(f"[generator] RAW_DIGEST_OUTPUT: {raw}")
        desc = clean_artifacts(_extract_text(raw).split('\n')[0].strip())

        if len(desc) > max_chars:
            truncated = desc[:max_chars]
            last_period = truncated.rfind('.')
            if last_period >= int(max_chars * 0.7):
                desc = truncated[:last_period + 1]
            else:
                last_space = truncated.rfind(' ')
                if last_space >= int(max_chars * 0.7):
                    desc = truncated[:last_space].rstrip('.,;:') + '.'
                else:
                    desc = truncated[:int(max_chars * 0.7)].rstrip('.,;: ') + '.'
        elif desc and not desc.endswith('.'):
            desc = desc.rstrip('.,;: ') + '.'

        return desc
    except Exception as e:
        logger.error(f"[generator] generate_digest failed: {e}")
        return summary

def update_context_memory(llm, history: str) -> str:
    prompt = _prompts["context_memory"].format(history=history)
    logger.info(f"=== MEMORY_PROMPT ===\n{prompt}\n=== END_MEMORY_PROMPT ===")
    try:
        raw = llm(prompt, max_tokens=config.MEMORY_MAX_TOKENS, temperature=0.3)
        logger.info(f"[generator] RAW_MEMORY_OUTPUT: {raw}")
        return _extract_text(raw).strip().replace("###", "").replace("---", "")
    except Exception as e:
        logger.error(f"[generator] update_context_memory failed: {e}")
        return history