"""
Docstring for workers.normalization.pipeline.entities

Takes raw text -> extracts emails, phones, urls
TODO (v2): orgs, names, locations + email DNS validation

Design principles:
- Does NOT modify text
- Only extracts spans
- Prefers false negatives over false positives
- Output feeds anonymization layer
"""

import re
from typing import Dict, List

import phonenumbers

# ------------------------------------------------------------
# Regex patterns
# ------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# NOTE: keep broad regex, libphonenumber validates candidates
PHONE_REGEX = re.compile(
    r"(\+?\d{1,3}[\s-]?)?(\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}"
)

URL_REGEX = re.compile(
    r"(https?://[^\s]+|www\.[^\s]+\.[^\s]+)"
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _build_url_positions(urls: List[dict]) -> set:
    """Returns a set of all char positions occupied by a URL span."""
    positions = set()
    for url in urls:
        positions.update(range(url["span"]["start"], url["span"]["end"]))
    return positions


def _is_valid_phone(value: str, region: str = "IN") -> bool:
    """Validate a phone candidate using libphonenumber."""
    try:
        parsed = phonenumbers.parse(value, region)
        return phonenumbers.is_possible_number(parsed) and phonenumbers.is_valid_number(parsed)
    except Exception:
        return False


# ------------------------------------------------------------
# Main extraction
# ------------------------------------------------------------

def extract_entities(*, raw_text: str) -> Dict[str, List[dict]]:
    entities: Dict[str, List[dict]] = {
        "emails": [],
        "phones": [],
        "urls": [],
        "names": [],          # v2
        "organizations": [],  # v2
        "locations": [],      # v2
    }

    # ------------------------------------------------------------
    # 1. Emails
    # ------------------------------------------------------------
    for match in EMAIL_REGEX.finditer(raw_text):
        entities["emails"].append(
            {
                "value": match.group(),
                "span": {"start": match.start(), "end": match.end()},
            }
        )

    # ------------------------------------------------------------
    # 2. URLs — extracted before phones so we can build overlap guard
    # ------------------------------------------------------------
    for match in URL_REGEX.finditer(raw_text):
        value = match.group()

        if len(value) < 8:
            continue

        value = value.rstrip(".,);]")

        entities["urls"].append(
            {
                "value": value,
                "span": {"start": match.start(), "end": match.start() + len(value)},
            }
        )

    url_positions = _build_url_positions(entities["urls"])

    # ------------------------------------------------------------
    # 3. Phones
    # ------------------------------------------------------------
    for match in PHONE_REGEX.finditer(raw_text):
        original_value = match.group()
        value = original_value.strip()

        digits_only = re.sub(r"\D", "", value)

        # Cheap filters first
        if len(digits_only) < 10:
            continue

        if re.fullmatch(r"(19|20)\d{2}[\s\-–](19|20)\d{2}", value):
            continue

        left_strip = len(original_value) - len(original_value.lstrip())
        right_strip = len(original_value) - len(original_value.rstrip())

        start = match.start() + left_strip
        end = match.end() - right_strip  # anchor to match.end() instead
        print("----------------------")
        print(repr(original_value), match.start(), match.end())

        # Reject if span overlaps any URL
        if url_positions.intersection(range(start, end)):
            continue

        # libphonenumber validation — false negatives preferred over false positives
        if not _is_valid_phone(value):
            continue

        entities["phones"].append(
            {
                "value": value,
                "span": {"start": start, "end": end},
            }
        )

    # ------------------------------------------------------------
    # 4. Deduplication
    # ------------------------------------------------------------
    for entity_type in ["emails", "phones", "urls"]:
        seen = set()
        unique_entities = []

        for entity in entities[entity_type]:
            key = (
                entity["value"],
                entity["span"]["start"],
                entity["span"]["end"],
            )

            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        entities[entity_type] = unique_entities

    return entities