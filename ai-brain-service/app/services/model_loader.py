import hashlib
import os
from threading import Lock

import numpy as np

_matcher = None
_summarizer = None
_lock = Lock()
_VECTOR_SIZE = 96


def _tokenize(text: str):
    return [token for token in str(text).lower().split() if token]


def _hash_embed(text: str) -> np.ndarray:
    vec = np.zeros(_VECTOR_SIZE, dtype=np.float64)
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
        idx = digest[0] % _VECTOR_SIZE
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        weight = 1.0 + (digest[2] / 255.0)
        vec[idx] += sign * weight

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


class LightweightMatcher:
    def encode(self, texts, batch_size=32, show_progress_bar=False, convert_to_numpy=False):
        if isinstance(texts, str):
            encoded = _hash_embed(texts)
            return encoded if convert_to_numpy else encoded.tolist()

        rows = np.stack([_hash_embed(text) for text in texts], axis=0)
        return rows if convert_to_numpy else rows.tolist()


class LightweightSummarizer:
    def __call__(self, text, max_length=90, min_length=30, do_sample=False, truncation=True):
        source = str(text or "")
        prompt = source.split(": ", 1)[0] if ": " in source else ""
        payload = source.split(": ", 1)[1] if ": " in source else source

        prefix = ""
        if "CFO" in prompt:
            prefix = "[CFO Analytics] "
        elif "young investor" in prompt:
            prefix = "[Investor Guide] "
        elif "founder" in prompt:
            prefix = "[Founder Pulse] "
        elif "student" in prompt:
            prefix = "[Student Explainer] "

        words = payload.split()
        if not words:
            summary = ""
        else:
            max_words = max(min_length, min(max_length, 60))
            summary = prefix + " ".join(words[:max_words])
        return [{"generated_text": summary}]


def _load_transformer_matcher():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def _load_transformer_summarizer():
    from transformers import pipeline

    return pipeline(
        "text2text-generation",
        model="google/flan-t5-small",
    )


def _use_heavy_models() -> bool:
    return os.getenv("USE_TRANSFORMER_MODELS", "").lower() in {"1", "true", "yes"}


def get_matcher():
    global _matcher
    if _matcher is None:
        with _lock:
            if _matcher is None:
                if _use_heavy_models():
                    try:
                        _matcher = _load_transformer_matcher()
                    except Exception:
                        _matcher = LightweightMatcher()
                else:
                    _matcher = LightweightMatcher()
    return _matcher


def get_summarizer():
    global _summarizer
    if _summarizer is None:
        with _lock:
            if _summarizer is None:
                if _use_heavy_models():
                    try:
                        _summarizer = _load_transformer_summarizer()
                    except Exception:
                        _summarizer = LightweightSummarizer()
                else:
                    _summarizer = LightweightSummarizer()
    return _summarizer
