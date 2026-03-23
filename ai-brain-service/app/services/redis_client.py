import redis
import json
import os
from typing import Optional, List, Dict, Any

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def get_cache(key: str) -> Optional[str]:
    return r.get(key)

def set_cache(key: str, value: str, ttl: int = 300):  # 5 min default
    r.setex(key, ttl, value)

def cache_articles(query: str, articles: List[Dict[str, Any]], ttl: int = 300):
    key = f"news:{query}"
    set_cache(key, json.dumps(articles), ttl)
