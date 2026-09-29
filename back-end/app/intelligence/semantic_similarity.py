import math
import re
from typing import Dict, List, Optional, Set, Tuple

from app.core.security_guard import sanitize_nlp_text

# Domain synonym maps to normalize terminology
SYNONYM_MAP: Dict[str, str] = {
    "subway": "underpass",
    "underpass": "underpass",
    "waterlogging": "flood",
    "waterlogged": "flood",
    "flooding": "flood",
    "floods": "flood",
    "flooded": "flood",
    "water": "flood",
    "inundated": "flood",
    "inundation": "flood",
    "downpour": "rain",
    "showers": "rain",
    "rainfall": "rain",
    "rains": "rain",
    "raining": "rain",
    "storm": "thunderstorm",
}

DOMAIN_BOOST_TERMS: Set[str] = {
    "flood",
    "rain",
    "thunderstorm",
    "cyclone",
    "lightning",
    "landslide",
    "heatwave",
    "coldwave",
    "drought",
    "station",
    "underpass",
    "bridge",
    "river",
    "dam",
    "road",
    "highway",
    "traffic",
    "submerged",
    "evacuation",
    "alert",
}

STOP_WORDS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "of",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "has",
    "have",
    "had",
    "it",
    "its",
    "this",
    "that",
    "near",
    "outside",
    "inside",
    "around",
}


class SemanticVectorizer:
    """Deterministic semantic vectorizer combining word tokens, bigrams, and domain boosting."""

    @staticmethod
    def normalize_word(word: str) -> str:
        """Strip suffixes and map domain synonyms."""
        w = word.lower()
        if w in SYNONYM_MAP:
            return SYNONYM_MAP[w]
        # Basic suffix strip
        for suffix in ("ing", "ed", "es", "s"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                stem = w[: -len(suffix)]
                if stem in SYNONYM_MAP:
                    return SYNONYM_MAP[stem]
                return stem
        return w

    def tokenize_with_weights(self, text: str) -> List[Tuple[str, float]]:
        """Normalize, stem, and generate word unigrams and bigrams with tiered weights."""
        if not text:
            return []
        sanitized = sanitize_nlp_text(text)
        if not sanitized:
            return []
        cleaned = re.sub(r"[^\w\s]", " ", sanitized.lower())
        raw_words = [w for w in cleaned.split() if w and w not in STOP_WORDS]
        norm_words = [self.normalize_word(w) for w in raw_words]

        weighted_tokens: List[Tuple[str, float]] = []

        # 1. Primary Word Unigrams (Weight 4.0 - 8.0)
        for w in norm_words:
            weight = (
                8.0 if (w in DOMAIN_BOOST_TERMS or any(d in w for d in DOMAIN_BOOST_TERMS)) else 4.0
            )
            weighted_tokens.append((w, weight))

        # 2. Word Bigrams (Weight 4.0)
        for i in range(len(norm_words) - 1):
            weighted_tokens.append((f"{norm_words[i]}_{norm_words[i + 1]}", 4.0))

        # 3. Character 4-grams (Weight 0.5) for robust sub-token/prefix matching
        for w in norm_words:
            if len(w) >= 4:
                for j in range(len(w) - 3):
                    weighted_tokens.append((f"c_{w[j : j + 4]}", 0.5))

        return weighted_tokens

    def text_to_vector(self, text: str) -> Dict[str, float]:
        """Convert text into term-frequency vector with domain boosting and L2 normalization."""
        weighted_tokens = self.tokenize_with_weights(text)
        if not weighted_tokens:
            return {}

        tf: Dict[str, float] = {}
        for token, weight in weighted_tokens:
            tf[token] = tf.get(token, 0.0) + weight

        # L2 Normalize
        norm_sq = sum(v * v for v in tf.values())
        if norm_sq > 0.0:
            norm = math.sqrt(norm_sq)
            for k in tf:
                tf[k] /= norm

        return tf

    def cosine_similarity(
        self,
        text_a: str,
        text_b: str,
        vec_a: Optional[List[float]] = None,
        vec_b: Optional[List[float]] = None,
    ) -> float:
        """Calculate cosine similarity between two incident texts or vector representations."""
        # 1. If precomputed dense embedding arrays are supplied
        if vec_a and vec_b and len(vec_a) == len(vec_b) and len(vec_a) > 0:
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = math.sqrt(sum(a * a for a in vec_a))
            norm_b = math.sqrt(sum(b * b for b in vec_b))
            if norm_a > 0.0 and norm_b > 0.0:
                sim = dot / (norm_a * norm_b)
                return max(0.0, min(1.0, float(sim)))

        # 2. Text-based deterministic token vector similarity
        clean_a = text_a.strip().lower() if text_a else ""
        clean_b = text_b.strip().lower() if text_b else ""

        if not clean_a or not clean_b:
            return 0.0

        if clean_a == clean_b:
            return 1.0

        dict_a = self.text_to_vector(clean_a)
        dict_b = self.text_to_vector(clean_b)

        if not dict_a or not dict_b:
            return 0.0

        # Dot product of sparse unit vectors
        common_keys = set(dict_a.keys()) & set(dict_b.keys())
        dot_product = sum(dict_a[k] * dict_b[k] for k in common_keys)

        return max(0.0, min(1.0, float(dot_product)))


semantic_vectorizer = SemanticVectorizer()
