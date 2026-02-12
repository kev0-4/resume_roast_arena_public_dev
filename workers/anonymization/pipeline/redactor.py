from typing import Dict, List, Tuple, Any
from copy import deepcopy

ENTITY_TYPES = ("emails", "phones", "urls")


def redact_content(*, blocks: Dict[str, List[Dict]],
                   entities: Dict[str, List[Dict]],
                   ) -> Tuple[Dict[str, List[dict]], Dict[str, List[dict]]]:
    """Applies span based redaction to blocks and logs actions to a file."""

    # build placeholder maps
    placeholder_map = _build_placeholder_map(entities=entities)

    redactions: Dict[str, List[dict]] = {
        entity_type: [] for entity_type in ENTITY_TYPES
    }

    redacted_blocks = deepcopy(blocks)

    # process each block
    for section, block_list in redacted_blocks.items():
        for block in block_list:
            block_text = block["text"]
            block_start = block["source_span"]["start"]
            block_end = block["source_span"]["end"]

           
            replacements = []

            for entity_type in ENTITY_TYPES:
                for entity in entities.get(entity_type, []):
                    span = entity['span']

                    if _span_overlaps(span, block_start, block_end):
                        local_start = span["start"] - block_start
                        local_end = span["end"] - block_start

                        placeholder = placeholder_map[entity_type][entity["value"]]

                        replacements.append(
                            (
                                local_start,
                                local_end,
                                placeholder,
                                entity_type,
                                span,
                            )
                        )

            # Apply replacements (Right-to-Left)
            # This ensures that indices to the left remain stable as we modify the string.
            replacements.sort(key=lambda x: x[0], reverse=True)
            for local_start, local_end, placeholder, entity_type, span in replacements:
                # Identify exactly what is being cut
                

                block_text = (
                    block_text[:local_start]
                    + placeholder
                    + block_text[local_end:]
                )

                redactions[entity_type].append(
                    {
                        "placeholder": placeholder,
                        "original_span": {
                            "start": span["start"],
                            "end": span["end"],
                        }
                    }
                )

            # Update the block with finished text
            block["text"] = block_text
    return redacted_blocks, redactions


def _build_placeholder_map(entities: Dict[str, List[dict]]) -> Dict[str, Dict[str, str]]:
    placeholder_map: Dict[str, Dict[str, str]] = {}
    for entity_type in ENTITY_TYPES:
        placeholder_map[entity_type] = {}
        counter = 1
        for entity in entities.get(entity_type, []):
            value = entity["value"]
            if value not in placeholder_map[entity_type]:
                placeholder_map[entity_type][value] = (
                    f"{{{{{entity_type.upper()[:-1]}_{counter}}}}}"
                )
                counter += 1
    return placeholder_map


def _span_overlaps(span: Dict, start: int, end: int) -> bool:
    return not (span["end"] <= start or span["start"] >= end)
