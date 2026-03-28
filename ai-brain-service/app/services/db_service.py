from datetime import datetime, timezone
import os

from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["personalized_news"]
users_col = db["users"]
clicks_col = db["article_clicks"]
activity_col = db["user_activity"]
audit_col = db["pipeline_audit"]


def save_user_click(user_id, persona):
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"persona": persona, "updated_at": _now()}},
        upsert=True,
    )


def record_feed_fetch(user_id: str, persona: str, article_count: int, audience_profile: str | None = None):
    users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"feed_fetches": 1, "articles_served": article_count},
            "$set": {
                "last_persona": persona,
                "last_audience_profile": audience_profile,
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
    article_ids = doc.get("recent_article_ids") or []
    return {
        "feed_fetches": int(doc.get("feed_fetches", 0)),
        "articles_served": int(doc.get("articles_served", 0)),
        "last_fetch_at": doc.get("last_fetch_at"),
        "last_persona": doc.get("last_persona"),
        "last_audience_profile": doc.get("last_audience_profile"),
        "last_persona_scores": doc.get("last_persona_scores"),
        "total_interactions": int(doc.get("total_interactions", 0)),
        "source_clicks": int(doc.get("source_clicks", 0)),
        "deep_reads": int(doc.get("deep_reads", 0)),
        "unique_articles": len(article_ids),
        "last_engagement_at": doc.get("last_engagement_at"),
        "recent_article_ids": article_ids[-40:],
    }


def record_user_activity(user_id: str, payload: dict, update_summary: bool = True):
    doc = {
        "user_id": user_id,
        "timestamp": _now(),
        **{k: v for k, v in payload.items() if v is not None},
    }
    activity_col.insert_one(doc)

    if not update_summary:
        return

    interaction = payload.get("interaction", "view")
    clicked = bool(payload.get("clicked", False))
    read_time = float(payload.get("read_time", 0) or 0)
    article_key = payload.get("article_id") or payload.get("url") or payload.get("article_title")

    inc = {}
    if clicked or interaction in {"source", "deep_read", "deep_read_view"}:
        inc["total_interactions"] = 1
    if interaction == "source":
        inc["source_clicks"] = 1
    if interaction in {"deep_read", "deep_read_view", "read"} or read_time >= 25:
        inc["deep_reads"] = 1

    update = {"$set": {"last_engagement_at": _now(), "updated_at": _now()}}
    if inc:
        update["$inc"] = inc
    if article_key:
        update["$addToSet"] = {"recent_article_ids": article_key}

    users_col.update_one({"user_id": user_id}, update, upsert=True)


def list_user_activity(user_id: str, limit: int = 100):
    cur = (
        activity_col.find({"user_id": user_id})
        .sort("timestamp", -1)
        .limit(max(1, min(limit, 500)))
    )
    out = []
    for d in cur:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


def save_last_persona_scores(user_id: str, persona_scores: dict):
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_persona_scores": persona_scores, "updated_at": _now()}},
        upsert=True,
    )


def record_pipeline_audit(user_id: str, payload: dict):
    audit_col.insert_one(
        {
            "user_id": user_id,
            "timestamp": _now(),
            **{k: v for k, v in payload.items() if v is not None},
        }
    )


def record_article_click(user_id: str, payload: dict):
    interaction = payload.get("interaction", "unknown")
    article_id = payload.get("article_id")
    doc = {
        "user_id": user_id,
        "clicked_at": _now(),
        **{k: v for k, v in payload.items() if v is not None},
    }
    clicks_col.insert_one(doc)
    record_user_activity(
        user_id,
        {
            "article_title": payload.get("title"),
            "topic": payload.get("topic"),
            "read_time": payload.get("read_time", 0),
            "clicked": True,
            "interaction": interaction,
            "url": payload.get("url"),
        },
        update_summary=False,
    )

    inc = {"total_interactions": 1}
    if interaction == "source":
        inc["source_clicks"] = 1
    if interaction in {"deep_read", "deep_read_view"}:
        inc["deep_reads"] = 1

    update = {
        "$inc": inc,
        "$set": {
            "last_engagement_at": _now(),
            "updated_at": _now(),
        },
    }
    if article_id:
        update["$addToSet"] = {"recent_article_ids": article_id}

    users_col.update_one({"user_id": user_id}, update, upsert=True)


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
