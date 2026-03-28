from collections import defaultdict

from app.services.db_service import list_user_activity


PERSONA_TOPIC_RULES = {
    "investor": {
        "keywords": {"market", "stock", "stocks", "finance", "fund", "mutual", "portfolio", "sip", "earnings", "inflation"},
        "long_read_bonus": 0.28,
        "click_bonus": 0.18,
    },
    "student": {
        "keywords": {"learn", "explainer", "beginner", "basic", "student", "guide", "fundamental", "education"},
        "short_read_bonus": 0.2,
        "click_bonus": 0.12,
    },
    "founder": {
        "keywords": {"startup", "founder", "business", "policy", "funding", "competitor", "launch", "gtm", "venture"},
        "long_read_bonus": 0.22,
        "click_bonus": 0.16,
    },
}


def _tokens(*values: str):
    merged = " ".join(value or "" for value in values).lower()
    return {part.strip(".,:;!?()[]{}") for part in merged.split() if part.strip()}


def detect_persona_from_behavior(user_id: str):
    activities = list_user_activity(user_id, limit=120)
    scores = defaultdict(float)

    for row in activities:
        tokens = _tokens(row.get("topic", ""), row.get("article_title", ""), row.get("interaction", ""))
        read_time = float(row.get("read_time") or 0.0)
        clicked = bool(row.get("clicked"))

        for persona, config in PERSONA_TOPIC_RULES.items():
            matches = len(tokens.intersection(config["keywords"]))
            scores[persona] += matches * 0.18

            if clicked:
                scores[persona] += config["click_bonus"]

            if persona in {"investor", "founder"} and read_time >= 45:
                scores[persona] += config["long_read_bonus"]

            if persona == "student" and 0 < read_time <= 35:
                scores[persona] += config["short_read_bonus"]

    if not scores:
        return {
            "suggested_persona": "student",
            "confidence_score": 0.34,
            "persona_scores": {
                "student": 0.34,
                "founder": 0.33,
                "investor": 0.33,
                "total_confidence": 0.34,
            },
            "reason": "Insufficient activity history. Defaulting to student-friendly mode.",
        }

    totals = {persona: max(0.01, score) for persona, score in scores.items()}
    for persona in PERSONA_TOPIC_RULES:
        totals.setdefault(persona, 0.01)

    total = sum(totals.values()) or 1.0
    normalized = {persona: round(totals[persona] / total, 4) for persona in PERSONA_TOPIC_RULES}
    suggested = max(normalized, key=normalized.get)
    confidence = round(normalized[suggested], 4)

    return {
        "suggested_persona": suggested,
        "confidence_score": confidence,
        "persona_scores": {
            "student": normalized["student"],
            "founder": normalized["founder"],
            "investor": normalized["investor"],
            "total_confidence": confidence,
        },
        "reason": f"Detected from click behavior, read time, and recurring topics linked to {suggested}.",
    }
