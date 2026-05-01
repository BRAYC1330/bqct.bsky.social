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
    if source == "chainbase" and has_search: return SIG_CHAINBASE
    return SIG_DEFAULT
async def build_reply(llm, thread_ctx: str, query: str, search_data: str = "", source: str = "", max_total: int = 300) -> str:
    sig = _get_signature(source, bool(search_data))
    max_body = max_total - len(sig)
    ctx = f"[SEARCH]\n{search_data}\n{thread_ctx}" if search_data else thread_ctx
    logger.info(f"=== FINAL CONTEXT FOR MODEL ===\n{ctx}")
    reply = generator.get_answer(llm, ctx, query, max_chars=max_body, temperature=0.5)
    reply = utils.truncate_response(reply, max_body)
    return reply.strip() + sig
async def build_digest(llm, trends, task_type: str, max_total: int = 300) -> str:
    if not trends: return "No trends available.\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
    sig = SIG_DIGEST
    max_body = max_total - len(sig)
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
            if len("\n".join(lines)) + len(header) > max_body:
                lines.pop()
                break
        if not lines: return "No trends available.\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
        body = f"{header}" + "\n".join(lines)
    else:
        item = trends[0]
        kw = item.get("keyword", "?")
        sc = item.get("score")
        st = item.get("rank_status", "same")
        summary = item.get("summary", "")
        e = emojis.get(st.lower(), "")
        title = f"{e + ' ' if e else ''}{kw} 📊 {sc}:"
        header = "TOP CRYPTO TREND:\n\n"
        max_desc = max_body - len(header) - len(title) - 1
        if max_desc < 20: return "No trends available.\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
        prompt = f"Write exactly two sentences for '{kw}'. Structure: Core fact. Impact or metric. Max 19 words total. Start directly. Context: {summary}"
        desc = generator.get_answer(llm, "", prompt, max_chars=max_desc, temperature=0.5)
        desc = utils.truncate_response(desc, max_desc)
        if not desc or len(desc) < 5:
            desc = utils.truncate_response(summary, max_desc)
        body = f"{header}{title} {desc}"
    final = body + sig
    return final