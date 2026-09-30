"""Regression test for R4 hazard classification: 60 posts (Fog, Dust Storm, Strong Wind)
in English and Hinglish/Hindi (Devanagari and Roman script).
"""

import uuid

from app.ingestion.normalizer import EventNormalizer
from app.intelligence.category_rules import classify_text_category
from app.intelligence.credibility_scorer import CredibilityScorer
from app.intelligence.schemas import ContradictionInput, IncidentCredibilityInputs, SourceFamily

POSTS = [
    # 20 FOG
    ("FOG", "Dense fog covering Noida Expressway, visibility dropped to almost zero."),
    ("FOG", "Heavy morning mist and smog slowing down flights at Delhi airport."),
    ("FOG", "Severe zero visibility fog alert issued for Punjab and Haryana highways."),
    ("FOG", "Thick pea-soup fog blankets Lucknow early morning, multiple vehicles pile up."),
    ("FOG", "Low visibility conditions due to dense fog in Varanasi this morning."),
    ("FOG", "Driving in extreme dense fog on Yamuna Expressway, please drive carefully."),
    ("FOG", "Freezing morning with heavy foggy weather across Jaipur bypass."),
    ("FOG", "Visibility drops below 50m due to dense fog in Chandigarh."),
    ("FOG", "Blinding fog reported along NH44, commuters stranded."),
    ("FOG", "Winter smog and thick fog causing train delays across northern plains."),
    ("FOG", "Yamuna expressway par bahut ghana kohra hai, kuch dikhai nahi de raha."),
    ("FOG", "Aaj subah se Delhi me zero visibility kohre ki wajah se hai."),
    ("FOG", "यमुना एक्सप्रेसवे पर घना कोहरा छाया हुआ है, दृश्यता शून्य हो गई।"),
    ("FOG", "NH-24 par bhari dhundh aur kohra chhaya hua hai, traffic bilkul slow hai."),
    ("FOG", "उत्तर भारत के कई जिलों में भारी कोहरा और धुंध के कारण ट्रेनें लेट हैं।"),
    ("FOG", "Subah subah itna dense kuhra tha ki 10 meter aage ka bhi nahi dikh raha tha."),
    ("FOG", "सड़क पर भयंकर धुंध और कुहासा है, गाड़ियां लाइट जलाकर चल रही हैं।"),
    ("FOG", "Purani Delhi railway station par dhoondh aur kohre ka aalam, visibility 10m."),
    ("FOG", "राजधानी में कड़ाके की ठंड के साथ छाया घना कोहरा।"),
    ("FOG", "Har taraf safed chadar jaisa kohra aur dhund pheli hui hai."),

    # 20 DUST_STORM
    ("DUST_STORM", "Massive dust storm hits Bikaner, turning the sky orange and blocking roads."),
    ("DUST_STORM", "Severe sandstorm approaching Jodhpur desert areas with high flying sand."),
    ("DUST_STORM", "Intense haboob dust plume sweeps across western Rajasthan highway."),
    ("DUST_STORM", "Blinding dust storm causes power outages and tree falls across Barmer."),
    ("DUST_STORM", "Sudden duststorm and flying sand reduces visibility to zero in Jaisalmer."),
    ("DUST_STORM", "Huge wall of dust seen advancing toward the city outskirts."),
    ("DUST_STORM", "High velocity dust storm warning issued for western desert belt."),
    ("DUST_STORM", "Severe dust storm accompanied by desert squall damages tin sheds."),
    ("DUST_STORM", "Blinding dust storm engulfs western highway, motorists stop vehicles."),
    ("DUST_STORM", "Massive sand storm sweeping through rural border towns."),
    ("DUST_STORM", "Bikaner me achanak dhool bhari aandhi aayi aur din me andhera ho gaya."),
    ("DUST_STORM", "Barmer border area par bhot bhayankar retila toofan chal raha hai."),
    ("DUST_STORM", "राजस्थान के कई हिस्सों में भयंकर धूल भरी आंधी और रेतीला तूफान आया।"),
    ("DUST_STORM", "Registan me tez dhool toofan shuru ho gaya, sab taraf ret ud rahi hai."),
    ("DUST_STORM", "जैसलमेर में तेज अंधड़ और धूल का तूफान, आसमान में छाया गुबार।"),
    ("DUST_STORM", "Mitti ki aandhi ne poora shahar gher liya, aankh kholna mushkil ho raha hai."),
    ("DUST_STORM", "जोधपुर में भीषण धूल भरी आंधी से घरों के टीन शेड उड़े।"),
    ("DUST_STORM", "Achanak tez dhool aandhi aane se visual band ho gaya, sandstorm alert."),
    ("DUST_STORM", "तेज धूल भरी हवा और रेत का तूफान पश्चिमी राजस्थान में तबाही मचा रहा है।"),
    ("DUST_STORM", "Dhool bhari andhi toofan ne sadkon par ret ke dher laga diye."),

    # 20 STRONG_WIND
    ("STRONG_WIND", "Violent strong wind blowing across the coastline, roaring gale ripping tarpaulins."),
    ("STRONG_WIND", "Extreme high wind gusts exceeding 80 km/h uprooting trees and electric poles."),
    ("STRONG_WIND", "Severe gale force winds howling through south Mumbai promenades."),
    ("STRONG_WIND", "Intense windstorm causes structural damage and signboards to collapse."),
    ("STRONG_WIND", "Buffeting strong winds making it impossible to walk along the beach front."),
    ("STRONG_WIND", "Dangerous gusty wind blowing tin roofs away in open rural areas."),
    ("STRONG_WIND", "Fierce wind gusts blowing over vehicles on open sea link bridges."),
    ("STRONG_WIND", "Powerful windstorm lashes coastal fishing hamlets without rain."),
    ("STRONG_WIND", "Sustained high velocity winds battering coastal installations."),
    ("STRONG_WIND", "Destructive winds bring down old hoarding on main market street."),
    ("STRONG_WIND", "Bhot tez hawa chal rahi hai, ped ki daaliyan toot kar sadak par gir gayi."),
    ("STRONG_WIND", "Bahar itni tez hawayen hain ki balcony ke gamle ud gaye."),
    ("STRONG_WIND", "मुंबई के तटीय इलाकों में बहुत तेज हवा और भीषण हवाएं चल रही हैं।"),
    ("STRONG_WIND", "Achanak se bhari jhakkad aur tez hawa shuru ho gayi bina baarish ke."),
    ("STRONG_WIND", "शहर में तेज तूफानी हवाएं और झक्कड़ चलने से कई पेड़ उखड़ गए।"),
    ("STRONG_WIND", "Hawa ka bhot tez jhonka aaya aur poori chhat ka tesh shed uda le gaya."),
    ("STRONG_WIND", "प्रचंड हवाएं और हवा के तेज झोंके तटीय मार्ग पर चल रहे हैं।"),
    ("STRONG_WIND", "Sea face par tez hawaon ke jhonke chal rahe hain, chalna mushkil hai."),
    ("STRONG_WIND", "आंधी और तेज हवाओं से बिजली के खंभे गिर गए, चारों तरफ तेज हवा है।"),
    ("STRONG_WIND", "Ghar ke bahar bhayanak tez pawan aur tez hawa chal rahi hai."),
]

HOAX_POSTS = [
    # 5 Old Videos (stale/contradictory timestamp, uncorroborated, fact-check contradiction)
    ("Old video: 2017 Florida hurricane reused as Mumbai cyclone", False, True, True),
    ("Old video: 2019 viral clip claimed as Dehradun cloudburst", False, True, True),
    ("Recycled 2015 Chennai flood clip shared on WhatsApp", False, True, True),
    ("Archived 2020 Bihar bridge collapse circulated as today", False, True, True),
    ("2004 Tsunami footage shared as Gujarat storm surge", False, True, True),
    # 5 Foreign Locations (no coordinates in India / foreign location, uncorroborated)
    ("Oklahoma tornado footage claimed as Bengaluru airport", False, False, False),
    ("Indonesia volcano ash claimed as Jaipur dust storm", False, False, False),
    ("Chicago winter blizzard claimed as Marine Drive Mumbai", False, False, False),
    ("Phoenix Arizona haboob claimed as Delhi sandstorm", False, False, False),
    ("NYC subway flood video claimed as Kolkata subway", False, False, False),
]


def test_r4_classification_benchmark_regression():
    """Verify that multilingual category classification achieves >= 85% accuracy."""
    correct_rules = 0
    correct_normalizer = 0
    total = len(POSTS)

    for expected, text in POSTS:
        pred_rules = classify_text_category(text)
        pred_norm = EventNormalizer.normalize_category(None, title=text)
        if pred_rules == expected:
            correct_rules += 1
        if pred_norm == expected:
            correct_normalizer += 1

    acc_rules = correct_rules / total
    acc_norm = correct_normalizer / total

    assert acc_rules >= 0.85, f"Category rules accuracy {acc_rules:.2%} is below 85%"
    assert acc_norm >= 0.85, f"Normalizer accuracy {acc_norm:.2%} is below 85%"


def test_r4_hoax_credibility_suppression():
    """Verify that uncorroborated, contradictory, or coordinate-less hoaxes receive low scores (< 0.45)."""
    scorer = CredibilityScorer()

    for title, has_coords, has_time, has_contra in HOAX_POSTS:
        neg_contra = []
        if has_contra:
            neg_contra.append(
                ContradictionInput(
                    signal_source_key="fact_check_archive_match",
                    contradiction_score=0.85,
                    is_diagnostic=True,
                    is_physical_sensor=False,
                )
            )

        inp = IncidentCredibilityInputs(
            incident_id=uuid.uuid4(),
            source_code="CITIZEN_WEB",
            source_type="CITIZEN_REPORT",
            source_base_trust=0.50 if not has_coords else 0.60,
            origin_family=SourceFamily.CITIZEN,
            has_coordinates=has_coords,
            has_timestamp=has_time,
            has_location_name=True,
            has_description=True,
            has_category=True,
            cluster_member_count=1,
            evidence_groups=[],
            observation_stations=[],
            negative_contradictions=neg_contra,
        )
        res = scorer.score_incident(inp)
        # All hoaxes must remain strictly below lowest verification threshold 0.45
        assert res.final_credibility_score < 0.45, (
            f"Hoax '{title}' got credibility {res.final_credibility_score:.4f} >= 0.45"
        )
