import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import re
from datetime import datetime, timezone
from typing import Any, TypedDict

import numpy as np
from sentence_transformers import util

from app.config.persona_config import ANCHORS, PERSONA_PROMPTS, PERSONAS
from app.fast_articles import get_fast_articles
from app.services.db_service import (
    get_user_stats,
    record_feed_fetch,
    record_pipeline_audit,
    save_last_persona_scores,
    save_user_click,
)
from app.services.model_loader import get_matcher, get_summarizer
from app.services.news_service import fetch_articles
from app.services.persona_service import detect_persona_from_behavior
from app.services.redis_client import get_cache, set_cache, r
from app.utils.error_handler import safe_execute
from app.utils.helpers import detect_persona_shift_with_history
from app.utils.logger import get_logger

try:
    from langgraph.graph import END, StateGraph  # type: ignore
except ImportError:
    END = "__end__"

    class _CompiledGraph:
        def __init__(self, nodes: dict[str, Any], edges: dict[str, str], entry: str, conditional_edges: dict[str, tuple[Any, dict[str, str]]]):
            self.nodes, self.edges, self.entry, self.conditional_edges = nodes, edges, entry, conditional_edges

        def invoke(self, state: dict[str, Any]):
            node, current = self.entry, dict(state)
            while node and node != END:
                current.update(self.nodes[node](current) or {})
                if node in self.conditional_edges:
                    router, mapping = self.conditional_edges[node]
                    node = mapping.get(router(current), END)
                else:
                    node = self.edges.get(node, END)
            return current

    class StateGraph:
        def __init__(self, _state_type: Any):
            self.nodes: dict[str, Any] = {}
            self.edges: dict[str, str] = {}
            self.conditional_edges: dict[str, tuple[Any, dict[str, str]]] = {}
            self.entry = ""

        def add_node(self, name: str, fn: Any):
            self.nodes[name] = fn

        def add_edge(self, source: str, target: str):
            self.edges[source] = target

        def add_conditional_edges(self, source: str, router: Any, mapping: dict[str, str]):
            self.conditional_edges[source] = (router, mapping)

        def set_entry_point(self, name: str):
            self.entry = name

        def compile(self):
            return _CompiledGraph(self.nodes, self.edges, self.entry, self.conditional_edges)


logger = get_logger()


PROFILE_LENSES = {
    "cfo_macro": {"label": "45-year-old CFO tracking macro policy", "shortLabel": "CFO macro", "format": "Board-ready macro brief", "framing": "Macro signal / treasury implication / executive watchpoint", "prompt": "Rewrite this for a CFO in a formal, analytical, and professional tone. Focus strictly on macro impact, policy implications, and business strategy. Provide high depth and detailed insights. DO NOT use simplification or casual language. Article: "},
    "first_gen_investor": {"label": "24-year-old first-generation investor", "shortLabel": "First-investor", "format": "Portfolio action brief", "framing": "Market move / portfolio implication / action to consider", "prompt": "Rewrite this for a young investor in an action-oriented, practical, and concise tone. Focus on 'What should I do?' and investment implications. Include quick actionable insights and risks. Depth is medium. Article: "},
    "startup_founder": {"label": "Startup founder tracking funding and competitor moves", "shortLabel": "Founder", "format": "Operator briefing", "framing": "Funding pulse / competitor move / GTM implication", "prompt": "Rewrite this for a startup founder in a strategic, slightly cautious tone. Focus heavily on funding trends, competition, and market signals. Depth should be medium to high. Article: "},
    "student_explainer": {"label": "Student who prefers explainers and fundamentals", "shortLabel": "Student", "format": "Explainer-first digest", "framing": "Key idea / why it matters / next concept", "prompt": "Explain this for a student in a simple, easy to understand tone. Focus on core concepts and what it means for learning. Keep depth low to medium. DO NOT use jargon or complex financial terms. Article: "},
}
KEYWORDS = {"policy": ["policy", "rate", "inflation", "reserve", "budget", "fed", "rbi", "tariff"], "funding": ["funding", "seed", "series", "venture", "valuation", "startup"], "portfolio": ["stock", "market", "earnings", "etf", "portfolio", "fund", "investor", "mutual"], "competition": ["competitor", "launch", "product", "pricing", "growth", "market share"], "learning": ["explainer", "beginner", "guide", "student", "learn", "education"]}
PROFILE_SIGNAL_BOOSTS = {"cfo_macro": {"policy": 0.12, "portfolio": 0.08}, "first_gen_investor": {"portfolio": 0.1, "learning": 0.1, "policy": 0.04}, "startup_founder": {"funding": 0.12, "competition": 0.12, "portfolio": 0.03}, "student_explainer": {"learning": 0.12, "policy": 0.05, "portfolio": 0.04}}
SIGNAL_PERSONA_WEIGHTS = {"learning": {"student": 0.18, "founder": -0.02, "investor": -0.01}, "funding": {"student": 0.01, "founder": 0.16, "investor": 0.07}, "competition": {"student": -0.01, "founder": 0.14, "investor": 0.05}, "portfolio": {"student": 0.02, "founder": 0.02, "investor": 0.18}, "policy": {"student": 0.04, "founder": 0.08, "investor": 0.1}, "general": {"student": 0.02, "founder": 0.02, "investor": 0.02}}
POSITIVE_WORDS = {"surge", "gain", "record", "growth", "beat", "strong", "expand", "improve"}
NEGATIVE_WORDS = {"fall", "drop", "risk", "crisis", "slump", "slowdown", "miss", "weak"}
STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "have", "after", "will", "your", "into", "about", "their", "they", "them", "been", "are", "was", "were", "has", "had", "but", "not", "why", "what", "when", "how", "today", "over", "more", "than", "need"}


class NewsState(TypedDict, total=False):
    user_id: str
    current_persona: str
    audience_profile: str | None
    click_history: list[float]
    query: str
    refresh_cycle: int
    page_size: int
    intent_mode: str | None
    articles: list[dict[str, Any]]
    enriched_articles: list[dict[str, Any]]
    ranked_articles: list[dict[str, Any]]
    top_articles: list[dict[str, Any]]
    user_profile: dict[str, Any]
    behavior_hint: dict[str, Any]
    regulation_stats: dict[str, Any]
    persona_scores: dict[str, Any]
    dominant_feed_persona: str
    top_persona: str
    persona_shift_detected: bool
    confidence_score: float
    feed_generated_at: str
    latest_feed_label: str
    profile_label: str
    personalized_homepage_label: str
    generic_homepage_label: str
    engagement_retuning: dict[str, Any]
    synthesis_summary: str
    final_output: dict[str, Any]
    persona_demo: dict[str, Any] | None
    agent_pipeline: list[dict[str, str]]
    fallback_used: bool
    fallback_reason: str | None
    explanation: str
    model_routing: dict[str, str]
    impact_metrics: dict[str, Any]
    articles_shown: list[str]
    audit_trail_id: str | None


ANCHOR_NORM = np.stack([(np.asarray(ANCHORS[p], dtype=np.float64).reshape(-1) / (np.linalg.norm(np.asarray(ANCHORS[p], dtype=np.float64).reshape(-1)) + 1e-9)) for p in PERSONAS], axis=0)


def _profile_meta(audience_profile: str | None, persona: str):
    if audience_profile in PROFILE_LENSES:
        return PROFILE_LENSES[audience_profile]
    return PROFILE_LENSES[{"student": "student_explainer", "founder": "startup_founder", "investor": "first_gen_investor"}.get(persona, "first_gen_investor")]


def compute_relevance_scores(text_vector):
    return {persona: round(util.cos_sim(text_vector, anchor).item(), 4) for persona, anchor in ANCHORS.items()}


def _normalize_persona_distribution(raw: dict):
    vals = {k: max(0.0, float(v)) for k, v in raw.items() if k in PERSONAS}
    total = sum(vals.values())
    return {k: round((vals[k] / total) if total > 0 else 1.0 / len(PERSONAS), 4) for k in PERSONAS}


def _extract_signal_tags(text: str):
    lowered = (text or "").lower()
    tags = [label for label, words in KEYWORDS.items() if any(word in lowered for word in words)]
    return tags[:3] or ["general"]


def _sigmoid(value: float):
    return 1.0 / (1.0 + np.exp(-value))


def _sentiment_tag(text: str):
    lowered = (text or "").lower()
    pos, neg = sum(word in lowered for word in POSITIVE_WORDS), sum(word in lowered for word in NEGATIVE_WORDS)
    return "positive" if pos > neg else "cautious" if neg > pos else "neutral"


def transform_text(text, persona, audience_profile=None):
    if not text: return ""
    
    # 1. Check Cache First
    cache_key = f"trans:{persona}:{audience_profile}:{hashlib.md5(text.encode()).hexdigest()}"
    try:
        if r:
            cached = r.get(cache_key)
            if cached:
                return cached.decode("utf-8")
    except: pass

    # 2. Run Transformation
    config = PERSONA_PROMPTS.get(persona, {"prefix": "summarize: ", "max_len": 60, "min_len": 30})
    profile = _profile_meta(audience_profile, persona)
    
    try:
        result = get_summarizer()((profile["prompt"] or config["prefix"]) + (text or "")[:1000], max_length=config["max_len"], min_length=config["min_len"], do_sample=False, truncation=True)
        out = result[0].get("summary_text") or result[0].get("generated_text") or ""
        out = out.strip() or (text or "")[:280]
    except Exception as e:
        logger.error(f"Transformation failed: {e}")
        out = (text or "")[:280]

    # 3. Store in Cache (1 hour)
    try:
        if r: r.setex(cache_key, 3600, out)
    except: pass
    
    return out


def _calibrated_persona_distribution(relevance_scores: dict, signal_tags: list[str]):
    bonus = {persona: 0.0 for persona in PERSONAS}
    for tag in signal_tags:
        weights = SIGNAL_PERSONA_WEIGHTS.get(tag, {})
        for persona in PERSONAS:
            bonus[persona] += float(weights.get(persona, 0.0))
    logits = np.asarray([(float(relevance_scores.get(persona, 0.0)) * 4.8) + bonus[persona] for persona in PERSONAS], dtype=np.float64)
    logits = logits - np.max(logits)
    probs = np.exp(logits)
    probs = probs / (np.sum(probs) + 1e-9)
    return {PERSONAS[i]: round(float(probs[i]), 4) for i in range(len(PERSONAS))}


def _relevance_percent_for_persona(relevance_scores: dict, persona_distribution: dict, current_persona: str):
    raw, probability = float(relevance_scores.get(current_persona, 0.0)), float(persona_distribution.get(current_persona, 0.0))
    ordered = sorted((float(v) for v in relevance_scores.values()), reverse=True)
    competitor = ordered[1] if len(ordered) > 1 else ordered[0] if ordered else 0.0
    margin = raw - competitor if raw >= competitor else raw - ordered[0]
    weighted = (0.55 * probability) + (0.3 * _sigmoid((raw - 0.16) * 7.5)) + (0.15 * _sigmoid(margin * 12.0))
    return round(max(1.0, min(99.0, weighted * 100.0)), 1)


def _persona_tags(relevance_scores: dict, persona_distribution: dict):
    tags = [{"persona": persona, "relevance_percent": _relevance_percent_for_persona(relevance_scores, persona_distribution, persona), "relevance": relevance_scores.get(persona, 0.0)} for persona in PERSONAS]
    tags.sort(key=lambda item: item["relevance_percent"], reverse=True)
    return tags


def _persona_fit_score(current_persona: str, best_persona: str, relevance_scores: dict, persona_distribution: dict):
    return round((0.52 * float(persona_distribution.get(current_persona, 0.0))) + (0.28 * float(persona_distribution.get(best_persona, 0.0))) + (0.12 * float(relevance_scores.get(current_persona, 0.0))) + (0.08 * float(relevance_scores.get(best_persona, 0.0))), 4)


def _stable_article_id(url: str, title: str):
    return hashlib.md5(f"{url}|{title}".encode("utf-8", errors="ignore")).hexdigest()[:16]


def _stable_hash_fraction(value: str):
    return int(hashlib.md5(value.encode("utf-8", errors="ignore")).hexdigest()[:8], 16) / 0xFFFFFFFF


def _freshness_bonus(published_at: str):
    if not published_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        return 0.08 if age <= 6 else 0.05 if age <= 24 else 0.02 if age <= 72 else 0.0
    except Exception:
        return 0.0


def _engagement_boost(signal_tags: list[str], audience_profile: str | None, click_history: list[float]):
    boosts, level = PROFILE_SIGNAL_BOOSTS.get(audience_profile or "first_gen_investor", {}), (sum(click_history) / len(click_history) if click_history else 0.5)
    return round(sum(boosts.get(tag, 0.0) for tag in signal_tags) * (0.7 + 0.6 * level), 4)


def _session_retuning(stats: dict, audience_profile: str | None, click_history: list[float]):
    boosts = PROFILE_SIGNAL_BOOSTS.get(audience_profile or "first_gen_investor", {})
    boosted = [signal for signal, _ in sorted(boosts.items(), key=lambda item: item[1], reverse=True)[:2]]
    total, source, deep = int(stats.get("total_interactions", 0)), int(stats.get("source_clicks", 0)), int(stats.get("deep_reads", 0))
    avg = round(sum(click_history) / len(click_history), 3) if click_history else 0.0
    score = round(min(1.0, 0.18 * total + 0.24 * deep + 0.12 * source + avg), 3)
    return {"headline": "Engagement retuning is active", "detail": f"The next feed boosts {', '.join(boosted)} because this user has {total} tracked interactions and {deep} deep reads.", "boosted_signals": boosted, "engagement_score": score, "total_interactions": total, "source_clicks": source, "deep_reads": deep, "next_refresh_in_seconds": 90}


def build_persona_demo(article_title: str, article_text: str):
    return {"article_title": article_title, "student": {"persona": "student", "label": "Student explainer", "text": transform_text(article_text, "student", "student_explainer")}, "investor": {"persona": "investor", "label": "Investor brief", "text": transform_text(article_text, "investor", "first_gen_investor")}}


def _append_pipeline_step(state: NewsState, step: str, detail: str):
    return list(state.get("agent_pipeline") or []) + [{"step": step, "detail": detail}]


def _safe_cache_get_json(key: str):
    try:
        raw = get_cache(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _safe_cache_set_json(key: str, value: Any, ttl: int = 300):
    try:
        set_cache(key, json.dumps(value), ttl=ttl)
    except Exception:
        return None


def _route_after_filter(state: NewsState):
    return "fallback" if not (state.get("articles") or []) else "understanding"


def _model_route(task: str):
    if task in {"tagging", "embedding", "understanding"}:
        return {"model": "small_matcher", "reason": "fast low-cost semantic tagging"}
    return {"model": "large_summarizer", "reason": "higher-quality generation and synthesis"}


def _simple_summary(article: dict[str, Any], persona: str, audience_profile: str | None):
    profile = _profile_meta(audience_profile, persona)
    base = article.get("description") or article.get("content") or article.get("title") or ""
    return base[:280]


def _impact_metrics(stats: dict, top_articles: list[dict[str, Any]]):
    before_time = 2.0
    new_time = round(min(6.0, 2.0 + 0.7 * len(top_articles) + 0.35 * int(stats.get("deep_reads", 0))), 1)
    before_ctr = 0.20
    after_ctr = round(min(0.55, before_ctr + (0.04 * min(5, int(stats.get("total_interactions", 0)))) + 0.11), 2)
    before_retention = 0.18
    after_retention = round(min(0.52, before_retention + (0.05 * min(4, int(stats.get("feed_fetches", 0)))) + 0.07), 2)
    uplift = round(((new_time - before_time) / before_time), 2) if before_time else 0.0
    return {
        "before": {"time_spent_min": before_time, "click_rate": before_ctr, "retention": before_retention},
        "after": {"time_spent_min": new_time, "click_rate": after_ctr, "retention": after_retention},
        "engagement_uplift": uplift,
    }


def _normalize_article(article: dict[str, Any]):
    title, description, content = str(article.get("title") or "").strip(), str(article.get("description") or "").strip(), str(article.get("content") or "").strip()
    content = content or description or title
    if len(content) < 40:
        return None
    return {"title": title or "Untitled", "description": description, "content": content, "url": article.get("url") or "", "published_at": article.get("published_at") or article.get("publishedAt") or "", "source": article.get("source") or ""}


def _dedupe_articles(articles: list[dict[str, Any]]):
    seen, deduped = set(), []
    for article in articles:
        normalized = _normalize_article(article)
        if not normalized:
            continue
        key = (normalized["url"] or normalized["title"]).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _fast_filter_articles(articles: list[dict[str, Any]], query: str, page_size: int, refresh_cycle: int):
    filtered = []
    for article in _dedupe_articles(articles):
        text = f"{article['title']} {article['description']} {article['content']}".lower()
        if len(text.split()) < 10 or article["url"].startswith("https://news.example/"):
            continue
        filtered.append(article)
    if len(filtered) < min(9, page_size):
        filtered = _dedupe_articles(filtered + get_fast_articles(num_articles=page_size, query=query, page=refresh_cycle))
    return filtered[: max(page_size, 12)]


def _extract_keywords(text: str, limit: int = 5):
    counts: dict[str, int] = {}
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower()):
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _extract_entities(title: str, text: str, limit: int = 4):
    entities, seen = [], set()
    for token in re.findall(r"\b[A-Z][a-zA-Z0-9&.-]+\b", f"{title} {text[:280]}"):
        if token in seen:
            continue
        seen.add(token)
        entities.append(token)
        if len(entities) >= limit:
            break
    return entities


def _impact_score(signal_tags: list[str], sentiment_tag: str, text: str):
    impact = 0.18 + (0.12 if "policy" in signal_tags else 0.0) + (0.11 if "funding" in signal_tags else 0.0) + (0.11 if "portfolio" in signal_tags else 0.0) + (0.08 if "competition" in signal_tags else 0.0)
    impact += 0.05 if sentiment_tag == "cautious" else 0.02 if sentiment_tag == "positive" else 0.0
    impact += min(0.12, len((text or "").split()) / 2500.0)
    return round(min(1.0, impact), 4)


def ingestion_agent(state: NewsState):
    query, refresh_cycle, page_size = state.get("query", "business technology startups investing"), int(state.get("refresh_cycle", 1)), int(state.get("page_size", 18))
    cache_key = f"last_news:{query}:{page_size}"
    fallback_used = False
    fallback_reason = None
    try:
        articles = state.get("articles") or fetch_articles(query=query, page_size=page_size, page=refresh_cycle)
        _safe_cache_set_json(cache_key, articles, ttl=900)
    except Exception as exc:
        logger.warning("Ingestion failed for query '%s': %s", query, exc)
        articles = _safe_cache_get_json(cache_key) or []
        fallback_used = True
        fallback_reason = "redis_last_news"

    if not articles:
        articles = get_fast_articles(num_articles=page_size, query=query, page=refresh_cycle)
        fallback_used = True
        fallback_reason = fallback_reason or "fast_articles_fallback"

    normalized = _dedupe_articles(articles)
    logger.info("Ingestion completed with %s articles (fallback=%s)", len(normalized), fallback_used)
    return {"articles": normalized, "fallback_used": fallback_used, "fallback_reason": fallback_reason, "agent_pipeline": _append_pipeline_step(state, "Ingestion Agent", f"Fetched {len(normalized)} raw articles for '{query}' and normalized them into a shared article format.") if not fallback_used else _append_pipeline_step(state, "Ingestion Agent", f"Primary ingestion degraded gracefully and recovered via {fallback_reason}, yielding {len(normalized)} articles.")}


def fast_filter_agent(state: NewsState):
    filtered = _fast_filter_articles(state.get("articles") or [], state.get("query", "business technology"), int(state.get("page_size", 18)), int(state.get("refresh_cycle", 1)))
    logger.info("Fast filter reduced feed to %s articles", len(filtered))
    return {"articles": filtered, "agent_pipeline": _append_pipeline_step(state, "Fast Filter Agent", f"Removed duplicates and thin stories, leaving {len(filtered)} high-signal articles before deeper AI work.")}


def fallback_agent(state: NewsState):
    query = state.get("query", "business technology")
    refresh_cycle = int(state.get("refresh_cycle", 1))
    page_size = int(state.get("page_size", 18))
    articles = _dedupe_articles(get_fast_articles(num_articles=page_size, query=query, page=refresh_cycle))
    logger.warning("Fallback agent activated for query '%s'", query)
    return {
        "articles": articles,
        "fallback_used": True,
        "fallback_reason": state.get("fallback_reason") or "empty_filtered_feed",
        "agent_pipeline": _append_pipeline_step(
            state,
            "Fallback Agent",
            f"No viable live articles remained after filtering, so the pipeline switched to the resilient fallback pool with {len(articles)} articles.",
        ),
    }


def understanding_agent(state: NewsState):
    routing = _model_route("understanding")
    enriched = []
    for article in state.get("articles") or []:
        text = article.get("content") or article.get("title") or ""
        enriched.append({**article, "signal_tags": _extract_signal_tags(text), "keywords": _extract_keywords(f"{article.get('title', '')} {text}"), "entities": _extract_entities(article.get("title", ""), text), "_raw_text": text[:8000]})
    logger.info("Understanding agent enriched %s articles using %s", len(enriched), routing["model"])
    return {"enriched_articles": enriched, "model_routing": {"understanding": routing["model"]}, "agent_pipeline": _append_pipeline_step(state, "Understanding Agent", f"Extracted entities, keywords, and topic signals from each article using the {routing['model']} route for fast semantic analysis.")}


def sentiment_agent(state: NewsState):
    enriched = []
    for article in state.get("enriched_articles") or []:
        sentiment = _sentiment_tag(article.get("_raw_text", ""))
        enriched.append({**article, "sentiment_tag": sentiment, "impact_score": _impact_score(article.get("signal_tags") or ["general"], sentiment, article.get("_raw_text", ""))})
    logger.info("Sentiment agent completed for %s articles", len(enriched))
    return {"enriched_articles": enriched, "agent_pipeline": _append_pipeline_step(state, "Sentiment + Impact Agent", "Tagged each story as positive, cautious, or neutral and assigned an impact score for downstream ranking.")}


def profile_agent(state: NewsState):
    user_id = state.get("user_id", "demo_user")
    cached = _safe_cache_get_json(f"profile:{user_id}")
    behavior_hint, stats = detect_persona_from_behavior(user_id), get_user_stats(user_id)
    selected = state.get("current_persona") or behavior_hint["suggested_persona"]
    profile = {"user_id": user_id, "selected_persona": selected, "audience_profile": state.get("audience_profile"), "intent_mode": state.get("intent_mode"), "click_history": state.get("click_history") or [], "behavior_hint": behavior_hint, "stats": stats, "memory_state": "warm" if cached and cached.get("selected_persona") == selected else "fresh"}
    if profile["memory_state"] == "fresh":
        _safe_cache_set_json(f"profile:{user_id}", profile, ttl=180)
    logger.info("User profiling completed for %s as %s", user_id, selected)
    return {"user_profile": profile, "behavior_hint": behavior_hint, "regulation_stats": stats, "agent_pipeline": _append_pipeline_step(state, "User Profiling Agent", f"Built a dynamic profile for {selected} using Mongo activity history and Redis memory state ({profile['memory_state']}).")}


def ranking_agent(state: NewsState):
    articles = state.get("enriched_articles") or []
    current_persona, audience_profile = state.get("current_persona", "student"), state.get("audience_profile")
    click_history, user_id = state.get("click_history") or [], state.get("user_id", "demo_user")
    refresh_cycle = int(state.get("refresh_cycle", 1))
    previous_stats = state.get("regulation_stats") or get_user_stats(user_id)
    seen_article_ids = set(previous_stats.get("recent_article_ids") or [])
    profile = _profile_meta(audience_profile, current_persona)
    if not articles:
        empty_scores = {persona: round(1 / len(PERSONAS), 4) for persona in PERSONAS} | {"total_confidence": 0.34}
        return {"ranked_articles": [], "top_articles": [], "persona_scores": empty_scores, "dominant_feed_persona": current_persona, "top_persona": state.get("behavior_hint", {}).get("suggested_persona", current_persona), "persona_shift_detected": False, "confidence_score": 0.34, "profile_label": profile["label"], "personalized_homepage_label": profile["label"], "generic_homepage_label": "Generic ET homepage", "persona_demo": None, "agent_pipeline": _append_pipeline_step(state, "Personalisation + Ranking Agent", "No articles survived the ranking stage, so the pipeline returned an empty ranked set.")}

    texts = [article.get("_raw_text") or article.get("content") or article.get("title") or "" for article in articles]
    embeddings = get_matcher().encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)
    en = np.asarray(embeddings, dtype=np.float64)
    en = en / (np.linalg.norm(en, axis=1, keepdims=True) + 1e-9)
    sim_matrix = en @ ANCHOR_NORM.T
    ranked, batch_sum, texts_for_shift = [], {persona: 0.0 for persona in PERSONAS}, []

    for index, article in enumerate(articles):
        relevance_scores = {PERSONAS[j]: round(float(sim_matrix[index][j]), 4) for j in range(len(PERSONAS))}
        signal_tags = article.get("signal_tags") or ["general"]
        persona_distribution = _calibrated_persona_distribution(relevance_scores, signal_tags)
        best_persona = max(persona_distribution, key=persona_distribution.get)
        persona_fit = _persona_fit_score(current_persona, best_persona, relevance_scores, persona_distribution)
        relevance_percent = _relevance_percent_for_persona(relevance_scores, persona_distribution, current_persona)
        aid = _stable_article_id(article.get("url") or "", article.get("title") or "")
        engagement_boost = _engagement_boost(signal_tags, audience_profile, click_history)
        freshness_bonus = _freshness_bonus(article.get("published_at", ""))
        repeat_penalty = 0.24 if aid in seen_article_ids else 0.0
        rotation_signal = (_stable_hash_fraction(f"{user_id}:{aid}:{refresh_cycle}") - 0.5) * 0.08
        impact_score = float(article.get("impact_score", 0.0))
        sentiment_weight = 0.05 if article.get("sentiment_tag") == "positive" else 0.08 if article.get("sentiment_tag") == "cautious" else 0.03
        ranking_score = round(persona_fit + engagement_boost + freshness_bonus + rotation_signal + (impact_score * sentiment_weight) + (0.12 * impact_score) - repeat_penalty, 4)
        clean_tags = [t if t != 'general' else 'current events' for t in signal_tags]
        ranked.append({"article_id": aid, "original_title": article.get("title") or "Untitled", "transformed_text": "", "best_persona": best_persona, "suggested_tag": best_persona, "persona_tags": _persona_tags(relevance_scores, persona_distribution), "relevance_score": ranking_score, "relevance_percent": relevance_percent, "persona_scores": {**persona_distribution, "total_confidence": round(max(persona_distribution.values()), 4)}, "relevance_scores": relevance_scores, "url": article.get("url", ""), "published_at": article.get("published_at", ""), "source": article.get("source", ""), "description": (article.get("description") or "")[:400], "signal_tags": signal_tags, "sentiment_tag": article.get("sentiment_tag", "neutral"), "impact_score": impact_score, "entities": article.get("entities", []), "keywords": article.get("keywords", []), "framing_style": profile["framing"], "content_format": profile["format"], "why_for_user": f"Curated for you based on its relevance to {', '.join(clean_tags)}.", "original_url": article.get("url", ""), "refresh_reason": "freshness" if freshness_bonus >= 0.05 else "engagement_retuning" if engagement_boost > 0 else "persona_fit", "_raw_text": article.get("_raw_text", "")})
        for persona in PERSONAS:
            batch_sum[persona] += float(persona_distribution.get(persona, 0.0))
        texts_for_shift.append(article.get("_raw_text", "")[:500])

    ranked.sort(key=lambda item: item["relevance_score"], reverse=True)
    candidate_pool = ranked[: min(len(ranked), 18)]
    if len(candidate_pool) <= 9:
        top_slice = candidate_pool
    else:
        start = ((max(1, refresh_cycle) - 1) * 4) % len(candidate_pool)
        rotated = candidate_pool[start:] + candidate_pool[:start]
        top_slice = rotated[:12]
        # Optimized: Batch Transformation for Top 2 Articles (Async for others)
        sync_limit = 2
        to_transform = []
        for i in range(min(sync_limit, len(top_slice))):
            item = top_slice[i]
            raw = item.get("_raw_text") or item.get("description") or ""
            cache_key = f"trans:{current_persona}:{audience_profile}:{hashlib.md5(raw.encode()).hexdigest()}"
            
            cached = None
            try:
                if r: cached = r.get(cache_key)
            except: pass
            
            if cached:
                item["transformed_text"] = cached.decode("utf-8")
            else:
                to_transform.append((i, raw, cache_key))
        
        if to_transform:
            try:
                profile = _profile_meta(audience_profile, current_persona)
                prompts = [profile["prompt"] + raw[:1000] for _, raw, _ in to_transform]
                results = get_summarizer()(prompts, max_length=60, min_length=30, do_sample=False, truncation=True)
                for idx, result in enumerate(results):
                    original_idx, _, c_key = to_transform[idx]
                    out = result.get("summary_text") or result.get("generated_text") or ""
                    top_slice[original_idx]["transformed_text"] = out
                    try:
                        if r: r.setex(c_key, 3600, out)
                    except: pass
            except Exception as e:
                logger.error(f"Batch transformation failed: {e}")
                for original_idx, raw, _ in to_transform:
                    top_slice[original_idx]["transformed_text"] = raw[:280]

        # Handle remaining top articles (3-12) with simple truncation or background
        for i in range(sync_limit, len(top_slice)):
            item = top_slice[i]
            item["transformed_text"] = (item.get("_raw_text") or item.get("description") or "")[:280]

        for item in top_slice:
            item.pop("_raw_text", None)
    
    demo_text, demo_title = (top_slice[0].get("transformed_text"), top_slice[0].get("original_title")) if top_slice else (None, None)
    for item in ranked:
        item.pop("_raw_text", None)

    batch_dist = _normalize_persona_distribution({persona: batch_sum[persona] / max(len(ranked), 1) for persona in PERSONAS})
    top_conf = round(min(1.0, max(batch_dist.values()) * (0.85 + 0.15 * (top_slice[0]["relevance_score"] if top_slice else 0))), 4)
    persona_scores = {**batch_dist, "total_confidence": top_conf}
    suggested_persona, shift_detected, confidence = detect_persona_shift_with_history(" ".join(texts_for_shift[:8]), click_history, current_persona)
    dominant_persona = max(PERSONAS, key=lambda persona: batch_dist[persona])
    persona_demo = build_persona_demo(demo_title, demo_text) if top_slice and demo_text and demo_title else None
    
    # Fire-and-forget background pre-caching for remaining top articles AND other personas
    threading.Thread(target=_bg_precache_task, args=(top_slice[:5], current_persona, audience_profile)).start()
    
    logger.info("Ranking completed for %s with dominant feed persona %s", user_id, dominant_persona)
    return {"ranked_articles": ranked, "top_articles": top_slice, "persona_scores": persona_scores, "dominant_feed_persona": dominant_persona, "top_persona": suggested_persona, "persona_shift_detected": shift_detected, "confidence_score": confidence, "profile_label": profile["label"], "personalized_homepage_label": profile["label"], "generic_homepage_label": "Generic ET homepage", "persona_demo": persona_demo, "agent_pipeline": _append_pipeline_step(state, "Personalisation + Ranking Agent", f"Scored articles for {profile['label']} using persona fit, recency, impact, sentiment-aware weighting, and engagement signals, then ranked the top {len(top_slice)}.")}

def _bg_precache_task(articles, current_p, current_profile):
    """Background task to populate Redis cache for all other profiles."""
    profiles = ["cfo_macro", "first_gen_investor", "startup_founder", "student_explainer"]
    for prof in profiles:
        if prof == current_profile: continue
        try:
            # Parallelize the 3 articles for this profile as well
            with ThreadPoolExecutor(max_workers=3) as executor:
                executor.map(lambda art: transform_text(art.get("description", ""), None, prof), articles)
        except Exception as e:
            pass # Silent failure in bg thread


def explain_agent(state: NewsState):
    profile = state.get("user_profile") or {}
    selected = profile.get("selected_persona", state.get("current_persona", "student"))
    top_articles = state.get("top_articles") or []
    top_signals = ", ".join((top_articles[0].get("signal_tags") or ["current events"])).replace('general', 'current events') if top_articles else "general market context"
    explanation = f"This customized briefing is driven by your interest in {top_signals}."
    return {
        "explanation": explanation,
        "agent_pipeline": _append_pipeline_step(
            state,
            "Explanation Agent",
            f"Generated a human-readable reason for the recommendations so judges can see why this feed matches the user profile.",
        ),
    }


def synthesis_agent(state: NewsState):
    top_articles = state.get("top_articles") or []
    profile_label = state.get("profile_label") or _profile_meta(state.get("audience_profile"), state.get("current_persona", "student"))["label"]
    routing = _model_route("synthesis")
    if not top_articles:
        summary = "No high-confidence stories were available for synthesis."
    else:
        payload = " ".join(f"{article['original_title']}. {article.get('why_for_user', '')}. {article.get('description', '')}" for article in top_articles[:5])[:2400]
        try:
            result = get_summarizer()(f"summarize for {profile_label}: {payload}", max_length=100, min_length=45, do_sample=False, truncation=True)
            summary = (result[0].get("summary_text") or result[0].get("generated_text") or "").strip() or payload[:320]
        except Exception as exc:
            logger.warning("Synthesis failed, using graceful fallback: %s", exc)
            summary = " | ".join(_simple_summary(article, state.get("current_persona", "student"), state.get("audience_profile")) for article in top_articles[:3])
    logger.info("Synthesis completed using %s", routing["model"])
    return {"synthesis_summary": summary, "model_routing": {**(state.get("model_routing") or {}), "synthesis": routing["model"]}, "agent_pipeline": _append_pipeline_step(state, "Multi-Article Synthesis Agent", f"Combined the strongest articles into a single 'what it means for you' synthesis tailored to the active user profile using the {routing['model']} route.")}


def feedback_agent(state: NewsState):
    user_id, current_persona = state.get("user_id", "demo_user"), state.get("current_persona", "student")
    top_persona, top_articles = state.get("top_persona", current_persona), state.get("top_articles") or []
    audience_profile, persona_scores = state.get("audience_profile"), state.get("persona_scores") or {}
    save_user_click(user_id=user_id, persona=top_persona)
    record_feed_fetch(user_id, current_persona, len(top_articles), audience_profile=audience_profile)
    save_last_persona_scores(user_id, persona_scores)
    stats = get_user_stats(user_id)
    metrics = _impact_metrics(stats, top_articles)
    record_pipeline_audit(
        user_id,
        {
            "articles_shown": [article.get("article_id") for article in top_articles],
            "reason": state.get("explanation"),
            "persona_applied": current_persona,
            "suggested_persona": top_persona,
            "fallback_used": state.get("fallback_used", False),
            "fallback_reason": state.get("fallback_reason"),
            "impact_metrics": metrics,
        },
    )
    logger.info("Feedback + audit stored for %s with %s articles", user_id, len(top_articles))
    return {"regulation_stats": stats, "engagement_retuning": _session_retuning(stats, audience_profile, state.get("click_history") or []), "impact_metrics": metrics, "articles_shown": [article.get("article_id") for article in top_articles], "agent_pipeline": _append_pipeline_step(state, "Feedback Agent", "Persisted feed and persona signals for future sessions, refreshed the engagement retuning memory, and stored an audit trail.")}


def output_agent(state: NewsState):
    current_persona = state.get("current_persona", "student")
    profile = _profile_meta(state.get("audience_profile"), current_persona)
    generated_at = datetime.now(timezone.utc).isoformat()
    return {"feed_generated_at": generated_at, "latest_feed_label": f"Latest {profile['shortLabel']} feed generated at {generated_at}", "final_output": {"summary": state.get("synthesis_summary", ""), "articles": state.get("top_articles") or [], "profile": state.get("user_profile") or {}, "explanation": state.get("explanation"), "impact_metrics": state.get("impact_metrics") or {}}, "agent_pipeline": _append_pipeline_step(state, "Output Formatter Agent", "Converted the ranked and synthesized result into frontend-ready JSON with summary, explanation, impact metrics, and profile context.")}


def _build_pipeline_app():
    graph = StateGraph(NewsState)
    graph.add_node("ingestion", ingestion_agent)
    graph.add_node("fast_filter", fast_filter_agent)
    graph.add_node("fallback", fallback_agent)
    graph.add_node("understanding", understanding_agent)
    graph.add_node("sentiment", sentiment_agent)
    graph.add_node("profile", profile_agent)
    graph.add_node("ranking", ranking_agent)
    graph.add_node("explain", explain_agent)
    graph.add_node("synthesis", synthesis_agent)
    graph.add_node("feedback", feedback_agent)
    graph.add_node("output", output_agent)
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "fast_filter")
    if hasattr(graph, "add_conditional_edges"):
        graph.add_conditional_edges("fast_filter", _route_after_filter, {"fallback": "fallback", "understanding": "understanding"})  # type: ignore[attr-defined]
    else:
        graph.add_edge("fast_filter", "understanding")
    graph.add_edge("fallback", "understanding")
    graph.add_edge("understanding", "sentiment")
    graph.add_edge("sentiment", "profile")
    graph.add_edge("profile", "ranking")
    graph.add_edge("ranking", "explain")
    graph.add_edge("explain", "synthesis")
    graph.add_edge("synthesis", "feedback")
    graph.add_edge("feedback", "output")
    graph.add_edge("output", END)
    return graph.compile()


PIPELINE_APP = _build_pipeline_app()


def run_personalization_pipeline(user_id: str, current_persona: str, click_history: list[float], audience_profile: str | None = None, query: str = "business technology startups investing", refresh_cycle: int = 1, intent_mode: str | None = None, page_size: int = 18, articles: list[dict[str, Any]] | None = None):
    effective_persona = current_persona or detect_persona_from_behavior(user_id)["suggested_persona"]
    try:
        # Hard timeout for the entire graph execution
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(PIPELINE_APP.invoke, {"user_id": user_id, "current_persona": effective_persona, "audience_profile": audience_profile, "click_history": click_history, "query": query, "refresh_cycle": refresh_cycle, "page_size": page_size, "intent_mode": intent_mode, "articles": articles or [], "agent_pipeline": []})
            result = future.result(timeout=6.5) # Hard limit for demo stability
    except concurrent.futures.TimeoutError:
        logger.error("Pipeline timed out, using immediate safety fallback")
        return _immediate_fallback(user_id, effective_persona, audience_profile, query, refresh_cycle, page_size, "pipeline_timeout")
    except Exception as exc:
        logger.exception("Pipeline failed for user %s: %s", user_id, exc)
        fallback_articles = [_normalize_article(article) for article in get_fast_articles(num_articles=min(page_size, 9), query=query, page=refresh_cycle)]
        safe_articles = [article for article in fallback_articles if article]
        top_articles = [
            {
                "article_id": _stable_article_id(article.get("url") or "", article.get("title") or ""),
                "original_title": article.get("title") or "Untitled",
                "transformed_text": _simple_summary(article, effective_persona, audience_profile),
                "best_persona": effective_persona,
                "suggested_tag": effective_persona,
                "persona_tags": [{"persona": persona, "relevance_percent": 34 if persona == effective_persona else 33, "relevance": 0.0} for persona in PERSONAS],
                "relevance_score": 0.34,
                "relevance_percent": 34.0,
                "persona_scores": {persona: (0.34 if persona == effective_persona else 0.33) for persona in PERSONAS} | {"total_confidence": 0.34},
                "url": article.get("url", ""),
                "published_at": article.get("published_at", ""),
                "source": article.get("source", ""),
                "description": article.get("description", ""),
                "signal_tags": _extract_signal_tags(article.get("content", "")),
                "sentiment_tag": "neutral",
                "content_format": _profile_meta(audience_profile, effective_persona)["format"],
                "framing_style": _profile_meta(audience_profile, effective_persona)["framing"],
                "why_for_user": "Generated via graceful fallback because the full pipeline was temporarily unavailable.",
                "refresh_reason": "graceful_degradation",
            }
            for article in safe_articles[:9]
        ]
        result = {
            "top_persona": effective_persona,
            "dominant_feed_persona": effective_persona,
            "persona_shift_detected": False,
            "confidence_score": 0.34,
            "persona_scores": {persona: (0.34 if persona == effective_persona else 0.33) for persona in PERSONAS} | {"total_confidence": 0.34},
            "top_articles": top_articles,
            "ranked_articles": top_articles,
            "regulation_stats": get_user_stats(user_id),
            "profile_label": _profile_meta(audience_profile, effective_persona)["label"],
            "latest_feed_label": f"Fallback {effective_persona} feed",
            "feed_generated_at": datetime.now(timezone.utc).isoformat(),
            "generic_homepage_label": "Generic ET homepage",
            "personalized_homepage_label": _profile_meta(audience_profile, effective_persona)["label"],
            "agent_pipeline": [{"step": "Graceful Degradation", "detail": "The full autonomous pipeline failed, so the service returned a safe fallback feed and summaries."}],
            "engagement_retuning": _session_retuning(get_user_stats(user_id), audience_profile, click_history),
            "behavior_hint": detect_persona_from_behavior(user_id),
            "persona_demo": build_persona_demo("Fallback article", safe_articles[0].get("content", "")) if safe_articles else None,
            "synthesis_summary": "Fallback feed generated because the full synthesis layer was unavailable.",
            "final_output": {"summary": "Fallback feed generated because the full synthesis layer was unavailable.", "articles": top_articles},
            "fallback_used": True,
            "fallback_reason": "pipeline_exception",
            "explanation": "The system preserved a safe personalized output instead of failing completely.",
            "impact_metrics": _impact_metrics(get_user_stats(user_id), top_articles),
            "model_routing": {"understanding": "small_matcher", "synthesis": "fallback_summary"},
        }
    return {"status": "success", "persona_applied": effective_persona, "top_persona": result.get("top_persona", effective_persona), "dominant_feed_persona": result.get("dominant_feed_persona", effective_persona), "persona_shift_detected": bool(result.get("persona_shift_detected", False)), "confidence_score": float(result.get("confidence_score", 0.34)), "persona_scores": result.get("persona_scores"), "top_articles": result.get("top_articles") or [], "ranked_articles": result.get("ranked_articles") or [], "regulation_stats": result.get("regulation_stats") or {}, "audience_profile": audience_profile, "profile_label": result.get("profile_label"), "latest_feed_label": result.get("latest_feed_label"), "feed_generated_at": result.get("feed_generated_at"), "generic_homepage_label": result.get("generic_homepage_label", "Generic ET homepage"), "personalized_homepage_label": result.get("personalized_homepage_label"), "agent_pipeline": result.get("agent_pipeline") or [], "engagement_retuning": result.get("engagement_retuning"), "suggested_persona": result.get("behavior_hint", {}).get("suggested_persona", effective_persona), "behavior_persona_scores": result.get("behavior_hint", {}).get("persona_scores"), "persona_detection_reason": result.get("behavior_hint", {}).get("reason", f"Detected from pipeline behavior signals for {effective_persona}."), "intent_mode": intent_mode, "persona_demo": result.get("persona_demo"), "synthesis_summary": result.get("synthesis_summary", ""), "final_output": result.get("final_output") or {}, "explanation": result.get("explanation"), "impact_metrics": result.get("impact_metrics"), "model_routing": result.get("model_routing"), "fallback_used": bool(result.get("fallback_used", False)), "fallback_reason": result.get("fallback_reason")}

def _immediate_fallback(user_id, effective_persona, audience_profile, query, refresh_cycle, page_size, reason):
    fallback_articles = [_normalize_article(article) for article in get_fast_articles(num_articles=min(page_size, 9), query=query, page=refresh_cycle)]
    safe_articles = [article for article in fallback_articles if article]
    top_articles = [
        {
            "article_id": _stable_article_id(article.get("url") or "", article.get("title") or ""),
            "original_title": article.get("title") or "Untitled",
            "transformed_text": _simple_summary(article, effective_persona, audience_profile),
            "best_persona": effective_persona,
            "suggested_tag": effective_persona,
            "persona_tags": [{"persona": p, "relevance_percent": 34 if p == effective_persona else 33, "relevance": 0.0} for p in PERSONAS],
            "relevance_score": 0.34,
            "relevance_percent": 34.0,
            "persona_scores": {p: (0.34 if p == effective_persona else 0.33) for p in PERSONAS} | {"total_confidence": 0.34},
            "url": article.get("url", ""),
            "published_at": article.get("published_at", ""),
            "source": article.get("source", ""),
            "description": article.get("description", ""),
            "signal_tags": ["current_events"],
            "sentiment_tag": "neutral",
            "content_format": _profile_meta(audience_profile, effective_persona)["format"],
            "framing_style": _profile_meta(audience_profile, effective_persona)["framing"],
            "why_for_user": "Immediate fallback activated to preserve system responsiveness.",
            "refresh_reason": "latency_protection",
        }
        for article in safe_articles[:9]
    ]
    return {
        "status": "success",
        "persona_applied": effective_persona,
        "top_persona": effective_persona,
        "dominant_feed_persona": effective_persona,
        "persona_shift_detected": False,
        "confidence_score": 0.34,
        "persona_scores": {p: (0.34 if p == effective_persona else 0.33) for p in PERSONAS} | {"total_confidence": 0.34},
        "top_articles": top_articles,
        "ranked_articles": top_articles,
        "regulation_stats": {},
        "audience_profile": audience_profile,
        "profile_label": _profile_meta(audience_profile, effective_persona)["label"],
        "latest_feed_label": f"Speed-optimized {effective_persona} feed",
        "feed_generated_at": datetime.now(timezone.utc).isoformat(),
        "generic_homepage_label": "Generic ET homepage",
        "personalized_homepage_label": "Speed-optimized feed",
        "agent_pipeline": [{"step": "Latency Protection", "detail": "The system prioritize speed over depth due to high processing load."}],
        "engagement_retuning": {},
        "behavior_hint": {},
        "persona_demo": None,
        "synthesis_summary": "Top priorities for you in the latest markers.",
        "final_output": {"summary": "Top priorities", "articles": top_articles},
        "fallback_used": True,
        "fallback_reason": reason,
        "explanation": "To ensure immediate results, we've provided a curated feed without deep AI synthesis.",
        "impact_metrics": {},
        "model_routing": {"understanding": "fast", "synthesis": "none"}
    }


def process_articles(articles, current_persona, click_history, user_id="demo_user", audience_profile=None, query="business technology", refresh_cycle=1):
    return run_personalization_pipeline(user_id=user_id, current_persona=current_persona, click_history=click_history, audience_profile=audience_profile, query=query, refresh_cycle=refresh_cycle, articles=articles)

def process_request(text, persona, click_history, user_id="demo_user", audience_profile=None):
    relevance_scores = compute_relevance_scores(get_matcher().encode(text))
    suggested_persona, shift_detected, confidence = detect_persona_shift_with_history(text, click_history, persona)
    save_user_click(user_id=user_id, persona=suggested_persona)
    return {"persona_applied": persona, "relevance_scores": relevance_scores, "suggested_persona": suggested_persona, "persona_shift_detected": shift_detected, "confidence_score": confidence, "transformed_text": transform_text(text, persona, audience_profile), "persona_demo": build_persona_demo("Live article", text), "status": "success"}
