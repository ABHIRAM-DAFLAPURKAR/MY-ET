# app/services/ai_service.py

import hashlib
from datetime import datetime, timezone

import numpy as np
from sentence_transformers import util

from app.services.model_loader import get_matcher, get_summarizer
from app.config.persona_config import ANCHORS, PERSONA_PROMPTS, PERSONAS
from app.utils.helpers import detect_persona_shift_with_history
from app.services.db_service import (
    save_user_click,
    record_feed_fetch,
    get_user_stats,
    save_last_persona_scores,
)


PROFILE_LENSES = {
    "cfo_macro": {
        "label": "45-year-old CFO tracking macro policy",
        "shortLabel": "CFO macro",
        "format": "Board-ready macro brief",
        "framing": "Macro signal / treasury implication / executive watchpoint",
        "prompt": "summarize for a CFO focused on macro policy, treasury risk, and board implications: ",
    },
    "first_gen_investor": {
        "label": "24-year-old first-generation investor",
        "shortLabel": "First-investor",
        "format": "Explainer-first market brief",
        "framing": "What happened / why it matters / term to know",
        "prompt": "explain this for a first-generation investor using simple language and practical context: ",
    },
    "startup_founder": {
        "label": "Startup founder tracking funding and competitor moves",
        "shortLabel": "Founder",
        "format": "Operator briefing",
        "framing": "Funding pulse / competitor move / GTM implication",
        "prompt": "rewrite this for a startup founder with product, funding, and competitor implications: ",
    },
    "student_explainer": {
        "label": "Student who prefers explainers and fundamentals",
        "shortLabel": "Student",
        "format": "Explainer digest",
        "framing": "Key idea / why it matters / next concept",
        "prompt": "explain this to a student with fundamentals first and jargon removed: ",
    },
}

KEYWORDS = {
    "policy": ["policy", "rate", "inflation", "reserve", "budget", "fed", "rbi", "tariff"],
    "funding": ["funding", "seed", "series", "venture", "valuation", "startup"],
    "portfolio": ["stock", "market", "earnings", "etf", "portfolio", "fund", "investor"],
    "competition": ["competitor", "launch", "product", "pricing", "growth", "market share"],
    "learning": ["explainer", "beginner", "guide", "student", "learn", "education"],
}

PROFILE_SIGNAL_BOOSTS = {
    "cfo_macro": {"policy": 0.12, "portfolio": 0.08},
    "first_gen_investor": {"portfolio": 0.1, "learning": 0.1, "policy": 0.04},
    "startup_founder": {"funding": 0.12, "competition": 0.12, "portfolio": 0.03},
    "student_explainer": {"learning": 0.12, "policy": 0.05, "portfolio": 0.04},
}

POSITIVE_WORDS = {"surge", "gain", "record", "growth", "beat", "strong", "expand", "improve"}
NEGATIVE_WORDS = {"fall", "drop", "risk", "crisis", "slump", "slowdown", "miss", "weak"}


def _anchor_norm_matrix():
    rows = []
    for p in PERSONAS:
        a = np.asarray(ANCHORS[p], dtype=np.float64).reshape(-1)
        a = a / (np.linalg.norm(a) + 1e-9)
        rows.append(a)
    return np.stack(rows, axis=0)


ANCHOR_NORM = _anchor_norm_matrix()


def _profile_meta(audience_profile: str | None, persona: str):
    if audience_profile in PROFILE_LENSES:
        return PROFILE_LENSES[audience_profile]
    fallback = {
        "student": "student_explainer",
        "founder": "startup_founder",
        "investor": "first_gen_investor",
    }.get(persona, "first_gen_investor")
    return PROFILE_LENSES[fallback]


def compute_relevance_scores(text_vector):
    scores = {}
    for persona, anchor in ANCHORS.items():
        score = util.cos_sim(text_vector, anchor).item()
        scores[persona] = round(score, 4)
    return scores


def _normalize_persona_distribution(raw: dict) -> dict:
    vals = {k: max(0.0, float(v)) for k, v in raw.items() if k in PERSONAS}
    s = sum(vals.values())
    if s <= 0:
        n = len(PERSONAS)
        return {k: round(1.0 / n, 4) for k in PERSONAS}
    return {k: round(vals[k] / s, 4) for k in PERSONAS}


def _extract_signal_tags(text: str):
    lowered = (text or "").lower()
    tags = [label for label, words in KEYWORDS.items() if any(word in lowered for word in words)]
    return tags[:3] or ["general"]


def _sentiment_tag(text: str):
    lowered = (text or "").lower()
    pos = sum(word in lowered for word in POSITIVE_WORDS)
    neg = sum(word in lowered for word in NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "cautious"
    return "neutral"


def transform_text(text, persona, audience_profile=None):
    config = PERSONA_PROMPTS.get(
        persona,
        {"prefix": "summarize: ", "max_len": 60, "min_len": 30},
    )
    profile = _profile_meta(audience_profile, persona)

    prefix = profile["prompt"] or config["prefix"]
    max_l = config["max_len"]
    min_l = config["min_len"]
    snippet = (text or "")[:1600]

    result = get_summarizer()(
        prefix + snippet,
        max_length=max_l,
        min_length=min_l,
        do_sample=False,
        truncation=True,
    )

    out = result[0].get("summary_text") or result[0].get("generated_text") or ""
    summary = out.strip() or snippet[:280]
    return f"{profile['format']}: {summary}"


def _relevance_percent_for_persona(relevance_scores: dict, current_persona: str) -> float:
    s = float(relevance_scores.get(current_persona, 0.0))
    pct = (s + 0.15) / 1.15 * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _persona_tags(relevance_scores: dict):
    tags = []
    for p in PERSONAS:
        tags.append(
            {
                "persona": p,
                "relevance_percent": _relevance_percent_for_persona(relevance_scores, p),
                "relevance": relevance_scores.get(p, 0.0),
            }
        )
    tags.sort(key=lambda x: x["relevance_percent"], reverse=True)
    return tags


def _stable_article_id(url: str, title: str) -> str:
    h = hashlib.md5(f"{url}|{title}".encode("utf-8", errors="ignore")).hexdigest()
    return h[:16]


def _agent_pipeline(profile_label: str, query: str):
    return [
        {
            "step": "Raw News Ingestion",
            "detail": f"Fetched the latest articles for query '{query}' with no manual curation.",
        },
        {
            "step": "Entity and Topic Extraction",
            "detail": "Detected company, market, policy, and learning signals directly from raw article text.",
        },
        {
            "step": "Sentiment Tagging",
            "detail": "Classified each story tone as positive, cautious, or neutral before ranking.",
        },
        {
            "step": "Personalized Ranking and Rewrite",
            "detail": f"Ranked articles for {profile_label} and rewrote the top stories in a profile-specific format.",
        },
        {
            "step": "Engagement Retuning",
            "detail": "Used prior clicks and deep reads to boost the next feed without manual curation.",
        },
    ]


def _stable_hash_fraction(value: str) -> float:
    digest = hashlib.md5(value.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _freshness_bonus(published_at: str) -> float:
    if not published_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_hours <= 6:
            return 0.08
        if age_hours <= 24:
            return 0.05
        if age_hours <= 72:
            return 0.02
    except Exception:
        return 0.0
    return 0.0


def _engagement_boost(signal_tags: list[str], audience_profile: str | None, click_history: list[float]) -> float:
    profile_key = audience_profile or "first_gen_investor"
    boosts = PROFILE_SIGNAL_BOOSTS.get(profile_key, {})
    engagement_level = sum(click_history) / len(click_history) if click_history else 0.5
    base = sum(boosts.get(tag, 0.0) for tag in signal_tags)
    return round(base * (0.7 + 0.6 * engagement_level), 4)


def _session_retuning(stats: dict, audience_profile: str | None, click_history: list[float]) -> dict:
    profile_key = audience_profile or "first_gen_investor"
    boosts = PROFILE_SIGNAL_BOOSTS.get(profile_key, {})
    boosted_signals = [signal for signal, _ in sorted(boosts.items(), key=lambda item: item[1], reverse=True)[:2]]
    total_interactions = int(stats.get("total_interactions", 0))
    source_clicks = int(stats.get("source_clicks", 0))
    deep_reads = int(stats.get("deep_reads", 0))
    avg_history_signal = round(sum(click_history) / len(click_history), 3) if click_history else 0.0
    engagement_score = round(
        min(1.0, 0.18 * total_interactions + 0.24 * deep_reads + 0.12 * source_clicks + avg_history_signal),
        3,
    )

    return {
        "headline": "Engagement retuning is active",
        "detail": f"The next feed boosts {', '.join(boosted_signals)} because this user has {total_interactions} tracked interactions and {deep_reads} deep reads.",
        "boosted_signals": boosted_signals,
        "engagement_score": engagement_score,
        "total_interactions": total_interactions,
        "source_clicks": source_clicks,
        "deep_reads": deep_reads,
        "next_refresh_in_seconds": 90,
    }


def process_articles(
    articles,
    current_persona,
    click_history,
    user_id="demo_user",
    audience_profile=None,
    query="business technology",
    refresh_cycle=1,
):
    previous_stats = get_user_stats(user_id)
    seen_article_ids = set(previous_stats.get("recent_article_ids") or [])
    valid = []
    for article in articles:
        text = article.get("content") or article.get("title") or ""
        if not text:
            continue
        valid.append((article, text[:8000]))

    if not valid:
        return {
            "status": "error",
            "message": "No processable articles",
            "top_articles": [],
        }

    profile = _profile_meta(audience_profile, current_persona)
    texts = [t[1] for t in valid]
    embeddings = get_matcher().encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )

    en = np.asarray(embeddings, dtype=np.float64)
    en = en / (np.linalg.norm(en, axis=1, keepdims=True) + 1e-9)
    sim_matrix = en @ ANCHOR_NORM.T

    ranked = []
    sum_vec = {p: 0.0 for p in PERSONAS}
    texts_for_shift = []

    for i, (article, text) in enumerate(valid):
        row = sim_matrix[i]
        relevance_scores = {
            PERSONAS[j]: round(float(row[j]), 4) for j in range(len(PERSONAS))
        }

        best_persona = max(relevance_scores, key=relevance_scores.get)
        persona_fit = 0.55 * relevance_scores.get(current_persona, 0.0) + 0.45 * relevance_scores.get(
            best_persona, 0.0
        )

        rel_pct = _relevance_percent_for_persona(relevance_scores, current_persona)
        tags = _persona_tags(relevance_scores)
        aid = _stable_article_id(article.get("url") or "", article.get("title") or "")
        signal_tags = _extract_signal_tags(text)
        sentiment_tag = _sentiment_tag(text)
        engagement_boost = _engagement_boost(signal_tags, audience_profile, click_history)
        freshness_bonus = _freshness_bonus(article.get("published_at", ""))
        repeat_penalty = 0.24 if aid in seen_article_ids else 0.0
        rotation_signal = (_stable_hash_fraction(f"{user_id}:{aid}:{refresh_cycle}") - 0.5) * 0.08
        ranking_score = round(persona_fit + engagement_boost + freshness_bonus + rotation_signal - repeat_penalty, 4)

        ranked.append(
            {
                "article_id": aid,
                "original_title": article.get("title") or "Untitled",
                "transformed_text": "",
                "best_persona": best_persona,
                "suggested_tag": best_persona,
                "persona_tags": tags,
                "relevance_score": ranking_score,
                "relevance_percent": rel_pct,
                "relevance_scores": relevance_scores,
                "url": article.get("url", ""),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", ""),
                "description": (article.get("description") or "")[:400],
                "signal_tags": signal_tags,
                "sentiment_tag": sentiment_tag,
                "framing_style": profile["framing"],
                "content_format": profile["format"],
                "why_for_user": f"{profile['label']} sees this through {', '.join(signal_tags)} with a {sentiment_tag} tone; prior engagement now boosts this angle.",
                "original_url": article.get("url", ""),
                "refresh_reason": "freshness" if freshness_bonus >= 0.05 else "engagement_retuning" if engagement_boost > 0 else "persona_fit",
                "_raw_text": text,
            }
        )

        for p in PERSONAS:
            sum_vec[p] += max(0.0, relevance_scores.get(p, 0.0))
        texts_for_shift.append(text[:500])

    ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
    if len(ranked) <= 9:
        top_slice = ranked[:9]
    else:
        candidate_pool = ranked[: min(len(ranked), 18)]
        start = ((max(1, refresh_cycle) - 1) * 4) % len(candidate_pool)
        rotated = candidate_pool[start:] + candidate_pool[:start]
        top_slice = rotated[:9]

    for item in top_slice:
        item["transformed_text"] = transform_text(item["_raw_text"], current_persona, audience_profile)
        item.pop("_raw_text", None)

    top_item_ids = {id(item) for item in top_slice}
    for item in ranked:
        if id(item) in top_item_ids:
            continue
        item.pop("_raw_text", None)

    top_articles = top_slice

    n = max(len(ranked), 1)
    avg_raw = {p: sum_vec[p] / n for p in PERSONAS}
    dist = _normalize_persona_distribution(avg_raw)
    top_conf = round(
        min(
            1.0,
            max(dist.values())
            * (0.85 + 0.15 * (top_articles[0]["relevance_score"] if top_articles else 0)),
        ),
        4,
    )
    persona_scores = {**dist, "total_confidence": top_conf}

    combined = " ".join(texts_for_shift[:8])
    suggested_persona, shift_detected, confidence = detect_persona_shift_with_history(
        combined, click_history, current_persona
    )

    dominant_persona = max(PERSONAS, key=lambda p: dist[p])

    save_user_click(user_id=user_id, persona=suggested_persona)
    record_feed_fetch(user_id, current_persona, len(top_articles), audience_profile=audience_profile)
    save_last_persona_scores(user_id, persona_scores)

    stats = get_user_stats(user_id)
    generated_at = datetime.now(timezone.utc).isoformat()
    engagement_retuning = _session_retuning(stats, audience_profile, click_history)

    return {
        "status": "success",
        "persona_applied": current_persona,
        "top_persona": suggested_persona,
        "dominant_feed_persona": dominant_persona,
        "persona_shift_detected": shift_detected,
        "confidence_score": confidence,
        "persona_scores": persona_scores,
        "top_articles": top_articles,
        "regulation_stats": stats,
        "audience_profile": audience_profile,
        "profile_label": profile["label"],
        "latest_feed_label": f"Latest {profile['shortLabel'] if 'shortLabel' in profile else profile['label']} feed generated at {generated_at}",
        "feed_generated_at": generated_at,
        "generic_homepage_label": "Generic ET homepage",
        "personalized_homepage_label": profile["label"],
        "agent_pipeline": _agent_pipeline(profile["label"], query),
        "engagement_retuning": engagement_retuning,
    }


def process_request(text, persona, click_history, user_id="demo_user", audience_profile=None):
    text_vector = get_matcher().encode(text)
    relevance_scores = compute_relevance_scores(text_vector)

    suggested_persona, shift_detected, confidence = detect_persona_shift_with_history(
        text, click_history, persona
    )

    transformed_text = transform_text(text, persona, audience_profile)

    save_user_click(user_id=user_id, persona=suggested_persona)

    return {
        "persona_applied": persona,
        "relevance_scores": relevance_scores,
        "suggested_persona": suggested_persona,
        "persona_shift_detected": shift_detected,
        "confidence_score": confidence,
        "transformed_text": transformed_text,
        "status": "success",
    }
