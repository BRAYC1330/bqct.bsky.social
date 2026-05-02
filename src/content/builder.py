import config
import utils
import generator
import logging
logger = logging.getLogger(__name__)

SIG_DIGEST = "\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\n\nQwen | Tavily"
SIG_CHAINBASE = "\n\nQwen | Chainbase"
SIG_DEFAULT = "\n\nQwen"

def _get_sig_block(source: str, has_search: bool) -> str:
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT

def _truncate(text: str, limit: int) -> str:
    if utils.count_graphemes(text) <= limit: return text
    cut = text[:limit]
    dot = cut.rfind(".")
    return cut[:dot+1] if dot != -1 else cut.rstrip(" \t") + "."

async def build_reply(llm, ctx: str, query: str, search_data: str = "", source: str = "", max_total: int = 300) -> str:
    sig_block = _get_sig_block(source, bool(search_data))
    limit = max_total - len(sig_block)
    full_ctx = f"[SEARCH]\n{search_data}\n{ctx}" if search_data else ctx
    reply = generator.get_answer(llm, full_ctx, query, max_chars=limit, temperature=0.5)
    return _truncate(reply, limit) + sig_block

async def build_digest(llm, trends, task_type: str, max_total: int = 300) -> str | None:
    if not trends: return None
    sig_block = SIG_DIGEST
    limit = max_total - len(sig_block)
    emojis = config.TREND_EMOJIS

    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:\n\n"
        lines = []
        for item in trends[:6]:
            kw, sc, st = item.get("keyword", "?"), item.get("score"), item.get("rank_status", "same")
            e = emojis.get(st.lower(), "")
            lines.append(f"{e} {kw} 📊 {sc}")
            if len("\n".join(lines)) + len(header) > limit:
                lines.pop(); break
        if not lines: return None
        body = header + "\n".join(lines)
    else:
        item = trends[0]
        kw, sc, st, summary = item.get("keyword", "?"), item.get("score"), item.get("rank_status", "same"), item.get("summary", "")
        e = emojis.get(st.lower(), "")
        title = f"{e + ' ' if e else ''}{kw} 📊 {sc}:"
        header = "TOP CRYPTO TREND:\n\n"
        desc_limit = limit - len(header) - len(title) - 1
        if desc_limit < 20: return None
        prompt = f"Write exactly two sentences for '{kw}'. Structure: Core fact. Impact or metric. Max 19 words total. Start directly. Context: {summary}"
        desc = generator.get_answer(llm, "", prompt, max_chars=desc_limit, temperature=0.5)
        body = f"{header}{title} {desc}"
    final = body + sig_block
    return final if utils.count_graphemes(final) <= max_total else None