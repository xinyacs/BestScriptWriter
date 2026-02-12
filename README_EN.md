# BestScriptWriter (Under Development)

> This project is under active development (APIs/data schemas/prompt templates may change in incompatible ways).
>
> Powered by **GLM + KIMI2.5**.

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](./LICENSE)
[![Docs License](https://img.shields.io/badge/Docs%20License-CC%20BY--SA%204.0-lightgrey.svg)](./compass/LICENSE)
[![Release](https://img.shields.io/badge/release-dev-orange.svg)](#)
[![Stars](https://img.shields.io/badge/stars-placeholder-lightgrey.svg)](#)

Quick Links:
- [Features](#1-overview)
- [Supported Video Types](#11-supported-video-types--use-cases)
- [Architecture & Agent Strategy](#3-agent--workflow-strategy-production-oriented)
- [Compass: Purpose & Implementation](#33-compass-purpose--implementation-skill-subset)
- [Quick Start (Local)](#51-local-run-recommended-for-development)
- [Docker Deployment](#52-docker-deployment-recommended-for-testing--small-scale-production)
- [Configuration (.env)](#6-configuration-env)
- [Licenses & Notices](#8-licenses--notices)

---

## 1. Overview

BestScriptWriter is a production-oriented system for short-form / vertical video creation, turning a high-level outline (L1) into a shootable storyboard script (L2):

- Provide text input (optionally with multiple images), and the system generates:
  - **L1**: chapter-level outline (each item includes `duration` and `rationale`)
  - **L2**: shot/segment-level script expanded from L1 (shot size, camera movement, scene, props, captions, voiceover, etc.)
- The system provides **versioned editing** APIs: edits to L1/L2 produce new versions (TaskRun) for auditability and rollback.
- Export capabilities:
  - **Print-friendly XLSX** for directors/actors
  - Per-shot **text-to-video prompt** export (Seedrance2.0 / sora2 / veo3)

### 1.1 Supported Video Types & Use Cases

This system focuses on the workflow:

**Text / text+image input → shootable storyboard script → per-shot prompt for T2V/I2V platforms**.

Typical use cases include:

- **E-commerce videos**
  - product highlights, scenario-based “planting”, unboxing/reviews, store launches, A+ assets.
- **Feed / informational / talking-head videos**
  - structured breakdown, pacing control, captions + shot language.
- **Short dramas / trailers / short films**
  - supports “chapter → shots” narrative organization; current version is primarily a storyboard-script generator and does not include a full-scale casting/dialogue-direction system.
- **Comics-to-video / animation (lightweight)**
  - works well for single-episode or short segments; character consistency and asset management are planned enhancements.

Scope boundaries:
- The current repository mainly provides **script & prompt-layer** capabilities; it does not include a complete asset pipeline (batch image/video generation, asset library, queue scheduler, etc.).
- Prompt export applies platform constraints for Seedrance2.0 / sora2 / veo3, but providers evolve quickly; you should calibrate rules against your target platform.

---

## 2. Core Concepts & Data Model

### 2.1 ScriptTask
- A task represents one content input (text + images) plus the subsequent L1/L2 generation results.

### 2.2 TaskRun (Run / Version)
- Each generation or edit of L1/L2 produces a `TaskRun`. Runs are chained via `parent_run_id`.
- Key fields:
  - `phase`: `l1` / `l2`
  - `status`: `RUNNING` / `DONE` / `ERROR`
  - `result_json`: structured output (L1 is a dict, L2 is a list[dict])

### 2.3 item_id (Stable Addressing)
- L1 `body[*]` gets an auto-injected `item_id`.
- L2 `sections[*]` and `sub_sections[*]` also include `item_id`.
- The system guarantees uniqueness within the same level and avoids collisions between `sub_sections.item_id` and its parent `section.item_id`.

---

## 3. Agent / Workflow Strategy (Production-Oriented)

The system follows a layered strategy: **layered generation + controlled expansion + auditable edits**.

### 3.1 L1 (Outline Layer)
- Goal: generate a well-structured outline with controllable duration.
- Output: `L1VideoScript` (title/keywords/body/total_duration).

### 3.2 L2 (Storyboard Layer)
- Goal: expand each L1 item into a shootable storyboard script.
- Convention: by default, **one L1 segment corresponds to one L2 section**.

### 3.3 Compass: Purpose & Implementation (Skill Subset)

Compass is positioned as a **reusable, versionable, composable subset of Prompt Skills**.

In production, prompts usually contain three categories:
- **Task-invariant rules & style** (e.g., director shot language preferences, style tone, platform conventions, terminology)
- **Task-specific facts** (your product/story/characters/scene settings)
- **Stage-specific formats & constraints** (different JSON structures for L1/L2; different limits per target platform)

Compass mainly addresses the first category by extracting those rules into Markdown documents so they become:
- **Controllable**: selecting director/style is equivalent to switching a skill bundle.
- **Maintainable**: authored as documents rather than scattered strings in code.
- **Composable**: reused across stages (L1, L2, PromptExport).

#### 3.3.1 Code Path

Implementation lives in `core/compass.py`:
- `CompassSelection`: the selected director/style (platform dimension is currently treated as optional/tolerant).
- `CompassRegistry`:
  - loads `*_compass.md` from `compass/{director|style|platform}`
  - parses frontmatter (`---` metadata)
  - caches docs by file mtime to avoid repeated disk reads
- `build_compass_prompt(...)`:
  - concatenates selected doc bodies
  - tolerates missing docs (useful for custom platforms/targets)

#### 3.3.2 Why It Is a “Skill Subset”

A full Skill system often also includes:
- parameterized tool/function calls (retrieval, template compilation, external tools)
- observability & evaluation (quality metrics, AB tests, regression sets)
- safety & compliance policies (sensitive content, brand allowlists, platform review rules)

Compass in this repo focuses on the most robust and widely applicable part: **rule-based text skills**. It naturally fits version control and audit requirements.

### 3.4 PromptExport (Per-shot Prompt Export)
- `PromptExportAgent` exports a single L2 shot (sub_section item) into prompts for different targets.
- `compass/prompt/` provides target-specific rule injection (e.g., `veo_compass.md`).

---

## 4. CLI (Workflow-based)

This repository currently provides a workflow-style entry:

- `agent/total_workflow.py`: `total_script_infer()` orchestrates:
  - optional Compass inference
  - L1 inference
  - L2 inference

You can use `application.py` as a script-like “CLI starter” and extend it into a real command-line tool (argparse/click) if needed.

---

## 5. Deploy & Run

### 5.1 Local Run (Recommended for Development)

1) Install dependencies

```bash
pip install -r requirements.txt
```

2) Configure environment variables

- Copy `.env.example` to `.env`
- Fill in:
  - `OPENAI_HOST`
  - `OPENAI_KEY`

3) Start server

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

4) First-run database initialization

- This project uses SQLite.
- **On first run, tables are created automatically via `create_all`** (see `startup_event()` in `main.py`).

5) Visit
- Home: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`

### 5.2 Docker Deployment (Recommended for Testing / Small-scale Production)

1) Prepare env

- Copy `docker/.env.example` to `docker/.env`
- Fill in `OPENAI_HOST` / `OPENAI_KEY`

2) Run

```bash
docker compose -f docker/docker-compose.yaml --env-file docker/.env up --build
```

3) Persistence

- SQLite: `./data/app.db` (mapped to `/app/data/app.db`)
- uploads: `./uploads/` (mapped to `/app/uploads`)

---

## 6. Configuration (.env)

All settings can be overridden via `.env` or environment variables.

### 6.1 Basics
- `APP_NAME`: application name
- `APP_VERSION`: version
- `DEBUG`: debug flag (affects SQL echo, etc.)

### 6.2 Server
- `HOST`: bind address
- `PORT`: bind port

### 6.3 Database
- `DATABASE_URL`: SQLAlchemy async DSN
  - default: `sqlite+aiosqlite:///./app.db`

### 6.4 LLM
- `OPENAI_HOST`: OpenAI-compatible base_url
- `OPENAI_KEY`: API key (do not commit)

### 6.5 Models
- `L0_AGENT_MODEL`: model used by L1 / PromptExport (adjust as needed)
- `L1_AGENT_MODEL`: model used by L2 (adjust as needed)

### 6.6 File Handling
- `FILE_UPLOAD_DIR`: upload directory
- `FILE_MAX_BYTES`: max file size (bytes)
- `FILE_PARSE_TIMEOUT_S`: parse timeout (seconds)
- `FILE_MAX_CONCURRENCY`: max parse concurrency
- `FILE_IMAGE_PREFIX`: allowed image MIME prefix (default `image/`)
- `FILE_MAX_IMAGES`: max images per request
- `FILE_MAX_IMAGE_BYTES`: max single image size
- `FILE_IMAGE_STREAM_CHUNK_BYTES`: file stream chunk size

---

## 7. Security & Best Practices

- Do not commit `.env` (contains secrets). Consider adding `.env` to `.gitignore`.
- For production, consider:
  - an external database (or at least bind-mount SQLite to stable storage)
  - reverse proxy (Nginx/Caddy)
  - strict CORS allowlist

---

## 8. Licenses & Notices

This project uses a **dual-license / dual-material** strategy:

- **Code**: Apache-2.0 (see [LICENSE](./LICENSE))
  - allows modification and commercial use
  - includes a strengthened attribution requirement via [NOTICE](./NOTICE)
- **Compass/Prompt Documents**: CC BY-SA 4.0 (see [compass/LICENSE](./compass/LICENSE))
  - prevents “prompt-only copy” from being re-licensed as closed-source

Trademark / endorsement:
- See [TRADEMARK](./TRADEMARK).
- The name **BestScriptWriter**, Compass document names, and associated marks must not be used to imply official endorsement or partnership.

If you use this project in a paper/article/product:
- please keep attribution and link back to this project, and declare your usage in NOTICE.
