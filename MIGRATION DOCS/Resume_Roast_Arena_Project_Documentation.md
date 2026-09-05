# Resume Roast Arena — Project Documentation & Migration Guide

> **Purpose:** Restore context after a long break or migrate the project to another ChatGPT/model.
>
> **Current documented state:** Core asynchronous backend pipeline through deterministic scoring has been implemented and end-to-end wired/tested. LLM generation, rendering, public sharing, and production hardening remain.

---

## 1. Project identity

**Product:** Resume Roast Arena

**One-liner:** Instant, anonymized resume “roasts”: automated, shareable scorecard and targeted fix suggestions.

**Target audience:** College students and early-career hires seeking fast feedback and viral shareability.

**Primary value:** Low-friction upload → automated harsh-but-actionable feedback → shareable roast card.

The canonical MVP brief explicitly describes the project as a **backend-only implementation initially, with no frontend UI required**, using Azure as the cloud platform. fileciteturn5file0L1-L8

---

# 2. Current architecture

The implemented pipeline evolved into:

```text
FastAPI /ingest
      |
      | upload raw file
      v
Azure Blob Storage
      |
      | enqueue_extraction
      v
Azure Service Bus
      |
      v
Extraction Worker
  Tika
    |
    | low confidence
    v
  Tesseract OCR
      |
      v
extracted.json
      |
      | enqueue_normalization
      v
Normalization Worker
  loader
  segmenter
  entities
  signals
  metrics
  assembler
      |
      v
normalized.json
      |
      | enqueue_anonymization
      v
Anonymization Worker
  loader
  redactor
  assembler
      |
      v
anonymized.json
      |
      | enqueue_scoring
      v
Scoring Worker
  loader
  rules
  scorer
  assembler
      |
      v
scored.json
      |
      | FUTURE
      v
Prompt Builder
      |
      v
LLM Roast Generator
      |
      v
Roast Result
      |
      v
Renderer
      |
      v
Public Share Link / Roast Card
```

The original architecture called for the same broad flow: client → ingest → Blob → queue → extraction → normalization → anonymization → rule evaluator/LLM → scoring → renderer → public link/CDN. fileciteturn4file0L1-L8

---

# 3. What is definitely completed

## 3.1 Ingestion API

Implemented:

```text
POST /ingest
GET /sessions/{session_id}
```

The ingest route currently:

1. Validates the uploaded file.
2. Gets the authenticated user when available.
3. Supports `X-Idempotency-Key`.
4. Creates a session.
5. Uploads the original file to Blob Storage.
6. Stores the raw blob path against the session.
7. Moves the session to `QUEUED`.
8. Enqueues an extraction message.
9. Returns `session_id`.

The user tested this route and confirmed the extraction worker was triggered successfully.

---

# 4. Extraction Worker — COMPLETE

## Architecture

```text
workers/extraction/
    main.py
    consumer.py
    processor.py
    state.py
    schemas.py
    errors.py
    extractor/
        tika.py
```

### Implemented

- Service Bus consumer.
- Message deserialization/validation.
- DB session handling.
- State transitions.
- Blob read.
- Apache Tika extraction.
- Confidence computation.
- Confidence threshold routing.
- Tesseract OCR fallback.
- Extracted payload assembly.
- Extracted artifact upload.
- Retry/transient error classification.
- Permanent failure handling.
- ACK / abandon / DLQ handling.
- Graceful shutdown.
- Worker `main.py`.

### Important extraction behavior

Current threshold:

```python
TIKA_CONFIDENCE_THRESHOLD = 0.50
```

Tika result:

```python
raw_text = result.get("text")
confidence = compute_confidence(raw_text)
```

If confidence is below the threshold:

```text
Tika → LowConfidenceError → Tesseract OCR
```

OCR confidence is currently represented as:

```python
OCR_CONFIDENCE = 0.80
```

Minimum extracted content is guarded before creating the artifact.

### Testing

Extraction was tested with:

- PDF
- Images

The worker successfully produced Blob artifacts.

---

# 5. Normalization Worker — COMPLETE

## Architecture

```text
workers/normalization/
    main.py
    consumer.py
    processor.py
    state.py
    schemas.py
    errors.py

    pipeline/
        loader.py
        segmenter.py
        entities.py
        signals.py
        metrics.py
        assembler.py
```

## Loader

`loader.py`:

```text
extracted.json
    ↓
read blob
    ↓
parse JSON
    ↓
validate minimum structure
    ↓
trusted dict
```

It treats:

- Blob read failures → transient.
- Invalid JSON/structure → permanent.

Required extracted fields include:

```text
session_id
raw_text
extraction_version
source
timestamps
```

---

## Segmenter

`segmenter.py`:

```text
raw_text
   ↓
split into lines with source spans
   ↓
detect known section headers
   ↓
accumulate section content
   ↓
flush blocks
   ↓
remove empty blocks
```

Current sections:

```text
summary
experience
education
skills
projects
certifications
other
```

Each block contains:

```json
{
  "text": "...",
  "source_span": {
    "start": 123,
    "end": 456
  }
}
```

Current known-header regexes include:

```text
summary / profile / objective
experience / work experience / employment
education / academics
skills / technical skills / technologies
projects / academic projects
certifications / certificates
```

Deferred:

```text
TODO v2: Header false-positive guard
```

---

# 6. Entity extraction — COMPLETE for v1

`entities.py` extracts:

```text
emails
phones
urls
```

The design deliberately prefers false negatives over false positives.

Future/deferred:

```text
names
organizations
locations
```

Also deferred:

```text
email DNS validation
dedicated NER/heuristics service
```

### Known limitation

The phone regex can falsely identify things such as years/numeric ranges as phones. This was explicitly observed during testing.

Example:

```text
2022 2026
2017-2020
```

can be detected as phones.

This should be fixed in a later anonymization/entity-quality pass.

---

# 7. Signals — COMPLETE v1

`signals.py` computes deterministic boolean/categorical features.

## Tier 1 — always available

Includes:

```text
has_summary
has_experience
has_projects
has_skills
has_education
has_certifications

has_email
has_phone
has_contact_info
has_links
has_professional_links

has_dates_in_experience

first-person basic signals

word-count related signals
```

## Tier 2 — optional spaCy

Designed for graceful degradation.

Includes:

```text
contextual first-person detection
first-person in experience
passive voice
action verbs
sentence quality
lexical diversity
```

The implementation guards advanced rules with:

```text
nlp_analysis_successful
```

so unavailable/failed NLP does not become an accidental negative signal.

Deferred:

```text
metric density
bullet consistency
stronger NER
better linguistic quality detection
```

---

# 8. Metrics — COMPLETE v1

`metrics.py` computes numeric metrics.

Current metrics:

```text
word_count
character_count

experience_block_count
experience_date_count

email_count
phone_count
url_count

avg_sentence_length
lexical_diversity

metric_density = null
```

Deferred:

```text
metric_density
bullet consistency
more sophisticated numeric achievement extraction
```

---

# 9. Normalized artifact

Typical shape:

```json
{
  "session_id": "...",
  "normalization_version": "1.0",

  "source": {
    "extraction_version": "1.0",
    "used_ocr": false,
    "confidence": 0.95
  },

  "content": {
    "blocks": {},
    "entities": {}
  },

  "signals": {},
  "metrics": {},

  "timestamps": {
    "extracted_at": "...",
    "normalized_at": "..."
  }
}
```

A real normalized artifact was successfully produced and inspected.

---

# 10. Anonymization Worker — COMPLETE

## Architecture

```text
workers/anonymization/
    main.py
    consumer.py
    processor.py
    state.py
    schemas.py
    errors.py

    pipeline/
        loader.py
        redactor.py
        assembler.py
```

## Loader

Loads and validates `normalized.json`.

---

## Redactor

`redactor.py` performs deterministic, span-based redaction.

Current entity types:

```text
emails
phones
urls
```

Placeholder format:

```text
{{EMAIL_1}}
{{PHONE_1}}
{{URL_1}}
```

Repeated identical entities receive the same placeholder.

Example:

```text
alice@example.com
alice@example.com
```

becomes:

```text
{{EMAIL_1}}
{{EMAIL_1}}
```

Redaction uses right-to-left replacement so original spans remain valid while replacing text.

Redaction metadata records the original span and generated placeholder.

### Tests

A dedicated redactor unit test suite was run.

All tests passed, including:

1. single email
2. multiple entities
3. multiple blocks
4. repeated email
5. no entities
6. right-to-left replacement
7. entity outside block range

---

# 11. Anonymized artifact

Current shape:

```json
{
  "session_id": "...",
  "anonymization_version": "1.0",

  "content": {
    "blocks": {}
  },

  "redactions": {
    "emails": [],
    "phones": [],
    "urls": []
  },

  "signals": {},
  "metrics": {},

  "timestamps": {
    "normalized_at": "...",
    "anonymized_at": "..."
  }
}
```

Important security rule:

> No external LLM/API call should receive non-anonymized resume content.

The original MVP explicitly requires PII redaction before external API calls. fileciteturn5file4L1-L8

---

# 12. Scoring Worker — COMPLETE v1

## Architecture

```text
workers/scoring/
    main.py
    consumer.py
    processor.py
    state.py
    schemas.py
    errors.py

    pipeline/
        loader.py
        rules.py
        scorer.py
        assembler.py
        prompt_builder.py
```

## State flow

```text
ANONYMIZED
    ↓
SCORING
    ↓
SCORED
```

---

## Scoring schemas

Severity is explicitly represented.

```text
critical
high
medium
low
```

Issue:

```json
{
  "code": "...",
  "message": "...",
  "severity": "high"
}
```

Strength:

```json
{
  "code": "...",
  "message": "..."
}
```

Summary:

```text
total_issues
critical_issues
high_issues
medium_issues
low_issues
total_strengths
```

This was deliberately changed from the earlier partial severity breakdown after reviewer feedback.

---

# 13. Scoring loader

Loads:

```text
anonymized/<session_id>/anonymized.json
```

Validates:

```text
session_id
content
signals
metrics
timestamps
```

It treats Blob read errors as transient and malformed JSON/structure as permanent.

Timestamp validation is intentionally light because scoring does not depend on timestamps for its actual rule evaluation.

---

# 14. Scoring rules — COMPLETE v1

Rules consume:

```text
signals
metrics
blocks
```

They do not reparse resume text.

Current rule categories:

### Section presence

```text
NO_EXPERIENCE
NO_PROJECTS
NO_SUMMARY
```

### Contact

```text
NO_CONTACT_INFO
NO_PROFESSIONAL_LINKS
```

### Experience

```text
NO_DATES_IN_EXPERIENCE
```

### Writing

```text
FIRST_PERSON_USAGE
RESUME_TOO_SHORT
RESUME_TOO_LONG
```

### Metrics

```text
EXCESSIVE_LENGTH
LONG_SENTENCES
LOW_VOCABULARY_VARIETY
```

### Strength examples

```text
HAS_EXPERIENCE
HAS_PROJECTS
HAS_SUMMARY
HAS_LINKS
HAS_SKILLS
GOOD_VOCABULARY
```

NLP rules were added with a guard:

```python
if signals.get("nlp_analysis_successful"):
```

Then:

```text
PASSIVE_VOICE
NO_ACTION_VERBS
```

are evaluated.

Important correction made during development:

`is_too_short` / `is_too_long` were not actually present in the final signals contract, so length scoring was moved to the reliable metrics layer:

```python
word_count = metrics.get("word_count", 0)
```

---

# 15. Scorer

`scorer.py`:

```text
evaluate_rules()
    ↓
dedupe issues
    ↓
dedupe strengths
    ↓
ScoringResult
```

Deduplication keys:

```text
issues: code + severity
strengths: code
```

No DB, Blob, or queue interaction.

---

# 16. Scoring assembler

Produces `scored.json`.

It:

- validates minimum upstream shape
- calculates severity summary
- preserves signals
- preserves metrics
- carries timestamps forward
- serializes Pydantic models

Example:

```json
{
  "session_id": "...",
  "scoring_version": "1.0",

  "summary": {
    "total_issues": 5,
    "critical_issues": 1,
    "high_issues": 2,
    "medium_issues": 1,
    "low_issues": 1,
    "total_strengths": 3
  },

  "issues": [],
  "strengths": [],

  "signals": {},
  "metrics": {},

  "timestamps": {
    "anonymized_at": "...",
    "scored_at": "..."
  }
}
```

---

# 17. Scoring processor/consumer/main — COMPLETE

The scoring worker has been wired with:

```text
processor.py
consumer.py
main.py
state.py
```

The consumer handles:

```text
invalid payload → DLQ
permanent processing failure → DLQ
transient failure → abandon/retry
max delivery count → DLQ
success → complete
SIGTERM/SIGINT → graceful shutdown
```

---

# 18. Service Bus chaining — COMPLETE

The pipeline was explicitly wired end-to-end.

Current chain:

```text
ingest
  → enqueue_extraction

extraction success
  → enqueue_normalization

normalization success
  → enqueue_anonymization

anonymization success
  → enqueue_scoring
```

The user tested the full chain and confirmed it works.

---

# 19. Prompt Builder — STARTED / NOT COMPLETE

A design was created for:

```text
workers/scoring/pipeline/prompt_builder.py
```

Purpose:

```text
scored/anonymized content
      ↓
LLM-readable prompt
```

One important design decision was made:

Stored anonymized artifact keeps:

```text
{{EMAIL_1}}
{{PHONE_1}}
```

but prompt construction converts these to:

```text
[EMAIL]
[PHONE]
```

Current recommended implementation:

```python
PLACEHOLDER_REGEX = re.compile(r"\{\{([A-Z]+)_\d+\}\}")

def normalize_placeholders(text: str) -> str:
    return PLACEHOLDER_REGEX.sub(
        lambda m: f"[{m.group(1)}]",
        text
    )
```

Reason:

```text
{{EMAIL_1}}
```

can look like a template/code variable to an LLM, whereas:

```text
[EMAIL]
```

clearly communicates redaction.

### Important unresolved issue

At the time of the pause, the prompt builder design expected resume blocks to be available to the prompt. The current `scored.json` design discussed earlier does not necessarily preserve `content.blocks`.

Before implementing the LLM layer, decide one of:

```text
A. Preserve anonymized content.blocks in scored.json
OR
B. Prompt builder loads anonymized.json separately
```

Do not accidentally send the original normalized/raw resume to an external model.

---

# 20. Important artifact paths

The project uses stage-specific Blob paths.

Expected pattern:

```text
raw/<session_id>/...
extracted/<session_id>/extracted.json
normalized/<session_id>/normalized.json
anonymized/<session_id>/anonymized.json
scored/<session_id>/scored.json
```

Verify the exact raw-file filename convention in the current Blob service before changing it.

---

# 21. Database state model

The pipeline requires states along the lines of:

```text
QUEUED
PROCESSING
EXTRACTED
NORMALIZING / NORMALIZED
ANONYMIZING / ANONYMIZED
SCORING
SCORED
FAILED
```

Exact enum names in the current codebase are authoritative.

Before further work, inspect the actual `JobStatusEnum` rather than assuming names.

---

# 22. Known architectural caveats to revisit

These are important because the project was built incrementally.

## A. Processor → enqueue ordering

Current implementation pattern should be reviewed carefully around:

```text
upload artifact
mark success
commit DB
enqueue next stage
```

The desired invariant is:

> Never enqueue a downstream stage before the upstream artifact and state transition are durably successful.

However, this creates a classic distributed-system problem if DB commit succeeds but enqueue fails.

Longer-term solution:

```text
Transactional outbox
```

or equivalent durable event mechanism.

Do not blindly “fix” this by putting everything in one transaction; Blob and Service Bus are separate systems.

---

## B. `upload_anonymized` / `upload_scored` error handling

At one point `upload_anonymized` was implemented with:

```python
try:
    ...
except Exception:
    print(...)
    pass
```

This is **not production safe**.

A failed Blob upload must raise an error so the processor does not mark the session successful.

Review all artifact upload functions and ensure they:

```text
raise on failure
```

rather than silently returning success.

---

## C. Time handling

The project currently uses `datetime.utcnow()` in several places.

Standardize timestamps later, preferably around timezone-aware UTC timestamps.

---

## D. Logging

Some worker code still uses:

```python
print(...)
```

Replace with structured logging / `emit_event`.

The original MVP explicitly calls for observability hooks throughout the pipeline. fileciteturn4file4L1-L8

---

## E. Pydantic version

A test log showed:

```text
Pydantic V2 warning:
orm_mode → from_attributes
```

This should be cleaned up when hardening the backend.

---

# 23. Original MVP requirements still not implemented

The canonical MVP brief includes substantially more than the current pipeline.

## LLM Roast Generator

Required:

```text
Azure OpenAI or OpenAI API
sanitized prompt
concise roast body
prompt templates in repo
token limits
rate limits
hallucination/safety monitoring
```

The original brief specifically calls for an LLM roast generator using sanitized prompt templates. fileciteturn4file0L1-L8

---

## LLM Roast Generator — Update 2026-09-05: DONE

`workers/llm/` implemented and verified end-to-end against real infra. Provider is **Gemini** (`google-genai`, `gemini-3.5-flash-lite`), not Azure OpenAI as planned above — no Anthropic/OpenAI key was available, Gemini had free-tier credits; `workers/llm/pipeline/client.py` is the single seam to swap providers again later (OpenAI mentioned as a likely future move). Prompt sanitization requirement is met: the prompt builder only ever receives anonymized content, placeholders normalized `{{EMAIL_1}}` → `[EMAIL]`.

---

## Composite scoring

The original MVP calls for numeric:

```text
Clarity
Credibility
Signal-to-Noise
```

plus scoring rationale.

Current deterministic scoring is primarily:

```text
issues
strengths
severity
summary
```

So **numeric composite scoring (Clarity/Credibility/Signal-to-Noise) is still outstanding.**

This distinction is important: the current "scoring worker" is an initial rule evaluator, not yet the complete scoring service described in the original MVP.

**Update 2026-09-05:** a *different*, simpler 0-100 composite score (not Clarity/Credibility/Signal-to-Noise) was designed for the roast card's stat display — see section 29. It's derived from `summary` (issue/strength counts), not a new scoring dimension, and doesn't replace this outstanding MVP item.

---

## Renderer

Still outstanding (implementation), but the visual design and the data it will use are now decided — see section 29.

```text
HTML roast card
→ PNG/OG image
→ Blob Storage
```

---

## Public Link Service

Still outstanding:

```text
short slug
→ roast asset
→ TTL/public resolver
```

**Planned follow-on (not yet designed):** a leaderboard / global comparison feature — ranking public roasts by the composite score (section 29), e.g. percentile stats like "better than 92% of resumes." Noted here 2026-09-05 so scoring/renderer decisions don't paint this into a corner (e.g. the composite score needs to stay a stored, comparable field, not just rendered text on the card).

---

## TTL / cleanup

Original requirements:

```text
raw uploads → delete after 24 hours
anonymous roast metadata → 30 days
logged-in retention → configurable
```

Still outstanding.

---

## Redis

Original design calls for:

```text
Azure Cache for Redis
```

for:

```text
transient session state
rate limiting
```

Still outstanding.

---

## Rate limiting / CAPTCHA

Still outstanding:

```text
per-IP rate limiting
per-session rate limiting
CAPTCHA for high-frequency anonymous usage
```

---

## Auth hardening

Google Sign-In via Firebase Authentication was part of the original plan, with anonymous uploads initially allowed. fileciteturn5file0L1-L8

Review the current auth implementation against this requirement.

---

## Observability

Original requirement:

```text
Azure Monitor
Application Insights
structured JSON logs
metrics
traces
```

Current code has telemetry hooks but still needs a production observability pass.

---

## CI/CD

Original requirement:

```text
GitHub Actions
container builds
Azure deployment
```

Still needs production implementation/verification.

---

## Docker / deployment

Original MVP expects containerized core services and local docker-compose orchestration. fileciteturn5file4L1-L8

Verify current Docker setup.

---

# 24. Testing status

Completed/observed:

```text
Extraction:
    PDF tested
    image tested
    Tika → OCR fallback tested

Anonymization:
    redactor unit tests
    all tests passed

Pipeline:
    ingest → extraction
    extraction → normalization
    normalization → anonymization
    anonymization → scoring
    full chain tested successfully
```

Still required:

```text
loader unit tests
segmenter edge-case tests
entity extraction tests
signals tests
metrics tests
rules tests
scorer tests
assembler tests
consumer tests
integration test:
    file → extraction → normalization → anonymization → scoring

LLM prompt tests
LLM output validation tests
renderer tests
full production-like integration test
```

The original MVP explicitly calls for unit tests for extraction, anonymizer, and rule engine plus a full file→roast→render integration test. fileciteturn5file4L1-L8

---

# 25. Recommended next implementation order

Do NOT jump directly into a frontend.

Recommended sequence:

```text
1. Audit current scoring artifact contract
2. Finish prompt_builder
3. Design LLM output schema
4. Implement LLM inference client
5. Implement roast generation worker/stage
6. Validate LLM output
7. Add numeric composite scoring/rationale
8. Persist roast result
9. Build renderer
10. Build public link service
11. Add TTL cleanup
12. Add Redis rate limiting
13. Harden observability
14. Add full integration tests
15. Dockerize
16. CI/CD
17. Azure deployment
18. Security/privacy review
```

---

# 26. Critical distinction for whoever resumes the project

There are two meanings of “scoring” in the project history.

### Current implementation

```text
signals + metrics
      ↓
rules
      ↓
issues + strengths + severity
```

### Original MVP target

```text
rule results
      +
LLM quality signals
      ↓
Clarity
Credibility
Signal-to-Noise
      ↓
final roast/scored result
```

Do not assume the current scoring worker is the final product scoring engine.

---

# 27. Migration checklist for a new model

When starting a new chat/model, give it this document and ask it to:

1. Read the project documentation.
2. Treat the existing codebase as authoritative over this document.
3. Do not rewrite completed components without inspecting them.
4. First inspect:
   ```text
   backend/src/db/sessions.py
   backend/src/services/blob.py
   backend/src/services/service_bus.py
   backend/src/services/session_service.py
   workers/
   ```
5. Run/inspect the current tests.
6. Verify the current Blob paths and DB enum values.
7. Identify discrepancies between documentation and code.
8. Then continue from the first unfinished item.

---

# 28. Current project status

**Updated 2026-09-05 (later same day)** — Renderer now built; see section 29 for the implementation notes appended below the original design decisions.

```text
INGEST                  ██████████  COMPLETE (incl. anonymous sessions)
EXTRACTION              ██████████  COMPLETE
NORMALIZATION           ██████████  COMPLETE
ANONYMIZATION           ██████████  COMPLETE
DETERMINISTIC SCORING   ██████████  COMPLETE
PROMPT BUILDER          ██████████  COMPLETE
LLM ROAST               ██████████  COMPLETE (Gemini, not the original OpenAI/Anthropic plan — see below)
COMPOSITE SCORE (0-100) ██████████  COMPLETE — Sessions.composite_score column (real migration), see
                                     section 29. NOT the same as the original MVP's Clarity/
                                     Credibility/Signal-to-Noise numeric scores, which are
                                     separately still outstanding.
RENDERER                ██████████  COMPLETE — workers/renderer/, ROASTED → RENDERING → DONE, see
                                     section 29. Verified end-to-end with a real generated PNG card.
PUBLIC LINK             ░░░░░░░░░░  NOT IMPLEMENTED
LEADERBOARD/GLOBAL CMP  ░░░░░░░░░░  NOT IMPLEMENTED — planned feature, composite_score is ready for
                                     it (stored + queryable), see section 29
TTL/CLEANUP             ░░░░░░░░░░  NOT IMPLEMENTED
REDIS/RATE LIMITING     ░░░░░░░░░░  NOT IMPLEMENTED
PRODUCTION HARDENING    ███░░░░░░░  PARTIAL
CI/CD/AZURE DEPLOY      ░░░░░░░░░░  NOT VERIFIED
```

Full pipeline (ingest → extraction → normalization → anonymization → scoring → LLM roast → render) verified working end-to-end against real infra on 2026-09-05, all the way to DONE with a real generated PNG card.

---

# 29. Roast Card & Leaderboard — Design Decisions (2026-09-05)

Design pass for the Renderer feature (public shareable roast card, HTML → PNG). Decided in conversation from a reference React component the user supplied (`ResumeRoastCard`) plus explicit direction on defaults. **Nothing in this section is implemented yet** — it's the agreed design for whoever builds the Renderer next, written down so it survives a new chat or context compaction.

## Design bar

User's own words: "i dont want you to make some basic ahh ugly looking shit. i want something google/spotify level aesthetic... as this will be a public facing card it cannot be plain looking or ugly looking." Treat the roast card as the project's most visible surface (it's the thing people actually share) — not a place to default to plain framework styling. User is sourcing reference components (21st.dev and similar) before implementation starts.

## Planned future feature this must not paint us into a corner on: Leaderboard / global comparison

Not designed yet, but explicitly on the roadmap — ranking public roasts against each other (e.g. percentile stats like "better than 92% of resumes," matching the reference component's `longStat` idea). Implication for scoring/renderer work now: the composite score below needs to end up as a **stored, comparable field** (not just text baked into a rendered PNG), since a future leaderboard needs to query/rank it. Don't design the renderer in a way that only produces a flattened image with no queryable score behind it.

## Decision 1 — the dynamic "stamp" (was hardcoded "ROASTED" in the reference)

Compute deterministically from `scored.json.summary` (`critical_issues`, `high_issues`, `medium_issues`, `low_issues`, `total_strengths` — all already real fields, see section 16):

```text
critical_issues > 0  or  high_issues >= 2   → "ROASTED"
total_issues == 0  and  total_strengths >= 3 → "SOLID" / "APPROVED"
everything else                              → "MID" / "NEEDS WORK"
```

Deterministic, not LLM-driven — free, reliable, no extra roundtrip. Possible future upgrade: let the LLM pick the tag itself (it already writes `verdict` in `roast.json`) for tone-matched copy instead of fixed strings — deferred, not decided.

## Decision 2 — stat display: composite 0-100 score is the DEFAULT

Nothing in the current pipeline produces a 0-100 score or a "buzzwords found" count — the reference component's `94/100` and `17` were placeholders with no real data behind them. Real fields that exist today: `scored.json.summary.{total_issues,critical_issues,high_issues,medium_issues,low_issues,total_strengths}`, plus `metrics.{word_count,experience_block_count,avg_sentence_length,lexical_diversity,email_count,phone_count,url_count}` (section 8/16).

**Decision:** compute a simple deterministic composite score and use it as the **default** stat shown on the card:

```text
score = clamp(100 − 20×critical_issues − 10×high_issues − 5×medium_issues − 2×low_issues, 0, 100)
```

Deterministic (no LLM cost), gives the punchy "X/100" chip, and — per the leaderboard note above — is the natural ranking unit for a future leaderboard (raw issue counts don't normalize across resumes of different lengths; a 0-100 score does).

**Also keep raw counts available** (`total_issues` / `total_strengths` directly) as a second display mode. Once there's a frontend, let the user toggle between "score" and "raw counts" views — but the composite score is what ships first and is the default when only one is shown (e.g. on the rendered PNG card, which can't have an interactive toggle).

This is a *different* number from the original MVP's Clarity/Credibility/Signal-to-Noise composite scoring (section 12/23), which is still a separate, unimplemented, larger piece of work — this is a lightweight display-layer score derived from existing rule-engine output, not a new scoring dimension.

The reference component's sparkline/`longStat` trend graph has **no real data source** in the current pipeline (no per-line or per-bullet time series exists anywhere) — dropped from v1. A future version could repurpose that visual slot for per-section issue counts, but `Issue` doesn't carry a `section` field yet (`workers/scoring/schemas.py`), so that needs its own small pipeline change first — not decided, not scheduled.

## Decision 3 — resume snippet at the top of the card

**v1 ships with the reference component's hardcoded/stylized mock text as-is** (not real anonymized resume content) — simplest, safest, fastest to ship, and the user confirmed this explicitly.

**Planned for later:** add a second mode using the real anonymized resume text (`content.blocks` from `anonymized.json`, redaction placeholders already normalized `{{EMAIL_1}}` → `[EMAIL]` the same way `prompt_builder.py` does it) in the same visual layout/typography — not a redesign, just swapping the text source. Two modes (hardcoded vs. real snippet) become a user-facing choice eventually, same pattern as decision 2's score-vs-counts toggle. Not implemented, not scheduled yet.

## Status

**Update 2026-09-05 (later same day): IMPLEMENTED.** `workers/renderer/` built, mirroring the `workers/llm/` package shape exactly (schemas/errors/state/processor/consumer/main + `pipeline/{loader,card_data,template,screenshot}`). Wired into the pipeline: `workers/llm/processor.py` now calls `enqueue_render(...)` right after uploading `roast.json`, before `mark_roasted`/commit. `ROASTED → RENDERING → DONE` reached in a real end-to-end run against real infra (Postgres/Azurite/Service Bus emulator/Tika/Gemini), producing a real generated PNG card with a real display name, real LLM verdict as punchline, and a real computed score/stamp.

**Implementation notes for anyone touching this worker:**

- **Rendering approach**: Jinja2 (already installed) renders `pipeline/templates/roast_card.html` — a hand-ported, static (non-animated) version of the reference React component, same colors/fonts/layout, `@keyframes` stripped to a fixed resting frame since it's a flattened PNG. Screenshotted via **Playwright's async API** (`playwright.async_api`, not sync) — sync API raises if called from a thread with a running asyncio loop, which `process_render_job` always is. One browser instance is lazily launched and reused across messages (cold start ~1-2s; not worth paying per message), guarded by an `asyncio.Lock()`. On a `PlaywrightError` (e.g. the browser process crashed) it relaunches once and retries before giving up as a `TransientRenderError`.
- **Chrome, not bundled Chromium**: launches via `chromium.launch(channel="chrome")`, reusing the system's already-installed `google-chrome-stable` instead of the ~300MB `playwright install chromium` download. **This is a deliberate local-dev shortcut, not a final decision** — before containerizing/deploying to Azure, switch to a pinned `playwright install chromium` (matching the installed `playwright` pip version). `channel="chrome"` drifts independently via whatever the deploy image's package manager resolves at build time, which isn't reproducible, and a minimal Docker base image won't have Chrome preinstalled anyway. There's a comment to this effect directly in `pipeline/screenshot.py` — don't let it silently ship to production as-is.
- **Font loading**: Google Fonts `@import` (Anton + JetBrains Mono, same as the reference) loads fine in practice — `page.set_content(html, wait_until="load")` followed by `await page.evaluate("document.fonts.ready")` was sufficient in testing (confirmed via an isolated Anton-vs-Arial-Bold rendered comparison — the two are visibly, unmistakably different, so the custom font really is applying). No `networkidle` wait needed.
- **Sizing**: renders at the reference's native 420×525 viewport, exported via `device_scale_factor≈2.571` (1080/420) to hit Instagram's recommended 1080×1350 without hand-recalculating every CSS px value from the reference component.
- **Layout deviation found during visual QA**: dropping the reference's fake sparkline (decision 2) left a large awkward empty gap between the stat chips and the footer when using the reference's original `justify-content: space-between` layout. Fixed by centering the punchline+stat-row block vertically in the bottom zone (`justify-content: center`) and pinning the footer independently via `position: absolute; bottom: 18px` rather than keeping it in the same flex flow — worth remembering if the sparkline slot ever gets a real replacement (decision 2's future per-section-issues idea), since that would change this spacing math again.
- **Enqueue ordering**: `enqueue_render` was added *before* `mark_roasted`/commit in `workers/llm/processor.py`, deliberately mirroring the existing enqueue-before-commit pattern used at every other stage (e.g. scoring enqueues `llm` before `mark_scored`). This is a conscious choice to stay consistent with the rest of the codebase, not an oversight — section 22.A of this doc already flags that ordering as an unresolved, project-wide architectural caveat ("never enqueue downstream before the upstream state transition is durably successful"); this call site inherits that same already-documented risk rather than introducing a new one, and fixing the systemic pattern was explicitly out of scope for this feature.
- **Migration**: `Sessions.composite_score` (`Integer`, nullable) added via a real Alembic migration (`backend/src/alembic/versions/6bca0908464c_add_composite_score_to_sessions.py`, `down_revision='fd4485ea5e78'`) — unlike the `RENDERING` enum value (no migration needed, `status` is a plain `String` column), a new column always needs one. Already applied to the local dev DB.

**Not done / explicitly deferred**: the real-anonymized-snippet toggle (decision 3), the raw-counts toggle (decision 2), and per-section issue tagging for a future sparkline replacement — none of these were in scope for v1.
