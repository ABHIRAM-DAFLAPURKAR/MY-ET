import os
import requests
import json
from typing import List, Dict, Any
from app.fast_articles import get_fast_articles
# Redis optional - fallback no-cache for reliability
# from .redis_client import get_cache, set_cache, cache_articles

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
if not NEWS_API_KEY:
    raise ValueError("NEWS_API_KEY must be set")
BASE_URL = "https://newsapi.org/v2/everything"


def fetch_articles(query="economy", page_size=30, page=1):
    cache_key = f"news:{query}:{page_size}:{page}"
    # Cache disabled for startup - use static fast_articles
    params = {
        "q": query,
        "apiKey": NEWS_API_KEY,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": min(page_size, 100),
        "page": max(1, int(page)),
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=8, headers={'User-Agent': 'NewsAI/1.0'})
        if response.status_code != 200:
            return get_fast_articles(num_articles=page_size, query=query, page=page)
        raw = response.json().get("articles", [])
    except:
        raw = []
    if not raw:
        return get_fast_articles(num_articles=page_size, query=query, page=page)
    out: List[Dict[str, Any]] = []
    for a in raw:
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        content = a.get("content") or ""
        if not content and desc:
            content = desc
        text = content or title
        if not text:
            continue
        out.append(
            {
                "title": title,
                "description": desc,
                "content": text,
                "url": a.get("url") or "",
                "published_at": a.get("publishedAt") or "",
                "source": (a.get("source") or {}).get("name", ""),
            }
        )
    return out[:page_size] or get_fast_articles(num_articles=page_size, query=query, page=page)
