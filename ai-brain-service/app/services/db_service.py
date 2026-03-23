from datetime import datetime, timezone
import os

from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["personalized_news"]
users_col = db["users"]
clicks_col = db["article_clicks"]


def save_user_click(user_id, persona):
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"persona": persona, "updated_at": _now()}},
        upsert=True,
    )


def record_feed_fetch(user_id: str, persona: str, article_count: int):
    """Increment regulation counters for real-time stats."""
    users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"feed_fetches": 1, "articles_served": article_count},
            "$set": {
                "last_persona": persona,
                "last_fetch_at": _now(),
            },
        },
        upsert=True,
    )


def get_user_persona(user_id):
    user = users_col.find_one({"user_id": user_id})
    return user.get("persona") if user else "student"


def get_user_stats(user_id: str) -> dict:
    doc = users_col.find_one({"user_id": user_id}) or {}
    return {
        "feed_fetches": int(doc.get("feed_fetches", 0)),
        "articles_served": int(doc.get("articles_served", 0)),
        "last_fetch_at": doc.get("last_fetch_at"),
        "last_persona": doc.get("last_persona"),
        "last_persona_scores": doc.get("last_persona_scores"),
    }


def save_last_persona_scores(user_id: str, persona_scores: dict):
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_persona_scores": persona_scores, "updated_at": _now()}},
        upsert=True,
    )


def record_article_click(user_id: str, payload: dict):
    """Store a user interaction with an article (source link, deep read, etc.)."""
    doc = {
        "user_id": user_id,
        "clicked_at": _now(),
        **{k: v for k, v in payload.items() if v is not None},
    }
    clicks_col.insert_one(doc)


def list_article_clicks(user_id: str, limit: int = 50):
    cur = (
        clicks_col.find({"user_id": user_id})
        .sort("clicked_at", -1)
        .limit(max(1, min(limit, 200)))
    )
    out = []
    for d in cur:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


def _now():
    return datetime.now(timezone.utc).isoformat()
