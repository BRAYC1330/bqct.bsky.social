import os
import logging
from llama_cpp import Llama
from src.state import settings as config

logger = logging.getLogger(__name__)

def load():
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[loader] Model not found: {model_path}")
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
        return llm
    except Exception as e:
        logger.error(f"[loader] Load failed: {e}")
        return None
