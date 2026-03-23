# app/services/ai_service.py

import hashlib

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


def _anchor_norm_matrix():
    """Stack normalized anchor embeddings for batch cosine similarity."""
    rows = []
    for p in PERSONAS:
        a = np.asarray(ANCHORS[p], dtype=np.float64).reshape(-1)
        a = a / (np.linalg.norm(a) + 1e-9)
        rows.append(a)
    return np.stack(rows, axis=0)


ANCHOR_NORM = _anchor_norm_matrix()


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


def transform_text(text, persona):
    config = PERSONA_PROMPTS.get(
        persona,
        {"prefix": "summarize: ", "max_len": 60, "min_len": 30},
    )

    prefix = config["prefix"]
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
    return out.strip() or snippet[:280]


def _relevance_percent_for_persona(relevance_scores: dict, current_persona: str) -> float:
    s = float(relevance_scores.get(current_persona, 0.0))
    pct = (s + 0.15) / 1.15 * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _persona_tags(relevance_scores: dict):
    """All personas with display relevance %, sorted by relevance."""
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


def process_articles(
    articles,
    current_persona,
    click_history,
    user_id="demo_user",
):
    """
    Fast path: batch-embed all candidates, rank with matrix cosine, then run
    transformer (slow) only on the top-K articles for the active persona.
    """
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
        aid = _stable_article_id(
            article.get("url") or "",
            article.get("title") or "",
        )

        ranked.append(
            {
                "article_id": aid,
                "original_title": article.get("title") or "Untitled",
                "transformed_text": "",
                "best_persona": best_persona,
                "suggested_tag": best_persona,
                "persona_tags": tags,
                "relevance_score": round(persona_fit, 4),
                "relevance_percent": rel_pct,
                "relevance_scores": relevance_scores,
                "url": article.get("url", ""),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", ""),
                "description": (article.get("description") or "")[:400],
                "_raw_text": text,
            }
        )

        for p in PERSONAS:
            sum_vec[p] += max(0.0, relevance_scores.get(p, 0.0))
        texts_for_shift.append(text[:500])

    ranked.sort(key=lambda x: x["relevance_score"], reverse=True)
    top_k = 9
    top_slice = ranked[:top_k]

    for item in top_slice:
        item["transformed_text"] = transform_text(item["_raw_text"], current_persona)
        del item["_raw_text"]

    remainder = ranked[top_k:]
    for item in remainder:
        del item["_raw_text"]

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
    record_feed_fetch(user_id, current_persona, len(top_articles))
    save_last_persona_scores(user_id, persona_scores)

    stats = get_user_stats(user_id)

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
    }


def process_request(text, persona, click_history, user_id="demo_user"):
    text_vector = get_matcher().encode(text)
    relevance_scores = compute_relevance_scores(text_vector)

    suggested_persona, shift_detected, confidence = detect_persona_shift_with_history(
        text, click_history, persona
    )

    transformed_text = transform_text(text, persona)

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
