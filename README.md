# Resume Processing & Analysis Platform (WIP)

> **Status:** 🚧 Actively under development
> **Goal:** Build a production-grade, distributed system for resume ingestion, extraction, normalization, analysis, and AI-assisted feedback.

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

Each stage is **decoupled**, **idempotent**, and **retry-safe**, following patterns used in production systems.

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

- **Extraction artifacts (`extracted.json`)**
- **Normalization worker skeleton**

  - Deterministic orchestration
  - State transitions (`EXTRACTED → NORMALIZING → NORMALIZED`)
  - Schema-first design

---

## Normalization (In Progress)

Normalization converts raw extracted text into a **canonical, structured representation**.

Planned output includes:

- Sectioned resume blocks (summary, experience, education, skills, projects)
- Entity detection (emails, phone numbers, names, organizations)
- Deterministic signals (presence of sections, metrics usage, dates, etc.)
- Quantitative metrics (word count, experience entries, skill count)

This stage is intentionally **rule-based and deterministic**, not ML-driven.

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
```

Failures are classified as:

- **Transient** → retried automatically
- **Permanent** → marked failed & dead-lettered

---

## What’s Next (Planned Work)

### 🚧 In Progress

- Normalization pipeline logic

  - Section segmentation
  - Entity extraction
  - Signal & metric computation

### ⏭️ Upcoming

- Anonymization (PII redaction using entity spans)
- Rule-based resume evaluation
- Scoring engine with explainability
- AI-assisted feedback / “resume roast”
- Rendering results (HTML / image)
- Public result links
- Caching & rate limiting
- Observability (metrics, tracing)
- CI/CD pipelines

---

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
