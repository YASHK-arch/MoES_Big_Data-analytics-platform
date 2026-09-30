"""Location-mismatch signal configuration.

ASSUMPTION - unverified: All penalty magnitudes, caps, and the curated foreign-place
list are project assumptions pending human review. They are not calibrated against
real-world data.

This module is used only for the location-mismatch credibility signal (L5).
It does NOT change resolver.py or the gazetteer lookup behaviour.
"""

from typing import FrozenSet

# ─── FEATURE FLAG ────────────────────────────────────────────────────────────
# Default OFF in production. Enable in tests via env or constructor override.
LOCATION_MISMATCH_ENABLED_DEFAULT: bool = False

# ─── PENALTY PARAMETERS (ASSUMPTION - unverified) ────────────────────────────
# Raw penalty magnitude applied when a confident mismatch is detected.
# ASSUMPTION: 0.10 is a "weak, capped" signal per the product requirement.
LOCATION_MISMATCH_RAW_PENALTY: float = 0.10

# Hard cap on the total adjustment this signal can apply.
# The actual adjustment is min(raw_penalty, cap).
# Sensitivity will be evaluated at 0.05 / 0.10 / 0.15 (Item 5c).
# ASSUMPTION: 0.10 is the recommended cap (see Item 5c evaluation).
LOCATION_MISMATCH_CAP: float = 0.10

# Minimum resolver confidence required to consider the text-place "known".
# Below this threshold, the text side is treated as UNKNOWN -> NEUTRAL.
# ASSUMPTION: 0.70 is a reasonable floor for a "confident" resolution.
LOCATION_MISMATCH_MIN_TEXT_CONFIDENCE: float = 0.70

# ─── CURATED FOREIGN PLACE LIST (ASSUMPTION - unverified) ────────────────────
# Used to detect "text says a foreign place, declared location is in India".
# This extends the existing FOREIGN_LOCATIONS gazetteer (which has 10 entries)
# with neighbouring countries and their capitals/major cities that are
# plausibly mentioned in Indian weather/disaster reporting contexts.
#
# ASSUMPTION: This list is minimal and curated by the agent. It may have gaps
# (e.g., Thimphu is Bhutan's capital; Yangon is Myanmar's largest city).
# A native-language reviewer should verify these entries before production use.
#
# These keys match the lowercase, ASCII normalized form that the extractor uses.
# They do NOT modify resolver.py or gazetteer.py.

CURATED_FOREIGN_PLACE_KEYS: FrozenSet[str] = frozenset(
    {
        # Already in gazetteer (included for completeness check)
        "nepal", "bangladesh", "sri lanka", "germany",
        "kathmandu", "pokhara", "rasuwa",
        "dhaka", "colombo", "berlin",
        # --- ASSUMPTION: additions below ---
        # Pakistan
        "pakistan", "islamabad", "karachi", "lahore", "peshawar", "rawalpindi",
        # China
        "china", "beijing", "shanghai", "kunming", "lhasa", "guangzhou",
        # Myanmar
        "myanmar", "burma", "naypyidaw", "yangon", "mandalay",
        # Afghanistan
        "afghanistan", "kabul", "kandahar",
        # Bhutan
        "bhutan", "thimphu", "paro",
        # Maldives
        "maldives", "male",
        # Thailand
        "thailand", "bangkok",
        # Indonesia
        "indonesia", "jakarta",
        # United Kingdom
        "united kingdom", "london",
        # France
        "france", "paris",
        # United States
        "united states", "washington",
        # Other frequently mentioned foreign place names
        "tibet",
    }
)
