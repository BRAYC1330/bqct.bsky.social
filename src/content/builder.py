from src.state import settings as config
from src.content import validator
from src.llm import inference as llm_infer

SIG_DIGEST = "\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\nQwen | Tavily"
SIG_CHAINBASE = "\nQwen | Chainbase"
SIG_DEFAULT = "\nQwen"

def _get_signature(source, has_search):
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT

def get_no_data_response(keyword):
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}\nQwen"

async def build_reply(llm, thread_ctx, query, search_data="", source="", max_total=300):
    sig = _get_signature(source, bool(search_data))
    max_body = max_total - len(sig)
    ctx = f"[SEARCH]\n{search_data}\n{thread_ctx}" if search_data else thread_ctx
    reply = llm_infer.get_answer(llm, ctx, query, max_chars=max_body, temperature=0.5)
    reply = validator.enforce_limit(reply, max_body)
    return reply.strip() + sig

async def build_digest(llm, trends, task_type, max_total=300):
    if not trends: return None
    sig = SIG_DIGEST
    max_body = max_total - len(sig)
    emojis = config.TREND_EMOJIS
    if task_type == "digest_mini":
        header = "TOP CRYPTO TRENDS:\n"
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
        if not lines: return None
        body = f"{header}" + "\n".join(lines)
    else:
        item = trends[0]
        kw = item.get("keyword", "?")
        sc = item.get("score")
        st = item.get("rank_status", "same")
        summary = item.get("summary", "")
        e = emojis.get(st.lower(), "")
        title = f"{e + ' ' if e else ''}{kw} 📊 {sc}:"
        header = "TOP CRYPTO TREND:\n"
        max_desc = max_body - len(header) - len(title) - 1
        if max_desc < 20: return None
        prompt = f"Write exactly two sentences for '{kw}'. Structure: Core fact. Impact or metric. Max 19 words total. Start directly. Context: {summary}"
        desc = llm_infer.get_answer(llm, "", prompt, max_chars=max_desc, temperature=0.5)
        body = f"{header}{title} {desc}"
    final = body + sig
    if validator.count_graphemes(final) > max_total: return None
    return final
