# Resume Roast Arena — Original Plan & Migration Context

## Source of truth

This document reconstructs the **original MVP brief** plus the implementation decisions made during development.

The original uploaded MVP prompt is the canonical product/system specification. It defines Resume Roast Arena as an anonymized, shareable resume feedback platform and explicitly says the initial implementation is backend-only. fileciteturn5file0L1-L8

---

# 1. Original product definition

**Product:** Resume Roast Arena — Minimum Viable Product

**One-liner:**

> Instant, anonymized resume “roasts”: automated, shareable scorecard and targeted fix suggestions.

**Target audience:**

> College students and early-career hires seeking fast feedback and viral shareability.

**Primary value:**

> Low-friction upload → automated harsh-but-actionable feedback → shareable roast card.

---

# 2. Original MVP goals

The original plan required:

- Accept PDF/DOCX/JPG/PNG.
- Reliable text extraction.
- DOCX/PDF parsing.
- OCR fallback.
- Rule-based flagging.
- LLM-derived roast generation.
- PII redaction before external calls.
- Persisted roast result.
- Shareable public link/asset.
- Ephemeral storage and TTL.
- Basic observability.
- Error handling.
- No frontend UI required initially.
- Status endpoints.
- Static roast-card assets.

These requirements are stated in the original MVP document. fileciteturn5file0L1-L8

---

# 3. Original component plan

The original system listed:

1. Ingest service
2. Extraction pipeline
3. Normalizer & Feature Extractor
4. Anonymizer
5. Rule-Based Evaluator
6. LLM Roast Generator
7. Scoring service
8. Renderer
9. Public Link Service
10. Queueing & Workers
11. Metadata DB
12. Cache
13. Observability
14. CI/CD

The original brief specifies these components explicitly. fileciteturn4file0L1-L8

---

# 4. Original technology plan

## Backend

```text
Python
FastAPI
```

## Queueing

Original alternatives:

```text
Celery + Redis
OR
Azure Functions + Service Bus
```

The implementation chose the **Azure Service Bus worker approach**.

## Storage

```text
Azure Blob Storage
```

## Database

```text
Azure Database for PostgreSQL
```

JSONB was intended for flags/metadata.

## Extraction

```text
Apache Tika
Tesseract
```

or Azure Cognitive Services OCR as an alternative.

The implementation chose:

```text
Apache Tika
+
Tesseract fallback
```

## LLM

Original:

```text
Azure OpenAI
or OpenAI API
```

The LLM must only receive sanitized/anonymized content.

## Cache

```text
Azure Cache for Redis
```

## Authentication

```text
Google Sign-In
Firebase Authentication
```

Anonymous uploads were allowed initially.

## Observability

```text
Azure Monitor
Application Insights
structured JSON logging
```

## Containers

```text
Docker
docker-compose
```

## CI/CD

```text
GitHub Actions
Azure deployment
```

These technology requirements are stated in the original brief. fileciteturn5file3L1-L8

---

# 5. Original system data flow

The original textual architecture was:

```text
Client
  ↓
API Gateway / Ingest
  ↓
Azure Blob Storage
  ↓
Queue
  ↓
Extraction Worker
  ↓
Normalizer
  ↓
Anonymizer
  ↓
Rule Evaluator + LLM Roast Generator
  ↓
Scoring
  ↓
Renderer
  ↓
Blob Storage
  ↓
Public Link Service
  ↓
CDN
```

The detailed original sequence describes each stage in this order. fileciteturn4file3L1-L8

---

# 6. Original extraction plan

The intended behavior:

```text
uploaded document
      ↓
Tika
      ↓
confidence check
      ↓
if insufficient/low confidence:
    OCR
      ↓
normalized representation
```

The implementation used:

```text
Tika
+
Tesseract
```

with a confidence threshold.

This portion is now working and tested.

---

# 7. Original normalization plan

The original normalizer was intended to extract:

```text
tokens
verbs
numeric information
metrics
skills
dates
bullet information
```

with:

```text
spaCy
or lightweight transformer
```

The actual implementation evolved into a deterministic normalization layer with:

```text
section segmentation
entity extraction
signals
metrics
```

This became the backbone for later stages.

---

# 8. Original anonymization plan

The original requirement was:

```text
deterministic PII redaction
```

including:

```text
email
phone
name
address
```

and the anonymizer had to run **before any LLM/API call**.

Current implementation covers:

```text
email
phone
URL
```

with names/organizations/locations deferred.

The original brief explicitly makes PII redaction a security requirement before external calls. fileciteturn5file4L1-L8

---

# 9. Original rule evaluator

Original concept:

```text
features
  ↓
JSON ruleset
  ↓
flags
severity
suggestions
```

The current implementation uses Python rule functions rather than an external JSON ruleset.

Current rule output is structured:

```json
{
  "code": "NO_SUMMARY",
  "message": "Missing summary section",
  "severity": "low"
}
```

Severity levels:

```text
critical
high
medium
low
```

This severity decision was intentionally made early so the eventual frontend/LLM can distinguish major issues from minor ones.

---

# 10. Original LLM plan

The original system expected:

```text
sanitized resume
+
top rule flags
+
constrained prompt
      ↓
Azure OpenAI / OpenAI
      ↓
concise roast
```

Required safeguards:

- sanitized prompt
- token limits
- rate limits
- hallucination monitoring
- safety controls
- prompt templates stored in repository
- unit tests for prompts

The original brief specifies a constrained LLM roast generator and prompt-template approach. fileciteturn4file0L1-L8

---

# 11. Original scoring plan

This is a key point.

The original MVP's scoring service was intended to produce:

```text
Clarity
Credibility
Signal-to-Noise
```

as composite numeric scores and store scoring rationale.

The current implementation has a **deterministic scoring/rule stage**, but the final numeric scoring system is not yet implemented.

Do not confuse:

```text
rule evaluation
```

with the final:

```text
composite scoring service
```

---

# 12. Original renderer plan

The renderer was intended to:

```text
roast/scored result
      ↓
HTML template
      ↓
PNG / OG image
      ↓
Azure Blob Storage
```

The output becomes the shareable “Roast Card”.

Not implemented yet.

---

# 13. Original public sharing plan

The public-link service was intended to:

```text
generated asset
      ↓
short public slug
      ↓
TTL/public resolver
      ↓
shareable URL
```

Example conceptual endpoint:

```text
/r/<slug>
```

Not implemented yet.

---

# 14. Original storage/privacy requirements

The original MVP requires:

### Raw upload TTL

```text
24 hours
```

### Anonymous roast metadata

```text
30 days
```

### Logged-in users

```text
configurable retention
```

### Security

```text
TLS 1.2+
Blob server-side encryption
managed DB access
```

### Privacy

```text
GDPR-friendly design
deletion endpoints
ephemeral storage
```

These requirements are explicitly stated in the original MVP. fileciteturn5file4L1-L8

---

# 15. Original rate limiting plan

Use Redis for:

```text
per-IP rate limiting
per-session rate limiting
transient session state
```

Anonymous high-frequency users:

```text
CAPTCHA
```

Not implemented yet.

---

# 16. Original observability plan

Every stage should emit structured events.

Conceptual events:

```text
ingest.started
ingest.validation.success
ingest.blob.uploaded
ingest.extraction.enqueued

extraction.started
extraction.completed
extraction.failed

normalization.started
normalization.completed
normalization.failed

anonymization.started
anonymization.completed
anonymization.failed

scoring.started
scoring.completed
scoring.failed

llm.started
llm.completed
llm.failed

render.started
render.completed
render.failed
```

The implementation already has telemetry/event infrastructure, but replacing remaining `print()` calls and standardizing event schemas is still required.

---

# 17. Original testing plan

Required:

```text
unit tests:
    extraction
    anonymizer
    rule engine
    prompt outputs

integration:
    file
      →
    extraction
      →
    normalization
      →
    anonymization
      →
    scoring
      →
    LLM
      →
    roast
      →
    render
```

The original brief explicitly calls for extraction/anonymizer/rule-engine unit tests and a full file→roast→render integration test. fileciteturn5file4L1-L8

---

# 18. Original deployment plan

Core services should be containers.

Local:

```text
docker-compose
```

CI/CD:

```text
GitHub Actions
```

Cloud:

```text
Azure
```

Deployment targets mentioned originally included:

```text
Azure Container Instances
or
App Service
```

The original plan also calls for:

```text
Postgres migrations
sample ruleset JSON
prompt templates
unit tests
local-dev runbook
staging deployment runbook
restore procedures
```

fileciteturn5file4L1-L8

---

# 19. Current directory structure

The structure evolved during implementation. The following reflects the architecture discussed and implemented.

```text
resume_roast_arena/
│
├── backend/
│   └── src/
│       ├── config.py
│       │
│       ├── db/
│       │   ├── session.py
│       │   └── sessions.py
│       │
│       ├── dependencies/
│       │   └── auth.py
│       │
│       ├── services/
│       │   ├── blob.py
│       │   ├── service_bus.py
│       │   ├── session_service.py
│       │   └── idempotency_service.py
│       │
│       ├── utils/
│       │   ├── telemetry.py
│       │   └── file_validation.py
│       │
│       └── routes/
│           └── ingest.py
│
├── workers/
│   │
│   ├── extraction/
│   │   ├── main.py
│   │   ├── consumer.py
│   │   ├── processor.py
│   │   ├── state.py
│   │   ├── schemas.py
│   │   ├── errors.py
│   │   └── extractor/
│   │       └── tika.py
│   │
│   ├── normalization/
│   │   ├── main.py
│   │   ├── consumer.py
│   │   ├── processor.py
│   │   ├── state.py
│   │   ├── schemas.py
│   │   ├── errors.py
│   │   └── pipeline/
│   │       ├── loader.py
│   │       ├── segmenter.py
│   │       ├── entities.py
│   │       ├── signals.py
│   │       ├── metrics.py
│   │       └── assembler.py
│   │
│   ├── anonymization/
│   │   ├── main.py
│   │   ├── consumer.py
│   │   ├── processor.py
│   │   ├── state.py
│   │   ├── schemas.py
│   │   ├── errors.py
│   │   └── pipeline/
│   │       ├── loader.py
│   │       ├── redactor.py
│   │       └── assembler.py
│   │
│   └── scoring/
│       ├── main.py
│       ├── consumer.py
│       ├── processor.py
│       ├── state.py
│       ├── schemas.py
│       ├── errors.py
│       └── pipeline/
│           ├── loader.py
│           ├── rules.py
│           ├── scorer.py
│           ├── assembler.py
│           └── prompt_builder.py
│
├── tests/
│   └── ...
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

**Important:** This is a migration-oriented representation based on the implementation discussed. The actual filesystem should be treated as authoritative.

---

# 20. Worker design pattern

Every worker follows approximately:

```text
main.py
   ↓
consumer.py
   ↓
processor.py
   ↓
pipeline/
   ↓
Blob artifact
```

### main.py

Only:

```text
logging
infrastructure initialization
consumer startup
```

### consumer.py

Only:

```text
Service Bus
deserialize
validate
DB session
processor
ACK / abandon / DLQ
shutdown
```

### processor.py

Only:

```text
state validation
state transition
pipeline orchestration
artifact upload
success/failure handling
```

### state.py

Only:

```text
DB state mutations
```

### schemas.py

Only:

```text
data contracts
```

### errors.py

Only:

```text
transient/permanent error taxonomy
```

### pipeline modules

Only stage-specific transformation logic.

---

# 21. Important design philosophy established

The project intentionally separates:

```text
Extraction
    = obtain text

Normalization
    = structure/features

Anonymization
    = privacy

Scoring
    = deterministic interpretation

Prompt Builder
    = LLM presentation layer

LLM
    = generative feedback

Renderer
    = presentation/shareability
```

Do not collapse these responsibilities unless there is a concrete architectural reason.

---

# 22. Placeholder decision

Stored anonymized artifacts retain deterministic placeholders:

```text
{{EMAIL_1}}
{{PHONE_1}}
{{URL_1}}
```

The LLM-facing layer should transform them:

```text
{{EMAIL_1}} → [EMAIL]
{{PHONE_1}} → [PHONE]
{{URL_1}} → [URL]
```

Do this in:

```text
prompt_builder.py
```

not in the anonymization artifact.

Reason:

```text
Anonymization = canonical/privacy-safe representation
Prompt builder = LLM-specific presentation
```

---

# 23. Severity decision

Scoring issues use:

```text
critical
high
medium
low
```

and summary contains the full breakdown:

```text
total_issues
critical_issues
high_issues
medium_issues
low_issues
total_strengths
```

This was adopted because the frontend/LLM should not have to reconstruct severity counts.

---

# 24. Known deferred improvements

## Extraction

```text
better confidence calibration
better OCR confidence
additional document types/edge cases
```

## Segmenter

```text
header false-positive guard
better bullet detection
more section aliases
```

## Entities

```text
names
organizations
locations
email DNS validation
better phone false-positive filtering
```

## Signals

```text
better spaCy coverage
better passive voice detection
stronger action-verb detection
sentence-quality improvements
metric density
bullet consistency
```

## Metrics

```text
metric density
achievement quantification
bullet-level metrics
```

## Anonymization

```text
name/address redaction
entity confidence
improved phone detection
```

## Scoring

```text
JSON-configurable rules
industry-specific rules
numeric composite scores
scoring rationale
LLM-derived quality signals
```

---

# 25. Immediate unfinished product work

After the deterministic pipeline:

```text
1. Finish prompt_builder
2. Define LLM output schema
3. Implement LLM client
4. Create roast-generation worker/stage
5. Add output validation
6. Add numeric scoring
7. Persist roast result
8. Build renderer
9. Build public link service
```

Then:

```text
10. TTL cleanup
11. Redis rate limiting
12. security hardening
13. observability hardening
14. integration testing
15. Docker/deployment
16. CI/CD
```

---

# 26. How the next model should resume

Do not immediately write code.

First ask it to inspect:

```text
backend/src/db/sessions.py
backend/src/services/blob.py
backend/src/services/service_bus.py
backend/src/services/session_service.py

workers/extraction/
workers/normalization/
workers/anonymization/
workers/scoring/
```

Then compare actual code against this document.

The next model should explicitly identify:

```text
implemented
partially implemented
missing
broken
```

before changing architecture.

---

# 27. Original architecture vs current implementation

## Original

```text
Ingest
 → Extraction
 → Normalizer
 → Anonymizer
 → Rule Evaluator + LLM
 → Scoring
 → Renderer
 → Public Link
```

## Current

```text
Ingest
 → Extraction
 → Normalization
 → Anonymization
 → Deterministic Scoring
 → Prompt Builder [started]
```

Therefore the project is **not finished**, but the most difficult backend pipeline foundation is in place.

---

# 28. Final migration instruction

When this document is handed to another model, the desired behavior is:

> Continue the existing architecture. Do not restart the project. Inspect the actual repository before proposing changes. Preserve existing artifact contracts unless there is a concrete compatibility reason to change them. Treat the original MVP requirements as the product target and the current code as the implementation source of truth.

---

## Canonical target

```text
UPLOAD
  ↓
EXTRACT
  ↓
NORMALIZE
  ↓
ANONYMIZE
  ↓
RULE EVALUATE
  ↓
LLM ROAST
  ↓
COMPOSITE SCORE
  ↓
RENDER
  ↓
PUBLIC SHARE
  ↓
TTL / CLEANUP
```

That is the project to finish.
