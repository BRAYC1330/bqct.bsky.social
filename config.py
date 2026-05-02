import os
import sys
from typing import Optional


class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


def _require(var_name: str) -> str:
    """Get required environment variable or raise ConfigError."""
    val = os.getenv(var_name)
    if not val or val.strip().lower() in ("", "{}", "null", "none"):
        raise ConfigError(f"Required environment variable {var_name} is not set")
    return val


def _env_int(name: str, default: int) -> int:
    """Get integer environment variable with default."""
    val = os.getenv(name, "")
    try:
        return int(val) if val.strip() else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Get float environment variable with default."""
    val = os.getenv(name, "")
    try:
        return float(val) if val.strip() else default
    except ValueError:
        return default

MODEL_PATH = os.getenv("MODEL_PATH", "models/qwen2.5-coder-14b-instruct-q5_k_m.gguf")
MODEL_N_CTX = _env_int("MODEL_N_CTX", 14000)
MODEL_N_THREADS = _env_int("MODEL_N_THREADS", 4)
MAX_TOKENS = _env_int("MAX_TOKENS", 250)
RESPONSE_MAX_CHARS = _env_int("RESPONSE_MAX_CHARS", 300)
SEARCH_TIMEOUT = _env_int("SEARCH_TIMEOUT", 30)
REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 60)
CONNECT_TIMEOUT = _env_int("CONNECT_TIMEOUT", 10)
TOKEN_TO_CHAR_RATIO = _env_float("TOKEN_TO_CHAR_RATIO", 0.6)
RAW_DEBUG = os.getenv("RAW_DEBUG", "true").lower() == "true"
DEBUG_OWNER = os.getenv("DEBUG_OWNER", "false").lower() == "true"
BOT_DID = _require("BOT_DID")
BOT_HANDLE = _require("BOT_HANDLE")
BOT_PASSWORD = _require("BOT_PASSWORD")
OWNER_DID = _require("OWNER_DID")
PAT = _require("PAT")
GITHUB_REPOSITORY = _require("GITHUB_REPOSITORY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
COMMUNITY_MAX_COMMENTS = _env_int("COMMUNITY_MAX_COMMENTS", 50)
COMMUNITY_MAX_REPLY_CHARS = _env_int("COMMUNITY_MAX_REPLY_CHARS", 300)
COMMUNITY_MAX_REPLIES = _env_int("COMMUNITY_MAX_REPLIES", 10)
LINK_CACHE_TTL = _env_int("LINK_CACHE_TTL", 300)
ALLOWED_LINK_DOMAINS = set(d.strip() for d in os.getenv("ALLOWED_LINK_DOMAINS", "bsky.app,atproto.com,chainbase.com,tavily.com").split(",") if d.strip())
MAX_LINK_CONTENT_SIZE = _env_int("MAX_LINK_CONTENT_SIZE", 600)
NOTIF_LIMIT = _env_int("NOTIF_LIMIT", 100)
TREND_EMOJIS = {"new": "🆕", "up": "↗️", "down": "↙️", "same": "➡️"}
TREND_STATS_EMOJI = "📊"
SIGNATURE_ICONS = "💜💛"
SEARCH_PARAM_KEYS = ["query", "time_range", "topic"]
DIGEST_MAX_TOKENS = _env_int("DIGEST_MAX_TOKENS", 80)
REPLY_MAX_TOKENS = _env_int("REPLY_MAX_TOKENS", 60)
TAVILY_MAX_TOKENS = _env_int("TAVILY_MAX_TOKENS", 40)
KEYWORD_MAX_TOKENS = _env_int("KEYWORD_MAX_TOKENS", 20)
ENGLISH_ONLY_SEARCH = os.getenv("ENGLISH_ONLY_SEARCH", "true").lower() == "true"
ENGLISH_ASCII_RATIO = _env_float("ENGLISH_ASCII_RATIO", 0.7)