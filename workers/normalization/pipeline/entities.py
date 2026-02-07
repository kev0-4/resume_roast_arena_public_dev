'''
Docstring for workers.normalization.pipeline.entities
Takes raw text -> extracts emails, phones,urls,TODO:orgs,names etc and check email dns with 'email-validator' for v2
#TODO: WILL IMPLEMENT A SEPERATE SPACEY NAMED ENTITY RECOGNIZATION + HEURISTICS SERVICE FOR LATER 
does not modify any text , or radact any PII . Prefers false negatives over false positives
returns spans used by anonymization  
'''
import re
from typing import Dict, List

# Regex patterns
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

PHONE_REGEX = re.compile(
    r"(\+?\d{1,3}[\s-]?)?(\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}"
)

URL_REGEX = re.compile(
    r"https?://[^\s]+|www\.[^\s]+"
)


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
    # 1. Extract emails
    for match in EMAIL_REGEX.finditer(raw_text):
        entities["emails"].append(
            {
                "value": match.group(),
                "span": {"start": match.start(), "end": match.end()},
            }
        )

    # ------------------------------------------------------------
    # 2. Extract phone numbers
    # ------------------------------------------------------------
    for match in PHONE_REGEX.finditer(raw_text):
        original_value = match.group()
        value = match.group().strip()

        # TODO:
        # - Add minimal length guard to avoid random numbers
        if len(value) < 7:
            continue
        left_strip = len(original_value) - len(original_value.lstrip())

        entities["phones"].append(
            {
                "value": value,
                "span": {
                    "start": match.start() + left_strip,
                    "end": match.start() + left_strip + len(value)
                },
            }
        )

    # ------------------------------------------------------------
    # 3. Extract URLs
    # ------------------------------------------------------------
    for match in URL_REGEX.finditer(raw_text):
        entities["urls"].append(
            {
                "value": match.group(),
                "span": {"start": match.start(), "end": match.end()},
            }
        )

    # ------------------------------------------------------------
    # 4. Post-processing (optional, v1 minimal)
    # ------------------------------------------------------------
    for entity_type in ["emails", "phones", "urls"]:
        seen = set()
        unique_entities = []

        for entity in entities[entity_type]:
            # Create a tuple key of (value, start, end)
            key = (
                entity["value"],
                entity["span"]["start"],
                entity["span"]["end"]
            )

            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)

        entities[entity_type] = unique_entities

    return entities
