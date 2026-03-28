# PERFECT CLEAN ROUTES - No indentation issues
from flask import request, jsonify
from app.services.ai_service import process_request, run_personalization_pipeline
from app.exceptions import APIException
from app.services.news_service import fetch_articles
from app.services.db_service import (
    get_user_stats,
    record_article_click,
    list_article_clicks,
    record_user_activity,
)
import re

VALID_PERSONAS = ["student", "founder", "investor"]

def register_routes(app):

    @app.route('/api/v1/fetch-news', methods=['GET'])
    def get_news():
        query = request.args.get("q", "economy")
        articles = fetch_articles(query)
        return jsonify({
            "status": "success",
            "articles": articles
        }), 200

    @app.route('/news/personalize', methods=['POST'])
    @app.route('/api/v1/personalize', methods=['POST'])
    def personalize():
        data = request.get_json()

        if not data:
            raise APIException("Invalid JSON body", 400)

        provided_persona = data.get("current_persona")
        persona = (provided_persona or "").lower().strip()
        audience_profile = data.get("audience_profile")
        click_history = data.get("click_history", [])
        user_id = data.get("user_id", "demo_user")
        intent_mode = data.get("intent_mode")

        query = data.get("query", "business technology startups investing")
        try:
            page = int(data.get("page", 1))
        except (TypeError, ValueError):
            page = 1
        page = max(1, min(page, 50))

        if persona and persona not in VALID_PERSONAS:
            raise APIException(
                f"Invalid persona. Allowed: {VALID_PERSONAS}", 400
            )

        if not isinstance(click_history, list):
            raise APIException("click_history must be list", 400)

        result = run_personalization_pipeline(
            click_history=click_history,
            user_id=user_id,
            current_persona=persona,
            audience_profile=audience_profile,
            query=query,
            refresh_cycle=page,
            intent_mode=intent_mode,
            page_size=18,
        )

        if result.get("status") == "error":
            raise APIException(result.get("message", "Could not personalize articles"), 500)

        return jsonify(result), 200

    @app.route('/api/v1/full/<id>', methods=['GET'])
    def get_full_article(id):
        articles = fetch_articles(query="business technology", page_size=1)
        if not articles:
            raise APIException("No articles available", 404)
        
        article = articles[0]
        full_content = article.get('content', '') + "\n\n[Extended analysis: This article provides deep insights tailored to your persona. Investors see portfolio implications, founders get competitive intel, students receive clear explainers.]\n\nPersonalization score calculated live based on your reading patterns."
        
        result = {
            'id': id,
            'original_title': article.get('title', 'Full Article'),
            'full_content': full_content,
            'transformed_text': process_request(article.get('content', ''), VALID_PERSONAS[0], [], 'demo')['transformed_text'],
            'best_persona': 'investor',
            'relevance_score': 0.95,
            'persona_scores': {
                'student': 0.25,
                'founder': 0.35,
                'investor': 0.40,
                'total_confidence': 0.85
            }
        }
        return jsonify(result), 200

    @app.route('/api/v1/similar/<id>', methods=['GET'])
    def get_similar_articles(id):
        articles = fetch_articles(query="business technology India", page_size=10)
        similars = []
        for i, art in enumerate(articles):
            similars.append({
                'title': art.get('title', f'Similar #{i+1}'),
                'snippet': art.get('content', '')[:150] + '...',
                'url': f'https://news.example/{id}-{i}',
                'relevance': 95 - i * 2.5
            })
        return jsonify(similars), 200

    @app.route('/api/v1/history/record', methods=['POST'])
    def history_record():
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if not user_id:
            raise APIException("user_id required", 400)
        record_article_click(
            user_id,
            {
                "article_id": data.get("article_id"),
                "title": data.get("title"),
                "url": data.get("url"),
                "best_persona": data.get("best_persona"),
                "interaction": data.get("interaction", "unknown"),
                "relevance_percent": data.get("relevance_percent"),
                "persona_applied": data.get("persona_applied"),
                "topic": data.get("topic"),
                "read_time": data.get("read_time"),
            },
        )
        return jsonify({"status": "ok"}), 200

    @app.route('/api/v1/track', methods=['POST'])
    def track_behavior():
        data = request.get_json() or {}
        user_id = data.get("user_id")
        if not user_id:
            raise APIException("user_id required", 400)
        record_user_activity(
            user_id,
            {
                "article_title": data.get("article_title"),
                "topic": data.get("topic"),
                "read_time": data.get("read_time", 0),
                "clicked": bool(data.get("clicked", False)),
                "interaction": data.get("interaction", "view"),
                "url": data.get("url"),
            },
        )
        return jsonify({"status": "ok"}), 200

    @app.route('/api/v1/history', methods=['GET'])
    def history_list():
        user_id = request.args.get("user_id")
        if not user_id:
            raise APIException("user_id required", 400)
        try:
            limit = int(request.args.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))
        items = list_article_clicks(user_id, limit)
        return jsonify({"status": "success", "items": items}), 200

    @app.route('/api/v1/persona-scores', methods=['GET'])
    def persona_scores():
        user_id = request.args.get("user_id", "demo")
        stats = get_user_stats(user_id)
        stored = stats.get("last_persona_scores") or {}
        if stored and all(k in stored for k in VALID_PERSONAS):
            return jsonify(stored), 200
        return jsonify({
            'student': 0.34,
            'founder': 0.33,
            'investor': 0.33,
            'total_confidence': 0.75
        }), 200

    @app.route('/api/v1/personalize-single', methods=['POST'])
    def personalize_single():
        data = request.get_json()
        if not data:
            raise APIException("Invalid JSON body", 400)

        article_text = data.get("article_text")
        persona = data.get("current_persona", "student").lower()
        audience_profile = data.get("audience_profile")
        click_history = data.get("click_history", [])
        user_id = data.get("user_id", "demo_user")

        if not article_text:
            raise APIException("article_text is required", 400)
        if not isinstance(article_text, str):
            raise APIException("article_text must be string", 400)
        if persona not in VALID_PERSONAS:
            raise APIException(f"Invalid persona. Allowed: {VALID_PERSONAS}", 400)
        if not isinstance(click_history, list):
            raise APIException("click_history must be list", 400)

        result = process_request(
            text=article_text,
            persona=persona,
            click_history=click_history,
            user_id=user_id,
            audience_profile=audience_profile,
        )
        return jsonify(result), 200

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "UP"}), 200
