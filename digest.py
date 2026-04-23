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
    if not isinstance(item, dict):
        return False
    keyword = item.get("keyword", "")
    summary = item.get("summary", "")
    if not isinstance(keyword, str) or not isinstance(summary, str):
        return False
    if re.search(r'[<>"\'`;{}\\]', keyword) or re.search(r'[<>"\'`;{}\\]', summary):
        return False
    return True

async def _update_gh_secret(key: str, value: str, pat: str, repo: str):
    if not value or not repo or not pat:
        return
    proc = await asyncio.create_subprocess_exec(
        "gh", "secret", "set", key, "--body", value, "--repo", repo,
        env={**os.environ, "GH_TOKEN": pat},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

def _get_trend_emoji(rank_status: str) -> str:
    safe_status = re.sub(r'[^a-zA-Z]', '', str(rank_status).lower())
    return config.TREND_EMOJIS.get(safe_status, "")

def _build_mini_content(trends, max_content_chars):
    lines = []
    ctx_entries = []
    current_len = 0
    for item in trends[:6]:
        kw = re.sub(r'[^\w\s\-\.\']', '', item.get("keyword", "?"))
        sc = int(item.get("score", 0))
        st = item.get("rank_status", "same")
        e = _get_trend_emoji(st)
        line = f"{e} {kw} {config.TREND_STATS_EMOJI}  {sc}"
        line_len = len(line) + (1 if lines else 0)
        if current_len + line_len > max_content_chars:
            break
        lines.append(line)
        ctx_entries.append({
            "id": re.sub(r'[^\w\-]', '', str(item.get("id", ""))),
            "keyword": kw,
            "summary": re.sub(r'[<>"\'`;{}\\]', '', item.get("summary", "")),
            "score": sc,
            "rank_status": st
        })
        current_len += line_len
    return "\n".join(lines), ctx_entries

def _build_full_content(trends, max_content_chars):
    item = trends[0]
    kw = re.sub(r'[^\w\s\-\.\']', '', item.get("keyword", "?"))
    sc = int(item.get("score", 0))
    st = item.get("rank_status", "same")
    summary = re.sub(r'[<>"\'`;{}\\]', '', item.get("summary", ""))
    e = _get_trend_emoji(st)
    prefix = f"{e} " if e else ""
    title = f"{prefix}{kw} {config.TREND_STATS_EMOJI}  {sc}: "
    return kw, summary, title, max_content_chars - len(title), {
        "id": re.sub(r'[^\w\-]', '', str(item.get("id", ""))),
        "keyword": kw,
        "summary": summary,
        "score": sc,
        "rank_status": st
    }

async def run(client, llm, task_type="digest_mini"):
    trends = await search.get_trending_topics_raw(client)
    if not trends:
        return False
    trends = [t for t in trends if _validate_trend_item(t)]
    if not trends:
        return False

    sig = f"Qwen | Chainbase TOPS {config.SIGNATURE_ICONS}"
    header = "TOP CRYPTO TRENDS:" if task_type == "digest_mini" else "TOP CRYPTO TREND:"
    
    if task_type not in ("digest_mini", "digest_full"):
        logger.warning(f"[DIGEST] Unknown task_type: {task_type}")
        return False

    pat = os.environ.get("PAT", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    posted = False
    uri = None
    ctx_entries = []

    for attempt in range(MAX_ATTEMPTS):
        retry_feedback = ""
        if attempt > 0:
            retry_feedback = f"\nWARNING: Previous attempt exceeded 300 characters. Strictly regenerate under limit."
        
        try:
            if task_type == "digest_mini":
                max_content = MAX_POST_CHARS - len(header) - len(sig) - 4
                content, ctx_entries = _build_mini_content(trends, max_content)
                prompt_data = {
                    "digest_data": "\n".join([f"- {e['keyword']}: {e['summary']}" for e in ctx_entries]),
                    "max_chars": MAX_POST_CHARS,
                    "max_content": max_content,
                    "header": header,
                    "signature": sig,
                    "retry_feedback": retry_feedback
                }
                prompt = generator.DIGEST_GENERATE.format(**prompt_data)
                response = llm(prompt, max_tokens=150, temperature=0.7)
                final_post = response["choices"][0]["text"].strip()
                
            elif task_type == "digest_full":
                kw, summary, title, max_desc, single_entry = _build_full_content(trends, 100)
                max_content = MAX_POST_CHARS - len(header) - len(sig) - 4
                prompt_data = {
                    "digest_data": f"{kw}: {summary}",
                    "max_chars": MAX_POST_CHARS,
                    "max_content": max_content,
                    "header": header,
                    "signature": sig,
                    "retry_feedback": retry_feedback
                }
                prompt = generator.DIGEST_GENERATE.format(**prompt_data)
                response = llm(prompt, max_tokens=150, temperature=0.3)
                final_post = response["choices"][0]["text"].strip()
                ctx_entries = [single_entry]

            if len(final_post) <= MAX_POST_CHARS:
                resp = await bsky.post_root(client, config.BOT_DID, final_post)
                uri = resp.get("uri")
                if config.RAW_DEBUG:
                    logger.info(f"=== RAW-{'MINI' if task_type == 'digest_mini' else 'FULL'}-POST ===\n{final_post}\n=== END ===")
                logger.info(f"[DIGEST] Attempt {attempt+1}: {len(final_post)} chars. Success.")
                posted = True
                break
            else:
                logger.warning(f"[DIGEST] Attempt {attempt+1}: {len(final_post)} chars. Exceeded limit.")
                
        except Exception as e:
            logger.error(f"[DIGEST] Attempt {attempt+1} failed: {e}")

    if posted and uri:
        now_utc = datetime.now(timezone.utc).isoformat()
        secret_key = "LAST_MINI_DIGEST" if task_type == "digest_mini" else "LAST_FULL_DIGEST"
        await asyncio.gather(
            _update_gh_secret(secret_key, now_utc, pat, repo),
            _update_gh_secret("ACTIVE_DIGEST_URI", uri, pat, repo),
            _update_gh_secret("CONTEXT_DIGEST", json.dumps(ctx_entries, ensure_ascii=False), pat, repo),
            return_exceptions=True
        )
        logger.info(f"[DIGEST] Posted successfully. URI: {uri[:40]}...")

    return posted
