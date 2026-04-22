import os
import logging
import subprocess
import json
from datetime import datetime, timezone
import config
import search
import generator
import bsky
import timers
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def _update_gh_secret(key, value):
    if not value:
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("PAT", "")
    if not repo or not pat:
        return
    cmd = ["gh", "secret", "set", key, "--body", value, "--repo", repo]
    try:
        subprocess.run(cmd, env={**os.environ, "GH_TOKEN": pat}, check=True, capture_output=True)
    except Exception as e:
        logger.error(f"[NEWS] Secret update failed: {e}")

def _write_output(key, value):
    path = os.getenv("GITHUB_OUTPUT")
    if path and value:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")

async def run(client, llm):
    now_utc = datetime.now(timezone.utc).isoformat()
    is_mini = timers.check_mini_timer()
    is_full = timers.check_full_timer()

    if not (is_mini or is_full):
        return False

    digest_type = "full" if is_full else "mini"
    timer_key = "LAST_FULL_DIGEST" if is_full else "LAST_MINI_DIGEST"

    _update_gh_secret(timer_key, now_utc)
    _write_output(timer_key, now_utc)

    trends = await search.get_trending_topics_raw()
    if not trends:
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    stats_emoji = config.TREND_STATS_EMOJI
    header = "TOP CRYPTO TREND:"
    overhead = len(header) + 4 + len(sig)
    available = max(50, 300 - overhead)
    budget_per_trend = max(40, int(available / 6))

    lines = []
    ctx_parts = []

    for item in trends[:6]:
        kw = item.get("keyword", "Unknown")
        sc = int(item.get("score", 0))
        st = item.get("rank_status", "same")
        e = config.TREND_EMOJIS.get(st.lower(), "")
        meta = f"{e} {kw} {stats_emoji} {sc}: "
        desc_budget = max(20, budget_per_trend - len(meta))

        desc = generator.generate_digest(llm, kw, item.get("summary", ""), desc_budget)

        safe_limit = desc_budget - 8
        if len(desc) > safe_limit:
            truncated = desc[:safe_limit]
            last_space = truncated.rfind(" ")
            desc = truncated[:last_space] + "." if last_space > 0 else truncated + "."

        line = f"{meta}{desc}"
        if len(line) > budget_per_trend:
            line = line[:budget_per_trend - 1] + "…"
        lines.append(line)
        ctx_parts.append(f"{kw}: {desc}")

    body = "\n".join(lines)
    final_post = f"{header}\n\n{body}\n\n{sig}"

    while len(final_post) > 300 and lines:
        lines.pop()
        body = "\n".join(lines)
        final_post = f"{header}\n\n{body}\n\n{sig}"

    if config.RAW_DEBUG:
        sep = "\n---\n"
        ctx_block = sep.join(ctx_parts)
        logger.info(f"=== RAW-DIGEST-POST-TEXT ===\n{final_post}\n=== END ===")
        logger.info(f"=== RAW-DIGEST-CONTEXT ===\n{ctx_block}\nGenerated: {now_utc}\n=== END ===")

    try:
        resp = await bsky.post_root(client, config.BOT_DID, final_post)
        uri = resp.get("uri")
        if uri:
            old_active = os.environ.get("ACTIVE_DIGEST_URI", "")
            if old_active and old_active not in ("{}", "null", ""):
                _update_gh_secret("PREV_DIGEST_URI", old_active)
            _update_gh_secret("ACTIVE_DIGEST_URI", uri)
            _update_gh_secret("LAST_DIGEST_URI", uri)
            _write_output("ACTIVE_DIGEST_URI", uri)
            _write_output("LAST_DIGEST_URI", uri)

            sep = "\n---\n"
            ctx_block = sep.join(ctx_parts)
            digest_ctx = f"DIGEST CONTEXT:\n{ctx_block}\nGenerated: {now_utc}"
            _update_gh_secret("CONTEXT_DIGEST", digest_ctx)
            return True
    except Exception as e:
        logger.error(f"[NEWS] Post failed: {e}")
    return False
