"""Hazard category compatibility matrix and keyword rules for disaster intelligence and duplicate detection."""

import re
from typing import Dict, List, Tuple

# Comprehensive multilingual category keyword dictionary (English + Hindi / Hinglish)
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "FLOOD_WATERLOGGING": [
        "flood", "flooding", "waterlog", "waterlogging", "submerged", "inundation",
        "overflow", "drainage", "water accumulation", "underpass", "danger mark",
        "baadh", "badh", "paani bhara", "jalbharao", "jalbhorao", "sadak par paani",
        "बाढ़", "जलभराव", "पानी भरा", "डूब गया",
    ],
    "URBAN_FLOOD": [
        "urban flood", "urban flooding", "city inundation", "street flooding",
        "underpass drowned", "traffic flooded", "city waterlogging", "shahri baadh",
        "शहरी बाढ़",
    ],
    "HEAVY_RAINFALL": [
        "heavy rain", "rainfall", "downpour", "monsoon", "shower", "cloudburst",
        "precipitation", "deluge", "torrential", "baarish", "barish",
        "bhaari barish", "barsat", "musladhar", "pani baras",
        "भारी बारिश", "बारिश", "बरसात", "मूसलाधार", "बादल फटा",
    ],
    "THUNDERSTORM_LIGHTNING": [
        "thunderstorm", "lightning", "thunder", "squall", "bijli", "bijlee",
        "aakashvani", "garaj", "badal garajna", "बिजली गिरी", "गरज", "तड़ित",
    ],
    "CYCLONE_STORM": [
        "cyclone", "cyclonic storm", "storm surge", "depression",
        "coastal storm", "chakravat", "samudri toofan", "चक्रवात", "समुद्री तूफान",
    ],
    "HAILSTORM": [
        "hailstorm", "hail", "hailstones", "ice pellets", "olavrishti",
        "ole padna", "ola", "ole", "patthar barsat", "ओलावृष्टि", "ओले",
    ],
    "LANDSLIDE": [
        "landslide", "mudslide", "rockfall", "debris", "mud flow",
        "bhooskhalan", "bhuskhalan", "pahad girna", "mitti dhasna", "ghat road blocked",
        "भूस्खलन", "पहाड़ खिसकना",
    ],
    "HEATWAVE": [
        "heatwave", "heat wave", "extreme heat", "extreme temperature", "loo",
        "scorching", "garmi", "loo lagna", "tapman", "badi garmi", "teekhi dhoop",
        "भीषण गर्मी", "लू", "तापमान",
    ],
    "DROUGHT": [
        "drought", "dry spell", "water scarcity", "famine", "crop failure",
        "sookha", "sukha", "akaal", "akal", "pani ki kami", "सूखा", "अकाल",
    ],
    "FOG": [
        "fog", "dense fog", "mist", "smog", "zero visibility", "low visibility",
        "kohra", "kuhra", "dhund", "dhundh", "dhoondh", "dhoond", "foggy", "pea soup",
        "visibility dropped", "blinding fog", "kuhasa", "kuasa", "ghana kohra",
        "कोहरा", "घना कोहरा", "धुंध", "कुहासा", "शून्य दृश्यता", "कम दृश्यता", "कोहरे",
    ],
    "DUST_STORM": [
        "dust storm", "sandstorm", "sand storm", "haboob", "duststorm", "flying sand",
        "dust plume", "wall of dust", "blinding dust",
        "dhool bhari aandhi", "dhool toofan", "retila toofan", "mitti ki aandhi", "dhool aandhi",
        "ret ud", "andhi toofan", "dhool bhari hawa", "mitti ka toofan", "dhool",
        "धूल भरी आंधी", "रेतीला तूफान", "धूल का तूफान", "धूल भरी हवा", "रेत का तूफान", "धूल अंधड़", "अंधड़", "धूल",
    ],
    "STRONG_WIND": [
        "strong wind", "high wind", "high velocity winds", "wind gusts", "gale", "gust", "gusts",
        "gusty wind", "squall", "windstorm", "winds", "wind", "howling wind", "buffeting wind",
        "destructive winds", "severe gusts", "tez hawa", "tez hawayen", "tez hawaen", "jhakkad",
        "tez aandhi", "hawaon", "hawa ka jhonka", "jhonka", "tez jhonka", "badi tez hawa",
        "tez pawan", "hawa chal rahi", "hawa",
        "तेज हवा", "तेज हवाएं", "झक्कड़", "भीषण हवाएं", "प्रचंड हवाएं", "तूफानी हवाएं", "हवा के झोंके", "हवाएं", "पवन",
    ],
    "OTHER": [
        "weather", "incident", "hazard", "disaster", "mausam",
    ],
}

# Pairwise category compatibility scores (0.0 = completely incompatible/reject, 1.0 = identical)
CATEGORY_COMPATIBILITY_MATRIX: Dict[Tuple[str, str], float] = {
    # Related precipitation and flooding hazards
    ("FLOOD_WATERLOGGING", "HEAVY_RAINFALL"): 0.75,
    ("HEAVY_RAINFALL", "FLOOD_WATERLOGGING"): 0.75,
    ("FLOOD_WATERLOGGING", "URBAN_FLOOD"): 0.90,
    ("URBAN_FLOOD", "FLOOD_WATERLOGGING"): 0.90,
    ("HEAVY_RAINFALL", "URBAN_FLOOD"): 0.85,
    ("URBAN_FLOOD", "HEAVY_RAINFALL"): 0.85,
    ("CYCLONE", "HEAVY_RAINFALL"): 0.70,
    ("HEAVY_RAINFALL", "CYCLONE"): 0.70,
    ("CYCLONE", "FLOOD_WATERLOGGING"): 0.65,
    ("FLOOD_WATERLOGGING", "CYCLONE"): 0.65,
    ("CYCLONE_STORM", "HEAVY_RAINFALL"): 0.75,
    ("HEAVY_RAINFALL", "CYCLONE_STORM"): 0.75,
    ("CYCLONE_STORM", "FLOOD_WATERLOGGING"): 0.70,
    ("FLOOD_WATERLOGGING", "CYCLONE_STORM"): 0.70,
    ("CYCLONE_STORM", "STRONG_WIND"): 0.85,
    ("STRONG_WIND", "CYCLONE_STORM"): 0.85,
    ("HEAVY_RAINFALL", "LANDSLIDE"): 0.65,
    ("LANDSLIDE", "HEAVY_RAINFALL"): 0.65,
    ("FLOOD_WATERLOGGING", "LANDSLIDE"): 0.60,
    ("LANDSLIDE", "FLOOD_WATERLOGGING"): 0.60,
    ("THUNDERSTORM", "LIGHTNING"): 0.85,
    ("LIGHTNING", "THUNDERSTORM"): 0.85,
    ("THUNDERSTORM", "HEAVY_RAINFALL"): 0.80,
    ("HEAVY_RAINFALL", "THUNDERSTORM"): 0.80,
    ("THUNDERSTORM_LIGHTNING", "HEAVY_RAINFALL"): 0.80,
    ("HEAVY_RAINFALL", "THUNDERSTORM_LIGHTNING"): 0.80,
    ("THUNDERSTORM_LIGHTNING", "STRONG_WIND"): 0.80,
    ("STRONG_WIND", "THUNDERSTORM_LIGHTNING"): 0.80,
    ("DUST_STORM", "STRONG_WIND"): 0.80,
    ("STRONG_WIND", "DUST_STORM"): 0.80,
    ("HEATWAVE", "DROUGHT"): 0.70,
    ("DROUGHT", "HEATWAVE"): 0.70,
    # Strictly Incompatible Hazards (hard gate: 0.0)
    ("HEATWAVE", "FLOOD_WATERLOGGING"): 0.0,
    ("FLOOD_WATERLOGGING", "HEATWAVE"): 0.0,
    ("HEATWAVE", "HEAVY_RAINFALL"): 0.0,
    ("HEAVY_RAINFALL", "HEATWAVE"): 0.0,
    ("HEATWAVE", "COLDWAVE"): 0.0,
    ("COLDWAVE", "HEATWAVE"): 0.0,
    ("HEATWAVE", "FOG"): 0.0,
    ("FOG", "HEATWAVE"): 0.0,
    ("DROUGHT", "FLOOD_WATERLOGGING"): 0.0,
    ("FLOOD_WATERLOGGING", "DROUGHT"): 0.0,
    ("DROUGHT", "HEAVY_RAINFALL"): 0.0,
    ("HEAVY_RAINFALL", "DROUGHT"): 0.0,
    ("DROUGHT", "LIGHTNING"): 0.0,
    ("LIGHTNING", "DROUGHT"): 0.0,
    ("DROUGHT", "THUNDERSTORM"): 0.0,
    ("THUNDERSTORM", "DROUGHT"): 0.0,
    ("DROUGHT", "CYCLONE"): 0.0,
    ("CYCLONE", "DROUGHT"): 0.0,
    ("DROUGHT", "URBAN_FLOOD"): 0.0,
    ("URBAN_FLOOD", "DROUGHT"): 0.0,
    ("DROUGHT", "CYCLONE_STORM"): 0.0,
    ("CYCLONE_STORM", "DROUGHT"): 0.0,
    ("COLDWAVE", "FLOOD_WATERLOGGING"): 0.0,
    ("FLOOD_WATERLOGGING", "COLDWAVE"): 0.0,
    ("FOG", "DUST_STORM"): 0.0,
    ("DUST_STORM", "FOG"): 0.0,
}


def classify_text_category(text: str) -> str:
    """Classify free-form text into the best matching hazard category using keyword rules."""
    clean = str(text or "").lower()
    if not clean:
        return "OTHER"

    best_cat = "OTHER"
    max_score = 0.0

    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat == "OTHER":
            continue
        score = 0.0
        for kw in kws:
            kw_clean = kw.lower()
            if " " in kw_clean:
                if kw_clean in clean:
                    score += 3.0
            else:
                if re.search(r"(?:\b|^)" + re.escape(kw_clean) + r"(?:\b|$)", clean):
                    score += 1.0
        if score > max_score:
            max_score = score
            best_cat = cat

    return best_cat if max_score > 0 else "OTHER"


def get_category_compatibility(cat_a: str, cat_b: str) -> float:
    """Calculate compatibility score between two hazard categories.

    - Exact same category: 1.00
    - Related meteorological phenomenon: 0.60 - 0.90
    - Mutually exclusive phenomenon (e.g. Heatwave vs Flood, Drought vs Storm): 0.00
    - Unspecified/Other pairing: 0.30
    """
    clean_a = str(cat_a or "").strip().upper()
    clean_b = str(cat_b or "").strip().upper()

    if not clean_a or not clean_b:
        return 0.40

    if clean_a == clean_b:
        return 1.00

    if (clean_a, clean_b) in CATEGORY_COMPATIBILITY_MATRIX:
        return CATEGORY_COMPATIBILITY_MATRIX[(clean_a, clean_b)]

    alias_map = {
        "CYCLONE_GALE": "CYCLONE_STORM",
        "CYCLONE": "CYCLONE_STORM",
        "EXTREME_HEAT": "HEATWAVE",
    }
    aliased_a = alias_map.get(clean_a, clean_a)
    aliased_b = alias_map.get(clean_b, clean_b)

    if aliased_a == aliased_b:
        return 1.00

    if (aliased_a, aliased_b) in CATEGORY_COMPATIBILITY_MATRIX:
        return CATEGORY_COMPATIBILITY_MATRIX[(aliased_a, aliased_b)]

    return 0.30
