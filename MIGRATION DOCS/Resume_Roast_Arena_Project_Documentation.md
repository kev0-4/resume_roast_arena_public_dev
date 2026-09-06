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

**Update 2026-09-05: DONE.** Every worker's `processor.py`, `workers/extraction/extractor/tika.py`, `workers/normalization/pipeline/segmenter.py`, and `workers/config.py` converted from `print()` to `emit_event()`. See section 34 for the full record. `workers/anonymization/pipeline/testAssembler.py`/`testRedactor.py` (manual console test-runner scripts) and `_DEPRECIATED_signals.py` (dead code) deliberately left untouched.

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

```text
short slug
→ roast asset
→ TTL/public resolver
```

**Update 2026-09-05: DONE.** `GET /r/{slug}` implemented — see section 30 for the full implementation record.

**Planned follow-on (not yet designed):** a leaderboard / global comparison feature — ranking public roasts by the composite score (section 29), e.g. percentile stats like "better than 92% of resumes." Noted here 2026-09-05 so scoring/renderer decisions don't paint this into a corner (e.g. the composite score needs to stay a stored, comparable field, not just rendered text on the card).

---

## TTL / cleanup

Original requirements:

```text
raw uploads → delete after 24 hours
anonymous roast metadata → 30 days
logged-in retention → configurable
```

**Update 2026-09-05: DONE** (raw + anonymous; logged-in retention still deliberately unconfigured, see section 32) — `workers/cleanup/`, see section 32.

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

```text
per-IP rate limiting
per-session rate limiting
CAPTCHA for high-frequency anonymous usage
```

**Update 2026-09-05: per-IP/per-session rate limiting DONE** (POST /ingest only) — see section 31. **CAPTCHA still not implemented.**

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

**Update 2026-09-05: test half DONE** — `.github/workflows/ci.yml` runs the full `pytest` suite on every push/PR, see section 33. **Container builds and Azure deployment still not implemented** — those need Azure credentials and a target environment that don't exist yet.

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

**Updated 2026-09-06 (later still)** — Dashboard/history page (section 40) closes out the original frontend page-build-order plan (section 36): landing, upload, processing, result, auth, leaderboard, radar chart, and dashboard are all built. Only Pydantic V2 warnings, the CI/CD deploy half, an error-states/polish pass, and the original MVP's unimplemented Clarity/Credibility/Signal-to-Noise scoring dimension remain open below.

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
PUBLIC LINK             ██████████  COMPLETE — GET /r/{slug}, see section 30. A roast can now
                                     actually be shared end-to-end. Only the original MVP's core
                                     pipeline items remain unimplemented below.
LEADERBOARD/GLOBAL CMP  ██████████  COMPLETE — GET /leaderboard (+/leaderboard/me), see sections 35
                                     and 38. Ranked by composite_score, same eligibility as the
                                     Public Link Service. Frontend page shipped in section 38.
                                     Percentile framing and time-windowed boards deliberately not
                                     built (v1 scope).
TTL/CLEANUP             ██████████  COMPLETE — workers/cleanup/, see section 32. Raw uploads deleted
                                     after 24h, anonymous sessions (row + all blobs) after 30d.
                                     Logged-in retention still deliberately unconfigured (spec says
                                     "configurable," nothing configures it yet).
REDIS/RATE LIMITING     ██████████  COMPLETE — POST /ingest only (5/hour, configurable), see section
                                     31. Redis finally used for something after being provisioned
                                     since the start of this project. CAPTCHA (spec's other
                                     anonymous-abuse mitigation) still not implemented.
PRODUCTION HARDENING    ████░░░░░░  PARTIAL — structured logging (print() -> emit_event) done across
                                     every worker, see section 34. Pydantic V2 warnings still open.
CI/CD (TEST)            ██████████  COMPLETE — .github/workflows/ci.yml runs the full pytest suite
                                     on every push/PR, see section 33. Container builds + Azure
                                     deploy still not implemented (no Azure credentials/target yet).
FRONTEND                ██████████  COMPLETE (page-build-out) — Next.js, see sections 36-40. Every
                                     planned page built and wired to the real backend: landing,
                                     upload, processing, result (incl. radar chart), leaderboard,
                                     dashboard/history. Firebase Google + GitHub auth user-confirmed
                                     working end-to-end, share buttons verified on real Android + iOS
                                     devices. Only an error-states/polish pass remains -- no new pages
                                     planned.
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

---

# 30. Public Link Service — IMPLEMENTED (2026-09-05)

`GET /r/{slug}` — the one deliberately unauthenticated route in the app, registered with no `/api/v1` prefix. Implements `context/mvp_prompt.txt`'s "Public Link Service issues a short public slug and links it to the stored asset (with TTL). Expose static `https://domain/r/<slug>` for sharing."

**Slug lifecycle**: generated in `workers/renderer/processor.py`, the very last step before `mark_done` — same call site that sets `render_blob_path`/`composite_score`. This means **a session can only ever have a slug once it's `DONE`** — the route needs no separate "exists but not ready yet" branch, that state is unreachable by construction. Format: 8 chars from an unambiguous 32-symbol alphabet (`backend/src/utils/slug.py`, no `0/o/1/l/i`), `secrets.choice`-generated, same style as `anon_identity.py`. `Sessions.slug` has a real DB-level unique index (not just app-level discipline) plus a bounded 5-attempt collision-retry loop in the processor.

**TTL enforcement**: read-time only, no deletion job (that's the separately-tracked, still-unbuilt "TTL cleanup" item — the row/blob still physically exist after expiry, the route just stops serving them). Per spec's "roast metadata TTL 30 days for anonymous; configurable for logged-in users": anonymous users (`Users.is_anonymous`) past 30 days from `session.created_at` get `410 Gone`. Logged-in users get **no expiry in v1** — nothing configures "configurable retention" yet, so no number was invented; deliberate scope decision.

**Response shape**: raw PNG bytes (`Response(content=png_bytes, media_type="image/png")`), proxied straight through the API by reading the blob server-side — no SAS token, no public blob container ACL, no CDN. Spec's "→ CDN" is an explicit later-phase concern (`context/scale_prompt.txt`); every other blob read in this codebase already works this way (server-mediated, not direct blob exposure), this just follows the same pattern. No wrapping HTML/Open-Graph page either — `<img src=".../r/<slug>">` or pasting the link directly both just work as-is; an OG-meta wrapper for nicer social-preview embeds is a natural future add, not needed without a frontend to link it from yet.

**Found and fixed along the way**: `conftest.py` only put the project root on `sys.path`, not `backend/` — meaning `pytest` run from the repo root could never actually import anything under `backend.src.*` (it needs `backend/` on `sys.path` too, for `backend/src/__init__.py`'s internal `from src.routes...` imports to resolve — the same fix every manual e2e script this session already had to apply by hand). It also didn't load `workers/.env`, so `DATABASE_URL` etc. were never set when running from the root either. Both fixed directly in `conftest.py`. Consequence: `backend/src/tests/` and any `backend/src/**/test_*.py` were **never actually being collected/run** before this — worth knowing if "the test suite" was assumed to include backend tests in an earlier session; it didn't, silently. Whole-repo `pytest` (not `pytest workers/`) now passes 100/100.

**Verified against real infra end-to-end**: a full session driven through the entire pipeline reached `DONE` with a slug, then `GET /r/{slug}` via the real FastAPI app returned `200`, `image/png`, and bytes identical to what's in blob storage; an unknown slug returned `404`.

**Not done / explicitly deferred**: TTL cleanup (deletion job), rate limiting on this route (mentioned in the original MVP's Redis rate-limiting plan, not built anywhere yet), an HTML/OG-meta wrapper response, vanity slugs (`context/scale_prompt.txt`, paid-tier future feature — the `slug` column can carry them as-is, no schema change needed later).

---

# 31. Rate Limiting — IMPLEMENTED (2026-09-05)

`POST /ingest` now rate-limited via Redis (`backend/src/dependencies/rate_limit.py`), the `redis_cache` container's first actual use in this project — it's been provisioned and configured since the start but nothing ever imported the `redis` package until now.

**Algorithm**: fixed-window counter, `INCR` + `EXPIRE` on a Redis key. Default **5 requests / hour**, env-configurable (`INGEST_RATE_LIMIT_MAX`, `INGEST_RATE_LIMIT_WINDOW_SECONDS` in both `workers/.env` and `backend/src/.env` — see the note about these two separate `.env` files below).

**Key strategy**: `user:{user_id}` for authenticated requests, `ip:{client_ip}` for anonymous ones. This split exists because there's no stable identity to rate-limit an anonymous *session* on across requests — every unauthenticated `/ingest` mints a brand-new generated anon user (`backend/src/utils/anon_identity.py`), so IP is the only thing that stays constant across an anonymous user's repeated requests. Client IP prefers the first hop of `X-Forwarded-For` (for when this eventually sits behind a real reverse proxy/CDN), falling back to `request.client.host` for direct connections — no proxy trust configuration exists yet, so `X-Forwarded-For` is trusted as-is for now; a production deploy behind a real proxy should ensure that header is stripped/overwritten at the edge, not passed through from the client unchecked.

**Failure mode**: fails **open** (allows the request, logs a warning) if Redis is unreachable. Deliberate — this is abuse/cost control on a pipeline that calls a paid LLM API, not a security boundary, and a Redis blip taking down the entire ingest flow would be a worse outcome than briefly allowing unlimited requests.

**Response**: `429 Too Many Requests` with a `Retry-After` header (seconds remaining in the current window, read from the Redis key's TTL).

**Two separate, drifted `.env` files found**: `workers/.env` (used by all the worker scripts and every e2e test this session) and `backend/src/.env` (what `backend/src/config.py` actually loads when run with `backend/src/` as the working directory, e.g. `uvicorn` started from there) are **not the same file** and had already drifted apart before this session — `backend/src/.env` was missing the LLM/render Service Bus queue names and the Gemini config entirely. Not fully reconciled here (out of scope for this feature), but both got the two new rate-limit vars added for consistency. Worth a proper audit/merge before any deploy.

**Verified against the real Redis container**: unit tests exercise the counter directly, including a real (not mocked) window-expiry wait; an end-to-end run against the actual FastAPI app confirmed 5 anonymous `POST /ingest` calls succeed and the 6th/7th both return `429` with a correct `Retry-After` value that counts down within the configured window.

**Not done / explicitly deferred**: CAPTCHA (spec's other anonymous-abuse mitigation), rate limiting on any other route (only `/ingest` is expensive enough to warrant it in v1), a sliding-window or token-bucket algorithm (fixed-window is simpler and sufficient for this threshold).

---

# 32. TTL Cleanup — IMPLEMENTED (2026-09-05)

`workers/cleanup/` — the actual deletion behind the retention policy `GET /r/{slug}` already enforced at *read* time (410 Gone for expired anonymous roasts). Before this, nothing ever deleted anything: raw resumes and full roast data lived in Blob/Postgres forever regardless of age.

**Not a Service-Bus consumer** like every other worker — this is a periodic sweep, not message-driven. `main.py` loops on `CLEANUP_SWEEP_INTERVAL_SECONDS` (default 1 hour), running two independent sweeps each pass (`sweep.py`):

1. `cleanup_raw_uploads`: deletes just the `raw/<id>/` blob for every session older than `RAW_UPLOAD_TTL_HOURS` (default 24), **regardless of status or owner** — matches spec literally ("Uploaded raw files auto-delete after 24 hours"), no carve-out.
2. `cleanup_expired_anonymous_sessions`: deletes the whole `Sessions` row *and every blob prefix* (via the new `delete_all_session_blobs()` in `blob.py`) for sessions owned by an anonymous user (`Users.is_anonymous`) older than `ANONYMOUS_ROAST_TTL_DAYS` (default 30). Logged-in users are never touched by this sweep — spec says "configurable retention" for them, but nothing configures it yet, so no number was invented (same reasoning already used for the Public Link's 410 check, section 30).

**Shared TTL constant fix**: `ANONYMOUS_ROAST_TTL_DAYS` used to be a hardcoded `30` local to `backend/src/routes/public.py`. Moved to `backend/src/config.py` (env-configurable) and imported by both the read-time 410 check and this sweep — otherwise the "says expired" and "actually deletes" logic could silently drift to different numbers.

**Avoiding re-scanning forever**: new `Sessions.raw_deleted_at` column (real migration) — the raw-upload sweep query is `WHERE raw_deleted_at IS NULL AND created_at < cutoff`, so an already-cleaned session is never re-processed on every future pass. The anonymous-session sweep needs no such flag since it deletes the row entirely.

**Deliberately not done**: the anonymous `Users` row itself is never deleted (a leftover anon user with no sessions is harmless orphan data — a users-cleanup sweep is a reasonable future addition, not required now); the spec's separate "deletion endpoints" (a user-facing right-to-erasure API, distinct from automatic TTL) — different, larger feature, not built here.

**Testing note for future work here**: this codebase has no `pytest-asyncio` and no prior async-test pattern. `workers/cleanup/test_sweep.py` uses the same `asyncio.run()`-per-test pattern every manual e2e script this session already used, wrapped with an explicit `await engine.dispose()` between tests — `backend/src/db/session.py`'s `engine` is a module-level singleton whose connection pool binds to whichever event loop first touches it; without disposing it at the end of each test's own loop, the next test's `asyncio.run()` (a *different* loop) reuses orphaned connections and asyncpg raises `MissingGreenlet`/`InterfaceError`. Also: **never touch an ORM object's attributes after a commit on the same session handle without an explicit refresh** — `db.commit()` expires all tracked objects' attributes by default, and touching one afterward (e.g. `session.id`) triggers an implicit lazy-reload that SQLAlchemy's asyncio mode doesn't support outside an explicit `await`, also raising `MissingGreenlet`. Fix used throughout: capture `session_id = session.id` as a plain value immediately after creation, and re-fetch via `get_session(session_id=...)` for anything needed after a later commit, rather than reusing the original ORM object.

**Verified against real infra**: `test_sweep.py`'s 6 tests backdate `created_at` directly (the only practical way to test a 24h/30d TTL without waiting) against real Postgres + real Azurite, confirming exactly the right things get deleted and the right things survive. Separately ran the actual deployable entrypoint (`run_sweep_once()`, not just the sweep functions directly) against a real backdated anonymous session end-to-end — row and blob both confirmed gone afterward.

---

# 33. CI (test half) — IMPLEMENTED (2026-09-05)

`.github/workflows/ci.yml` — runs the full `pytest` suite on every push (all branches) and every PR into `main`. This is the *test* half of the original MVP's "GitHub Actions to build images and deploy" — container builds and Azure deployment are a separate, not-yet-started follow-up (no Azure credentials or target environment exist yet).

**Also added `requirements.txt`** at the repo root (`pip freeze` from the working venv, 134 packages) — `backend/src/requirements.txt` was never a real installable file, just a single comment line listing package names (confirmed repeatedly this session); CI cannot install dependencies without a real one. `backend/src/requirements.txt` now has a note pointing at the real file instead of duplicating it.

**What's actually in CI**: `postgres:16`, `bitnami/redis:latest`, and `mcr.microsoft.com/azure-storage/azurite:latest` as GitHub Actions service containers (same images as `backend/docker-compose.yml`), then `alembic upgrade head`, then `pytest`. **Deliberately not in CI**: Tika, the Service Bus emulator, or a real Gemini API key — confirmed by reading every one of the 111 checked-in tests that none of them call any of the three (only this session's throwaway manual e2e scripts exercised the full pipeline with real Tika/Service-Bus/Gemini calls, and those were never part of `pytest`). Standing up Service Bus's SQL-Edge-backed emulator in CI and paying for real LLM calls on every push are both scope decisions, not oversights. **No GitHub secrets are needed** — every credential the suite touches is a throwaway local-dev-emulator value (Azurite's storage key specifically is Microsoft's published well-known emulator key, identical everywhere, not a secret).

**Real bug this caught** (verification method matters — see below): `backend/src/services/service_bus.py` raises `RuntimeError` at *import* time if `AZURE_SERVICE_BUS_CONNECTION_STRING`/`AZURE_SERVICE_BUS_QUEUE_NAME` are unset. That import happens transitively for *every single test* via `backend/src/__init__.py`'s import chain (`routes.injest` → `service_bus.py`), even though no test calls Service Bus directly. The first test file to trigger it fails with that `RuntimeError` — and every subsequent test file's import of anything under `backend.src.*` then fails with a confusing `KeyError: 'src'` (a partially-registered package left in `sys.modules` after the first import raised partway through). Fixed by setting a syntactically valid but non-functional connection string in the workflow — nothing needs to actually connect.

**Verification method — this is the point of "test fully"**: installed `act` (nektos/act) and Docker were already available, so the workflow was *actually executed* locally against real Docker service containers before ever pushing — not just read as YAML. That's what caught the bug above; a YAML-only review would have missed it (the workflow file itself was syntactically fine — the bug was a runtime env var gap only a real run surfaces). After the fix: `act` reported `111 passed, ... job succeeded`. Separately confirmed on GitHub's own hosted runners too via this feature's own PR (#3) — both "test" checks (triggered once by the branch push, once by the PR) passed, log-verified to show `111 passed` on GitHub's infrastructure, not just locally.

**Trigger note**: `on: push` (any branch) + `on: pull_request` (into `main`) means a PR from a pushed branch runs the suite twice (once per trigger) — a minor inefficiency, not a bug; left as-is rather than adding `concurrency`/path-filter tuning that wasn't asked for.

# 34. Structured Logging — IMPLEMENTED (2026-09-05)

Every worker's `processor.py` (extraction, normalization, anonymization, scoring, llm, renderer) used plain `print()` for its entire debug trace. Converted to `emit_event()` (`backend/src/utils/telemetry.py`) — the structured-logging pattern already established elsewhere in this codebase (state.py files, `service_bus.py`, every `backend/src/routes/*` file) but never applied inside the processor orchestration files themselves. `workers/normalization/processor.py` had even already imported `emit_event` and never called it once.

**Naming convention**: `<worker>.<step>`, dotted, matching what already existed (`session.status.marked_processing`, `servicebus.enqueue.success`) — e.g. `scoring.inputs_extracted`, `llm.response_received`, `render.slug_generated`. Every event carries `session_id` plus whatever contextual data is available at that point (counts, confidence scores, token usage, etc.) and a `status` level (`INFO`/`WARNING`/`ERROR`).

**Judgment calls made, not blind 1:1 conversion**:
- `workers/config.py`'s conversion deliberately does **not** log the raw `VALUES` dict the way the old `print(VALUES)` did — it can contain secrets (`SECRET_KEY`, DB/Redis passwords), and `emit_event` **persists** to `log_entry.json` rather than a transient console print, a materially different risk profile.
- `workers/extraction/consumer.py` (like every `consumer.py` in this repo) already used Python's stdlib `logging.Logger` consistently for its own operational logging — its leftover debug prints were converted to `logger.debug(...)` to match *that file's own* established pattern, not forced into `emit_event`. Every worker's `consumer.py`/`main.py` already does this correctly; only the leftover raw prints inside `extraction/consumer.py`'s `_handle_message` needed fixing.
- One debug print in `workers/normalization/pipeline/entities.py` (dumping `repr(original_value)` per phone-regex match candidate) was **removed**, not converted — it can fire many times per single resume, and a 1:1 `emit_event` conversion would have spammed the structured log with zero lasting informational value per entry.
- `workers/extraction/extractor/tika.py` had two "before text"/"after text" prints bracketing a `.strip()` call with no real informational content — removed rather than manufacturing a meaningless event for each.

**Deliberately not touched**: `workers/anonymization/pipeline/testAssembler.py` and `testRedactor.py` — manual console test-runner scripts (`if __name__ == "__main__":` style, ✓/✗ pass-fail output) meant for a human to read directly, not part of the live pipeline; converting their prints would make them useless for their actual purpose. `workers/normalization/pipeline/_DEPRECIATED_signals.py` — dead code (filename says so). Two prints inside `workers/normalization/consumer.py` — already inside a commented-out, disabled code block, not live.

**Verified against real infra**: ran the full pipeline end-to-end (ingest → extraction → normalization → anonymization → scoring → LLM roast → render, reaching `DONE` with a real slug) and inspected the actual resulting `log_entry.json` directly — 62 structured entries, correctly ordered, `session_id` threaded through every single one, meaningful contextual data at each step (Tika confidence, block/entity/signal/metric counts, LLM token usage, composite score, generated slug). 111/111 tests still passing — this is a pure observability refactor, no behavior changes.

---

# 35. Leaderboard / Global Comparison — IMPLEMENTED (2026-09-06)

The feature flagged back in section 29 as "planned, not designed yet" when `Sessions.composite_score` was first made a stored/queryable column specifically to support it. `GET /leaderboard` — public, unauthenticated (no `/api/v1` prefix, registered the same way as `public_router`), returns roasts ranked by `composite_score` descending.

**Scope decision — same population as the Public Link Service**: eligibility is `slug IS NOT NULL AND composite_score IS NOT NULL`, plus the same anonymous-TTL exclusion `public.py`'s `GET /r/{slug}` already enforces (`ANONYMOUS_ROAST_TTL_DAYS`, shared `config.py` constant). Since a slug is only ever generated once a session reaches `DONE` (the renderer's last step), this is naturally "every roast that's currently a live, shareable public link" — a leaderboard entry and that same roast's `/r/{slug}` card can never disagree about whether it's still visible. Logged-in users are never excluded by age (no retention limit configured yet, matching `public.py`).

**Ranking**: `composite_score DESC`, tiebroken by `created_at ASC` (earlier submission ranks higher on a tie) — deterministic, no random ordering on ties.

**Response shape** (`backend/src/schemas/leaderboard_schemas.py`): `{total, limit, offset, entries: [{rank, slug, display_name, composite_score, created_at}]}`. `limit`/`offset` are query params (`limit` 1-100, default 20; `offset` ≥0, default 0) — `total` lets a caller compute total pages. `display_name` reuses `Users.display_name` exactly as the renderer already does for the roast card itself (`workers/renderer/processor.py`) — for an anonymous session that's the generated fun name (e.g. "OverqualifiedGoblin6248"), for a logged-in user it's their real Firebase display name (already the case on the shareable card today; the leaderboard isn't introducing a new privacy surface, just reusing the existing one). Falls back to `"Anonymous Applicant"` if somehow null.

**No frontend** — same as the rest of this backend (the roast card itself is a server-rendered PNG, not a page this API builds). This is the JSON data endpoint a future frontend would consume; not in scope here.

**Deliberately not built**: the reference component's percentile framing ("better than 92% of resumes," mentioned as a `longStat` idea back in section 29) — not implemented, `total` + `rank` in the response is enough for a caller to compute it client-side if wanted (`1 - rank/total`), didn't seem worth a second endpoint or extra DB round-trip for v1. No time-windowed leaderboards (weekly/monthly) — all-time only.

**Real bug caught during implementation**: `get_leaderboard`'s first draft selected whole `SessionModel` ORM instances via the join query, then a caller touched `.id`/`.composite_score` on them in a list comprehension. Because the objects were already tracked (and expired by an earlier `db.commit()`) in the same `AsyncSession`'s identity map, SQLAlchemy's async ORM raised `MissingGreenlet` on that attribute access — the same class of gotcha already documented in this codebase's tests (`workers/cleanup/test_sweep.py`'s docstring: "never touch ORM object attributes after a commit without an explicit refresh"), but this time triggered by the *service function's own return value* rather than a test bypassing it. Fixed by selecting individual scalar columns (`SessionModel.id`, `.slug`, `.composite_score`, `.created_at`, `Users.display_name`) instead of full ORM rows, and returning plain dicts — sidesteps the whole footgun class rather than requiring every future caller to remember to re-fetch.

**Verified against real infra**: 7 new tests against real Postgres (`backend/src/routes/test_leaderboard.py`) — score ordering, tiebreak-by-`created_at`, slug-required exclusion, anonymous-TTL exclusion, logged-in-never-expires, pagination, and one `TestClient`-driven route test confirming the full FastAPI wiring (query params → service → Pydantic response). Also ran the query directly against this session's real accumulated Postgres data (43 eligible sessions from earlier feature work this session, e.g. real anonymous display names like "OverqualifiedGoblin6248" and "PublicLinkTestUser" from the public-link-service tests) and confirmed correct descending order — not just synthetic fixture data. 118/118 tests passing (111 prior + 7 new).

## Follow-up (2026-09-06): indexed the query

User asked whether an unindexed `ORDER BY composite_score` would force a full-table scan on every request, and whether it should be cached instead. Answer landed on: add the index now (fixes a real, present inefficiency, zero staleness, zero new moving parts), defer caching (Redis is already provisioned and easy to bolt on later, but there's no read traffic yet to justify the staleness/invalidation tradeoffs it introduces) — a plain index turns the top-N query into an O(log n) walk that stays cheap as the table grows, which is the actual problem worth solving pre-emptively; caching only pays off once QPS is high enough that even a cheap indexed query adds up, which isn't the situation here.

**Migration**: `backend/src/alembic/versions/a3f1c9d84e21_add_leaderboard_index_to_sessions.py` — `ix_sessions_leaderboard`, a **partial composite index** on `Sessions(composite_score DESC, created_at ASC) WHERE slug IS NOT NULL AND composite_score IS NOT NULL`, matching `get_leaderboard`'s exact `WHERE`/`ORDER BY` shape. Partial (not a plain full-table index) because most `Sessions` rows never reach `DONE` (in-progress or failed pipelines) — indexing only rows that can ever actually appear on the leaderboard keeps the index smaller and cheaper to maintain on every write. Applied to the local dev DB.

**Verified the index is actually used, not just present**: at the table's real current size (56 rows), `EXPLAIN` on the live query shows Postgres correctly *not* using the index — a `Seq Scan` + `Sort` costs less than the index at that size, which is expected, healthy cost-based-optimizer behavior, not a bug. Confirmed the index is nonetheless valid and selectable (`Bitmap Index Scan` appears when `enable_seqscan` is forced off). To confirm it actually kicks in naturally at realistic scale without forcing anything, populated a throwaway `TEMP TABLE` (auto-dropped, no pollution of real dev data) with 200,000 synthetic rows and the same partial index: `EXPLAIN` there shows Postgres picking the index scan on its own (`cost=0.42..1.70` for `LIMIT 20`, vs. a full sort that would scale with table size). This is the expected lifecycle — cheap now, automatically takes over once the data volume justifies it, no code change needed when that crossover happens.

---

# 36. Frontend — Next.js Build-Out (2026-09-06)

This project had zero frontend code before this session (see section 28's earlier revisions: "Backend-first MVP; no frontend required initially"). This section covers the first real frontend, built page-by-page against the backend that already existed, with two backend additions built specifically to unblock it.

**Stack**: Next.js (App Router) + TypeScript + Tailwind v4 + framer-motion, in `frontend/`. Each page was adapted from a reference component the user sourced (21st.dev-style components), not built from scratch — the brief was explicit: "proper Production grade SaaS," not a generic/plain UI.

## Backend prerequisites (had to happen before any page could call the API for real)

- **CORS middleware** (`backend/src/__init__.py`, `CORS_ALLOWED_ORIGINS` in `config.py`) — didn't exist at all before this; every route only ever worked server-to-server (curl, tests, worker scripts). Defaults to the Next.js dev server origin.
- **`GET /sessions/{id}` extended** with `slug`, `error_code`, `error_message` — needed for the processing page's polling flow to know where to redirect on success and what to show on failure.
- **Real production-hygiene fix found along the way**: added a FastAPI `lifespan` handler disposing the async DB engine on shutdown. Not just cleanup — it fixed a real latent bug where a second `TestClient`-driven test making its own real DB call in the same suite run reliably raised `RuntimeError: attached to a different loop` (a pre-existing landmine in `test_leaderboard.py`'s own route test, just never triggered until a second DB-touching `TestClient` test existed alongside it).
- **`GET /r/{slug}/data`** (new, alongside the existing PNG route) — full analysis JSON: composite score, stamp, severity breakdown, real metrics, verdict/roast/fixes/highlights, live leaderboard rank. Built with real-time performance explicitly in mind (the user's own ask, not assumed): fixed a real blocking-I/O bug on *both* this route and the PNG route (`read_blob` is a synchronous Azure SDK call that was blocking the entire event loop on every request — wrapped in `asyncio.to_thread`), the route's 3 I/O operations (2 blob reads + a rank query) run concurrently via `asyncio.gather`, rank is a single indexed `COUNT` query (`get_session_rank`, reusing the leaderboard's own partial index) rather than a leaderboard scan, and the response carries `Cache-Control: public, max-age=30, stale-while-revalidate=60` (everything except rank is immutable once a session is `DONE`). Verified concurrency actually works, not just claimed: 20 simultaneous requests to this endpoint interleaved with 20 health checks against the real running server completed in 0.68s total, all 200s — if the blocking-I/O bug were still there this would have taken multiple seconds serialized.
- **LLM `highlights` field** (`workers/llm/pipeline/validator.py`, `workers/scoring/pipeline/prompt_builder.py`) — the result page needed to "highlight specific words on the resume," and the pipeline had no field for that at all (the rules engine only ever produced boolean category flags, never the actual offending text). Extended the LLM roast prompt to also return 2-4 quoted excerpts + a comment each, with a **grounding check enforced in code**: every returned quote is checked as a verbatim substring of the actual resume text the LLM was shown, and silently dropped if it isn't a real match. This is the actual safeguard against AI-invented "highlights" — verified with a real (non-mocked) Gemini call, which returned 3 real highlights including one that caught a literal `"untitled"` document-title placeholder left in the test resume.

## Pages built, in order

1. **Landing (`/`)** — hero adapted from a reference component (bold color-blocked hero, huge stacked drop-shadow headline, floating cards, hand-drawn doodles, spinning CTA badge, white feature section). Palette iterated per user feedback from an initial ember/ash attempt (matching the roast card's own colors) to "Blue & Lime" (the user's explicit preference for the reference's own colors) — see section 29's palette and `frontend/DESIGN_NOTES.md` for why two different palettes coexist in this project on purpose.
2. **Upload (`/roast`)** — drag-and-drop, file preview, anonymous-vs-signin toggle (UI only at this point, no auth wired yet), wired to the real `POST /ingest` once CORS existed.
3. **Processing (`/roast/[sessionId]`)** — polls `GET /sessions/{id}` every 2s, shows the session's real current pipeline stage via a stage-driven loading animation (adapted from a user-supplied reference, rebuilt to be driven by real polled status rather than a self-cycling timer — 7 stages mapped from the real backend `JobStatusEnum`). Auto-redirects to the result page on `DONE`.
4. **Result (`/r/[slug]`)** — the page a finished roast actually lands on: the card image, an animated score count-up (adapted from a user-supplied spring-animation reference), severity breakdown chart, real metrics, the full roast text, grounded quote "Receipts," a fixes checklist, and share actions. **First server-rendered page in this build** — every prior page was a pure client component, but this one's entire purpose is being pasted into Slack/Twitter/etc., and link-preview unfurling reads server-rendered `<meta>` tags, not executed client JS. `generateMetadata()` fetches the real analysis server-side and sets real `og:image`/`og:title` pointing at the actual roast card PNG.

## Share buttons — the most iterated single feature in this build

Went through several real rounds based on the user's own live device testing, not simulated checks alone:

- Replaced an initial single generic "Share" button with six named ones: copy link, X, LinkedIn, WhatsApp, Reddit, Instagram (`frontend/src/components/result/social-icons.tsx` has hand-written brand-mark SVGs — lucide-react has no brand/logo icons in the installed version).
- **X, LinkedIn, WhatsApp, Reddit**: real platform share-intent URLs, all confirmed working. LinkedIn showing the card image but never any pre-filled post text is a real platform limitation, not a bug — LinkedIn's `share-offsite` endpoint deliberately stopped accepting pre-fill text years ago (anti-spam); it only takes a `url` param and reads title/description from that page's own OG tags, which is exactly why the image already works there.
- **Instagram**: no web share-intent exists on Instagram's side at all. Three real iterations, each driven by an actual bug found on a real device:
  1. First attempt: `instagram-stories://share` deep link + writing the image to the clipboard, gated to any mobile device. Worked in every simulated (Chromium-based) check.
  2. Failed on a real phone. Root cause: fetching the image *inside* the click handler meant `navigator.clipboard.write` was being called after an awaited network round-trip — Safari on iOS revokes "user activation" after any awaited work, silently rejecting the clipboard write. Fixed by prefetching the image on page mount instead of on click, so the click handler could call the clipboard API with no network wait in between.
  3. Still failed on the user's real Samsung (Android) phone even after that fix. Real root cause: the whole `instagram-stories://` + clipboard mechanism is **iOS-only** — Meta's documented "Stories from your app" trick relies on a private Instagram pasteboard data type only reachable from native Swift code; Android's actual equivalent is a native Android `Intent` (`com.instagram.share.ADD_TO_STORY` with a `content://` URI extra) that a website's JavaScript cannot construct at all. The deep link was being attempted unconditionally on every mobile device, Android included, silently doing nothing and burning the timeout window every time. Fixed by actually splitting the code path by OS: iOS still attempts the deep link, Android goes straight to the Web Share API (`navigator.share` with the image as a file) — Android's real, working mechanism for this. **User confirmed working on both a real Android phone and a real iPhone after this fix.**
- Verification method worth remembering: real Cloudflare quick tunnels (`cloudflared tunnel --url http://localhost:PORT`) were used to get real public HTTPS URLs, since none of this (OG tag crawling by real bots, mobile share intents opening real apps) is testable from `localhost`. This required adding `allowedDevOrigins` to `next.config.ts` (read from a `NEXT_DEV_ALLOWED_ORIGIN` env var) — this Next.js version blocks cross-origin requests to internal dev endpoints (HMR's WebSocket included) by default, which looked like "the buttons do nothing" before the real cause (dev-origin blocking, found by reading Next's own source directly in `node_modules` rather than guessing) was identified. Proved the OG image mechanism itself works by curling a public tunnel URL with a `Twitterbot/1.0` User-Agent and fetching the real image it returned — a real 1080×1350 PNG, the same sequence Twitter's own crawler performs.

## Not yet built (as of section 36; auth landed in section 37)

A dedicated frontend leaderboard page (the backend endpoint has existed since section 35), and a dashboard/history page (would need a new backend list-sessions endpoint, treated as optional/stretch from the start).

# 37. Frontend Auth — Firebase Google + GitHub sign-in (2026-09-06)

The backend side of this (`firebase_admin` init, `verify_id_token()`, `get_current_user`/`get_current_user_optional` dependencies, `POST /api/v1/auth/firebase`) already existed from earlier backend work and needed no changes. This section is the frontend wiring plus one real credentials incident worth recording.

**Decision — Google + GitHub only, no email/password**: explicitly discussed with the user rather than assumed. Email/password would mean owning an OTP/reset-flow and email-delivery pipeline this project has no infrastructure for; anonymous use stays the default path regardless (the whole point of the product is "roast me, no signup required"), so the two OAuth providers cover the "I want my roasts tied to an account" case without that cost.

**Firebase project-ID mismatch caught before any code was built against it**: the user's first-pasted web config had `projectId: "resume-roast-arena67"`, which does not match the backend's actual service account (`project_id: "resume-roast-arena"`, from `backend/src/services/service-account.json`). Flagged immediately, before wiring anything — an ID-token signed by one Firebase project will never verify against a different project's Admin SDK, which would have failed silently/confusingly at sign-in time rather than at setup time. User corrected with the right config on the second attempt; all `NEXT_PUBLIC_FIREBASE_*` values in `frontend/.env.local`/`.env.example` are the corrected ones.

**What's public vs. secret here, and why each was handled differently**:
- `service-account.json` (backend) — real secret, gitignored, never printed.
- Firebase web config (`NEXT_PUBLIC_FIREBASE_*`) — meant to be public by Firebase's own design (it's shipped in every client bundle); still went in `.env.local`/`.env.example` for consistency with the rest of the project's env-var conventions, not because it's sensitive.
- An Instagram App Secret the user pasted earlier (unrelated to auth, from the Instagram share-button work in section 36) was explicitly never used or stored anywhere — verified via a repo-wide grep — since the Stories deep-link feature only ever needed the App *ID*, not the secret. User was told to consider rotating it since it was shared in chat.

**Build**:
- `frontend/src/lib/firebase.ts` — client SDK init, `GoogleAuthProvider`/`GithubAuthProvider`.
- `frontend/src/lib/auth-context.tsx` — `AuthProvider`/`useAuth()`; `onAuthStateChanged` calls the backend's `/auth/firebase` (`syncFirebaseAuth()` in `api.ts`) on every sign-in so `backendUser` (display_name, photo_url, role) is available, not just the raw Firebase user.
- `frontend/src/components/site/auth-menu.tsx` — navbar sign-in dropdown (Google/GitHub) / signed-in avatar+signout menu, rendered from `navbar.tsx` on every page.
- `frontend/src/app/roast/page.tsx` — upload flow now calls `getIdToken()` and attaches it as `Authorization: Bearer` on `POST /ingest` when signed in; when `null` (not signed in), the request goes through exactly as it did before auth existed — the backend already resolves the user from that header itself via `get_current_user_optional`, so this page needed no branching logic beyond "pass the token if there is one."
- `social-icons.tsx` moved from `components/result/` to `components/icons/` (no longer result-page-specific) with `GoogleLogo`/`GitHubLogo` added alongside the existing brand marks.

**Verified with real Playwright runs against the local dev servers** (not just build/lint passing):
- Firebase SDK initializes with zero console errors or warnings against the real `resume-roast-arena` project config — rules out `auth/invalid-api-key` and any other config-mismatch class of failure.
- All three `/roast` auth states screenshotted and confirmed correct: anonymous default ("Continue anonymously" / "Sign in for extra features"), the inline Google/GitHub picker, and (from the navbar) the signed-in avatar menu.
- Clicking "Continue with Google" opens a real popup at `resume-roast-arena.firebaseapp.com/__/auth/handler` with the correct `apiKey`/`providerId` — confirms the client config resolves to the same Firebase project as the backend's service account end-to-end. Completing an actual OAuth round-trip needs a real Google/GitHub account and was left for the user to confirm themselves, the same way real-device confirmation was needed (and given) for the Instagram share flow in section 36.
- Backend suite: 139 passed, no regressions (no backend code changed this phase besides the service-account file already existing in the worktree). Frontend `build` and `lint` both clean.

**User-confirmed working** (2026-09-06): real Google sign-in completed successfully end-to-end — display name, session, and backend sync via `/auth/firebase` all correct. One real quirk reported: the navbar profile photo showed broken after signing in.

**Broken-avatar fix**: traced the actual stored value first rather than guessing — the Users row's `photo_url` in Postgres (a real pre-existing row for this Google account, matched by `firebase_uid`) is a valid, currently-live `lh3.googleusercontent.com` URL (curled directly, got a real 200 `image/jpeg`). Reproduced the exact signed-in state in a clean headless browser using a Firebase custom token minted for the same real uid (sidesteps needing a live OAuth popup) — it rendered correctly there too, ruling out a data or config bug. Root cause is environment-dependent on the user's actual browser (ad-blockers/privacy extensions commonly blocklist Google's avatar CDN since it's Google-associated) — not something fixable from this codebase. What *was* a real gap: `auth-menu.tsx`'s `<Image>` had no `onError` handler, so a blocked/failed request left a permanent broken-image icon instead of the initials-avatar fallback the component already had code for when there's no `photoUrl` at all. Added `onError` → `photoFailed` state → same fallback. Verified both paths with Playwright: unblocked renders the real photo, and with the CDN request forced to abort (simulating an ad-blocker), it now cleanly shows the initials avatar. `build`/`lint` clean, hooks-order lint error caught and fixed along the way (the new `useState` had to move above an early `return` in the component). Committed and pushed separately from the initial auth commit.

**Status**: shipped and user-confirmed, pushed to `worktree-frontend-landing`, not yet merged to `main`.

# 38. Leaderboard Frontend Page (2026-09-06)

`GET /leaderboard` (section 35) had no frontend consumer until this section — the page itself, plus two backend additions it needed.

## Planning note

Composition was agreed with the user before building anything: a hero header with a top-3 podium, a plain ranked list below with "load more" pagination (the user's own earlier preference — "usually in frontend we show top 10-15... then once user clicks view more then we show rest", from the original leaderboard-caching discussion in section 35), and a "your rank" banner for signed-in users. The user explicitly asked to keep the podium treatment and to add the "your rank" banner rather than leave it as a stretch idea ("it is better to build a good app than leave half baked features"). They also asked that leaderboard entries be clickable through to "their submitted resumes/roasts page" — every row and podium card links to `/r/{slug}`, that page's existing result view (score, roast, highlights, share actions). **Noted for a future feature, not built here**: this only surfaces the *roast* (the analysis/output), never the original *uploaded resume document* itself — nothing in this app currently exposes the raw uploaded file back to a viewer at all (extraction/anonymization/scoring all consume it, nothing re-serves it), and doing so would be a genuinely separate, security-sensitive feature (raw files are already deleted after 24h per the TTL policy in section 32, and re-exposing a user's original document needs its own access-control thinking, not something to bolt onto a leaderboard row's link).

## Backend additions

- **`Sessions.stamp` column** (migration `e2b7a4c910f3`) — the roast card's tier badge (ROASTED/MID/SOLID) is derived from a session's severity *summary* (critical/high issue counts, strength count — see `workers/renderer/pipeline/card_data.py:compute_stamp`), not from `composite_score`. A paginated leaderboard listing many rows can't afford a blob read per row just to show a badge, so `stamp` is now stored once at the same DONE transition that already sets `composite_score` (`workers/renderer/state.py:mark_done`, `workers/renderer/processor.py`) — same reasoning as why `composite_score` itself is a stored column. Nullable: existing DONE sessions predate this and aren't backfilled; the frontend simply omits the badge when null (`StampBadge` returns nothing for a null stamp).
- **`GET /leaderboard/me`** (auth required, `backend/src/routes/leaderboard.py` + `session_service.get_user_leaderboard_position`) — a signed-in user's own rank. Finds their most recent eligible session (mirrors the "you always land on your newest result" convention already used by the processing-page redirect, not their best-ever score) and ranks it via the existing `get_session_rank`. Returns `200` + `null` (not `404`) when the user has no eligible roast yet — an expected state for a brand-new signer-in, not an error condition.

## Frontend

- `app/leaderboard/page.tsx` — client component (consistent with every page except `/r/[slug]`, which is server-rendered specifically for OG tags this page doesn't need). Fetches page 1 on mount, "Load more" appends subsequent pages via the existing `limit`/`offset` params — no new pagination mechanism invented.
- `components/leaderboard/podium.tsx` — top 3 as a 2-1-3 visual layout (CSS order, not array order, so #1 renders center/tallest regardless of source order), a `Crown` icon (lucide-react) on #1.
- `components/leaderboard/leaderboard-row.tsx` — ranks 4+, plain list rows on the white content panel (same panel pattern as the result page).
- `components/leaderboard/stamp-badge.tsx` — shared badge, `dark`/`light` variant (lime-on-transparent for the podium's dark cards, blue-on-white for list rows on the white panel) — no per-tier color scheme invented; matches every other stamp badge in this codebase (uniform lime outline regardless of tier).
- `components/leaderboard/your-rank-banner.tsx` — fetches `/leaderboard/me` client-side once signed in via `useAuth()`; renders nothing at all while signed out (no sign-in nag competing with the page header) or while the signed-in user has no eligible roast yet.
- `lib/relative-time.ts` — small hand-rolled "2d ago" formatter; no new date library pulled in for something this simple.
- Navbar's "Leaderboard" link (previously a `href="#"` placeholder shared by all three nav items) now points at the real page; the other two links are untouched.

## Verified

- 4 new backend tests (stamp round-trips through `get_leaderboard`; `/leaderboard/me` requires auth; returns null for no eligible session; returns the correct rank/stamp/score for one that does). Caught and fixed a real `DetachedInstanceError` writing these — passing a detached ORM `Users` instance across a `dependency_overrides` boundary in a test hits the exact identity-map class of bug documented elsewhere in this codebase's tests; fixed by overriding with a plain object carrying just `.id`, not the ORM instance. 143/143 backend tests pass.
- Frontend `build`/`lint` clean; one `react-hooks/set-state-in-effect` violation caught and fixed in `your-rank-banner.tsx` (a synchronous `setState` in the effect body's early-return branch was redundant anyway, since the render guard already checks `!firebaseUser` first — removed rather than restructured).
- Verified against the real running dev stack with Playwright, not just build passing: zero console errors on `/leaderboard`, `Load more` actually grows the visible list, navbar link lands on the real page. The your-rank banner was verified in *both* states using the same real account and the same Firebase-custom-token technique used to verify the broken-avatar fix earlier this session (mints a real token for a known real `uid` via the Admin SDK, sidesteps needing a live OAuth popup): confirmed absent for the account's real current state (no eligible session), then a throwaway eligible session was inserted directly in Postgres, the banner rendered with the correct real rank/total/stamp/score, and the throwaway row was deleted immediately after.

**Status**: shipped, pushed to `worktree-frontend-landing`, not yet merged to `main`.

## Follow-up (2026-09-06): polish pass per direct user feedback

The first pass above landed but the user's reaction was "looks bland" — three concrete fixes followed from a reference component they supplied:

1. **Visual redesign** — tier-colored stamp badges (SOLID stays `brand-lime`; two new tokens added, `tier-mid` `#EF9F27` and `tier-roasted` `#E24B4A`, recorded in `DESIGN_NOTES.md` per this project's palette-tracking convention — scoped to the leaderboard's `StampBadge` only, every other stamp badge in the codebase still uses the old uniform-lime outline, not touched here). Podium rebuilt as chunky black-bordered per-rank blocks (#1 tallest, lime-filled) with a `Trophy` icon on #1 and avatar circles (deterministic initial+hue — leaderboard entries have no real profile photo). Ranked list rebuilt as one hard-shadow bordered card (`leaderboard-list.tsx`) with hairline row dividers rather than a shadow-per-row (deliberate: at 50+ rows a shadow per row reads as noise, not a leaderboard — the chunky brand language stays on the accents instead), plus a `ChevronRight` hover affordance per row.
2. **Pagination cap** — "Load more" now hard-stops at 100 total entries (`MAX_ENTRIES` in `leaderboard/page.tsx`) no matter how large the real total is, with a "Showing the top 100 roasts" note once capped — an unbounded load-more was an unintentional-infinite-scroll trap the user flagged directly. Verified against the real dev DB's 400+ accumulated rows: clicking through stops at exactly 100 rendered entries.
3. **"Your rank" now reflects your best submission, not your latest** — `get_user_leaderboard_position` (`backend/src/services/session_service.py`) changed from ordering by `created_at DESC` to `composite_score DESC, created_at ASC` (the same tiebreak `get_leaderboard` itself uses, so "my rank" never disagrees with which entry the leaderboard would actually show for a tie). The prior test for this happened to have the same session be both latest *and* best, so it never actually exercised the distinction its name claimed — rewritten so best and latest are different sessions, plus a new dedicated tiebreak test.

Verified: 12/12 leaderboard tests, 144/144 full backend suite (real Postgres). Frontend build/lint clean. Redesign visually confirmed via Playwright against the live dev stack using throwaway SOLID/MID/ROASTED sessions inserted directly in Postgres (the real accumulated dev data all predates the `stamp` column and is uniformly null, so it couldn't show the tier-color differentiation on its own), screenshotted, then deleted.

**Noted, not built (at the time)**: a radar/spider chart for per-category subscores on the result page — deprioritized until the leaderboard was fixed. Built in the next follow-up below, once the layout complaint was addressed.

## Follow-up 2 (2026-09-06): layout rewrite + your-rank always visible

The redesign above still didn't land — user's next reaction: "the blue and white segregation is not working here... too much empty space... the blue hero block is sized way bigger than its content." Root cause was structural, not cosmetic: the page was `flex-1` main content plus a separate `mt-auto` white section stacked below it, so the blue area stretched to fill whatever vertical space the (short) podium didn't use, then abruptly switched to white for the list. Rebuilt per another reference component the user supplied:

- Single `bg-brand-blue` for the entire page, no separate section/color transition.
- `hero-panel.tsx` — title + tagline + podium now live inside one bordered, hard-shadowed card sized to its own content (`podium.tsx` simplified back down to just the podium blocks, hero-panel.tsx owns the surrounding card).
- `search-box.tsx` — client-side filter over the already-loaded ranked-list entries (not a new backend search endpoint). Filters ranks 4+ only, with a real empty state.
- Deliberately **not** added despite being in the reference: period tabs (Weekly/Monthly/All-time — real time-windowed backend filtering, already flagged out of v1 scope above) and rank-delta arrows (needs historical rank tracking that doesn't exist anywhere in the schema). Flagged as separate future asks, not part of a layout fix.

Separately, the same feedback round caught a real UX regression: the "your rank" banner (added in the first pass) returned `null` entirely whenever a signed-in user had no eligible leaderboard position — user: *"where did you remove your rank tab bro? even if no resume is submited show a '--' or Null rank or something."* A card that's just gone reads as broken, not intentional. Fixed: the card now always renders once signed in — a real position shows the actual rank/stamp/score, no position shows a "--" placeholder that doubles as a CTA linking to `/roast`. Still fully hidden while signed out (no identity to show a rank for).

Verified with Playwright against the live dev stack: zero console errors, search filters and empty-states correctly, full-page screenshot confirms no dead blue space. Your-rank's both states (placeholder / real) re-verified with the same real-account + Firebase-custom-token + throwaway-session technique used earlier in this session. Build/lint clean.

# 39. Radar Chart — Per-Category Subscores on the Result Page (2026-09-06)

The deferred item from section 38's first follow-up, picked back up once the leaderboard layout was fixed, per the user's own sequencing ("once this is done add the radar chart").

**Real investigation before building anything**: checked whether per-axis subscores (clarity/impact/formatting/etc.) already existed anywhere in the scoring pipeline — they didn't, `RoastAnalysisResponse` only ever exposed the aggregate `composite_score` and severity summary counts. But `workers/scoring/pipeline/rules.py`'s full rule output (`issues`/`strengths`, each with a `code`) was already being read into `scored.json` and already loaded server-side by `GET /r/{slug}/data` for the `summary` field — just never exposed at that granularity. That's real, existing, groundable data; building the radar chart meant deriving from it, not inventing new scoring logic or a second LLM call.

**`_compute_subscores` (`backend/src/routes/public.py`)**: every issue code in `rules.py` partitioned into exactly one of 6 axes — Structure, Contact, Experience, Clarity, Conciseness (all deduction-based: start at 100, lose severity-weighted points per issue in that category, floor at 0), and Skills (a special case — `rules.py` has no "missing skills" issue to deduct from, only the `HAS_SKILLS` strength, so it's scored 100 if present else a flat 55, deliberately not 0 since that would claim a penalty the rule engine doesn't actually detect). Wired into the existing `/r/{slug}/data` response as a new `subscores` field — no new blob reads, the issues/strengths list was already being loaded.

**`radar-chart.tsx`**: plain SVG (no charting library — one hand-sized chart doesn't justify the dependency), reskinned from a reference component (which itself was rebuilt off visx internally) to this project's real theme tokens and real data shape. One real bug caught during verification: the "Contact & Links" label clipped past the SVG's edge — fixed by shortening to "Contact" (a backend-side rename, since it's the label text itself) and widening the chart's margin generally for headroom.

**Verified**: 4 new/updated backend tests (category-compounding, floor-at-zero clamping, both Skills branches) plus the existing route test extended with real subscore assertions — 148/148 full suite against real Postgres. Frontend build/lint clean. Playwright screenshot of a real `/r/{slug}` page (backed by real blob data, not the lightweight DB-only fixtures used elsewhere this session) confirms all 6 axis labels render without clipping and the polygon reflects the real per-category numbers from a real backend response.

**Status (section 39)**: shipped, pushed to `worktree-frontend-landing`, not yet merged to `main`.

# 40. Dashboard — User Roast History Page (2026-09-06)

The stretch/optional item from the original frontend page-build-order plan (section 36), picked as "next feature" once the leaderboard and radar chart were both done — needed the one piece of backend it was always flagged as blocked on: a list-sessions endpoint.

**`GET /api/v1/sessions/me`** (`backend/src/routes/injest.py`, auth required, paginated) — a signed-in user's own sessions, most recent first, *regardless of status*. Deliberately not scoped to the leaderboard-eligible subset `get_leaderboard`/`get_user_leaderboard_position` use: a history page is exactly where a user should be able to see an in-progress or `FAILED` session too, not just the ones that made it all the way to a public roast card. Registered **above** `GET /sessions/{session_id}` in the same file on purpose — Starlette matches routes in registration order, and `{session_id}` is typed loosely enough (`uuid.UUID | str`) that `"me"` would otherwise match it as a literal session id and never reach this route at all.

**`/dashboard`** — single `bg-brand-blue` background top to bottom from the very first draft, applying the leaderboard's own layout lesson (section 38's second follow-up) proactively rather than repeating the empty-hero-block mistake. Each row buckets the 15 possible `SessionStatus` values down to 3 (done/failed/processing): done rows show score+stamp and link to `/r/{slug}`, processing rows link back to `/roast/{session_id}` so a user can jump back to an in-progress upload, failed rows show the real stored error message inline. Real signed-out and empty states (not just a blank list), each with a CTA to `/roast`. Linked from the navbar's signed-in dropdown as "My Roasts" — not the public top nav, since the page is meaningless when signed out.

**Real bug caught writing the backend tests**: accessing a just-created session's `.id` *after* a later commit on the same db session (e.g. creating the next fixture session in the same test) raised `MissingGreenlet`. Async SQLAlchemy expires every instance in a session's identity map on any commit, not just the object being committed, and unlike sync SQLAlchemy there's no implicit lazy-load bridge for accessing an expired attribute outside an awaited call — it raises instead of silently blocking. Same underlying class of bug as the `DetachedInstanceError` gotcha documented in section 38 (leaderboard tests), caught one step earlier in the object lifecycle here. Fixed by capturing each id immediately after its own commit rather than batching captures at the end of a multi-session test setup.

**Verified**: 4 new backend tests (auth required; status bucketing + most-recent-first ordering across done/failed/in-progress; a user never sees another user's sessions; pagination) — 152/152 full suite against real Postgres. Frontend build/lint clean (two `set-state-in-effect`/unescaped-entity lint errors caught and fixed along the way). Playwright-verified against the live dev stack: a real account's actual `UPLOADED`-status history (from months-old real test data still sitting in the dev DB) renders correctly bucketed as "Processing," and two throwaway `DONE`/`FAILED` sessions were inserted directly in Postgres to exercise the other two row treatments, screenshotted, then deleted — confirmed the `DONE` row's link resolves to the correct real `/r/{slug}` and the navbar's "My Roasts" link lands on the page end-to-end.

**Status (first pass)**: shipped, pushed to `worktree-frontend-landing`.

## Follow-up (2026-09-06): rebuilt as a real dashboard, not just a history list

The first pass above was, in the user's words, just a list — "where is profile where is overall metrics, where is rank." They asked for a component plan before building, then supplied a reference layout: profile header; a shared blue card with the latest roast summary and its subscore radar side by side; a Rank/Best/Average KPI row; a full-width score trend chart; the roast history list below all of it.

Rebuilt against real data throughout, reusing existing infrastructure rather than duplicating it:
- **`get_user_stats`** (`session_service.py`) — one SQL aggregate (COUNT/MAX/AVG over `composite_score` where not null), wired into `GET /api/v1/sessions/me` as a new `stats` field. Scoped to sessions with a real score, same "roasts means DONE" convention used everywhere else in this app.
- **`RadarChart` gets a `variant` prop** (`"light"`/`"dark"`) instead of a second component — the dashboard's blue hero card needed white labels/grid/points where the result page's white panel needed black ones. Same component, same real subscore data source (`GET /r/{slug}/data`, unchanged), just themed per background.
- **Rank KPI reuses `GET /leaderboard/me`** (built for the leaderboard page's own banner) rather than a new endpoint — the "your rank" concept is identical here.
- **Score trend** (`score-trend.tsx`) — plain SVG line chart, same no-library reasoning as the radar chart, built from the same session list already being fetched for the history section (no new request).

**A real coincidental gotcha surfaced during verification, not a bug**: `GET /r/{slug}/data` recomputes `stamp` fresh from the session's severity summary on every request (documented, deliberate — matches the renderer's original computation), while `GET /sessions/me`'s history rows read the *stored* `Sessions.stamp` column directly. Both are correct independently; they only visibly disagree if a session's stored stamp doesn't actually match its own summary — which only happened in this session's own throwaway test fixtures (three synthetic rows sharing one fixture's summary but given different hand-picked stamp values for testing convenience), never in real pipeline-produced data where both are derived from the same summary at the same time.

**Verified**: 2 new backend tests (stats reflect only scored sessions; null-safe with none at all) — 154/154 full suite. Frontend build/lint clean. Playwright-verified with 3 throwaway DONE sessions carrying *real* uploaded `scored.json`/`roast.json` blobs (not just DB rows — needed for the latest-roast card's verdict+radar to render at all) at ascending scores: the KPI row's average (65) exactly matches `(45+68+82)/3`, the trend chart's three points ascend in the correct chronological order, and the result page's own radar chart (light variant) is unchanged pixel-for-pixel — confirming the shared component's new variant prop didn't regress its original use.

**Status**: shipped, pushed to `worktree-frontend-landing`, not yet merged to `main`. This closes out the original frontend page-build-order plan from section 36 — landing, upload, processing, result, auth, leaderboard, radar chart, and now a real dashboard are all built. Remaining frontend work is polish (error states pass) rather than new pages.

# 41. Two Real Pipeline Bugs Found Answering "Can I Actually Upload My Resume?" (2026-09-06)

The user asked directly: "is the whole frontend ready now? can i upload my resume and use all features of the website?" Every page had been built and individually verified this session, but nothing had actually tested a real file uploaded through the real live site completing the real pipeline via **live Service Bus queue consumption** — every prior "full pipeline verified end-to-end" claim in this project's history (section 28, and the original `[[pipeline-e2e-verification]]` memory) was true for the pipeline's *logic*, exercised by calling `process_*_job` functions directly in a script, never for the actual queue wiring connecting the six worker stages. Answering the user's question honestly meant actually trying it — and it didn't work, twice, for two separate real reasons.

## Discovery: the workers weren't even running

`docker-compose` (in `backend/`) only starts the infra containers — Postgres, Redis, Azurite, Tika, the Service Bus emulator, SQL Edge — confirmed all had been running 21-25+ hours straight, with **zero of the 6 Python worker processes alive**. Nothing about that is visible from the site itself (every page loads fine; the gap only shows up on an actual upload). Started all 6 (`python -m workers.<name>.main` from the repo root) — this alone surfaced bug 1.

## Bug 1 — two workers crashed on startup: missing `backend/` on `sys.path`

`workers/llm/main.py` and `workers/renderer/main.py` only added the repo root to `sys.path`, not `backend/` — unlike `extraction`/`normalization`/`anonymization`'s `main.py`, which add both. `backend/src/__init__.py` does `from src.config import ...` (absolute), so without `backend/` on the path both crashed at import, before their consumer loop ever started. Fixed by matching the already-working pattern.

## Bug 2 — the real one: enqueue-before-commit race, scoring→llm and llm→render

With all 6 workers actually running, a real upload through the live `/roast` page (Playwright driving a real file input, not a script) got stuck at `SCORED` forever. Root cause, found by (1) peeking the actual Service Bus queue to confirm 0 messages were sitting there — ruling out "just slow" — then (2) comparing exact log timestamps between the scoring and LLM workers' own processes, which showed the LLM worker's "Received" event happening *before* the scoring worker's own "Enqueued" event for the same run — only possible if the LLM worker had received something unrelated, meaning the real message had already vanished:

`workers/scoring/processor.py` and `workers/llm/processor.py` both called the next stage's `enqueue_*()` **before** committing the current stage's status change. Each downstream worker is a separate process with its own DB connection, guarding on the session's current status the instant it receives a message. Enqueueing before the commit landed let a fast consumer (routine against a local emulator) read the still-stale status, silently guard-return, and the message still gets marked complete regardless — the consumer's success log doesn't distinguish a guarded no-op from real work, so the drop is invisible anywhere in the logs. `normalization`/`anonymization`'s processors already had this right (commit before enqueue); scoring and llm didn't. Fixed by reordering both to match.

## Verified — 4 consecutive real uploads through the live site

2 uploads reproduced bug 2 exactly pre-fix (stuck at `SCORED`, confirmed via direct Postgres + queue-peek inspection). Post-fix: 1 upload reached the LLM stage for real (proving the fix) but failed on a separate, unrelated, real LLM-output-parsing brittleness (Gemini occasionally omits a required section from its free-text response — not chased further, since the app already handles it gracefully: a real "That didn't work" screen with the actual error and a working "Try Again" button, not a hang). 1 upload completed fully live, zero manual intervention: real Gemini roast quoting the actual uploaded resume's content, real radar chart, real leaderboard rank, real rendered card, zero console errors. Backend suite still 154/154 after the reordering.

**Status**: both fixes shipped, pushed to `worktree-frontend-landing`, not yet merged to `main`. All 6 worker processes left running for the user's own real test. The 6 processes to start (from the repo root, one each): `python -m workers.extraction.main`, `workers.normalization.main`, `workers.anonymization.main`, `workers.scoring.main`, `workers.llm.main`, `workers.renderer.main` — none of these are started by `docker-compose`, which only brings up the infra containers.

# 42. Navbar Fix — Split the Roast Pill, New "How It Works" Page (2026-09-06)

Direct feedback after confirming the site works end-to-end: "the buttons on landing page at the top, except leaderboard none of them work... Resume (idk use of this), Roast (these 2 are valid... wait), Leaderboard (valid), How it works (does nothing), Examples (again does nothing)."

**"RESUME"/"ROAST" logo split**: both pills were visually distinct but shared one `Link` to `/` — read as two buttons, only one of which (implicitly) did anything. Split per the user's own confirmed choice: `RESUME` stays the brand mark linking home, `ROAST` becomes its own real link straight to `/roast` (the upload page) — a persistent "get started" CTA in the nav. Zero visual regression (confirmed via Playwright screenshot, pixel-identical — only the underlying `href`s changed).

**New `/how-it-works` page**, replacing the dead `href="#"`: four real steps (upload → processing → score → leaderboard rank), each illustrated with a **real screenshot of that actual live page** — captured via Playwright against the running dev stack, not mockups. Folds in what a separate "Examples" nav item would have shown (real roasted resumes) into the fourth step's leaderboard podium screenshot plus a closing "Browse real roasts on the leaderboard" link, rather than keeping two nav items that would have overlapped — "Examples" removed from `NAV_LINKS` entirely rather than inventing a separate destination for it, per the user's own "remove or come with a better page idea" answer. Single `bg-brand-blue` background top to bottom from the first draft this time (the leaderboard/dashboard's own layout lesson from earlier sections, applied proactively instead of needing a follow-up correction), same chunky-border/hard-shadow card language as the leaderboard and dashboard.

**Screenshot sourcing**: three throwaway sessions created directly in Postgres for clean, presentable capture subjects — a mid-pipeline `SCORING`-status session for the processing-page shot, a `DONE` session with real uploaded `scored.json`/`roast.json` for the score banner (had to redo the fixture once to guarantee a genuine `SOLID`-computed stamp — same `_compute_stamp`-from-summary behavior documented in section 39/40, not from a hand-set DB column), and three clean top-ranked entries for a presentable leaderboard podium (the real dev leaderboard is dominated by hundreds of accumulated `LeaderboardTestroute` test-fixture rows from this project's own test suite). All deleted immediately after capture, same cleanup discipline as every other throwaway-data use this session. Final image assets: ~110KB total across 4 PNGs.

**Verified**: build/lint clean, Playwright screenshot of the live page confirms all four steps render with zero console errors, and all four nav links resolve correctly (`RESUME`→`/`, `ROAST`→`/roast`, `Leaderboard`→`/leaderboard`, `How it works`→`/how-it-works`).

**Status**: shipped, pushed to `worktree-frontend-landing`, not yet merged to `main`.
