"""Location-mismatch credibility signal — pure, stateless, network-free function.

Detects when the main geographic entity mentioned in a report's text resolves to
a different state (or a non-Indian place) than the report's declared location.

Product Rules enforced:
  P1. MISMATCH needs both sides known. Either unknown -> NEUTRAL (0.0).
  P2. Multi-place post: not a mismatch if the declared state is among the text places.
  P3. Aliases and canonical forms handled via existing gazetteer (extractor).
  P4. Negative adjustment only, never positive, never auto-reject, never status change.
  P5. Explainable: declared place, text place, resolution method, verdict, contribution.

ASSUMPTION - unverified: penalty magnitude, cap, and curated foreign list per
location_mismatch_config.py.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from app.intelligence.extractor import EntityExtractor, entity_extractor
from app.intelligence.gazetteer import (
    AMBIGUOUS_PLACES,
    FOREIGN_LOCATIONS,
    INDIAN_CITIES,
    INDIAN_LOCALITIES,
    INDIAN_STATES,
)
from app.intelligence.location_mismatch_config import (
    CURATED_FOREIGN_PLACE_KEYS,
    LOCATION_MISMATCH_CAP,
    LOCATION_MISMATCH_MIN_TEXT_CONFIDENCE,
    LOCATION_MISMATCH_RAW_PENALTY,
)

logger = logging.getLogger(__name__)

# Pre-sort curated keys by length (longest first) for greedy word-boundary matching.
# Keys not in FOREIGN_LOCATIONS (i.e. not in extractor._all_place_keys) are caught here.
_CURATED_KEYS_SORTED: List[str] = sorted(
    CURATED_FOREIGN_PLACE_KEYS, key=len, reverse=True
)


class MismatchVerdict(str, Enum):
    """Result of location mismatch evaluation."""

    NEUTRAL = "NEUTRAL"      # One or both sides unknown -> no penalty
    CONSISTENT = "CONSISTENT"  # Text place state == declared state -> no penalty
    MISMATCH = "MISMATCH"    # Text place resolves to different state or foreign -> penalty


@dataclass(frozen=True)
class LocationMismatchResult:
    """Explainable result of the location-mismatch signal evaluation."""

    verdict: MismatchVerdict
    declared_place: Optional[str]
    declared_state: Optional[str]
    text_place: Optional[str]
    text_state: Optional[str]
    text_country: Optional[str]
    text_confidence: float
    adjustment: float       # <= 0.0 always; 0.0 when NEUTRAL or CONSISTENT
    cap_applied: float      # the cap value that was active
    method: str             # how the text-side was resolved
    explanation: str        # one-line human-readable verdict

    def as_explain_dict(self) -> dict:
        """Return a dict for embedding in credibility_explanation JSON."""
        return {
            "signal": "location_mismatch",
            "verdict": self.verdict.value,
            "declared_place": self.declared_place,
            "declared_state": self.declared_state,
            "text_place": self.text_place,
            "text_state": self.text_state,
            "text_country": self.text_country,
            "text_confidence": round(self.text_confidence, 4),
            "adjustment": round(self.adjustment, 4),
            "cap": round(self.cap_applied, 4),
            "method": self.method,
            "explanation": self.explanation,
            "assumption": (
                "ASSUMPTION - unverified: penalty magnitude, cap, and curated "
                "foreign-place list are project assumptions. "
                "Evaluated on synthetic hoaxes only."
            ),
        }


def _normalize(s: Optional[str]) -> Optional[str]:
    """Lowercase and strip for comparison."""
    if s is None:
        return None
    return s.strip().lower()


def _state_for_key(key: str) -> Optional[str]:
    """Return canonical state name for a gazetteer key, or None."""
    if key in INDIAN_LOCALITIES:
        return INDIAN_LOCALITIES[key].get("state")
    if key in INDIAN_CITIES:
        return INDIAN_CITIES[key].get("state")
    if key in INDIAN_STATES:
        return INDIAN_STATES[key].get("state")
    return None


def _is_foreign_key(key: str) -> bool:
    """True if this key is in the gazetteer foreign set or curated extension."""
    return key in FOREIGN_LOCATIONS or key in CURATED_FOREIGN_PLACE_KEYS


def _extract_all_entities(
    text: str,
    extractor: EntityExtractor,
) -> List[str]:
    """Return all gazetteer-matched entity keys from text (lowercased).

    Two-pass scan:
    1. Extractor (covers Indian gazetteer + the 10 FOREIGN_LOCATIONS entries).
    2. Direct word-boundary scan of CURATED_FOREIGN_PLACE_KEYS for keys that are
       not in the extractor's _all_place_keys (e.g. 'pakistan', 'islamabad').
    """
    entities = extractor.extract_entities(text)
    result_keys: List[str] = [e.normalized_text for e in entities]
    seen: Set[str] = set(result_keys)

    lower_text = text.lower()
    # Only scan keys absent from extractor to avoid double-counting
    for key in _CURATED_KEYS_SORTED:
        if key in seen:
            continue
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, lower_text):
            result_keys.append(key)
            seen.add(key)

    return result_keys


def evaluate_location_mismatch(
    *,
    report_text: Optional[str],
    declared_state: Optional[str],
    declared_city: Optional[str] = None,
    declared_country: Optional[str] = "India",
    penalty: float = LOCATION_MISMATCH_RAW_PENALTY,
    cap: float = LOCATION_MISMATCH_CAP,
    min_text_confidence: float = LOCATION_MISMATCH_MIN_TEXT_CONFIDENCE,
    extractor: Optional[EntityExtractor] = None,
) -> LocationMismatchResult:
    """Evaluate whether the report text describes a different location than declared.

    Args:
        report_text: Free-text description/title of the incident.
        declared_state: The state chosen by the reporter (from the report form).
        declared_city: Optional city chosen by the reporter.
        declared_country: Reporter's declared country (default "India").
        penalty: Raw penalty to apply when MISMATCH (ASSUMPTION - unverified).
        cap: Hard cap on the total adjustment (ASSUMPTION - unverified).
        min_text_confidence: Min resolver confidence for text-side to be "known".
        extractor: Entity extractor instance (uses global singleton if None).

    Returns:
        LocationMismatchResult with verdict, adjustment, and explanation fields.
    """
    _ext = extractor or entity_extractor

    # ─── P1: Check declared side ──────────────────────────────────────────────
    declared_state_norm = _normalize(declared_state)
    declared_country_norm = _normalize(declared_country) or "india"

    if not declared_state_norm and declared_country_norm == "india":
        # Declared location unknown (no state, no foreign country) -> NEUTRAL
        return LocationMismatchResult(
            verdict=MismatchVerdict.NEUTRAL,
            declared_place=declared_city or declared_state,
            declared_state=declared_state,
            text_place=None,
            text_state=None,
            text_country=None,
            text_confidence=0.0,
            adjustment=0.0,
            cap_applied=cap,
            method="none",
            explanation="NEUTRAL: declared state unknown; cannot evaluate mismatch.",
        )

    # ─── P1: Check text side ─────────────────────────────────────────────────
    if not report_text or not report_text.strip():
        return LocationMismatchResult(
            verdict=MismatchVerdict.NEUTRAL,
            declared_place=declared_city or declared_state,
            declared_state=declared_state,
            text_place=None,
            text_state=None,
            text_country=None,
            text_confidence=0.0,
            adjustment=0.0,
            cap_applied=cap,
            method="none",
            explanation="NEUTRAL: no report text; cannot resolve text-side location.",
        )

    all_keys = _extract_all_entities(report_text, _ext)

    if not all_keys:
        return LocationMismatchResult(
            verdict=MismatchVerdict.NEUTRAL,
            declared_place=declared_city or declared_state,
            declared_state=declared_state,
            text_place=None,
            text_state=None,
            text_country=None,
            text_confidence=0.0,
            adjustment=0.0,
            cap_applied=cap,
            method="none",
            explanation="NEUTRAL: no geographic entity found in text.",
        )

    # ─── P2: Multi-place — check if declared state is among ALL text entities ─
    # If the declared city appears in text, it's consistent
    declared_city_norm = _normalize(declared_city)

    # Collect all Indian states resolved from text
    text_states: List[str] = []
    text_foreign_keys: List[str] = []
    first_indian_key: Optional[str] = None
    first_foreign_key: Optional[str] = None

    for key in all_keys:
        if _is_foreign_key(key):
            text_foreign_keys.append(key)
            if first_foreign_key is None:
                first_foreign_key = key
        else:
            st = _state_for_key(key)
            if st:
                text_states.append(st.lower())
                if first_indian_key is None:
                    first_indian_key = key
            # If the key is the declared city itself -> consistent
            if declared_city_norm and key == declared_city_norm:
                st_city = _state_for_key(key)
                if st_city:
                    text_states.append(st_city.lower())

    # Look up declared state canonical form in INDIAN_STATES
    declared_state_canonical: Optional[str] = None
    if declared_state_norm in INDIAN_STATES:
        declared_state_canonical = INDIAN_STATES[declared_state_norm]["state"].lower()
    elif declared_city_norm and declared_city_norm in INDIAN_CITIES:
        # Derive state from declared city
        declared_state_canonical = INDIAN_CITIES[declared_city_norm]["state"].lower()

    # P2: If declared state appears in text_states -> CONSISTENT
    if declared_state_canonical and declared_state_canonical in text_states:
        # The declared state was found in the text -> no mismatch
        text_key = first_indian_key or (text_foreign_keys[0] if text_foreign_keys else None)
        text_place_name = text_key.replace("_", " ").title() if text_key else None
        text_state_str = _state_for_key(text_key) if text_key and not _is_foreign_key(text_key) else None
        return LocationMismatchResult(
            verdict=MismatchVerdict.CONSISTENT,
            declared_place=declared_city or declared_state,
            declared_state=declared_state,
            text_place=text_place_name,
            text_state=text_state_str,
            text_country="India",
            text_confidence=0.90,
            adjustment=0.0,
            cap_applied=cap,
            method="gazetteer_entity_extraction",
            explanation=(
                f"CONSISTENT: declared state '{declared_state}' found among "
                f"text entities {text_states[:3]}."
            ),
        )

    # ─── Check for foreign entities in text while declared is India ───────────
    declared_is_india = declared_country_norm in ("india", "भारत")

    if text_foreign_keys and declared_is_india:
        # Text mentions a foreign place; declared is India -> MISMATCH
        fkey = text_foreign_keys[0]
        # Check confidence: if it's in official FOREIGN_LOCATIONS with known coords -> 0.90
        # country-level -> 0.0 but we still know it's foreign
        fdata = FOREIGN_LOCATIONS.get(fkey, {})
        txt_conf = 0.90 if fdata.get("lat") is not None else 0.70
        # Curated-only keys (not in official FOREIGN_LOCATIONS) get lower confidence
        if fkey not in FOREIGN_LOCATIONS:
            txt_conf = 0.70

        if txt_conf < min_text_confidence:
            return LocationMismatchResult(
                verdict=MismatchVerdict.NEUTRAL,
                declared_place=declared_city or declared_state,
                declared_state=declared_state,
                text_place=fkey,
                text_state=None,
                text_country=fdata.get("country") or fkey,
                text_confidence=txt_conf,
                adjustment=0.0,
                cap_applied=cap,
                method="foreign_gazetteer",
                explanation=(
                    f"NEUTRAL: text-side confidence {txt_conf:.2f} below threshold "
                    f"{min_text_confidence:.2f}; treating as unknown."
                ),
            )

        raw_adj = -min(penalty, cap)
        return LocationMismatchResult(
            verdict=MismatchVerdict.MISMATCH,
            declared_place=declared_city or declared_state,
            declared_state=declared_state,
            text_place=fdata.get("place_name") or fkey.title(),
            text_state=None,
            text_country=fdata.get("country") or fkey.title(),
            text_confidence=txt_conf,
            adjustment=raw_adj,
            cap_applied=cap,
            method="foreign_gazetteer",
            explanation=(
                f"MISMATCH: declared location is in India ({declared_state or declared_country}), "
                f"but text primary place '{fdata.get('place_name') or fkey.title()}' "
                f"is in {fdata.get('country') or fkey.title()}. "
                f"Adjustment: {raw_adj:.4f} (cap={cap:.2f}, ASSUMPTION - unverified)."
            ),
        )

    # ─── Check for Indian state mismatch ─────────────────────────────────────
    if first_indian_key and declared_state_canonical:
        text_key_state = _state_for_key(first_indian_key)
        if text_key_state and text_key_state.lower() != declared_state_canonical:
            # Different Indian state in text vs declared
            raw_adj = -min(penalty, cap)
            return LocationMismatchResult(
                verdict=MismatchVerdict.MISMATCH,
                declared_place=declared_city or declared_state,
                declared_state=declared_state,
                text_place=first_indian_key.title(),
                text_state=text_key_state,
                text_country="India",
                text_confidence=0.90,
                adjustment=raw_adj,
                cap_applied=cap,
                method="indian_gazetteer",
                explanation=(
                    f"MISMATCH: declared state '{declared_state}' ({declared_state_canonical}), "
                    f"but text primary place '{first_indian_key.title()}' is in "
                    f"'{text_key_state}'. "
                    f"Adjustment: {raw_adj:.4f} (cap={cap:.2f}, ASSUMPTION - unverified)."
                ),
            )

    # ─── NEUTRAL: text entities present but no confident mismatch determinable ─
    # (e.g., only ambiguous entities, or text state consistent with declared)
    text_place_name = (
        first_indian_key.title() if first_indian_key else
        (first_foreign_key.title() if first_foreign_key else None)
    )
    return LocationMismatchResult(
        verdict=MismatchVerdict.NEUTRAL,
        declared_place=declared_city or declared_state,
        declared_state=declared_state,
        text_place=text_place_name,
        text_state=_state_for_key(first_indian_key) if first_indian_key else None,
        text_country="India" if first_indian_key else None,
        text_confidence=0.0,
        adjustment=0.0,
        cap_applied=cap,
        method="none",
        explanation="NEUTRAL: insufficient confidence to determine mismatch.",
    )
