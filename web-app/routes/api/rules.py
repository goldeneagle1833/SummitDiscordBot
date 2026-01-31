"""Rules assistant API routes."""

import logging

from flask import Blueprint, jsonify, request

from utils.auth import require_auth

logger = logging.getLogger(__name__)

rules_bp = Blueprint("rules", __name__)

# Lazy-loaded rules assistant components
_rules_retriever = None
_rules_generator = None


def _get_rules_assistant():
    """Lazy load rules assistant components."""
    global _rules_retriever, _rules_generator

    if _rules_retriever is None or _rules_generator is None:
        try:
            from core.retriever import RulesRetriever
            from core.generator import RulesGenerator

            _rules_retriever = RulesRetriever()
            _rules_generator = RulesGenerator()
            _rules_generator.ensure_initialized()
        except Exception as e:
            logger.error(f"Failed to initialize Rules Assistant: {e}", exc_info=True)
            raise

    return _rules_retriever, _rules_generator


@rules_bp.route("/rules-assistant", methods=["POST"])
@require_auth
def rules_assistant():
    """API endpoint for Rules Assistant chat.

    Requires either:
    - Valid session (logged-in user from browser)
    - Valid API key (X-API-Key header for server-to-server calls)
    """
    try:
        data = request.get_json()
        question = data.get("question", "").strip()

        if not question:
            return jsonify({"success": False, "error": "Question is required"}), 400

        if len(question) > 500:
            return jsonify({
                "success": False,
                "error": "Question is too long (max 500 characters)"
            }), 400

        retriever, generator = _get_rules_assistant()

        retrieved_chunks = retriever.search(question, top_k=5)
        response = generator.generate(question, retrieved_chunks)

        return jsonify({
            "success": True,
            "answer": response.answer,
            "sources": response.sources
        })

    except Exception as e:
        logger.error(f"Rules Assistant API error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process your question. Please try again.",
        }), 500
