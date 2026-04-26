import os
import sys
import pathlib
import yaml
import logging
import re
from typing import Any, Optional, Tuple
from llama_cpp import Llama
import config
import utils
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
try:
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        _prompts: dict[str, Any] = yaml.safe_load(f)
    if not isinstance(_prompts, dict) or "digest_refine" not in _prompts:
        logger.error(f"[generator] Invalid prompts.yaml at {PROMPTS_PATH}")
        sys.exit(1)
    logger.info(f"[generator] Prompts loaded: {PROMPTS_PATH} | Version: {_prompts.get('version', 'unknown')}")
except FileNotFoundError:
    logger.error(f"[generator] prompts.yaml not found at {PROMPTS_PATH}")
    sys.exit(1)
except yaml.YAMLError as e:
    logger.error(f"[generator] Failed to parse prompts.yaml: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"[generator] Unexpected error loading prompts: {e}")
    sys.exit(1)

def get_model() -> Optional[Llama]:
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[generator] Model not found: {model_path}")
        return None
    try:
        llm = Llama(model_path=model_path, n_ctx=config.MODEL_N_CTX, n_gpu_layers=0, n_threads=config.MODEL_N_THREADS, n_batch=2048, verbose=False)
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except OSError as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None
    except RuntimeError as e:
        logger.error(f"[generator] Model initialization error: {e}")
        return None

def clean_artifacts(text: str) -> str:
    text = re.sub(r'\s*\[score:\s*\d+\]\s*:', ':', text)
    text = re.sub(r'\s*\[\d+\s*characters?\]', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'^\[ROOT\]\s*@[^\s]+:\s*', '', text)
    text = re.sub(r'^\[[A-Z_]+\]\s*', '', text)
    return text.strip()

def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices and isinstance(choices[0], dict):
            return choices[0].get("text", "").strip()
    return ""

def _truncate_to_tokens(text: str, max_tokens: int, llm: Llama) -> str:
    if utils.count_tokens(text, llm) <= max_tokens:
        return text
    words = text.split()
    out = []
    current_tokens = 0
    for w in words:
        t = utils.count_tokens(w + " ", llm)
        if current_tokens + t > max_tokens:
            break
        out.append(w)
        current_tokens += t
    return " ".join(out)

def extract_tavily_intent(llm: Llama, query: str) -> Tuple[str, str]:
    safe_q = utils.sanitize_input(query, max_len=500)
    prompt = _prompts["tavily_intent"].format(query=safe_q)
    logger.info(f"=== TAVILY_PROMPT ===\n{prompt}\n=== END_TAVILY_PROMPT ===")
    try:
        raw: Any = llm(prompt, max_tokens=config.TAVILY_MAX_TOKENS, temperature=0.1)
        logger.info(f"[generator] RAW_TAVILY_INTENT_OUTPUT: {raw}")
        if "| TIME:" in str(raw):
            raw_str = str(raw)
            q_part, t_part = raw_str.split("| TIME:", 1)
            query_out = q_part.replace("QUERY:", "").strip()
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"):
                time_range = ""
            return query_out, time_range
        return query, ""
    except (ValueError, TypeError, RuntimeError) as e:
        logger.warning(f"[generator] Tavily intent extraction failed: {e}")
        return query, ""

def extract_chainbase_keyword(llm: Llama, text: str) -> str:
    safe_t = utils.sanitize_input(text, max_len=500)
    prompt = _prompts["chainbase_keyword"].format(text=safe_t)
    logger.info(f"=== KEYWORD_PROMPT ===\n{prompt}\n=== END_KEYWORD_PROMPT ===")
    try:
        raw: Any = llm(prompt, max_tokens=config.KEYWORD_MAX_TOKENS, temperature=0.1)
        logger.info(f"[generator] RAW_KEYWORD_OUTPUT: {raw}")
        raw_str = str(raw)
        keyword = raw_str.strip().split("\n")[0].replace("KEYWORD:", "").strip().strip('"')
        keyword = re.sub(r'[^a-zA-Z0-9\s]', '', keyword).strip()
        words = keyword.split()
        if not words:
            return utils.sanitize_input(text, max_len=30)
        final_keyword = " ".join(words[:3])
        if len(final_keyword) > 50:
            return utils.sanitize_input(text, max_len=30)
        return final_keyword
    except (ValueError, TypeError, RuntimeError) as e:
        logger.warning(f"[generator] Chainbase keyword extraction failed: {e}")
        return utils.sanitize_input(text, max_len=30)

def get_reply(llm: Llama, memory: str, root_thread: str, search_data: str, query: str) -> str:
    safe_mem = utils.sanitize_input(memory, max_len=1000)
    safe_root = utils.sanitize_input(root_thread, max_len=1000)
    safe_search = utils.sanitize_input(search_data, max_len=2000)
    safe_query = utils.sanitize_input(query, max_len=500)
    prompt = _prompts["reply"].format(memory=safe_mem or "None", root_thread=safe_root or "None", search_data=safe_search or "None", query=safe_query)
    logger.info(f"[generator] REPLY_PROMPT_VERSION: {_prompts.get('version', 'unknown')}")
    logger.info(f"=== REPLY_PROMPT ===\n{prompt}\n=== END_REPLY_PROMPT ===")
    try:
        raw: Any = llm(prompt, max_tokens=config.REPLY_MAX_TOKENS, temperature=0.7)
        logger.info(f"[generator] RAW_REPLY_OUTPUT: {raw}")
        return utils.validate_and_fix_output(_extract_text(raw))
    except (ValueError, TypeError, RuntimeError) as e:
        logger.error(f"[generator] get_reply failed: {e}")
        return "Error generating reply."

def generate_digest(llm: Llama, keyword: str, summary: str, max_tokens_limit: int) -> str:
    safe_kw = utils.sanitize_input(keyword, max_len=100)
    safe_sum = utils.sanitize_input(summary, max_len=1000)
    prompt = _prompts["digest_refine"].format(keyword=safe_kw, summary=safe_sum, max_desc_chars=100)
    logger.info(f"[generator] DIGEST_PROMPT_VERSION: {_prompts.get('version', 'unknown')}")
    logger.info(f"=== DIGEST_PROMPT ===\n{prompt}\n=== END_DIGEST_PROMPT ===")
    try:
        raw: Any = llm(prompt, max_tokens=min(max_tokens_limit + 20, config.DIGEST_MAX_TOKENS), temperature=0.3)
        desc = clean_artifacts(_extract_text(raw).split('\n')[0].strip())
        if utils.count_tokens(desc, llm) > max_tokens_limit:
            desc = _truncate_to_tokens(desc, max_tokens_limit, llm)
            if not desc.endswith(('.', '!', '?')):
                desc += "."
        elif desc and not desc.endswith(('.', '!', '?')):
            desc += "."
        return desc
    except (ValueError, TypeError, RuntimeError) as e:
        logger.error(f"[generator] generate_digest failed: {e}")
        return utils.sanitize_input(summary, max_len=100)

def update_context_memory(llm: Llama, history: str) -> str:
    safe_h = utils.sanitize_input(history, max_len=4000)
    token_limit = int(config.MEMORY_MAX_TOKENS * 0.8)
    if utils.count_tokens(safe_h, llm) > token_limit:
        safe_h = _truncate_to_tokens(safe_h, token_limit, llm)
    prompt = _prompts["context_memory"].format(history=safe_h)
    logger.info(f"=== MEMORY_PROMPT ===\n{prompt}\n=== END_MEMORY_PROMPT ===")
    try:
        raw: Any = llm(prompt, max_tokens=config.MEMORY_MAX_TOKENS, temperature=0.3)
        logger.info(f"[generator] RAW_MEMORY_OUTPUT: {raw}")
        return _extract_text(raw).strip().replace("###", "").replace("---", "")
    except (ValueError, TypeError, RuntimeError) as e:
        logger.error(f"[generator] update_context_memory failed: {e}")
        return utils.sanitize_input(history, max_len=4000)