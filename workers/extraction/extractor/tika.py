import requests
from typing import Tuple
from ..errors import TransientExtractionError,PermanentExtractionError
from ...config import TIKA_SERVER_ENDPOINT
from backend.src.utils.telemetry import emit_event
from tika import parser
import os
os.environ['TIKA_SERVER_ENDPOINT'] = 'http://localhost:9998'
os.environ['TIKA_CLIENT_ONLY'] = 'True'

TIKA_TIMEOUT = 30

def extract_with_tika(raw_bytes: bytes):
    headers = {
        "Content-Type": "application/octet-stream",
        "Accept": "text/plain",
    }

    try:
        response = parser.from_buffer(raw_bytes)
        emit_event(
            "extraction.tika.raw_response",
            {"status_code": response.get('status'), "status": "INFO"},
        )
    except requests.exceptions.Timeout as e:
        raise TransientExtractionError("Tika timeout") from e

    except requests.exceptions.ConnectionError as e:
        raise TransientExtractionError("Tika connection error") from e
    except Exception as e:
        raise TransientExtractionError("Unexpected Tika error") from e

    if int(response.get('status')) >= 500:
        raise TransientExtractionError(
            f"Tika server error: {response.get('status')}"
        )

    if int(response.get('status')) == 415:
        raise PermanentExtractionError("Unsupported file type")

    if int(response.get('status')) != 200:
        raise PermanentExtractionError(
            f"Tika failed with status {response.get('status')}"
        )
    text = response.get('content')
    text = text.strip()
    confidence = 90
    res = {
        "text": text,
        "confidence": confidence,
        "response_code": response.get('status')
    }

    emit_event(
        "extraction.tika.complete",
        {"confidence": confidence, "char_count": len(text), "status": "INFO"},
    )
    return res


def extract_with_ocr(raw_bytes: bytes):
    headers = {
    "X-Tika-OCRLanguage": "eng",
    "X-Tika-PDFOcrStrategy": "ocr_only"
    }

    try:
        response = parser.from_buffer(raw_bytes,headers=headers)
        emit_event(
            "extraction.ocr.raw_response",
            {"status_code": response.get('status'), "status": "INFO"},
        )
    except requests.exceptions.Timeout as e:
        raise TransientExtractionError("Tika timeout") from e

    except requests.exceptions.ConnectionError as e:
        raise TransientExtractionError("Tika connection error") from e
    except Exception as e:
        raise TransientExtractionError("Unexpected Tika error") from e

    if int(response.get('status')) >= 500:
        raise TransientExtractionError(
            f"Tika server error: {response.get('status')}"
        )

    if int(response.get('status')) == 415:
        raise PermanentExtractionError("Unsupported file type")

    if int(response.get('status')) != 200:
        raise PermanentExtractionError(
            f"Tika failed with status {response.get('status')}"
        )
    text = response.get('content')
    text = text.strip()
    confidence = 90
    res = {
        "text": text,
        "confidence": confidence,
        "response_code": response.get('status')
    }

    emit_event(
        "extraction.ocr.complete",
        {"confidence": confidence, "char_count": len(text), "status": "INFO"},
    )
    return res


def compute_confidence(text: str) -> float:
    char_count = len(text)
    word_count = len(text.split())

    if char_count >= 800:
        return 0.95
    if char_count >= 300:
        return 0.75
    if char_count >= 100:
        return 0.5
    return 0.2
