import re
from src.state import settings as config
from src.clients import bsky as bsky_client

def is_english(text):
    if not text or not config.ENGLISH_ONLY_SEARCH: return True
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / len(text)) >= config.ENGLISH_ASCII_RATIO

def clean(text):
    if not text: return ""
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'[\s\n]*Qwen(\s*\|\s*(Tavily|Chainbase|Chainbase TOPS))?\s*[\s\n]*$', '', text, flags=re.I | re.MULTILINE)
    text = re.sub(r'[\U0001F300-\U0001F9FF\U0000FE00-\U0000FE0F\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U00002600-\U000026FF\U00002700-\U000027BF\U0001F1E0-\U0001F1FF]+', '', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://[^\s<>"{}|\\^`\[\]]+', '', text)
    text = re.sub(r'[*_#~`>|]', '', text)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n', text)
    text = re.sub(r'\.\s*\+\s*[A-Z][a-z]+\.\s*\+\s*[A-Z][a-z]+', '', text)
    text = re.sub(r'(Be Well\.?\s*)+', '', text, flags=re.I)
    text = re.sub(r'(White House\.?\s*)+', '', text, flags=re.I)
    return text.strip()

async def format_thread(chain, owner_did, bot_did, client, max_recent=20):
    if not chain: return ""
    root = clean(chain.get("root_text", ""))
    posts = chain.get("chain", [])
    recent_posts = posts[-max_recent:] if len(posts) > max_recent else posts
    dialogue = []
    seen_hashes = set()
    seen_hashes.add(hash(root))
    for post in recent_posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        text = clean(rec.get("text", ""))
        if not text: continue
        post_hash = hash(text)
        if post_hash in seen_hashes: continue
        seen_hashes.add(post_hash)
        embed = rec.get("embed")
        embed_txt = bsky_client._extract_embed_text(embed)
        if embed_txt: text += f" [EMBED: {embed_txt}]"
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        for u in urls:
            content = await bsky_client._fetch_url_content(client, u)
            if content: text += f" [LINK: {content}]"
        if did == owner_did: prefix = "Q:"
        elif did == bot_did: prefix = "A:"
        else: prefix = "@user:"
        dialogue.append(f"{prefix} {text}")
    parts = [f"[ROOT]\n{root}"]
    if dialogue: parts.append(f"[RECENT]\n" + "\n".join(dialogue))
    return "\n".join(parts)
