import os
import logging
import asyncio
import json
import re
from datetime import datetime, timezone
import config
import search
import generator
import bsky
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

MAX_POST_CHARS = 300
MAX_ATTEMPTS = 3

def _validate_trend_item(item: dict) -> bool:
    return isinstance(item, dict) and isinstance(item.get("keyword"), str) and isinstance(item.get("summary"), str) and not re.search(r'[<>"\'`;{}\\]', item["keyword"]) and not re.search(r'[<>"\'`;{}\\]', item["summary"])

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(re.sub(r'[^a-zA-Z]', '', str(rank_status).lower()), "")

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw(client)
    trends = [t for t in trends if _validate_trend_item(t)]
    if not trends:
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    header = "TOP CRYPTO TRENDS:" if task_type == "digest_mini" else "TOP CRYPTO TREND:"
    if task_type not in ("digest_mini", "digest_full"):
        return False

    pat = os.environ.get("PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    posted = False
    uri = None
    ctx_entries = []

    for attempt in range(MAX_ATTEMPTS):
        retry_feedback = f"\nWARNING: Previous attempt exceeded {MAX_POST_CHARS} characters. Strictly regenerate shorter." if attempt > 0 else ""
        try:
            if task_type == "digest_mini":
                max_content = MAX_POST_CHARS - len(header) - len(sig) - 4
                lines = []
                ctx_entries = []
                cur_len = 0
                for item in trends[:6]:
                    kw = re.sub(r'[^\w\s\-\.\']', '', item["keyword"])
                    sc = int(item["score"])
                    e = _get_trend_emoji(item["rank_status"])
                    line = f"{e} {kw} {config.TREND_STATS_EMOJI}  {sc}"
                    add_len = len(line) + (1 if lines else 0)
                    if cur_len + add_len > max_content:
                        break
                    lines.append(line)
                    ctx_entries.append({"id": re.sub(r'[^\w\-]', '', str(item["id"])), "keyword": kw, "summary": re.sub(r'[<>"\'`;{}\\]', '', item["summary"]), "score": sc, "rank_status": item["rank_status"]})
                    cur_len += add_len
                if not lines:
                    return False
                digest_data = "\n".join([f"- {e['keyword']}: {e['summary']}" for e in ctx_entries])
            else:
                item = trends[0]
                kw = re.sub(r'[^\w\s\-\.\']', '', item["keyword"])
                sc = int(item["score"])
                e = _get_trend_emoji(item["rank_status"])
                prefix = f"{e} " if e else ""
                title = f"{prefix}{kw} {config.TREND_STATS_EMOJI}  {sc}: "
                max_content = MAX_POST_CHARS - len(header) - len(sig) - 4
                clean_summary = re.sub(r'[<>"\'`;{}\\]', '', item['summary'])
                digest_data = f"{kw}: {clean_summary}"
                ctx_entries = [{"id": re.sub(r'[^\w\-]', '', str(item["id"])), "keyword": kw, "summary": item["summary"], "score": sc, "rank_status": item["rank_status"]}]

            prompt = generator.digest_generate.format(digest_data=digest_data, max_chars=MAX_POST_CHARS, max_content=max_content, header=header, signature=sig, retry_feedback=retry_feedback)
            response = llm(prompt, max_tokens=150, temperature=0.7 if task_type == "digest_mini" else 0.3)
            final_post = response["choices"][0]["text"].strip()

            if len(final_post) <= MAX_POST_CHARS:
                resp = await bsky.post_root(client, config.BOT_DID, final_post)
                uri = resp.get("uri")
                if config.RAW_DEBUG:
                    logger.info(f"=== RAW-{'MINI' if task_type == 'digest_mini' else 'FULL'}-POST ===\n{final_post}\n=== END ===")
                logger.info(f"[DIGEST] Attempt {attempt+1}: {len(final_post)} chars. Success.")
                posted = True
                break
            else:
                logger.warning(f"[DIGEST] Attempt {attempt+1}: {len(final_post)} chars. Exceeded.")
        except Exception as e:
            logger.error(f"[DIGEST] Attempt {attempt+1} failed: {e}")

    if posted and uri:
        now_utc = datetime.now(timezone.utc).isoformat()
        await asyncio.gather(
            utils.update_github_secret("LAST_MINI_DIGEST" if task_type == "digest_mini" else "LAST_FULL_DIGEST", now_utc, pat, repo),
            utils.update_github_secret("ACTIVE_DIGEST_URI", uri, pat, repo),
            utils.update_github_secret("CONTEXT_DIGEST", json.dumps(ctx_entries, ensure_ascii=False), pat, repo),
            return_exceptions=True
        )
    return posted