# AGENTS.md — Developer and AI Agent Guidelines

## 1. Project Overview & Identity
- **Project**: National Weather Big Data Analytics Platform (Smart India Hackathon 2026 — Problem Statement ID: `SIH26069`)
- **System Purpose**: An AI-augmented, big data ingestion and analytics platform designed to ingest multi-source weather and disaster data (citizen reports, IMD automatic weather stations, open government portals, RSS, and public feeds), process and classify events, detect duplicates, score credibility with explainability, corroborate against meteorological baselines, and provide real-time situational awareness dashboards and verification queues for disaster management authorities (NDRF, SDRF, DEOCs).

---

## 2. Source of Truth & Architecture Hierarchy
Before writing code or making modifications, every agent and human developer **MUST** consult the project's documentation suite located in `/docs`:

1. [docs/PRD.md](docs/PRD.md) — Product Requirements, User Personas, Core Use Cases, SIH Scope.
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — High-Level Design, Data Flow, Ingestion, Intelligence Pipeline, Real-Time Architecture.
3. [docs/TECH_STACK.md](docs/TECH_STACK.md) — Approved Frameworks, Libraries, Utilities, and Technical Constraints.
4. [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — Conceptual and Logical Entity Relationships, Field Constraints, Spatial Schemas.
5. [docs/API_CONTRACT.md](docs/API_CONTRACT.md) — RESTful Endpoints, Request/Response Schemas, Error Envelopes, Auth Scopes.
6. [docs/EXTERNAL_SETUP.md](docs/EXTERNAL_SETUP.md) — Local vs. External Infrastructure, API Keys, Environment Variables.
7. [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Phased Roadmap and Verification Gates.
8. [.agents/rules/project-rules.md](.agents/rules/project-rules.md) — Persistent behavioral rules and strict guardrails.

---

## 3. Strict Operating Rules for AI Agents

### Rule 1: Read and Inspect Before Acting
- Always inspect existing code and read the relevant documentation before proposing changes or writing code.
- Never assume an API, schema, or utility exists without verifying in the workspace.

### Rule 2: Adhere to Approved Stack & Decisions
- **Frontend**: React, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query, React Hook Form, Zod, Leaflet, Recharts.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), GeoAlchemy2, Alembic, httpx.
- **Data & Cache**: PostgreSQL 16+ with PostGIS extension (system of record), Redis 7+ / Redis Streams (caching, event streaming), MinIO / S3 (media storage).
- **AI/ML**: Deterministic rules + lightweight ML/embeddings + targeted LLM explanations. No black-box unexplainable AI.
- Do NOT introduce unapproved databases (e.g., MongoDB, DynamoDB) or message brokers (e.g., Kafka) into the local MVP without documented justification and approval.

### Rule 3: Storage & Schema Discipline
- **PostgreSQL + PostGIS is the sole system of record**.
- Geographic coordinates **MUST** be stored as PostGIS spatial points (`SRID 4326`).
- **NEVER store binary media (images/videos) in PostgreSQL**. Store binary blobs in S3/MinIO and persist only metadata (URI, bucket, MIME type, SHA256 checksum, dimensions) in the database.
- Schema changes must strictly go through Alembic migrations. Never execute ad-hoc raw DDL directly against production/testing schemas.

### Rule 4: Data Validation & Strong Typing
- All backend input and output **MUST** be validated using strict Pydantic v2 models.
- All frontend forms and API interactions **MUST** be validated with Zod and typed TypeScript interfaces.
- Validate geographic bounding boxes, coordinates, file sizes, and MIME types on upload.

### Rule 5: Security & Secrets Hygiene
- **NEVER hardcode secrets, API keys, tokens, or credentials in any source file.**
- **NEVER commit `.env` files or local config containing real credentials to Git.**
- Use `.env.example` templates with sanitized placeholders.
- Never stage build artifacts, `node_modules`, `__pycache__`, or `.venv` files.

### Rule 6: Credibility & AI Boundaries
- Clearly distinguish between `credibility_score` (computed statistical/algorithmic score between 0.0 and 1.0) and `verification_status` (`PENDING`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`, `DUPLICATE`).
- Credibility calculations must be explainable with a structured breakdown (e.g., source reliability factor, spatial/temporal corroboration factor, metadata consistency factor).
- AI/LLM outputs must **NEVER** be presented as absolute ground truth.

### Rule 7: Modular, Clean, and Tested Code
- Keep modules focused and single-responsibility. Avoid giant files or monolithic components (>300 lines).
- Write automated tests for all backend services, business logic, intelligence calculations, and API endpoints.
- Maintain clean error handling and structured JSON error responses with standard error codes.

### Rule 8: Handling Ambiguity
- If you encounter conflicting specifications, missing requirements, or ambiguous technical paths, **STOP and document/report the ambiguity** rather than making a silent architectural decision.

---

## 4. Verification & Checkpoint Workflows
Before declaring any task or phase complete:
1. Run the verification workflow defined in [.agents/workflows/verify.md](.agents/workflows/verify.md).
2. Follow the commit checkpoint protocol in [.agents/workflows/checkpoint.md](.agents/workflows/checkpoint.md).
