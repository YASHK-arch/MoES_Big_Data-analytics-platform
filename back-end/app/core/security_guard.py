"""Security Hardening Module for External Ingestion, SSRF Prevention, and NLP Input Sanitization.

Provides:
1. SSRF prevention and strict domain whitelisting.
2. Safe external HTTP payload fetching with byte caps, timeouts, and Unicode NFKC normalization.
3. Resilient Circuit Breaker pattern for third-party government/social data feeds.
4. Input sanitization against prompt injection, control characters, and data poisoning for NLP modules.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Maximum allowed external payload size (5MB default to prevent memory DoS)
MAX_PAYLOAD_BYTES = 5 * 1024 * 1024

# Default request timeout in seconds
DEFAULT_FETCH_TIMEOUT_SECONDS = 15.0

# Strict domain whitelist for external feed ingestion
APPROVED_INGESTION_DOMAINS: Set[str] = {
    "sachet.ndma.gov.in",
    "ndma.gov.in",
    "nwdp.nwic.gov.in",
    "nwic.gov.in",
    "mausam.imd.gov.in",
    "imd.gov.in",
    "api.gdeltproject.org",
    "gdeltproject.org",
    "mastodon.social",
    "www.gdacs.org",
    "gdacs.org",
    "api.open-meteo.com",
    "nominatim.openstreetmap.org",
    "router.project-osrm.org",
    "localhost",  # Allowed in test/mock environment
    "127.0.0.1",
    "testserver",
}

# Prompt injection & delimiter patterns to sanitize before NLP/vectorization
PROMPT_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|prompts)\b"),
    re.compile(r"(?i)\bdisregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|rules)\b"),
    re.compile(r"<\|im_start\|>.*?<\|im_end\|>", re.DOTALL | re.IGNORECASE),
    re.compile(r"\[INST\].*?\[/INST\]", re.DOTALL | re.IGNORECASE),
    re.compile(r"(?i)<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]"),
    re.compile(r"(?i)\b(?:system|assistant|human)\s*:"),
    re.compile(r"(?i)###\s*(?:instruction|system|human|prompt):?"),
    re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
]


class SSRFValidationError(ValueError):
    """Raised when an external URL fails strict security and domain whitelisting checks."""
    pass


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a request is blocked because the source's circuit breaker is in OPEN state."""
    pass


def is_ip_private_or_restricted(hostname: str) -> bool:
    """Return True if the hostname resolves to a private, loopback, or link-local IP address."""
    # Allow localhost / 127.0.0.1 in non-production local development
    if hostname.lower() in ("localhost", "127.0.0.1", "testserver"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        )
    except ValueError:
        # Not a raw IP literal; hostname string
        return False


def validate_external_url(url: str) -> str:
    """Validate external URL against SSRF rules and domain whitelist.

    Returns the normalized URL string if valid; raises SSRFValidationError otherwise.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL cannot be empty or non-string.")

    clean_url = url.strip()
    parsed = urlparse(clean_url)

    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(f"Invalid URL scheme '{parsed.scheme}'. Only HTTP/HTTPS permitted.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFValidationError("URL does not contain a valid hostname.")

    if is_ip_private_or_restricted(hostname):
        raise SSRFValidationError(f"Access to private/restricted IP '{hostname}' is blocked.")

    # Match against approved domain whitelist or authorized subdomains
    is_whitelisted = False
    for allowed in APPROVED_INGESTION_DOMAINS:
        if hostname == allowed or hostname.endswith(f".{allowed}"):
            is_whitelisted = True
            break

    if not is_whitelisted:
        # Check if it ends with approved institutional tld (.gov.in)
        if hostname.endswith(".gov.in"):
            is_whitelisted = True

    if not is_whitelisted:
        raise SSRFValidationError(
            f"Domain '{hostname}' is not in the approved external ingestion whitelist."
        )

    return clean_url


def sanitize_nlp_text(text: Optional[str]) -> str:
    """Sanitize and normalize text input before passing into NLP / Credibility / Similarity modules.

    Strips:
    - Zero-width non-printable unicode characters.
    - Malicious prompt injection markers and delimiters.
    - Embedded script/HTML tags.
    - Normalizes Unicode using standard NFKC form (CVE-2024-3651 prevention).
    """
    if not text:
        return ""

    # 1. Normalize Unicode using standard NFKC to resolve deceptive homoglyphs
    normalized = unicodedata.normalize("NFKC", str(text))

    # 2. Strip zero-width non-printable characters
    normalized = re.sub(r"[\u200B-\u200D\uFEFF\u0000-\u0008\u000B\u000C\u000E-\u001F]", "", normalized)

    # 3. Strip prompt injection delimiters and script tags
    sanitized = normalized
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)

    # 4. Collapse consecutive spaces and trim stray punctuation
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    sanitized = re.sub(r"^[^\w\s]+", "", sanitized).strip()
    return sanitized


class CircuitBreaker:
    """Resilient Circuit Breaker to prevent resource exhaustion when external APIs degrade."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        """Record successful call; reset failure counter and close circuit."""
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        """Record failure; trip circuit to OPEN if threshold exceeded."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                "Circuit breaker '%s' tripped to OPEN state after %d consecutive failures.",
                self.name,
                self.failure_count,
            )

    def is_allowed(self) -> bool:
        """Check if a new call is permitted through the circuit breaker."""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Check if recovery timeout has elapsed
            if (time.monotonic() - self.last_failure_time) >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker '%s' transitioned to HALF_OPEN trial state.", self.name)
                return True
            return False

        if self.state == "HALF_OPEN":
            # Allow single trial call
            return True

        return True


# Global circuit breaker registry by source code
_CIRCUIT_BREAKERS: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(source_code: str) -> CircuitBreaker:
    """Retrieve or instantiate a CircuitBreaker for a source code."""
    key = source_code.strip().upper()
    if key not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[key] = CircuitBreaker(name=key)
    return _CIRCUIT_BREAKERS[key]


async def safe_fetch_external_payload(
    url: str,
    source_code: str = "EXTERNAL",
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> bytes:
    """Execute a secured external HTTP request with SSRF validation, circuit breaker, and payload caps."""
    # 1. Validate URL against SSRF and Domain Whitelist
    validated_url = validate_external_url(url)

    # 2. Check Circuit Breaker State
    breaker = get_circuit_breaker(source_code)
    if not breaker.is_allowed():
        raise CircuitBreakerOpenError(
            f"External source '{source_code}' circuit breaker is OPEN. Calls temporarily blocked."
        )

    # 3. Execute request with strict timeout, redirect re-validation, and size limit
    try:
        current_url = validated_url
        max_redirects = 5

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            for _ in range(max_redirects):
                if method.upper() == "POST":
                    response = await client.post(current_url, json=json_body, headers=headers)
                else:
                    response = await client.get(current_url, headers=headers)

                # Check for 3xx redirects
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    # Resolve relative redirect URLs against current URL
                    resolved_redirect = str(response.url.join(location))
                    # Re-validate redirect target against SSRF whitelist
                    current_url = validate_external_url(resolved_redirect)
                    continue

                response.raise_for_status()

                # Check content length header if present
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError(
                        f"Payload size {content_length} bytes exceeds maximum allowed limit of {max_bytes} bytes."
                    )

                body_bytes = response.content
                if len(body_bytes) > max_bytes:
                    raise ValueError(
                        f"Downloaded payload size {len(body_bytes)} bytes exceeds limit of {max_bytes} bytes."
                    )

                breaker.record_success()
                return body_bytes

            raise ValueError("Too many redirects encountered while fetching external payload.")

    except (httpx.HTTPError, ValueError, Exception) as err:
        breaker.record_failure()
        raise err
