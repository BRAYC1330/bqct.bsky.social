import os
import logging
import json
from datetime import datetime, timezone
import config
import search
import generator
import bsky
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

MAX_POST_TOKENS = 180

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(rank_status.lower(), "")

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw()
    logger.info(f"[digest] PARSED_TRENDS_COUNT: {len(trends)}")
    if not trends:
        logger.warning("[digest] No trends fetched")
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    stats_emoji = config.TREND_STATS_EMOJI
    sig_tokens = utils.count_tokens(sig, llm)

    posted = False
    try:
        if task_type == "digest_mini":
            header = "TOP CRYPTO TRENDS:"
            lines = []
            header_tokens = utils.count_tokens(header, llm)
            for item in trends[:6]:
                kw, sc, st = item.get("keyword", "?"), int(item.get("score", 0)), item.get("rank_status", "same")
                e = _get_trend_emoji(st)
                line = f"{e} {kw} {stats_emoji}  {sc}"
                line_toks = utils.count_tokens(line, llm) + 1
                if utils.count_tokens("\n".join(lines), llm) + header_tokens + sig_tokens + line_toks > MAX_POST_TOKENS:
                    break
                lines.append(line)
            if not lines:
                return False
            joined_lines = "\n".join(lines)
            final_post = f"{header}\n\n{joined_lines}\n\n{sig}"
            if utils.count_tokens(final_post, llm) > MAX_POST_TOKENS:
                logger.warning(f"[digest] SKIPPED: MINI OVERFLOW")
                return False
            if config.RAW_DEBUG:
                logger.info(f"=== RAW-MINI-POST ===\n{final_post}\n=== END ===")
            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            if resp.get("uri"):
                now_utc = datetime.now(timezone.utc).isoformat()
                utils.update_github_secret("LAST_MINI_DIGEST", now_utc)
                utils.update_github_secret("ACTIVE_DIGEST_URI", resp["uri"])
                posted = True
        elif task_type == "digest_full":
            item = trends[0]
            kw, sc, st, summary = item.get("keyword", "?"), int(item.get("score", 0)), item.get("rank_status", "same"), item.get("summary", "")
            e = _get_trend_emoji(st)
            header = "TOP CRYPTO TREND:"
            title = f"{e + ' ' if e else ''}{kw} {stats_emoji}  {sc}: "
            header_toks = utils.count_tokens(header, llm)
            title_toks = utils.count_tokens(title, llm)
            sig_toks = utils.count_tokens(sig, llm)
            max_desc_tokens = MAX_POST_TOKENS - header_toks - title_toks - sig_toks - 4
            if max_desc_tokens < 10:
                return False
            desc = generator.generate_digest(llm, kw, summary, max_desc_tokens)
            final_post = f"{header}\n\n{title}{desc}\n\n{sig}"
            if utils.count_tokens(final_post, llm) > MAX_POST_TOKENS:
                logger.warning(f"[digest] SKIPPED: FINAL OVERFLOW")
                return False
            if config.RAW_DEBUG:
                logger.info(f"=== RAW-FULL-POST ===\n{final_post}\n=== END ===")
            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            if resp.get("uri"):
                now_utc = datetime.now(timezone.utc).isoformat()
                utils.update_github_secret("LAST_FULL_DIGEST", now_utc)
                utils.update_github_secret("ACTIVE_DIGEST_URI", resp["uri"])
                posted = True
    except Exception as e:
        logger.error(f"[digest] Post failed: {e}")
    return posted