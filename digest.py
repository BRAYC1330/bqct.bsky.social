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

MAX_POST_CHARS = 300

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
        logger.error(f"[DIGEST] Secret update failed: {e}")

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(rank_status.lower(), "")

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
            ctx_entries = []
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
                ctx_entries.append({
                    "id": item.get("id", ""),
                    "keyword": kw,
                    "summary": item.get("summary", ""),
                    "score": sc,
                    "rank_status": st
                })
                current_len += line_len

            if not lines:
                return False

            body = "\n".join(lines)
            final_post = f"{header}\n{body}\n{sig}"

            if config.RAW_DEBUG:
                logger.info(f"=== RAW-MINI-POST ===\n{final_post}\n=== END ===")

            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            uri = resp.get("uri")
            if uri:
                now_utc = datetime.now(timezone.utc).isoformat()
                _update_gh_secret("LAST_MINI_DIGEST", now_utc)
                _update_gh_secret("ACTIVE_DIGEST_URI", uri)
                _update_gh_secret("CONTEXT_DIGEST", json.dumps(ctx_entries, ensure_ascii=False))
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

            max_desc = MAX_POST_CHARS - len(header) - len(sig) - len(title) - 2
            if max_desc < 20:
                logger.warning("[DIGEST] Not enough space for description")
                return False

            prompt = generator.DIGEST_REFINE_SYSTEM.format(keyword=kw, summary=summary, max_desc_chars=max_desc)
            response = llm(prompt, max_tokens=min(max_desc + 30, 150), temperature=0.3)
            desc = response["choices"][0]["text"].strip().split("\n")[0]
            
            if len(desc) > max_desc:
                words = desc.split()
                desc = ""
                for word in words:
                    if len(desc) + len(word) + 1 <= max_desc:
                        desc = (desc + " " + word).strip()
                    else:
                        break

            final_post = f"{header}\n{title}{desc}\n{sig}"

            if config.RAW_DEBUG:
                logger.info(f"=== RAW-FULL-POST ===\n{final_post}\n=== END ===")

            resp = await bsky.post_root(client, config.BOT_DID, final_post)
            uri = resp.get("uri")
            if uri:
                now_utc = datetime.now(timezone.utc).isoformat()
                _update_gh_secret("LAST_FULL_DIGEST", now_utc)
                _update_gh_secret("ACTIVE_DIGEST_URI", uri)
                _update_gh_secret("CONTEXT_DIGEST", json.dumps([{
                    "id": item.get("id", ""),
                    "keyword": kw,
                    "summary": summary,
                    "score": sc,
                    "rank_status": st
                }], ensure_ascii=False))
                posted = True

    except Exception as e:
        logger.error(f"[DIGEST] Post failed: {e}")

    return posted
