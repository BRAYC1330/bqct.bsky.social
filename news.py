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

async def post_if_due(client, llm):
    trends = await search.get_trending_topics_raw()
    if not trends:
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    now_utc = datetime.now(timezone.utc).isoformat()
    stats = config.TREND_STATS_EMOJI
    ctx_parts = []
    post_lines = []
    header = "TOP CRYPTO TREND:"

    for item in trends[:6]:
        kw = item.get("keyword", "?")
        sc = int(item.get("score", 0))
        st = item.get("rank_status", "")
        e = config.TREND_EMOJIS.get(st.lower(), "")
        line = f"{e} {kw} {stats} {sc}"
        post_lines.append(line)
        ctx_parts.append(f"{kw}: score={sc}, trend={st}, summary={item.get('summary', '')[:150]}")

    post_text = f"{header}\n\n" + "\n".join(post_lines) + f"\n\n{sig}"

    if config.RAW_DEBUG:
        logger.info(f"=== RAW-DIGEST-INPUT ===\n{json.dumps(trends[:6], ensure_ascii=False, indent=2)}\n=== END ===")
        logger.info(f"=== RAW-DIGEST-POST-TEXT ===\n{post_text}\n=== END ===")

    digest_ctx = "DIGEST CONTEXT:\n" + "\n---\n".join(ctx_parts) + f"\nGenerated: {now_utc}"
    if config.RAW_DEBUG:
        logger.info(f"=== RAW-DIGEST-CONTEXT ===\n{digest_ctx}\n=== END ===")

    try:
        resp = await bsky.post_root(client, config.BOT_DID, post_text)
        uri = resp.get("uri")
        if uri:
            cmd = ["gh", "secret", "set", "CONTEXT_DIGEST", "--body", digest_ctx, "--repo", os.environ["GITHUB_REPOSITORY"]]
            subprocess.run(cmd, env={**os.environ, "GH_TOKEN": os.environ["PAT"]}, check=True)
            updates = {"LAST_DIGEST_TIME": now_utc, "ACTIVE_DIGEST_URI": uri, "LAST_DIGEST_URI": uri}
            github_output = os.getenv("GITHUB_OUTPUT", "")
            if github_output:
                with open(github_output, "a") as f:
                    for k, v in updates.items():
                        f.write(f"{k}={v}\n")
            return True
    except Exception as e:
        logger.error(f"[NEWS] Post failed: {e}")
    return False
