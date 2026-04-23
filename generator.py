import os
import yaml
import logging
from llama_cpp import Llama
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def get_model():
    model_path = os.path.join(config.MODEL_DIR, config.MODEL_FILE)
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
        logger.info(f"[generator] Model loaded: {config.MODEL_FILE}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {e}")
        return None

def extract_search_params(llm, user_query: str, context: str = "") -> dict:
    prompt = f"""Extract search parameters from the query. Return JSON only.
Query: {user_query}
Context: {context}
Format: {{"query": "search terms", "limit": 5, "time_range": "24h"}}
Output:"""
    try:
        raw = llm(prompt, max_tokens=100, temperature=0.1, stop=["}", "\n\n"])
        raw = raw.strip().rstrip("}") + "}"
        return yaml.safe_load(raw)
    except:
        return {"query": user_query, "limit": 5}

def get_answer(llm, context: str, user_query: str, search_data: str = "", max_chars: int = 280, temperature: float = 0.7) -> str:
    prompt = f"""You are a concise crypto assistant. Reply in 1-2 short sentences.
Context: {context}
Query: {user_query}
Search: {search_data if search_data else "N/A"}
Rules:
- Max {max_chars} characters including spaces and emojis.
- No hashtags, no links, no markdown.
- Be helpful and direct.
Reply:"""
    response = llm(prompt, max_tokens=150, temperature=temperature)
    return response.strip()

def update_summary(llm, memory: str, user_query: str, reply: str) -> str:
    if not memory:
        return f"Q: {user_query[:100]} -> A: {reply[:100]}"
    return memory[-200:] + f" | Q: {user_query[:50]} -> A: {reply[:50]}"
