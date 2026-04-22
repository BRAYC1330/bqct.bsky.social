import os
import logging
import subprocess
import json
from datetime import datetime, timezone
import config
import search
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def post_if_due(client, llm, digest_type="mini"):
    trends = await search.get_trending_topics_raw()
    if not trends:
        return None

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    now_utc = datetime.now(timezone.utc).isoformat()
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

        desc = await generator.generate_digest(llm, kw, item.get("summary", ""), desc_budget)

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
        logger.info(f"=== RAW-DIGEST-POST-TEXT ===\n{final_post}\n=== END ===")
        logger.info(f"=== RAW-DIGEST-CONTEXT ===\n{'\n---\n'.join(ctx_parts)}\nGenerated: {now_utc}\n=== END ===")

    try:
        resp = await bsky.post_root(client, config.BOT_DID, final_post)
        uri = resp.get("uri")
        if uri:
            digest_ctx = f"DIGEST CONTEXT:\n{'\n---\n'.join(ctx_parts)}\nGenerated: {now_utc}"
            cmd = ["gh", "secret", "set", "CONTEXT_DIGEST", "--body", digest_ctx, "--repo", os.environ["GITHUB_REPOSITORY"]]
            subprocess.run(cmd, env={**os.environ, "GH_TOKEN": os.environ["PAT"]}, check=True)
            return {"uri": uri, "time": now_utc, "type": digest_type}
    except Exception as e:
        logger.error(f"[NEWS] Post failed: {e}")
    return None
