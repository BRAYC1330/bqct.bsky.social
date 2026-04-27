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
def extract_search_intent(llm, context: str, user_query: str) -> tuple:
    prompt = f"""Extract search query and time filter.
Rules:
- If time is a search filter, use: day, week, month, year.
- If time is part of the question itself, use: none.
- Return ONLY: QUERY: <text> | TIME: <day/week/month/year/none>
Context: {context}
User: "{user_query}"
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
def extract_chainbase_keyword(llm, text: str) -> str:
    prompt_tpl = _prompts.get("chainbase_keyword", "Extract the main keyword or entity from the text.\nOutput format: KEYWORD: [1 word]\nText: {text}\nResult:")
    prompt = prompt_tpl.format(text=text)
    try:
        raw = llm(prompt, max_tokens=10, temperature=0.1)
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        raw = raw.strip()
        if "KEYWORD:" in raw.upper():
            raw = raw.split("KEYWORD:")[-1].strip()
        return re.sub(r'[^\w\s]', '', raw).split()[0] if raw else ""
    except:
        return ""
def get_answer(llm, context: str, user_query: str, search_data: str = "", max_chars: int = 280, temperature: float = 0.3) -> str:
    ctx_lines = []
    if context:
        ctx_lines.append(context)
    if search_data:
        ctx_lines.append(f"[SEARCH]\n{search_data}")
    ctx_block = "\n\n".join(ctx_lines)
    prompt = f"""{ctx_block}

Query: {user_query}

Rules:
- Max {max_chars} characters including spaces and emojis.
- No hashtags, no links, no markdown.
- Be helpful and direct.
Reply:"""
    output = llm(prompt, max_tokens=150, temperature=temperature)
    raw_text = output.get("choices", [{}])[0].get("text", "")
    logger.info(f"[LLM] RAW_REPLY_OUTPUT: {raw_text}")
    return raw_text.strip()