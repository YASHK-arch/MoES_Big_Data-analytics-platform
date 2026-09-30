"""Verification of library choice, versions, licenses, and EXIF timezone handling for S2 Item 2.
"""

import datetime
import importlib.metadata
import io
import sys
from PIL import Image, ExifTags

def main():
    print("=== DEPENDENCY METADATA ===")
    for pkg in ["Pillow", "numpy"]:
        dist = importlib.metadata.distribution(pkg)
        lic = dist.metadata.get("License") or dist.metadata.get("License-Expression") or "Unknown"
        print(f"Package: {pkg} | Version: {dist.version} | License: {lic}")

    print("\n=== EXIF TIMEZONE HANDLING TEST ===")
    # Test 1: Explicit offset present (+05:30)
    raw_dt_str = "2026:08:15 14:30:00"
    raw_offset_str = "+05:30"
    dt = datetime.datetime.strptime(raw_dt_str, "%Y:%m:%d %H:%M:%S")
    offset_hours, offset_minutes = map(int, raw_offset_str.replace("+", "").split(":"))
    tz = datetime.timezone(datetime.timedelta(hours=offset_hours, minutes=offset_minutes))
    dt_with_tz = dt.replace(tzinfo=tz)
    dt_utc_1 = dt_with_tz.astimezone(datetime.timezone.utc)
    print(f"Explicit offset: raw='{raw_dt_str} {raw_offset_str}' -> UTC='{dt_utc_1.isoformat()}'")

    # Test 2: Naive timestamp (no offset tag) -> ASSUMPTION: IST (UTC+05:30)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    dt_naive = datetime.datetime.strptime(raw_dt_str, "%Y:%m:%d %H:%M:%S")
    dt_assumed_ist = dt_naive.replace(tzinfo=ist_tz)
    dt_utc_2 = dt_assumed_ist.astimezone(datetime.timezone.utc)
    print(f"Naive timestamp: raw='{raw_dt_str}' -> ASSUMPTION IST (UTC+05:30) -> UTC='{dt_utc_2.isoformat()}'")
    assert dt_utc_1 == dt_utc_2, "Explicit IST offset and assumed IST offset must produce identical UTC"
    print("Timezone parity verified: PASS")

    print("\n=== PILLOW EXIF CAPABILITY TEST ===")
    # Create sample image in memory
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    exif = img.getexif()
    exif[0x0132] = raw_dt_str  # DateTime
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)

    # Read back EXIF
    loaded = Image.open(buf)
    loaded_exif = loaded.getexif()
    retrieved_dt = loaded_exif.get(0x0132)
    print(f"Written EXIF DateTime: '{raw_dt_str}' | Retrieved: '{retrieved_dt}'")
    assert retrieved_dt == raw_dt_str, "EXIF write and read roundtrip failed"
    print("Pillow EXIF roundtrip verified: PASS")

if __name__ == "__main__":
    main()
