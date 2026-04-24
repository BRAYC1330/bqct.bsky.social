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
import utils
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

MAX_POST_CHARS = 300
MAX_ATTEMPTS = 3
SAFETY_MARGIN = 10

def _validate_trend_item(item: dict) -> bool:
    return isinstance(item, dict) and isinstance(item.get("keyword"), str) and isinstance(item.get("summary"), str) and not re.search(r'[<>"\'`;{}\\]', item["keyword"]) and not re.search(r'[<>"\'`;{}\\]', item["summary"])

def _get_trend_emoji(rank_status: str) -> str:
    return config.TREND_EMOJIS.get(re.sub(r'[^a-zA-Z]', '', str(rank_status).lower()), "")

def _calculate_max_content(task_type: str, trends_count: int = 1) -> int:
    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    header = "TOP CRYPTO TRENDS:" if task_type == "digest_mini" else "TOP CRYPTO TREND:"
    static_overhead = len(sig) + len(header) + SAFETY_MARGIN
    if task_type == "digest_mini":
        static_overhead += 4 * trends_count + 2 * (trends_count - 1)
    else:
        static_overhead += 10
    return MAX_POST_CHARS - static_overhead

def _build_mini_digest_lines(trends: list, max_content: int) -> tuple[list, list]:
    lines, ctx_entries = [], []
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
        ctx_entries.append({
            "id": re.sub(r'[^\w\-]', '', str(item["id"])),
            "keyword": kw,
            "summary": re.sub(r'[<>"\'`;{}\\]', '', item["summary"]),
            "score": sc,
            "rank_status": item["rank_status"]
        })
        cur_len += add_len
    return lines, ctx_entries

def _build_full_digest_line(trend: dict) -> tuple[str, dict]:
    item = trend
    kw = re.sub(r'[^\w\s\-\.\']', '', item["keyword"])
    sc = int(item["score"])
    e = _get_trend_emoji(item["rank_status"])
    prefix = f"{e} " if e else ""
    ctx_entry = {
        "id": re.sub(r'[^\w\-]', '', str(item["id"])),
        "keyword": kw,
        "summary": item["summary"],
        "score": sc,
        "rank_status": item["rank_status"]
    }
    return f"{prefix}{kw} {config.TREND_STATS_EMOJI}  {sc}: ", ctx_entry

async def _generate_digest_post(llm, task_type: str, digest_data: str, header: str, sig: str, max_content: int, retry_count: int) -> str:
    retry_feedback = ""
    if retry_count > 0:
        retry_feedback = f"\nWARNING: Previous attempt was {retry_count * 15}+ chars over limit. Regenerate strictly under {max_content} chars for content section."
    
    prompt = generator.digest_generate.format(
        digest_data=digest_data,
        max_chars=MAX_POST_CHARS,
        max_content=max_content,
        header=header,
        signature=sig,
        retry_feedback=retry_feedback
    )
    response = llm(prompt, max_tokens=150, temperature=0.7 if task_type == "digest_mini" else 0.3)
    return response["choices"][0]["text"].strip()

def _validate_post_length(post: str, task_type: str) -> tuple[bool, str]:
    if len(post) <= MAX_POST_CHARS:
        return True, ""
    overflow = len(post) - MAX_POST_CHARS
    return False, f"overflow_{overflow}"

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
        try:
            if task_type == "digest_mini":
                max_content = _calculate_max_content(task_type, trends_count=6)
                lines, ctx_entries = _build_mini_digest_lines(trends, max_content)
                if not lines:
                    return False
                digest_data = "\n".join([f"- {e['keyword']}: {e['summary']}" for e in ctx_entries])
            else:
                max_content = _calculate_max_content(task_type, trends_count=1)
                title_prefix, ctx_entry = _build_full_digest_line(trends[0])
                ctx_entries = [ctx_entry]
                digest_data = f"{trends[0]['keyword']}: {re.sub(r'[<>"\'`;{}\\]', '', trends[0]['summary'])}"

            final_post = await _generate_digest_post(llm, task_type, digest_data, header, sig, max_content, attempt)
            
            is_valid, error_info = _validate_post_length(final_post, task_type)
            
            if is_valid:
                resp = await bsky.post_root(client, config.BOT_DID, final_post)
                uri = resp.get("uri")
                if config.RAW_DEBUG:
                    logger.info(f"=== RAW-{'MINI' if task_type == 'digest_mini' else 'FULL'}-POST ===\n{final_post}\n=== END ===")
                logger.info(f"[DIGEST] {task_type}: {len(final_post)}/{MAX_POST_CHARS} chars. Posted.")
                posted = True
                break
            else:
                logger.warning(f"[DIGEST] Attempt {attempt+1}: {len(final_post)} chars. {error_info}. Retrying...")
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"[DIGEST] Attempt {attempt+1} failed: {e}")
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(1)

    if posted and uri:
        now_utc = datetime.now(timezone.utc).isoformat()
        await asyncio.gather(
            utils.update_github_secret("LAST_MINI_DIGEST" if task_type == "digest_mini" else "LAST_FULL_DIGEST", now_utc, pat, repo),
            utils.update_github_secret("ACTIVE_DIGEST_URI", uri, pat, repo),
            utils.update_github_secret("CONTEXT_DIGEST", json.dumps(ctx_entries, ensure_ascii=False), pat, repo),
            return_exceptions=True
        )
        return True
    else:
        logger.warning(f"[DIGEST] {task_type}: Failed after {MAX_ATTEMPTS} attempts. Skipping.")
        return False