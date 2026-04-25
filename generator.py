import os
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
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts = yaml.safe_load(f)

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

def extract_tavily_intent(llm, query: str) -> tuple:
    prompt = _prompts["tavily_intent"].format(query=query)
    logger.info(f"[generator] RAW_TAVILY_INTENT_PROMPT:\n{prompt}")
    try:
        raw = llm(prompt, max_tokens=60, temperature=0.1)
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
    logger.info(f"[generator] RAW_KEYWORD_PROMPT:\n{prompt}")
    try:
        raw = llm(prompt, max_tokens=20, temperature=0.1)
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
    logger.info(f"[generator] RAW_REPLY_PROMPT:\n{prompt}")
    try:
        raw = llm(prompt, max_tokens=100, temperature=0.7)
        logger.info(f"[generator] RAW_REPLY_OUTPUT: {raw}")
        return raw["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"[generator] get_reply failed: {e}")
        return "Error generating reply."

def generate_digest(llm, keyword: str, summary: str, max_chars: int) -> str:
    prompt = _prompts["digest_refine"].format(keyword=keyword, summary=summary, max_desc_chars=max_chars)
    logger.info(f"[generator] RAW_DIGEST_PROMPT:\n{prompt}")
    try:
        raw = llm(prompt, max_tokens=100, temperature=0.2)
        logger.info(f"[generator] RAW_DIGEST_OUTPUT: {raw}")
        return raw["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"[generator] generate_digest failed: {e}")
        return summary

def update_context_memory(llm, history: str) -> str:
    prompt = _prompts["context_memory"].format(history=history)
    logger.info(f"[generator] RAW_MEMORY_PROMPT:\n{prompt}")
    try:
        raw = llm(prompt, max_tokens=300, temperature=0.3)
        logger.info(f"[generator] RAW_MEMORY_OUTPUT: {raw}")
        return raw["choices"][0]["text"].strip().replace("###", "").replace("---", "")
    except Exception as e:
        logger.error(f"[generator] update_context_memory failed: {e}")
        return history