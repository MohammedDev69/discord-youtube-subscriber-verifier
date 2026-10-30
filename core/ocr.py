import io
import re
import asyncio
import logging
import concurrent.futures
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np
from PIL import Image, ImageEnhance
import pytesseract
import aiohttp
from langdetect import detect

from core.config import get_available_ocr_languages

logger = logging.getLogger("youtube-verifier.ocr")

# Supported subscription keywords across multiple languages
SUBSCRIPTION_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "active": ["subscribed", "you're subscribed", "subscriber"],
        "inactive": ["subscribe", "join"],
    },
    "ar": {
        "active": ["مشترك", "أنت مشترك", "اشتركت"],
        "inactive": ["اشتراك", "اشترك", "انتساب"],
    },
    "fr": {
        "active": ["abonné", "vous êtes abonné"],
        "inactive": ["s'abonner", "abonnement"],
    },
    "es": {
        "active": ["suscrito", "estás suscrito"],
        "inactive": ["suscribirse", "suscripción"],
    },
    "de": {
        "active": ["abonniert", "du hast abonniert"],
        "inactive": ["abonnieren", "abonnent"],
    },
    "tr": {
        "active": ["abonesin", "abone oldun"],
        "inactive": ["abone ol", "abone"],
    },
    "pt": {
        "active": ["inscrito", "você está inscrito"],
        "inactive": ["inscrever-se", "inscrição"],
    },
}

# YouTube UI Region patterns (percentage-based bounding boxes: x1, y1, x2, y2)
YOUTUBE_UI_PATTERNS = [
    # Top header / channel card
    {"region": (0.0, 0.0, 1.0, 0.35), "weight": 1.2},
    # Right-hand or mid subscribe button area
    {"region": (0.35, 0.05, 1.0, 0.45), "weight": 1.4},
    # Mobile view button area
    {"region": (0.0, 0.1, 1.0, 0.6), "weight": 1.1},
    # Full image fallback
    {"region": (0.0, 0.0, 1.0, 1.0), "weight": 0.8},
]


@dataclass
class VerificationResult:
    """Encapsulates the full result of a screenshot verification."""
    is_verified: bool
    confidence: float
    detected_language: str
    channel_matched: bool
    subscription_detected: bool
    failure_reason: Optional[str] = None
    detected_texts: Optional[List[str]] = None


def normalize_text(text: str) -> str:
    """Removes special characters, whitespace, and normalizes text for robust matching."""
    if not text:
        return ""
    # Remove leading '@' from channel handles
    cleaned = text.replace("@", "")
    return re.sub(r"\W+", "", cleaned.lower())


def detect_language_safe(text: str) -> str:
    """Safely detects text language with English fallback."""
    try:
        if not text or len(text.strip()) < 8:
            return "en"
        return detect(text)
    except Exception:
        return "en"


async def download_image(url: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[bytes]:
    """Downloads an image securely from Discord with a size limit and timeout."""
    should_close = False
    if session is None:
        session = aiohttp.ClientSession()
        should_close = True

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                # Limit max image download to 15 MB
                content = await response.read()
                if len(content) > 15 * 1024 * 1024:
                    logger.warning(f"Image rejected: size ({len(content)} bytes) exceeds 15MB limit.")
                    return None
                return content
            else:
                logger.warning(f"Failed to download image. Status: {response.status}")
                return None
    except Exception as exc:
        logger.error(f"Error downloading image from {url}: {exc}")
        return None
    finally:
        if should_close:
            await session.close()


def preprocess_image(pil_img: Image.Image, method: str = "enhanced") -> Image.Image:
    """
    Applies image preprocessing techniques to maximize OCR recognition accuracy.
    """
    try:
        if method == "enhanced":
            # Boost contrast and sharpness for clear text edges
            contrast = ImageEnhance.Contrast(pil_img).enhance(2.0)
            sharp = ImageEnhance.Sharpness(contrast).enhance(2.0)
            return sharp

        # Convert to OpenCV BGR
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        if method == "default":
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            return Image.fromarray(gray)

        elif method == "adaptive":
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            return Image.fromarray(binary)

        elif method == "bilateral":
            # Bilateral filter reduces noise while keeping edges crisp
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            filtered = cv2.bilateralFilter(gray, 9, 75, 75)
            return Image.fromarray(filtered)

        elif method == "color_filter":
            # Filter for YouTube button highlights (Blue, Grey, White)
            hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
            lower_blue = np.array([90, 40, 40])
            upper_blue = np.array([140, 255, 255])
            mask = cv2.inRange(hsv, lower_blue, upper_blue)
            result = cv2.bitwise_and(cv_img, cv_img, mask=mask)
            gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            return Image.fromarray(gray)

    except Exception as e:
        logger.warning(f"Preprocessing method '{method}' failed: {e}")

    return pil_img


def extract_regions_of_interest(image: Image.Image) -> List[Tuple[Image.Image, float]]:
    """Extracts priority zones according to typical YouTube interface layouts."""
    width, height = image.size
    regions = []

    for pattern in YOUTUBE_UI_PATTERNS:
        r = pattern["region"]
        weight = pattern["weight"]
        x1 = int(r[0] * width)
        y1 = int(r[1] * height)
        x2 = int(r[2] * width)
        y2 = int(r[3] * height)

        if x2 > x1 and y2 > y1:
            cropped = image.crop((x1, y1, x2, y2))
            regions.append((cropped, weight))

    return regions


def _ocr_single_region(region: Image.Image, method: str, weight: float, lang_arg: str) -> List[Tuple[str, float]]:
    """Runs Tesseract on a single image region with specific preprocessing."""
    results = []
    try:
        processed = preprocess_image(region, method)
        configs = [
            f"--oem 3 --psm 6 {lang_arg}",
            f"--oem 3 --psm 11 {lang_arg}",
            f"--oem 3 --psm 4 {lang_arg}",
        ]

        for cfg in configs:
            text = pytesseract.image_to_string(processed, config=cfg)
            if text and len(text.strip()) > 2:
                confidence = weight * (0.85 if method == "enhanced" else 0.65)
                results.append((text.strip(), confidence))
    except Exception as exc:
        logger.debug(f"OCR region failed ({method}): {exc}")

    return results


def run_ocr_pipeline(image_bytes: bytes) -> List[Tuple[str, float]]:
    """
    Executes multi-method OCR on image bytes using a thread pool.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.error(f"Cannot decode image: {e}")
        return []

    # Determine available Tesseract languages
    available_langs = get_available_ocr_languages()
    lang_parts = []
    if "eng" in available_langs:
        lang_parts.append("eng")
    if "ara" in available_langs:
        lang_parts.append("ara")
    if not lang_parts and available_langs:
        lang_parts.append(available_langs[0])

    lang_arg = f"-l {'+'.join(lang_parts)}" if lang_parts else ""

    regions = extract_regions_of_interest(image)
    methods = ["enhanced", "default", "adaptive"]

    all_results: List[Tuple[str, float]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for region, weight in regions:
            for method in methods:
                futures.append(
                    executor.submit(_ocr_single_region, region, method, weight, lang_arg)
                )

        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    all_results.extend(res)
            except Exception as e:
                logger.warning(f"Error in OCR worker: {e}")

    return all_results


def evaluate_subscription(
    detected_texts: List[Tuple[str, float]],
    channel_name: str,
    alternative_names: Optional[List[str]] = None,
    threshold: float = 0.7,
) -> VerificationResult:
    """
    Evaluates detected text fragments to determine if the screenshot proves
    an active subscription to the specified YouTube channel.
    """
    if not detected_texts:
        return VerificationResult(
            is_verified=False,
            confidence=0.0,
            detected_language="en",
            channel_matched=False,
            subscription_detected=False,
            failure_reason="No readable text detected in the provided image.",
            detected_texts=[],
        )

    all_raw_texts = [text for text, _ in detected_texts]
    norm_target_channel = normalize_text(channel_name)
    norm_alt_names = [normalize_text(name) for name in (alternative_names or [])]

    best_match = {
        "channel_match": False,
        "subscription_active": False,
        "subscription_inactive": False,
        "confidence": 0.0,
        "lang": "en",
    }

    # Combined full text for global scanning
    combined_text = " ".join(all_raw_texts).lower()

    for text, conf in detected_texts:
        text_lower = text.lower()
        norm_text = normalize_text(text)
        detected_lang = detect_language_safe(text)

        # 1. Channel Name Matching
        ch_match = norm_target_channel in norm_text
        if not ch_match and norm_alt_names:
            ch_match = any(alt in norm_text for alt in norm_alt_names if len(alt) >= 3)

        # 2. Check for active subscription keywords (e.g. "Subscribed", "مشترك")
        sub_active = False
        sub_inactive = False

        for lang, key_dict in SUBSCRIPTION_KEYWORDS.items():
            if any(k in text_lower for k in key_dict["active"]):
                sub_active = True
                detected_lang = lang
                break

        # Check for inactive button prompt (e.g., "Subscribe" without "d", "اشتراك")
        if not sub_active:
            for lang, key_dict in SUBSCRIPTION_KEYWORDS.items():
                if any(k in text_lower for k in key_dict["inactive"]):
                    sub_inactive = True
                    detected_lang = lang
                    break

        # Calculate local confidence score
        score = conf
        if sub_active:
            score *= 1.6
        if ch_match:
            score *= 1.6
        if sub_inactive and not sub_active:
            score *= 0.5  # Penalize if it shows the "Subscribe" button rather than "Subscribed"

        if score > best_match["confidence"]:
            best_match = {
                "channel_match": ch_match or best_match["channel_match"],
                "subscription_active": sub_active or best_match["subscription_active"],
                "subscription_inactive": sub_inactive or best_match["subscription_inactive"],
                "confidence": score,
                "lang": detected_lang,
            }

    # Global fallback for channel matching if found across the whole image
    global_norm = normalize_text(combined_text)
    if not best_match["channel_match"]:
        if norm_target_channel in global_norm:
            best_match["channel_match"] = True
        elif any(alt in global_norm for alt in norm_alt_names if len(alt) >= 3):
            best_match["channel_match"] = True

    # Global check for active subscription if not detected locally
    if not best_match["subscription_active"]:
        for lang, key_dict in SUBSCRIPTION_KEYWORDS.items():
            if any(k in combined_text for k in key_dict["active"]):
                best_match["subscription_active"] = True
                best_match["lang"] = lang
                break

    # Profile page heuristic: avoid false positives when just showing channel profile
    profile_indicators = ["videos", "subscribers", "views", "about", "playlist", "community", "فيديو", "مشاهدة"]
    profile_count = sum(1 for ind in profile_indicators if ind in combined_text)
    if profile_count >= 3 and not best_match["subscription_active"]:
        best_match["confidence"] *= 0.4

    # Determine pass/fail
    channel_ok = best_match["channel_match"]
    sub_ok = best_match["subscription_active"]
    confidence_ok = best_match["confidence"] >= threshold
    is_verified = channel_ok and sub_ok and confidence_ok

    failure_reason = None
    if not is_verified:
        if not channel_ok and not sub_ok:
            failure_reason = f"Could not find channel '{channel_name}' or subscription proof in the screenshot."
        elif not channel_ok:
            failure_reason = f"Channel name '{channel_name}' was not detected in the screenshot."
        elif not sub_ok:
            if best_match["subscription_inactive"]:
                failure_reason = "Screenshot displays the 'Subscribe' button instead of confirmed 'Subscribed' status."
            else:
                failure_reason = "No confirmed subscription indicator ('Subscribed' / 'مشترك') was detected."
        elif not confidence_ok:
            failure_reason = f"Verification confidence ({best_match['confidence']:.2f}) was below threshold ({threshold:.2f}). Please provide a clearer screenshot."

    return VerificationResult(
        is_verified=is_verified,
        confidence=min(best_match["confidence"], 1.0),
        detected_language=best_match["lang"],
        channel_matched=channel_ok,
        subscription_detected=sub_ok,
        failure_reason=failure_reason,
        detected_texts=all_raw_texts,
    )


async def verify_screenshot_async(
    image_bytes: bytes,
    channel_name: str,
    alternative_names: Optional[List[str]] = None,
    threshold: float = 0.7,
) -> VerificationResult:
    """Asynchronous wrapper that runs the CPU-heavy OCR pipeline in a worker thread."""
    loop = asyncio.get_running_loop()
    detected_texts = await loop.run_in_executor(None, run_ocr_pipeline, image_bytes)
    return evaluate_subscription(detected_texts, channel_name, alternative_names, threshold)

