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

MAX_POST_CHARS = 300

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(rank_status.lower(), "")

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw()
    logger.info(f"[digest] PARSED_TRENDS_COUNT: {len(trends)}")
    logger.info(f"[digest] PARSED_TRENDS_FULL_DATA: {json.dumps(trends, indent=2, ensure_ascii=False)}")
    if not trends:
        logger.warning("[digest] No trends fetched")
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    stats_emoji = config.TREND_STATS_EMOJI

    posted = False
    try:
        if task_type == "digest_mini":
            header = "TOP CRYPTO TRENDS:"
            lines = []
            current_len = len(header) + len(sig) + 2
            for item in trends[:6]:
                kw, sc, st = item.get("keyword", "?"), int(item.get("score", 0)), item.get("rank_status", "same")
                e = _get_trend_emoji(st)
                line = f"{e} {kw} {stats_emoji}  {sc}"
                if current_len + len(line) + (1 if lines else 0) > MAX_POST_CHARS: break
                lines.append(line)
                current_len += len(line) + 1
            if not lines: return False
            joined_lines = "\n".join(lines)
            final_post = f"{header}\n\n{joined_lines}\n\n{sig}"
            if len(final_post) > MAX_POST_CHARS: 
                logger.warning(f"[digest] SKIPPED: MINI OVERFLOW ({len(final_post)} > {MAX_POST_CHARS})")
                return False
            if config.RAW_DEBUG: logger.info(f"=== RAW-MINI-POST ===\n{final_post}\n=== END ===")
            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            if resp.get("uri"):
                now_utc = datetime.now(timezone.utc).isoformat()
                utils.update_github_secret("LAST_MINI_DIGEST", now_utc)
                utils.update_github_secret("ACTIVE_DIGEST_URI", resp["uri"])
                posted = True
        elif task_type == "digest_full":
            item = trends[0]
            kw, sc, st, summary = item.get("keyword", "?"), int(item.get("score", 0)), item.get("rank_status", "same"), item.get("summary", "")
            logger.info(f"[digest] DIGEST_KEYWORD: {kw}")
            logger.info(f"[digest] DIGEST_SUMMARY: {summary}")
            e = _get_trend_emoji(st)
            header = "TOP CRYPTO TREND:"
            title = f"{e + ' ' if e else ''}{kw} {stats_emoji}  {sc}: "
            max_desc = MAX_POST_CHARS - len(header) - len(sig) - len(title) - 4
            if max_desc < 20: return False
            desc = generator.generate_digest(llm, kw, summary, max_desc)
            if len(desc) > max_desc:
                logger.warning(f"[digest] SKIPPED: DESC OVERFLOW ({len(desc)} > {max_desc})")
                return False
            final_post = f"{header}\n\n{title}{desc}\n\n{sig}"
            if len(final_post) > MAX_POST_CHARS:
                logger.warning(f"[digest] SKIPPED: FINAL OVERFLOW ({len(final_post)} > {MAX_POST_CHARS})")
                return False
            if config.RAW_DEBUG: logger.info(f"=== RAW-FULL-POST ===\n{final_post}\n=== END ===")
            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            if resp.get("uri"):
                now_utc = datetime.now(timezone.utc).isoformat()
                utils.update_github_secret("LAST_FULL_DIGEST", now_utc)
                utils.update_github_secret("ACTIVE_DIGEST_URI", resp["uri"])
                posted = True
    except Exception as e:
        logger.error(f"[digest] Post failed: {e}")
    return posted