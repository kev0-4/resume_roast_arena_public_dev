

'''
Docstring for workers.normalization.pipeline.metrics
Metrics computation for normalization pipeline.
Responsibilities:
- Compute numeric / continuous metrics
- No boolean judgments
'''
'''
sample output format
{
  "word_count": int,
  "character_count": int,

  "experience_block_count": int,
  "experience_date_count": int,

  "email_count": int,
  "phone_count": int,
  "url_count": int,

  "avg_sentence_length": float,

  "lexical_diversity": float,

  "metric_density": float   # v2 optional
}
'''

import re
from typing import Dict


YEAR_REGEX = re.compile(r"(19|20)\d{2}")
SENTENCE_SPLIT_REGEX = re.compile(r"[.!?]+")



def compute_metrics(blocks: Dict[str, list], entities: Dict[str, list],raw_text: str) -> Dict[str,float]:
    metrics: Dict[str, float] = {}


    # 1. Text size metrics
    # ------------------------------------------------------------
    words = raw_text.split()
    metrics["word_count"] = len(words)
    metrics["character_count"] = len(raw_text)


    # 2. Experience metrics
    # ------------------------------------------------------------
    experience_blocks = blocks.get("experience", [])
    metrics["experience_block_count"] = len(experience_blocks)

    date_count = 0
    for block in experience_blocks:
        date_count += len(YEAR_REGEX.findall(block.get("text", "")))
    metrics["experience_date_count"] = date_count


    # 3. Contact metrics
    # ------------------------------------------------------------
    metrics["email_count"] = len(entities.get("emails", []))
    metrics["phone_count"] = len(entities.get("phones", []))
    metrics["url_count"] = len(entities.get("urls", []))



    # 4. Sentence metrics
    # ------------------------------------------------------------
    sentences = [
        s.strip() for s in SENTENCE_SPLIT_REGEX.split(raw_text)
        if s.strip()
    ]

    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        metrics["avg_sentence_length"] = round(avg_len, 2)
    else:
        metrics["avg_sentence_length"] = 0.0

    # 5. Vocabulary metrics
    # ------------------------------------------------------------
    alpha_words = [
        w.lower() for w in words
        if w.isalpha()
    ]

    if alpha_words:
        unique_words = len(set(alpha_words))
        metrics["lexical_diversity"] = round(
            unique_words / len(alpha_words), 3
        )
    else:
        metrics["lexical_diversity"] = 0.0


    # 6. Metric density (v2 placeholder)
    # ------------------------------------------------------------
    # TODO (v2):
    # metrics["metric_density"] = compute_metric_density(raw_text)
    metrics["metric_density"] = None
    return metrics
    

