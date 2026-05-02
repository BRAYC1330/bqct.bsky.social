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


def get_model() -> Optional[Llama]:
    """Load and initialize the LLM model.
    
    Returns:
        Loaded Llama model instance or None on failure
    """
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
    """Extract search query and time range from user input using LLM.
    
    Args:
        llm: Loaded LLM instance
        thread_context: Context from the conversation thread
        user_query: User's original query
        
    Returns:
        Tuple of (search_query, time_range)
    """
    prompt = _prompts["tavily_intent"].format(
        thread_context=thread_context,
        user_query=user_query
    )
    
    try:
        raw = llm(prompt, max_tokens=60, temperature=0.1)
        
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip().strip('"')
            time_range = t_part.strip().lower()
            
            # Validate time_range
            if time_range not in ("day", "week", "month", "year"):
                time_range = ""
            
            return query, time_range
        
        return user_query, ""
    except Exception as e:
        logger.warning(f"[generator] extract_search_intent failed: {e}")
        return user_query, ""


def extract_chainbase_keyword(llm: Llama, text: str) -> str:
    """Extract a single keyword for Chainbase search using LLM.
    
    Args:
        llm: Loaded LLM instance
        text: Input text to extract keyword from
        
    Returns:
        Extracted keyword or empty string on failure
    """
    prompt = _prompts["chainbase_keyword"].format(text=text)
    
    try:
        raw = llm(prompt, max_tokens=10, temperature=0.1)
        
        if isinstance(raw, dict):
            raw = raw.get("choices", [{}])[0].get("text", "")
        
        raw = raw.strip()
        
        if "KEYWORD:" in raw.upper():
            raw = raw.split("KEYWORD:")[-1].strip()
        
        # Remove non-word characters and take first word
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
    """Generate answer using LLM based on context and query.
    
    Args:
        llm: Loaded LLM instance
        context: Context information for the query
        user_query: User's question or query
        max_chars: Maximum character limit for response
        temperature: LLM temperature for randomness
        
    Returns:
        Generated response text
    """
    prompt = _prompts["reply"].format(
        context=context,
        query=user_query,
        max_chars=max_chars
    )
    
    try:
        output = llm(prompt, max_tokens=150, temperature=temperature)
        raw_text = output.get("choices", [{}])[0].get("text", "")
        raw_text = raw_text.strip()
        
        # Remove common prefixes
        for prefix in ("A: ", "A:", "Q: ", "Q:"):
            if raw_text.startswith(prefix):
                raw_text = raw_text[len(prefix):]
                break
        
        logger.info(f"[LLM] RAW_REPLY_OUTPUT: {raw_text}")
        return raw_text.strip()
    except Exception as e:
        logger.error(f"[generator] get_answer failed: {e}")
        return ""