import os
import logging
import subprocess
import json
from datetime import datetime, timezone
import config
import search
import generator
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def _update_gh_secret(key, value):
    if not value: return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat: return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e:
        logger.error(f"[DIGEST] Secret update failed: {e}")

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw()
    if not trends:
        return False
    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    stats_emoji = config.TREND_STATS_EMOJI
    header = "TOP CRYPTO TREND:"
    lines = []
    ctx_entries = []
    for item in trends[:6]:
        kw = item.get("keyword", "Unknown")
        sc = int(item.get("score", 0))
        st = item.get("rank_status", "same")
        is_new = item.get("is_new", False)
        item_id = item.get("id", "")
        summary = item.get("summary", "")
        e = config.TREND_EMOJIS.get(st.lower(), "")
        lines.append(f"{e} {kw} {stats_emoji} {sc}")
        ctx_entries.append({"id": item_id, "keyword": kw, "summary": summary, "score": sc, "rank_status": st, "is_new": is_new})
    body = "\n".join(lines)
    final_post = f"{header}\n\n{body}\n\n{sig}"
    digest_ctx_json = json.dumps(ctx_entries, ensure_ascii=False, indent=2)
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-DIGEST-POST-TEXT ===\n{final_post}\n=== END ===")
        logger.info(f"=== RAW-DIGEST-CONTEXT-JSON ===\n{digest_ctx_json}\n=== END ===")
    try:
        resp = await bsky.post_root(client, config.BOT_DID, final_post)
        uri = resp.get("uri")
        if uri:
            _update_gh_secret("ACTIVE_DIGEST_URI", uri)
            _update_gh_secret("CONTEXT_DIGEST", digest_ctx_json)
            return True
    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")
    return False
