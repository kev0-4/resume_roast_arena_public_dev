# Resume Processing & Analysis Platform (WIP)

> **Status:** 🟢 Core pipeline complete, verified end-to-end
> **Goal:** Build a production-grade, distributed system for resume ingestion, extraction, normalization, and downstream analysis (anonymization, scoring, AI feedback).

---

## Overview

This project is a **backend-heavy, distributed resume processing platform** designed with **real-world production constraints** in mind.

The system accepts resumes in multiple formats (PDF, DOCX, images), processes them asynchronously, extracts structured information, and prepares the data for downstream analysis such as anonymization, rule-based evaluation, scoring, and AI-generated feedback.

The focus of this project is **architecture, reliability, correctness, and scalability**, not just feature demos.

---

## High-Level Architecture

```
Client
  ↓
FastAPI (Ingest API)
  ↓
Blob Storage (raw files)
  ↓
Azure Service Bus (queue)
  ↓
Extraction Worker (Tika + OCR)
  ↓
Blob Storage (extracted.json)
  ↓
Normalization Worker
  ↓
Blob Storage (normalized.json)
```

Each stage is **decoupled**, **idempotent**, **stateless**, and **retry-safe**, following patterns used in production systems.

---

## Key Design Principles

- **Asynchronous, event-driven architecture**
- **At-least-once message delivery**
- **Explicit state machine per job**
- **Clear retry vs dead-letter semantics**
- **Stateless workers**
- **Deterministic, explainable processing**
- **Separation of concerns across pipeline stages**

---

## Tech Stack

### Backend & Infrastructure

- **Python**
- **FastAPI** (API layer)
- **SQLAlchemy (async)** + **PostgreSQL**
- **Docker & Docker Compose**
- **Azure Service Bus** (with emulator for local dev)
- **Azure Blob Storage** (raw & processed artifacts)

### Document Processing

- **Apache Tika (Docker-based)** for text extraction
- **Tesseract OCR (via Tika)** for scanned/image resumes

### Architecture Patterns

- Worker-based pipeline (extract → normalize → …)
- Message-driven orchestration
- Idempotency keys for safe retries
- Explicit job state transitions

---

## Current Pipeline Status

### ✅ Completed

- **FastAPI application setup**
- **Health & service routes**
- **Authentication layer**
- **Idempotent ingest endpoint**
- **Resume upload & validation**
- **Blob storage integration**
- **Azure Service Bus integration**
- **Extraction worker**
  - Tika-based text extraction
  - OCR fallback using Tesseract
  - Confidence-based decision logic
  - Correct retry vs permanent failure handling
  - **Enqueues normalization job**

- **Extraction artifacts (`extracted.json`)**
- **Normalization worker skeleton**
  - Deterministic orchestration
  - State transitions (`EXTRACTED → NORMALIZING → NORMALIZED`)
  - Schema-first design
  - Normalization converts extracted text into a **canonical, structured representation**.
  - Implemented components:
    - Loader (`extracted.json` validation)
    - Deterministic segmenter (resume sections)
    - Regex-based entity extraction (emails, phones, URLs)
    - Tiered signal computation (boolean / categorical)
    - Numeric metrics computation
    - Assembler (schema-stable `normalized.json`)
    - State transitions (`EXTRACTED → NORMALIZED`)

  Output artifact:

  ```
  normalized/<session_id>/normalized.json
  ```

  This stage is **fully deterministic** and **non-ML** by design.

---

## Artifacts Produced

| Stage         | Artifact                                  |
| ------------- | ----------------------------------------- |
| Ingest        | `raw/<session_id>/<filename>`             |
| Extraction    | `extracted/<session_id>/extracted.json`   |
| Normalization | `normalized/<session_id>/normalized.json` |

Artifacts are immutable and traceable across stages.

---

## Job State Machine

Each resume follows a strict lifecycle:

```
QUEUED
  ↓
PROCESSING
  ↓
EXTRACTED
  ↓
NORMALIZING
  ↓
NORMALIZED
  ↓
ANONYMIZING
  ↓
ANONYMIZED
```

Failures are classified as:

- **Transient** → retried automatically
- **Permanent** → marked failed & dead-lettered

---

## What’s Next (Planned)

### 🔜 Next Pipeline Stage

- **Anonymization**
  - Span-based PII redaction
  - Deterministic masking
  - `anonymized.json`
  - No ML, no heuristics

### 🔮 Future Stages

- Rule-based evaluation engine
- Scoring with explainability
- AI-assisted resume feedback (“resume roast”)
- Rendering (HTML / image cards)
- Public shareable result links
- Observability (metrics, tracing)
- CI/CD pipelines
- Performance tuning & caching

## Why This Project Matters

This project is **not a CRUD app** or a demo script.

It demonstrates:

- Distributed systems thinking
- Real-world backend architecture
- Worker-based async processing
- Message queues & failure handling
- Production-grade document processing
- Clean separation between deterministic logic and AI-driven stages

It is being built incrementally, with **correctness and scalability prioritized over speed**.

---

## Project Status

> ⚠️ This project is **actively being developed**.
> The architecture and core pipeline are stable, while higher-level features are being layered on top.

---

## Author

Built by **Kevin Tandon**
Focused on backend systems, distributed architecture, and production-ready design.

> For myself cd backedn && uvicorn app:app , cd to proj root and python -m workers.normalization.main
