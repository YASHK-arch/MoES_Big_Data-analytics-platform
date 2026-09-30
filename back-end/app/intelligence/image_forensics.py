"""Image forensics intelligence module: reused-image detection and EXIF consistency.

Features:
- Pure deterministic perceptual hashing (pHash) and difference hashing (dHash)
- Safe EXIF extraction with strict bounds checking and decompression-bomb protection (P6)
- Explicit timezone normalization with documented Indian Standard Time assumption for naive timestamps
- Explainable consistency checks: EXIF time vs incident time, EXIF GPS vs incident location
- Cross-incident image reuse detection with same-incident duplicate filtering (P3)
- Privacy-preserving derived outputs for public/operator viewing (P5)
- Weak, capped credibility adjustments that never alter verification status (P2)
"""

from __future__ import annotations

import datetime
import hashlib
import io
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import ExifTags, Image, ImageFile, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.intelligence.physical_corroboration.evaluator import haversine_distance_km

logger = logging.getLogger(__name__)

# Prevent decompression bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 40_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = False

# Precompute 32x32 DCT-II matrix for deterministic, zero-external-dependency pHash
_N = 32
_n = np.arange(_N)
_k = np.arange(_N)[:, None]
_factor = np.sqrt(2.0 / _N)
_DCT_MATRIX = _factor * np.cos(np.pi * (2 * _n + 1) * _k / (2.0 * _N))
_DCT_MATRIX[0, :] /= np.sqrt(2.0)

# Indian Standard Time (UTC+05:30)
# ASSUMPTION - unverified: Camera devices in India without offset tags record local wall-clock IST
IST_TIMEZONE = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class ForensicVerdict(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class ForensicCheckResult(BaseModel):
    """Explainable result for an individual forensic consistency check."""

    model_config = ConfigDict(frozen=True)

    check_type: str = Field(
        ...,
        description="Type of check: EXIF_TIME, EXIF_LOCATION, IMAGE_REUSE",
    )
    verdict: ForensicVerdict = Field(
        ...,
        description="Verdict for this check: SUPPORTS, CONTRADICTS, NEUTRAL",
    )
    observed_value: Optional[str] = Field(
        default=None,
        description="Privacy-preserving observed signal value",
    )
    expected_value: Optional[str] = Field(
        default=None,
        description="Expected reference value from incident declaration",
    )
    difference: Optional[str] = Field(
        default=None,
        description="Quantitative difference between observed and expected",
    )
    reason: str = Field(
        ...,
        description="Plain-language deterministic explanation for the verdict",
    )
    matched_incident_ids: List[str] = Field(
        default_factory=list,
        description="List of other incident UUIDs where identical image hash was found (P5: IDs only)",
    )


class ImageForensicResult(BaseModel):
    """Forensic analysis findings for a single report image."""

    model_config = ConfigDict(frozen=True)

    media_id: Optional[str] = None
    sha256: str
    phash: str
    dhash: str
    has_exif: bool = False
    exif_timestamp_utc: Optional[str] = None
    timezone_assumed_ist: bool = False
    checks: List[ForensicCheckResult] = Field(default_factory=list)
    overall_verdict: ForensicVerdict = ForensicVerdict.NEUTRAL
    credibility_adjustment: float = 0.0
    error_reason: Optional[str] = None


class IncidentForensicsSummary(BaseModel):
    """Aggregate forensic findings across all images attached to an incident."""

    model_config = ConfigDict(frozen=True)

    incident_id: str
    images: List[ImageForensicResult] = Field(default_factory=list)
    overall_verdict: ForensicVerdict = ForensicVerdict.NEUTRAL
    total_credibility_adjustment: float = 0.0
    simulated: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Hash Algorithms & Distances
# ─────────────────────────────────────────────────────────────────────────────


def compute_phash(image: Image.Image) -> str:
    """Compute 64-bit perceptual hash (pHash) using 32x32 DCT low frequencies."""
    img = image.convert("L").resize((32, 32), Image.Resampling.BILINEAR)
    pixels = np.asarray(img, dtype=np.float64)
    dct = _DCT_MATRIX @ pixels @ _DCT_MATRIX.T
    sub = dct[:8, :8]
    med = float(np.median(sub[1:, 1:])) if sub.size > 1 else float(np.median(sub))
    bits = (sub > med).flatten()
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    return f"{val:016x}"


def compute_dhash(image: Image.Image) -> str:
    """Compute 64-bit difference hash (dHash) using 9x8 horizontal pixel gradients."""
    img = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    pixels = np.asarray(img, dtype=np.int32)
    diff = pixels[:, 1:] > pixels[:, :-1]
    val = 0
    for b in diff.flatten():
        val = (val << 1) | int(b)
    return f"{val:016x}"


def hamming_distance(h1: str, h2: str) -> int:
    """Compute bitwise Hamming distance between two hexadecimal hash strings."""
    if not h1 or not h2:
        return 64
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except ValueError:
        return 64


# ─────────────────────────────────────────────────────────────────────────────
# EXIF Metadata Extraction
# ─────────────────────────────────────────────────────────────────────────────


def _convert_dms_to_dd(dms: Any, ref: Optional[str]) -> Optional[float]:
    """Convert EXIF GPS degrees, minutes, seconds rational tuple to decimal degrees."""
    if not dms or len(dms) < 3:
        return None
    try:
        deg = float(dms[0])
        minute = float(dms[1])
        sec = float(dms[2])
        dd = deg + (minute / 60.0) + (sec / 3600.0)
        if ref and ref.upper() in ("S", "W"):
            dd = -dd
        return round(dd, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def extract_exif_metadata(image_bytes: bytes) -> Dict[str, Any]:
    """Safely extract and parse EXIF metadata from raw image bytes.

    Never raises exceptions. Adheres strictly to Product Rules:
    - P1: Missing EXIF is represented cleanly as has_exif=False.
    - P6: Bounds check size before decompression.
    """
    max_bytes = getattr(settings, "IMAGE_FORENSICS_MAX_FILE_BYTES", 15 * 1024 * 1024)
    if len(image_bytes) > max_bytes:
        return {
            "has_exif": False,
            "error_reason": f"File size ({len(image_bytes)} bytes) exceeds limit ({max_bytes} bytes)",
        }

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Check dimension bounds before full decompression
            w, h = img.size
            max_pixels = getattr(settings, "IMAGE_FORENSICS_MAX_PIXELS", 40_000_000)
            if w * h > max_pixels:
                return {
                    "has_exif": False,
                    "error_reason": f"Image dimensions {w}x{h} exceed pixel limit ({max_pixels})",
                }

            raw_exif = img.getexif()
            if not raw_exif:
                return {"has_exif": False, "error_reason": "No EXIF header present"}

            # Map tag IDs to human-readable names
            exif_dict: Dict[str, Any] = {}
            for tag_id, value in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                exif_dict[tag_name] = value

            # Also check Exif IFD sub-table (0x8769) for DateTimeOriginal
            exif_ifd = raw_exif.get_ifd(0x8769)
            if exif_ifd:
                for tag_id, value in exif_ifd.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    exif_dict[tag_name] = value

            # Parse DateTimeOriginal, DateTimeDigitized, or DateTime
            raw_dt_str = (
                exif_dict.get("DateTimeOriginal")
                or exif_dict.get("DateTimeDigitized")
                or exif_dict.get("DateTime")
            )

            # Check timezone offset tag (OffsetTimeOriginal / OffsetTime)
            offset_str = exif_dict.get("OffsetTimeOriginal") or exif_dict.get("OffsetTime")

            captured_dt_utc: Optional[datetime.datetime] = None
            timezone_assumed_ist = False

            if raw_dt_str and isinstance(raw_dt_str, str):
                try:
                    # Clean format "YYYY:MM:DD HH:MM:SS"
                    clean_dt_str = raw_dt_str.strip()[:19]
                    parsed_naive = datetime.datetime.strptime(clean_dt_str, "%Y:%m:%d %H:%M:%S")

                    if offset_str and isinstance(offset_str, str) and ":" in offset_str:
                        sign = -1 if offset_str.startswith("-") else 1
                        clean_off = offset_str.lstrip("+-").strip()
                        off_h, off_m = map(int, clean_off.split(":"))
                        tz = datetime.timezone(datetime.timedelta(hours=sign * off_h, minutes=sign * off_m))
                        captured_dt_utc = parsed_naive.replace(tzinfo=tz).astimezone(datetime.timezone.utc)
                    else:
                        # ASSUMPTION - unverified: naive EXIF timestamp assumed Indian Standard Time (IST, UTC+05:30)
                        captured_dt_utc = parsed_naive.replace(tzinfo=IST_TIMEZONE).astimezone(datetime.timezone.utc)
                        timezone_assumed_ist = True
                except (ValueError, TypeError):
                    pass

            # Parse GPS IFD (0x8825)
            gps_ifd = raw_exif.get_ifd(0x8825)
            lat: Optional[float] = None
            lon: Optional[float] = None

            if gps_ifd:
                gps_dict = {ExifTags.GPSTAGS.get(t, str(t)): v for t, v in gps_ifd.items()}
                lat = _convert_dms_to_dd(gps_dict.get("GPSLatitude"), gps_dict.get("GPSLatitudeRef"))
                lon = _convert_dms_to_dd(gps_dict.get("GPSLongitude"), gps_dict.get("GPSLongitudeRef"))

            camera_make = str(exif_dict.get("Make", "")).strip() or None
            camera_model = str(exif_dict.get("Model", "")).strip() or None

            return {
                "has_exif": True,
                "captured_at_utc": captured_dt_utc.isoformat() if captured_dt_utc else None,
                "timezone_assumed_ist": timezone_assumed_ist,
                "latitude": lat,
                "longitude": lon,
                "camera_make": camera_make,
                "camera_model": camera_model,
                "raw_dt_str": str(raw_dt_str) if raw_dt_str else None,
            }
    except (UnidentifiedImageError, OSError, ValueError, TypeError) as e:
        return {"has_exif": False, "error_reason": f"Corrupt or unsupported image format: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Consistency Checks (Pure Logic)
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_exif_time(
    exif_dt_utc: Optional[datetime.datetime],
    incident_dt_utc: Optional[datetime.datetime],
    support_hours: Optional[float] = None,
    contradict_hours: Optional[float] = None,
) -> ForensicCheckResult:
    """Evaluate time consistency between photo EXIF capture time and declared incident time.

    Product Rule P1: Missing EXIF is NEUTRAL, never a penalty.
    """
    s_hours = (
        support_hours
        if support_hours is not None
        else getattr(settings, "IMAGE_FORENSICS_EXIF_TIME_SUPPORT_HOURS", 3.0)
    )
    c_hours = (
        contradict_hours
        if contradict_hours is not None
        else getattr(settings, "IMAGE_FORENSICS_EXIF_TIME_CONTRADICT_HOURS", 24.0)
    )

    if exif_dt_utc is None:
        return ForensicCheckResult(
            check_type="EXIF_TIME",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=None,
            expected_value=incident_dt_utc.isoformat() if incident_dt_utc else None,
            difference=None,
            reason="Photo does not contain EXIF capture timestamp (common in social media uploads); treated as neutral",
        )

    if incident_dt_utc is None:
        return ForensicCheckResult(
            check_type="EXIF_TIME",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=exif_dt_utc.isoformat(),
            expected_value=None,
            difference=None,
            reason="Incident declaration does not specify an occurrence timestamp; treated as neutral",
        )

    delta_hours = abs((exif_dt_utc - incident_dt_utc).total_seconds()) / 3600.0

    if delta_hours <= s_hours:
        return ForensicCheckResult(
            check_type="EXIF_TIME",
            verdict=ForensicVerdict.SUPPORTS,
            observed_value=exif_dt_utc.isoformat(),
            expected_value=incident_dt_utc.isoformat(),
            difference=f"{delta_hours:.2f} hours",
            reason=f"Photo capture time is within {s_hours:.1f}h of declared incident time (difference: {delta_hours:.2f}h)",
        )
    elif delta_hours > c_hours:
        return ForensicCheckResult(
            check_type="EXIF_TIME",
            verdict=ForensicVerdict.CONTRADICTS,
            observed_value=exif_dt_utc.isoformat(),
            expected_value=incident_dt_utc.isoformat(),
            difference=f"{delta_hours:.2f} hours",
            reason=f"Photo capture time differs by {delta_hours:.1f}h (> {c_hours:.1f}h threshold) from declared incident time",
        )
    else:
        return ForensicCheckResult(
            check_type="EXIF_TIME",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=exif_dt_utc.isoformat(),
            expected_value=incident_dt_utc.isoformat(),
            difference=f"{delta_hours:.2f} hours",
            reason=f"Photo capture time difference ({delta_hours:.2f}h) is between support ({s_hours:.1f}h) and contradict ({c_hours:.1f}h) boundaries",
        )


def evaluate_exif_gps(
    exif_lat: Optional[float],
    exif_lon: Optional[float],
    incident_lat: Optional[float],
    incident_lon: Optional[float],
    support_km: Optional[float] = None,
    contradict_km: Optional[float] = None,
) -> ForensicCheckResult:
    """Evaluate spatial consistency between photo EXIF GPS and declared incident coordinates.

    Product Rule P1: Missing GPS is NEUTRAL, never a penalty.
    Product Rule P5: Privacy — raw coordinates are NOT exposed in explain fields.
    """
    s_km = (
        support_km
        if support_km is not None
        else getattr(settings, "IMAGE_FORENSICS_EXIF_GPS_SUPPORT_KM", 15.0)
    )
    c_km = (
        contradict_km
        if contradict_km is not None
        else getattr(settings, "IMAGE_FORENSICS_EXIF_GPS_CONTRADICT_KM", 50.0)
    )

    if exif_lat is None or exif_lon is None:
        return ForensicCheckResult(
            check_type="EXIF_LOCATION",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=None,
            expected_value="COORDINATES_SPECIFIED" if incident_lat is not None else None,
            difference=None,
            reason="Photo does not contain embedded GPS coordinates (common due to camera privacy settings); treated as neutral",
        )

    if incident_lat is None or incident_lon is None:
        return ForensicCheckResult(
            check_type="EXIF_LOCATION",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value="COORDINATES_PRESENT",
            expected_value=None,
            difference=None,
            reason="Incident has no declared spatial coordinates to compare against; treated as neutral",
        )

    distance_km = haversine_distance_km(exif_lat, exif_lon, incident_lat, incident_lon)

    if distance_km <= s_km:
        return ForensicCheckResult(
            check_type="EXIF_LOCATION",
            verdict=ForensicVerdict.SUPPORTS,
            observed_value="COORDINATES_PRESENT",
            expected_value="DECLARED_INCIDENT_LOCATION",
            difference=f"{distance_km:.2f} km",
            reason=f"Photo GPS coordinates match declared location within {distance_km:.2f} km (<= {s_km:.1f} km)",
        )
    elif distance_km > c_km:
        return ForensicCheckResult(
            check_type="EXIF_LOCATION",
            verdict=ForensicVerdict.CONTRADICTS,
            observed_value="COORDINATES_PRESENT",
            expected_value="DECLARED_INCIDENT_LOCATION",
            difference=f"{distance_km:.2f} km",
            reason=f"Photo GPS coordinates are {distance_km:.2f} km away from declared incident location (> {c_km:.1f} km)",
        )
    else:
        return ForensicCheckResult(
            check_type="EXIF_LOCATION",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value="COORDINATES_PRESENT",
            expected_value="DECLARED_INCIDENT_LOCATION",
            difference=f"{distance_km:.2f} km",
            reason=f"Photo GPS distance ({distance_km:.2f} km) is within ambiguous margin ({s_km:.1f} - {c_km:.1f} km)",
        )


def evaluate_image_reuse(
    current_incident_id: Optional[str],
    candidate_matches: List[Dict[str, Any]],
    incident_dt_utc: Optional[datetime.datetime],
    incident_lat: Optional[float],
    incident_lon: Optional[float],
    reuse_time_hours: Optional[float] = None,
    reuse_distance_km: Optional[float] = None,
) -> ForensicCheckResult:
    """Evaluate potential cross-incident photo reuse.

    Product Rule P3: Reuse is flagged ONLY across DIFFERENT incidents that are far apart in time or place.
    The same photo on the same incident is ordinary duplication, not a flag.
    Product Rule P5: matched_incident_ids exposes other incident IDs only.
    """
    t_hours = (
        reuse_time_hours
        if reuse_time_hours is not None
        else getattr(settings, "IMAGE_FORENSICS_REUSE_TIME_HOURS", 48.0)
    )
    d_km = (
        reuse_distance_km
        if reuse_distance_km is not None
        else getattr(settings, "IMAGE_FORENSICS_REUSE_DISTANCE_KM", 50.0)
    )

    if not candidate_matches:
        return ForensicCheckResult(
            check_type="IMAGE_REUSE",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value="0 matches",
            expected_value="0 cross-incident matches",
            difference="0",
            reason="No duplicate or visually similar images found in platform database",
            matched_incident_ids=[],
        )

    distant_matches: List[str] = []
    same_incident_count = 0
    local_syndication_count = 0

    for match in candidate_matches:
        match_inc_id = str(match.get("incident_id", ""))
        if not match_inc_id:
            continue

        # Same incident duplication check (P3)
        if current_incident_id and match_inc_id == current_incident_id:
            same_incident_count += 1
            continue

        # Check distance and time delta
        match_time: Optional[datetime.datetime] = match.get("created_at") or match.get("occurred_at")
        match_lat: Optional[float] = match.get("latitude")
        match_lon: Optional[float] = match.get("longitude")

        is_distant = False
        time_diff_hours: Optional[float] = None
        space_diff_km: Optional[float] = None

        if match_time and incident_dt_utc:
            if match_time.tzinfo is None:
                match_time = match_time.replace(tzinfo=datetime.timezone.utc)
            time_diff_hours = abs((match_time - incident_dt_utc).total_seconds()) / 3600.0
            if time_diff_hours > t_hours:
                is_distant = True

        if match_lat is not None and match_lon is not None and incident_lat is not None and incident_lon is not None:
            space_diff_km = haversine_distance_km(match_lat, match_lon, incident_lat, incident_lon)
            if space_diff_km > d_km:
                is_distant = True

        if is_distant:
            if match_inc_id not in distant_matches:
                distant_matches.append(match_inc_id)
        else:
            local_syndication_count += 1

    if distant_matches:
        return ForensicCheckResult(
            check_type="IMAGE_REUSE",
            verdict=ForensicVerdict.CONTRADICTS,
            observed_value=f"{len(distant_matches)} distant matches",
            expected_value="0 cross-incident matches",
            difference=f"{len(distant_matches)} distant incident(s)",
            reason=(
                f"Identical or near-identical image previously appeared in {len(distant_matches)} "
                f"separate incident(s) separated by > {t_hours:.0f}h or > {d_km:.0f}km"
            ),
            matched_incident_ids=distant_matches,
        )
    elif same_incident_count > 0:
        return ForensicCheckResult(
            check_type="IMAGE_REUSE",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=f"{same_incident_count} duplicates on same incident",
            expected_value="N/A",
            difference="0 distant matches",
            reason="Same image submitted multiple times for this incident; handled by standard clustering, not flagged as reuse",
            matched_incident_ids=[],
        )
    else:
        return ForensicCheckResult(
            check_type="IMAGE_REUSE",
            verdict=ForensicVerdict.NEUTRAL,
            observed_value=f"{local_syndication_count} localized co-occurring matches",
            expected_value="0 cross-incident matches",
            difference="0 distant matches",
            reason="Matching image found only in nearby concurrent reports of the same weather event; not flagged as fraudulent reuse",
            matched_incident_ids=[],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Overall Forensic Evaluator
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_image_forensics(
    sha256: str,
    phash: str,
    dhash: str,
    exif_data: Dict[str, Any],
    incident_dt_utc: Optional[datetime.datetime],
    incident_lat: Optional[float],
    incident_lon: Optional[float],
    current_incident_id: Optional[str] = None,
    candidate_matches: Optional[List[Dict[str, Any]]] = None,
    cap: Optional[float] = None,
    media_id: Optional[str] = None,
) -> ImageForensicResult:
    """Evaluate all forensic consistency checks and calculate capped credibility adjustment.

    Product Rule P2: Image signals are weak, capped in total, and never alter verification status.
    """
    max_cap = cap if cap is not None else getattr(settings, "IMAGE_FORENSICS_CAP", 0.05)

    checks: List[ForensicCheckResult] = []

    # 1. EXIF Time Check
    exif_dt: Optional[datetime.datetime] = None
    captured_at_str = exif_data.get("captured_at_utc")
    if captured_at_str:
        try:
            exif_dt = datetime.datetime.fromisoformat(captured_at_str)
        except ValueError:
            pass

    time_check = evaluate_exif_time(exif_dt, incident_dt_utc)
    checks.append(time_check)

    # 2. EXIF Location Check
    lat = exif_data.get("latitude")
    lon = exif_data.get("longitude")
    gps_check = evaluate_exif_gps(lat, lon, incident_lat, incident_lon)
    checks.append(gps_check)

    # 3. Image Reuse Check
    reuse_check = evaluate_image_reuse(
        current_incident_id=current_incident_id,
        candidate_matches=candidate_matches or [],
        incident_dt_utc=incident_dt_utc,
        incident_lat=incident_lat,
        incident_lon=incident_lon,
    )
    checks.append(reuse_check)

    # Overall Verdict Calculation
    num_contradicts = sum(1 for c in checks if c.verdict == ForensicVerdict.CONTRADICTS)
    num_supports = sum(1 for c in checks if c.verdict == ForensicVerdict.SUPPORTS)

    if num_contradicts > 0:
        overall_verdict = ForensicVerdict.CONTRADICTS
        # Capped negative adjustment: e.g. -0.05
        # Weak penalty: proportional to contradict severity, bounded by max_cap
        raw_adjustment = -0.03 * num_contradicts
        credibility_adjustment = max(-max_cap, raw_adjustment)
    elif num_supports >= 2:
        overall_verdict = ForensicVerdict.SUPPORTS
        # Capped positive boost: e.g. +0.02
        raw_adjustment = 0.015 * num_supports
        credibility_adjustment = min(max_cap, raw_adjustment)
    else:
        overall_verdict = ForensicVerdict.NEUTRAL
        credibility_adjustment = 0.0

    return ImageForensicResult(
        media_id=media_id,
        sha256=sha256,
        phash=phash,
        dhash=dhash,
        has_exif=exif_data.get("has_exif", False),
        exif_timestamp_utc=captured_at_str,
        timezone_assumed_ist=exif_data.get("timezone_assumed_ist", False),
        checks=checks,
        overall_verdict=overall_verdict,
        credibility_adjustment=round(credibility_adjustment, 4),
        error_reason=exif_data.get("error_reason"),
    )


def process_raw_image_bytes(
    image_bytes: bytes,
    incident_dt_utc: Optional[datetime.datetime],
    incident_lat: Optional[float],
    incident_lon: Optional[float],
    current_incident_id: Optional[str] = None,
    candidate_matches: Optional[List[Dict[str, Any]]] = None,
    media_id: Optional[str] = None,
) -> ImageForensicResult:
    """Process uploaded image bytes through full hashing, EXIF, and forensic pipeline.

    Product Rule P6: Never crash or reject report on corrupt/unsupported images -> returns NEUTRAL.
    """
    sha256 = hashlib.sha256(image_bytes).hexdigest()

    # Size check before decode (P6)
    max_bytes = getattr(settings, "IMAGE_FORENSICS_MAX_FILE_BYTES", 15 * 1024 * 1024)
    if len(image_bytes) > max_bytes:
        return ImageForensicResult(
            media_id=media_id,
            sha256=sha256,
            phash="0" * 16,
            dhash="0" * 16,
            has_exif=False,
            checks=[
                ForensicCheckResult(
                    check_type="SIZE_LIMIT",
                    verdict=ForensicVerdict.NEUTRAL,
                    observed_value=f"{len(image_bytes)} bytes",
                    expected_value=f"<= {max_bytes} bytes",
                    difference=f"{len(image_bytes) - max_bytes} bytes excess",
                    reason="Image file exceeds maximum allowable size before decode; treated as neutral",
                )
            ],
            overall_verdict=ForensicVerdict.NEUTRAL,
            credibility_adjustment=0.0,
            error_reason="FILE_TOO_LARGE",
        )

    # Decode and compute hashes
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            # Check dimensions before reading pixels (P6)
            w, h = pil_img.size
            max_pixels = getattr(settings, "IMAGE_FORENSICS_MAX_PIXELS", 40_000_000)
            if w * h > max_pixels:
                return ImageForensicResult(
                    media_id=media_id,
                    sha256=sha256,
                    phash="0" * 16,
                    dhash="0" * 16,
                    has_exif=False,
                    checks=[
                        ForensicCheckResult(
                            check_type="PIXEL_LIMIT",
                            verdict=ForensicVerdict.NEUTRAL,
                            observed_value=f"{w}x{h} ({w * h} pixels)",
                            expected_value=f"<= {max_pixels} pixels",
                            difference=f"{w * h - max_pixels} excess pixels",
                            reason="Image dimensions exceed maximum allowable pixel count; treated as neutral",
                        )
                    ],
                    overall_verdict=ForensicVerdict.NEUTRAL,
                    credibility_adjustment=0.0,
                    error_reason="PIXEL_LIMIT_EXCEEDED",
                )

            ph = compute_phash(pil_img)
            dh = compute_dhash(pil_img)
    except (UnidentifiedImageError, OSError, ValueError) as err:
        return ImageForensicResult(
            media_id=media_id,
            sha256=sha256,
            phash="0" * 16,
            dhash="0" * 16,
            has_exif=False,
            checks=[
                ForensicCheckResult(
                    check_type="IMAGE_DECODE",
                    verdict=ForensicVerdict.NEUTRAL,
                    observed_value="CORRUPT_PAYLOAD",
                    expected_value="VALID_IMAGE",
                    difference=None,
                    reason=f"Image could not be decoded: {err}; treated as neutral",
                )
            ],
            overall_verdict=ForensicVerdict.NEUTRAL,
            credibility_adjustment=0.0,
            error_reason=f"DECODE_ERROR: {err}",
        )

    # Extract EXIF metadata
    exif_data = extract_exif_metadata(image_bytes)

    # Evaluate forensics
    return evaluate_image_forensics(
        sha256=sha256,
        phash=ph,
        dhash=dh,
        exif_data=exif_data,
        incident_dt_utc=incident_dt_utc,
        incident_lat=incident_lat,
        incident_lon=incident_lon,
        current_incident_id=current_incident_id,
        candidate_matches=candidate_matches,
        media_id=media_id,
    )
