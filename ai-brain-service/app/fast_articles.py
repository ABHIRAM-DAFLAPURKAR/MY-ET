import json
from typing import List, Dict, Any
import random

# Static cache for ultra-fast loads (Redis optional)
CACHED_ARTICLES = [
    {'title': 'Market Surge', 'content': 'Stocks up 2% on Fed signals. Tech leads gains.', 'url': 'https://news1', 'published_at': '2024-10-01', 'source': 'WSJ', 'description': 'Brief desc'},
    {'title': 'AI Funding Boom', 'content': 'VCs pour $5B into AI startups this quarter.', 'url': 'https://news2', 'published_at': '2024-10-02', 'source': 'TechCrunch', 'description': 'VC trends'},
] * 10

def get_fast_articles(num_articles=18) -> List[Dict[str, Any]]:
    return random.sample(CACHED_ARTICLES, min(num_articles, len(CACHED_ARTICLES)))
