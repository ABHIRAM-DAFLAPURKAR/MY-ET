from sentence_transformers import util

from app.services.model_loader import get_matcher
from app.config.persona_config import ANCHORS


def detect_persona_shift_with_history(text, click_history, current_persona):
    if not text or not str(text).strip():
        return current_persona, False, 0.0

    text_vec = get_matcher().encode(str(text))

    scores = {}
    for persona, anchor_vec in ANCHORS.items():
        score = util.cos_sim(text_vec, anchor_vec).item()
        scores[persona] = score

    best_persona = max(scores, key=scores.get)
    best_score = scores[best_persona]

    if click_history:
        engagement = sum(click_history) / len(click_history)
    else:
        engagement = 0.35

    confidence = round(min(1.0, max(0.0, best_score * (0.5 + 0.5 * engagement))), 4)

    if best_persona != current_persona and best_score > 0.42 and engagement > 0.45:
        return best_persona, True, confidence

    return current_persona, False, confidence
