import config
import utils
import generator
import logging
logger = logging.getLogger(__name__)
SIG_DIGEST = "\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\n\nQwen | Tavily"
SIG_CHAINBASE = "\n\nQwen | Chainbase"
SIG_DEFAULT = "\n\nQwen"
def _get_signature(source: str, has_search: bool) -> str:
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT
def get_no_data_response(keyword: str) -> str:
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}\n\nQwen"
async def build_reply(llm, thread_ctx: str, query: str, search_data: str = "", source: str = "", max_total: int = 300) -> str:
    sig = _get_signature(source, bool(search_data))
    max_body = max_total - len(sig)
    if search_data:
        ctx = f"[SEARCH]\n{search_data}\n{thread_ctx}"
    else:
        ctx = thread_ctx
    reply = generator.get_answer(llm, ctx, query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_reply(reply, max_body)
    return reply.strip() + sig
async def build_digest(llm, trends, task_type: str, max_total: int = 300) -> str | None:
    if not trends: return None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:\n\n"
        lines = []
        for item in trends[:6]:
            kw = item.get("keyword", "?")
            sc = item.get("score")
            st = item.get("rank_status", "same")
            e = emojis.get(st.lower(), "")
            lines.append(f"{e} {kw} 📊 {sc}")
            if len("\n".join(lines)) + len(header) > max_total - len(sig):
                lines.pop()
                break
        if not lines: return None
        body = f"{header}" + "\n".join(lines)
        final = body + sig
        return final if utils.count_graphemes(final) <= max_total else None
    item = trends[0]
    kw = item.get("keyword", "?")
    sc = item.get("score")
    st = item.get("rank_status", "same")
    summary = item.get("summary", "")
    e = emojis.get(st.lower(), "")
    title = f"{e + ' ' if e else ''}{kw} 📊 {sc}:"
    header = "TOP CRYPTO TREND:\n\n"
    fixed_len = len(header) + len(title) + 1 + len(sig)
    max_desc = max_total - fixed_len
    if max_desc < 30: return None
    for attempt in range(3):
        constraint = ""
        temp = 0.5
        if attempt == 1:
            constraint = "\nNOTE: Keep it under 280 chars total. Use short, direct sentences."
            temp = 0.6
        elif attempt == 2:
            constraint = "\nCRITICAL: Strictly under 290 chars. Drop filler words. Use abbreviations."
            temp = 0.7
        prompt = f"Summarize '{kw}' in 1-2 short sentences. Start directly. Context: {summary}{constraint}"
        desc = generator.get_answer(llm, "", prompt, max_chars=max_desc, temperature=temp).strip()
        body = f"{header}{title} {desc}"
        final = body + sig
        if utils.count_graphemes(final) <= max_total:
            return final
        logger.info(f"[DIGEST] Attempt {attempt+1} too long ({utils.count_graphemes(final)} chars), retrying...")
    logger.warning(f"[DIGEST] Failed to generate {task_type} within limits after 3 attempts")
    return None