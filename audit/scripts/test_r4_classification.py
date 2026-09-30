"""Script to test R4 classification on 60 posts (Fog, Dust Storm, Strong Wind)
and 10 hoax-style posts.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "back-end"))

from app.ingestion.normalizer import EventNormalizer
from app.intelligence.category_rules import classify_text_category

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

def eval_code_path(name, fn):
    print(f"\n================ Evaluation: {name} ================")
    cats = ["FOG", "DUST_STORM", "STRONG_WIND"]
    confusion = {true_c: {pred_c: 0 for pred_c in cats + ["OTHER"]} for true_c in cats}
    correct = 0
    misses = []

    for expected, text in POSTS:
        predicted = fn(text)
        if predicted not in confusion[expected]:
            confusion[expected][predicted] = 0
        confusion[expected][predicted] += 1
        if predicted == expected:
            correct += 1
        else:
            misses.append((expected, predicted, text))

    print(f"Overall Accuracy: {correct}/{len(POSTS)} = {correct/len(POSTS)*100:.2f}%")
    for c in cats:
        c_tot = sum(confusion[c].values())
        c_cor = confusion[c].get(c, 0)
        print(f"  {c} Accuracy: {c_cor}/{c_tot} = {c_cor/c_tot*100:.2f}%")

    print("\nConfusion Table:")
    header = f"{'True \\ Pred':<15}" + "".join(f"{c:<15}" for c in cats + ["OTHER"])
    print(header)
    for true_c in cats:
        row = f"{true_c:<15}" + "".join(f"{confusion[true_c].get(p, 0):<15}" for p in cats + ["OTHER"])
        print(row)

    if misses:
        print(f"\nMisses ({len(misses)}):")
        for exp, pred, t in misses:
            print(f"  Expected: {exp:<12} Predicted: {pred:<12} Text: {t}")

if __name__ == "__main__":
    eval_code_path("classify_text_category", classify_text_category)
    eval_code_path("EventNormalizer.normalize_category(None, title)", lambda t: EventNormalizer.normalize_category(None, title=t))
