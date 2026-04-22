import os
import sys
import pathlib
import yaml

PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _p = yaml.safe_load(f)

SYSTEM_PROMPT = _p["system"]
SUMMARIZE_SYSTEM = _p["summarize"]
QUERY_REFINE_SYSTEM = _p["query_refine"]
DIGEST_REFINE_SYSTEM = _p["digest_refine"]
COMMUNITY_SYSTEM = _p["community"]

def _require(var_name: str):
    val = os.getenv(var_name)
    if not val or val.strip().lower() in ("", "{}", "null", "none"):
        print(f"ERROR: Required env var {var_name} is not set", file=sys.stderr)
        sys.exit(1)
    return val

MODEL_PATH = os.getenv("MODEL_PATH", "models/qwen2.5-coder-14b-instruct-q5_k_m.gguf")
MODEL_N_CTX = int(os.getenv("MODEL_N_CTX", "14000"))
MODEL_N_THREADS = int(os.getenv("MODEL_N_THREADS", "4"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
RESPONSE_MAX_CHARS = int(os.getenv("RESPONSE_MAX_CHARS", "300"))
CONTEXT_SLOT_COUNT = int(os.getenv("CONTEXT_SLOT_COUNT", "10"))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "30"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
CONNECT_TIMEOUT = int(os.getenv("CONNECT_TIMEOUT", "10"))
TOKEN_TO_CHAR_RATIO = float(os.getenv("TOKEN_TO_CHAR_RATIO", "0.6"))
RAW_DEBUG = os.getenv("RAW_DEBUG", "true").lower() == "true"

BOT_DID = _require("BOT_DID")
BOT_HANDLE = _require("BOT_HANDLE")
BOT_PASSWORD = _require("BOT_PASSWORD")
OWNER_DID = _require("OWNER_DID")
PAT = _require("PAT")
GITHUB_REPOSITORY = _require("GITHUB_REPOSITORY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
COMMUNITY_MAX_COMMENTS = int(os.getenv("COMMUNITY_MAX_COMMENTS", "50"))
COMMUNITY_MAX_REPLY_CHARS = int(os.getenv("COMMUNITY_MAX_REPLY_CHARS", "300"))
COMMUNITY_MAX_LIKES = int(os.getenv("COMMUNITY_MAX_LIKES", "30"))
COMMUNITY_MAX_REPLIES = int(os.getenv("COMMUNITY_MAX_REPLIES", "10"))
LINK_CACHE_TTL = int(os.getenv("LINK_CACHE_TTL", "300"))
ALLOWED_LINK_DOMAINS = set(os.getenv("ALLOWED_LINK_DOMAINS", "bsky.app,atproto.com,chainbase.com,tavily.com").split(","))
MAX_LINK_CONTENT_SIZE = int(os.getenv("MAX_LINK_CONTENT_SIZE", "400"))
NOTIF_LIMIT = int(os.getenv("NOTIF_LIMIT", "100"))
TREND_EMOJIS = {"new": "🆕", "up": "↗️", "down": "↙️", "same": "➡️"}
TREND_STATS_EMOJI = "📊"
SIGNATURE_ICONS = "💜💛"
SEARCH_PARAM_KEYS = ["query", "time_range", "topic"]
