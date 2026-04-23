import os
import logging
import httpx
import config
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def get_trending_topics_raw() -> list:
    # Mock data for testing digest generation
    return [
        {"id": "btc", "keyword": "Bitcoin", "summary": "Price holding above $60K", "score": 150, "rank_status": "up", "is_new": False},
        {"id": "eth", "keyword": "Ethereum", "summary": "ETF inflows continue", "score": 120, "rank_status": "same", "is_new": False},
        {"id": "sol", "keyword": "Solana", "summary": "Network activity surge", "score": 95, "rank_status": "up", "is_new": True},
        {"id": "xrp", "keyword": "XRP", "summary": "Legal clarity progress", "score": 80, "rank_status": "down", "is_new": False},
        {"id": "ada", "keyword": "Cardano", "summary": "Upgrade announcement", "score": 70, "rank_status": "same", "is_new": False},
        {"id": "dot", "keyword": "Polkadot", "summary": "Parachain auctions update", "score": 60, "rank_status": "same", "is_new": False},
    ]

def clean_search_results(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, list):
        return " ".join([r.get("title", "") + " " + r.get("content", "")[:150] for r in raw])
    return str(raw)[:500]

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY:
        return ""
    url = "https://api.tavily.com/search"
    headers = {"Authorization": f"Bearer {config.TAVILY_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "search_depth": "basic", "max_results": 3, "include_raw_content": True}
    if time_range:
        payload["time_range"] = time_range
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            return clean_search_results(r.json().get("results", []))
    except Exception as e:
        logger.error(f"[tavily] Error: {e}")
        return ""

async def fetch_chainbase(query: str) -> str:
    return ""
