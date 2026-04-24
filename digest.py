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
BUFFER_CHARS = 10

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(rank_status.lower(), "")

def _cut_at_sentence(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_end = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_end > max_len * 0.6:
        return truncated[:last_end + 1].strip()
    return truncated.rsplit(' ', 1)[0].strip() + "..."

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw()
    if not trends:
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    stats_emoji = config.TREND_STATS_EMOJI

    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:"
    elif task_type == "digest_full":
        header = "TOP CRYPTO TREND:"
    else:
        logger.warning(f"[DIGEST] Unknown task_type: {task_type}")
        return False

    posted = False

    try:
        if task_type == "digest_mini":
            lines = []
            current_len = len(header) + len(sig) + 2
            for item in trends[:6]:
                kw = item.get("keyword", "?")
                sc = int(item.get("score", 0))
                st = item.get("rank_status", "same")
                e = _get_trend_emoji(st)
                line = f"{e} {kw} {stats_emoji}  {sc}"
                line_len = len(line) + (1 if lines else 0)
                if current_len + line_len > MAX_POST_CHARS:
                    break
                lines.append(line)
                current_len += line_len

            if not lines:
                return False

            body = "\n".join(lines)
            final_post = f"{header}\n\n{body}\n\n{sig}"

            if len(final_post) > MAX_POST_CHARS:
                return False

            if config.RAW_DEBUG:
                logger.info(f"=== RAW-MINI-POST ===\n{final_post}\n=== END ===")

            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            uri = resp.get("uri")
            if uri:
                utils.update_github_secret("LAST_MINI_DIGEST", datetime.now(timezone.utc).isoformat())
                utils.update_github_secret("ACTIVE_DIGEST_URI", uri)
                posted = True

        elif task_type == "digest_full":
            item = trends[0]
            kw = item.get("keyword", "?")
            sc = int(item.get("score", 0))
            st = item.get("rank_status", "same")
            summary = item.get("summary", "")
            e = _get_trend_emoji(st)
            prefix = f"{e} " if e else ""
            title = f"{prefix}{kw} {stats_emoji}  {sc}: "

            separators = 4
            max_desc = MAX_POST_CHARS - len(header) - len(sig) - len(title) - separators - BUFFER_CHARS
            if max_desc < 20:
                return False

            desc = generator.generate_digest(llm, kw, summary, max_desc)
            if len(desc) > max_desc:
                desc = _cut_at_sentence(desc, max_desc)
            
            final_post = f"{header}\n\n{title}{desc}\n\n{sig}"
            
            if len(final_post) > MAX_POST_CHARS:
                final_post = final_post[:MAX_POST_CHARS].rsplit(' ', 1)[0] + "...\n\n" + sig

            if config.RAW_DEBUG:
                logger.info(f"=== RAW-FULL-POST ===\n{final_post}\n=== END ===")

            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            uri = resp.get("uri")
            if uri:
                utils.update_github_secret("LAST_FULL_DIGEST", datetime.now(timezone.utc).isoformat())
                utils.update_github_secret("ACTIVE_DIGEST_URI", uri)
                posted = True

    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")

    return posted