"""
L5 Item 2: Resolver capability probe.

Tests:
1. Foreign place name resolution
2. Multi-place post resolution
3. Alias handling (Bombay/Mumbai, Bangalore/Bengaluru, etc.)

Reports gaps and what is/isn't supported.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.intelligence.resolver import LocationResolver
from app.intelligence.gazetteer import FOREIGN_LOCATIONS, INDIAN_CITIES, INDIAN_STATES

resolver = LocationResolver()

def probe(label: str, text: str) -> None:
    result = resolver.resolve(text=text)
    print(f"\n  [{label}]")
    print(f"  text       : {text!r}")
    print(f"  status     : {result.resolution_status.value}")
    print(f"  place_name : {result.place_name}")
    print(f"  state      : {result.state}")
    print(f"  country    : {result.country}")
    print(f"  confidence : {result.confidence}")
    print(f"  method     : {result.resolution_method.value}")
    print(f"  provider   : {result.provider}")
    if result.metadata:
        print(f"  metadata   : {result.metadata}")


def main():
    print("L5 Item 2: Resolver Capability Probe")
    print("="*70)

    # 1. Foreign place names in FOREIGN_LOCATIONS
    print("\n--- 1. FOREIGN PLACE NAMES (in FOREIGN_LOCATIONS gazetteer) ---")
    for key in ["kathmandu", "dhaka", "colombo", "nepal", "bangladesh", "berlin"]:
        probe(f"foreign:{key}", f"Massive flooding reported in {key.title()} area")

    # 2. Foreign place name NOT in gazetteer
    print("\n--- 2. FOREIGN PLACE NOT IN GAZETTEER ---")
    for name in ["London", "Beijing", "Islamabad", "Kabul", "Bangkok", "Paris"]:
        probe(f"unknown-foreign:{name}", f"Disaster relief needed in {name}")

    # 3. Multi-place post: declared state among text places (should NOT flag mismatch per P2)
    print("\n--- 3. MULTI-PLACE POST (declared state is one of the text states) ---")
    probe("multi-place-ok-state-in-text",
          "Heavy rain affects Mumbai and Chennai — Maharashtra and Tamil Nadu on alert")
    probe("multi-place-ok-city-in-decl-state",
          "Floods in Guwahati and Shillong; Assam government responds")
    probe("multi-place-ok-resolver-picks-first",
          "Flooding in Bengaluru and Pune; Karnataka more severely hit")

    # 4. Multi-place post: declared state NOT in text (should flag mismatch per P2)
    probe("multi-place-mismatch",
          "Heavy rains in Nepal and Kathmandu region; no Indian states mentioned")

    # 5. Aliases — Bombay/Mumbai, Bangalore/Bengaluru, Madras/Chennai, etc.
    print("\n--- 4. ALIAS HANDLING ---")
    alias_pairs = [
        ("bombay", "Mumbai"),
        ("bangalore", "Bengaluru"),
        ("madras", "Chennai"),
        ("calcutta", "Kolkata"),
        ("allahabad", "Prayagraj"),
        ("trivandrum", "Thiruvananthapuram"),
        ("vizag", "Visakhapatnam"),
        ("baroda", "Vadodara"),
        ("poona", "Pune"),
        ("cochin", "Kochi"),
        ("gurgaon", "Gurugram"),
        ("banaras", "Varanasi"),
        ("kashi", "Varanasi"),
    ]
    for alias, canonical in alias_pairs:
        r = resolver.resolve(text=f"Severe flooding in {alias.title()}")
        match = r.city == canonical or r.place_name and canonical in (r.place_name or "")
        print(f"  alias={alias!r:15} -> city={r.city!r:25} canonical={canonical!r:20} OK={match}")

    # 6. Devanagari/Hinglish — NOT in current gazetteer
    print("\n--- 5. DEVANAGARI / HINGLISH (NOT in gazetteer) ---")
    devanagari_tests = [
        ("मुंबई", "Mumbai in Devanagari"),
        ("दिल्ली", "Delhi in Devanagari"),
        ("बेंगलुरु", "Bengaluru in Devanagari"),
        ("Dilli", "Hinglish for Delhi"),
        ("Bambai", "Hinglish for Mumbai"),
    ]
    for text, label in devanagari_tests:
        r = resolver.resolve(text=f"Flood in {text}")
        print(f"  {label}: status={r.resolution_status.value}, place={r.place_name!r}")

    # 7. What's in FOREIGN_LOCATIONS — full list
    print("\n--- 6. FOREIGN_LOCATIONS GAZETTEER CONTENTS ---")
    print(f"  Total entries: {len(FOREIGN_LOCATIONS)}")
    for k, v in FOREIGN_LOCATIONS.items():
        print(f"  key={k!r:20} country={v.get('country')!r:15} lat={v.get('lat')} lon={v.get('lon')}")

    # 8. Gaps report
    print("\n--- 7. GAPS IDENTIFIED ---")
    print("  a) Devanagari script: NOT supported. Resolver uses ASCII lowercase matching.")
    print("     Hinglish variants (Dilli, Bambai): NOT in gazetteer.")
    print("  b) Many neighbouring countries/capitals missing from FOREIGN_LOCATIONS:")
    missing = [
        "Pakistan / Islamabad / Karachi / Lahore",
        "China / Beijing / Kunming (shares border with India)",
        "Myanmar / Naypyidaw / Yangon",
        "Afghanistan / Kabul",
        "Bhutan / Thimphu",
        "Maldives / Male",
    ]
    for m in missing:
        print(f"     MISSING: {m}")
    print("  c) Germany/Berlin in gazetteer — likely test artifact; retained as-is.")
    print("  d) Multi-place: resolver returns FIRST matched entity. For mismatch detection,")
    print("     we need ALL entities to check if declared state is among them (P2).")
    print("     The existing resolver.resolve() only returns ONE result.")
    print("     The extractor.extract_entities() returns ALL — we will use the extractor directly.")
    print("  e) Ambiguous places (Rajpur, Bilaspur, Rampur, Aurangabad): resolver returns")
    print("     AMBIGUOUS status with confidence=0.0 when no context disambiguates.")
    print("     For mismatch detection, ambiguous -> NEUTRAL (P1 applies).")


if __name__ == "__main__":
    main()
