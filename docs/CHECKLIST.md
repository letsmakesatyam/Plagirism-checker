# Implementation Checklist — College Plagiarism Checker

Stack: **FastAPI + PostgreSQL + React** (replaces the earlier Node/Express version).
This file is updated after every phase. ✅ = done & tested, 🔲 = not started, 🟡 = in progress.

---

## Phase 1 — Foundation (Auth, DB, Project Skeleton) ✅ COMPLETE

- ✅ Project folder structure (backend / frontend / database / docker / docs / scripts / assets)
- ✅ FastAPI app skeleton (`app/main.py`) with CORS + health check
- ✅ Config layer (`app/config.py`) via pydantic-settings
- ✅ SQLAlchemy engine/session (`app/database.py`)
- ✅ `User` model (single table, `role` enum for Faculty/Student — see README > Database Design)
- ✅ Alembic migrations configured and first migration applied against real Postgres
- ✅ Password hashing + JWT (`app/core/security.py`) — uses `bcrypt` directly (passlib had a
  version-incompatibility bug, documented in README > Troubleshooting)
- ✅ `get_current_user` / `require_role` dependencies for route protection
- ✅ Auth routes: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- ✅ **Tested end-to-end** against a live server + live Postgres: register (faculty & student),
  login, protected route access, wrong password → 401, missing token → 401, duplicate email → 409
- ✅ Dockerfile (backend) + docker-compose.yml (Postgres + backend)
  - ⚠️ Not build-tested (no Docker daemon in this sandbox) — syntax-validated only.
    Please run `docker compose up --build` on your machine and report any issues.
- ✅ `.env.example`, `.gitignore`, `.dockerignore`

## Phase 2 — Assignments, Submissions & File Upload ✅ COMPLETE

- ✅ `Assignment` model (title, description, due date, faculty_id, is_active, timestamps)
- ✅ `Submission` model (student_id, assignment_id, file path, status, extracted_text,
  paragraphs (JSONB), page_count, word_count, was_ocr_used, timestamps)
- ✅ Faculty routes: create / list (own) / get / edit / delete assignment
- ✅ Student routes: list active assignments, upload PDF/DOCX submission
- ✅ Role enforcement verified (student blocked from creating assignments → 403)
- ✅ File upload validation: extension allow-list, size limit, empty-file rejection,
  unique stored filenames (UUID-based, original name preserved separately)
- ✅ Text extraction pipeline (`app/services/extraction.py`):
  - PyMuPDF + pdfplumber for text-layer PDFs
  - python-docx for DOCX
  - Tesseract OCR fallback (via PyMuPDF page rendering) when a PDF's text layer is
    too sparse (likely scanned) — **verified working**: OCR correctly triggered on an
    image-only test PDF and recovered the page's text
- ✅ Text cleaning: whitespace normalization, repeated-header/footer stripping,
  paragraph splitting — stored as both flat text and a JSONB paragraph array
  (paragraph array is what Phase 3 embeddings will consume)
- ✅ **Tested end-to-end** against a live server: assignment create/list/permission-check,
  DOCX upload+extraction, text-PDF upload+extraction (no OCR triggered, correctly),
  scanned-PDF upload+extraction (OCR triggered, correctly), invalid file type → 400,
  faculty view of all submissions for their assignment, student's own submission list

## Phase 3 — Embeddings & Vector Search ✅ COMPLETE

- ✅ `ParagraphEmbedding` model (one row per paragraph; its DB id doubles as the FAISS vector id)
- ✅ `app/services/embeddings.py` — sentence-transformers (`all-MiniLM-L6-v2`) wrapper,
  lazy-loaded singleton, batch encoding, L2-normalized 384-dim output
- ✅ `app/services/vector_index.py` — FAISS `IndexIDMap2(IndexFlatIP)` wrapper:
  add / search / save / load / remove, thread-safe via a module lock
- ✅ `app/services/embedding_pipeline.py` — chains extraction output → paragraph DB
  rows → batch embedding → FAISS indexing → disk persistence
- ✅ `Submission.status` extended with `EMBEDDING` / `EMBEDDED` states;
  `embedding_error` column added for failure surfacing
- ✅ Upload route chains embedding generation after extraction, with proper error
  isolation (an embedding failure returns 201 + `status: failed` + a clear message,
  not a 500 crash)
- ✅ Diagnostic/preview endpoint `GET /api/submissions/{id}/similar-paragraphs` —
  proves FAISS retrieval works end-to-end and is the building block Phase 4's
  internal-plagiarism scoring will sit on top of
- ✅ **FAISS mechanics tested directly** with synthetic 384-dim vectors: correctly
  clusters similar vectors and separates dissimilar ones, persists correctly across
  a simulated process restart (save → clear in-memory → reload from disk → same
  search results), and `remove_vectors` correctly excludes removed ids from later
  searches
- ✅ **Full API integration tested live**: upload → extraction succeeds → embedding
  step correctly attempted → fails gracefully (201 response, `status: failed`,
  descriptive `embedding_error`) rather than crashing, when the model download
  couldn't complete
- ⚠️ **Not verified: actual model download/inference.** `huggingface.co` (where
  `all-MiniLM-L6-v2`'s weights are hosted) is not in this build environment's
  allowed network domains, so the real embedding generation itself couldn't be
  exercised here — only the code path and its error handling could be. This should
  work normally with standard internet access (your machine, or Docker with normal
  egress) — **please verify this is the first thing you test**, and report back
  if `sentence-transformers` fails to download the model.
- 🐛 Two real bugs caught during testing and fixed (see git history / diffs):
  1. Alembic's `--autogenerate` does not detect new values added to an existing
     PostgreSQL ENUM type — required manually adding `ALTER TYPE ... ADD VALUE`
     statements to the migration.
  2. Those manual statements initially used the wrong casing (`'embedding'`
     instead of `'EMBEDDING'`) — SQLAlchemy's `Enum` type stores the Python enum
     member's *name*, not its `.value`. Confirmed by inspecting actual database
     rows before fixing. Left uncaught, this would have crashed the first time any
     submission reached the `EMBEDDING`/`EMBEDDED` status.

## Phase 4 — Plagiarism Detection ✅ COMPLETE (internal ✅, internet ✅, AI detection ✅)

- ✅ **Internal plagiarism** (`app/services/internal_plagiarism.py`): compares submission
  vs. every other indexed submission (current assignment + past submissions, both covered
  automatically since FAISS indexes everything) via nearest-neighbour search per paragraph,
  thresholded at `INTERNAL_SIMILARITY_THRESHOLD` (0.85). Produces a paragraph-coverage
  `internal_score`, per-paragraph match evidence, and a "copied from" summary grouped by
  source submission. See README section 10 for full algorithm + rationale.
- ✅ `Report` + `InternalMatch` models, migration `5a7cb1b88041`
- ✅ `POST /api/submissions/{id}/generate-report`, `GET /api/submissions/{id}/report`
- ⚠️ **Not verified live** — same reason as Phase 3's embedding step: no Postgres +
  no Hugging Face network access in this sandbox. Code is syntax-checked
  (`python -m py_compile`) but not exercised against a running server/DB. **Please run
  this first**: upload a submission, wait for `status=embedded`, upload a second,
  similar/duplicate submission, then call `generate-report` on the second one and
  confirm `internal_score` and `internal_matches` look right.
- ✅ **Internet plagiarism** (`app/services/internet_plagiarism.py`): compares submission
  paragraphs against a locally indexed knowledge-base corpus (not live web crawling — see
  README section 11 for why), thresholded at `INTERNET_SIMILARITY_THRESHOLD` (0.78).
  Produces `internet_score` and a source-wise breakdown (title/URL/category/% matched).
- ✅ `InternetSource` + `InternetSourceParagraph` models, separate FAISS index
  (`app/services/vector_index_sources.py`), migration `d14eb8117dc1`
- ✅ Source ingestion (`app/services/source_ingestion.py`): from pasted text (tested via
  seed script logic) and from URL (via `httpx` — not network-tested here)
- ✅ `POST /api/internet-sources`, `POST /api/internet-sources/from-url`,
  `GET /api/internet-sources` (faculty only)
- ✅ `backend/scripts/seed_internet_sources.py` — 6 original demo sources, one per
  required category, for immediate offline testing
- ✅ Report generation refactored into an orchestrator (`app/services/report_generation.py`):
  internal + internet checks now run together per `generate-report` call, each writing
  independent columns so one check's failure doesn't discard the other's results;
  `overall_originality_score = 100 - max(internal_score, internet_score)`
- ⚠️ **Not verified live** — no Postgres, no Hugging Face access, and no outbound network
  for URL ingestion in this sandbox. Code is syntax-checked only. **Please test in this
  order on your machine**: (1) run the seed script, (2) upload+embed a submission whose
  text closely paraphrases one of the 6 seeded topics above, (3) call `generate-report` and
  confirm `internet_score` and `internet_sources` in the response look right, (4) try
  `POST /api/internet-sources/from-url` against a real page.
- ✅ **AI-generated-text detection** (`app/services/ai_detection.py`): runs an open-source
  RoBERTa classifier (`openai-community/roberta-base-openai-detector`, originally released
  for GPT-2-output detection) per paragraph via Hugging Face `transformers`. Paragraphs
  under 20 words are skipped (not enough signal). Uses two thresholds
  (`AI_LIKELY_THRESHOLD`=0.65, `AI_HUMAN_THRESHOLD`=0.35) to produce three buckets —
  `likely_ai` / `uncertain` / `likely_human` — deliberately avoiding a forced binary
  verdict, per the spec's "never claim certainty" requirement. `ai_score` = % of
  evaluated paragraphs labeled `likely_ai`. **Explicit, documented limitation**: this
  model was trained on GPT-2-era text, not on modern LLMs (GPT-4/Claude/Gemini/etc.),
  so treat it as a working baseline, not an authority — see README section 12.
- ✅ `AIResult` model + `AILabel` enum, migration `155f14e44913` (also adds
  `reports.likely_ai_count` / `likely_human_count` / `uncertain_count`)
- ✅ Wired into the same orchestrator (`report_generation.generate_full_report`) as a
  third pure check — `app/api/routes/reports.py` needed **zero changes**, confirming the
  Phase 4b orchestrator design worked as intended
- ⚠️ **Not verified live** — same sandbox constraints as every ML step so far: no
  Postgres, and `huggingface.co` isn't reachable here, so the classifier itself was
  never downloaded or run. Code is syntax-checked (`python -m py_compile`, passes clean
  across the whole backend) only. **Please test on your machine**: run `generate-report`
  on a submission with a few reasonably long paragraphs (20+ words each) and confirm
  `ai_score`, `ai_results`, and the three counters look right; try including a
  paragraph you know is AI-written and one you wrote yourself, since the model's real
  accuracy can only be judged empirically.
- 🔲 Matched paragraph highlighting + source/AI attribution (frontend, Phase 6)

## Phase 5 — Reports & Dashboards ✅ BACKEND COMPLETE (frontend UI is Phase 6)

- ✅ **PDF report export**: `GET /api/submissions/{id}/report/pdf` (`app/services/report_pdf.py`,
  via `reportlab` — pure Python, no system dependencies). Renders scores table (originality/
  internal/internet/AI), the AI-detection limitation note, and up to 20 matches per section
  (internal + internet) with paragraph text and similarity.
- ✅ **Faculty dashboard**: `GET /api/faculty/dashboard` (`app/services/dashboard.py`) — cards
  (total assignments/submissions, status breakdown), recent submissions, top plagiarism
  (lowest `overall_originality_score`), most-copied internet sources, top similar students
  (whose submissions are most often the *source* of an internal match), and per-assignment
  analytics (submission count, reports generated, average originality score).
- ✅ **Student dashboard**: `GET /api/students/dashboard` — total available assignments,
  own submission count + status breakdown, recent submissions (with originality score if a
  report exists), and pending assignments (active, not yet submitted to).
- ✅ **Comparison page (backend)**: `GET /api/submissions/{a}/compare/{b}` (`app/services/
  comparison.py`, faculty-only, must own submission A's assignment) — paragraph-by-paragraph
  view of both submissions with whichever of *this pair's* paragraphs matched each other,
  reusing already-computed `InternalMatch` rows rather than re-running similarity search.
  Requires both submissions to have a generated report (409 if not).
- ✅ **Search & filters**: `GET /api/assignments?search=`, `GET /api/submissions/mine?
  status_filter=&search=`, `GET /api/assignments/{id}/submissions?status_filter=&search=`
  (matches filename or student name), and a new faculty-only `GET /api/reports?status_filter=
  &min_originality=&max_originality=&assignment_id=&search=` for report search/filtering
  across all their assignments.
- ✅ New schemas: `app/schemas/dashboard.py`, `app/schemas/comparison.py`
- ✅ No new migration needed — Phase 5 is entirely read-side aggregation over Phase 1-4 tables
  plus one new export format; no new columns or tables.
- ⚠️ **Not verified live** — same sandbox constraints as always (no Postgres). Code is
  syntax-checked (`python -m py_compile`, clean across the whole backend) only. Please test
  on your machine: generate a couple of reports, then hit `/api/faculty/dashboard`, `/api/
  students/dashboard`, `/api/reports` with a few filter combos, `/api/submissions/{a}/compare/
  {b}` on two submissions from the same assignment, and download a PDF via `/api/submissions/
  {id}/report/pdf`.
- ✅ Faculty/student dashboard **UI** (cards, charts) and the comparison page **UI** — built
  in Phase 6 below, consuming the endpoints above.

## Phase 6 — Frontend Build-out ✅ COMPLETE (with one documented limitation)

- ✅ React 18 + Vite + Tailwind scaffold (`frontend/`), React Query + Axios + React Hook Form +
  Recharts. `npm install && npm run build` verified clean in this sandbox (778 modules,
  no errors) — this is the first frontend build actually exercised, since earlier phases
  had no frontend to build.
- ✅ Design system: distinctive visual identity (forest green `#1F4B3F` + brass accent
  `#B8863B` on a paper background, Fraunces display / Inter body / IBM Plex Mono data type),
  chosen deliberately to avoid the generic cream+terracotta / near-black+neon AI-tool
  defaults. Signature element: `ScoreSeal`, a circular "certification stamp" score
  indicator reused across dashboards and reports.
- ✅ JWT auth: `src/context/AuthContext.jsx` (login/register/logout, session restore via
  `GET /api/auth/me`, token persisted in `localStorage`), `Login.jsx` / `Register.jsx`
  (role picker + student/faculty-specific fields), axios interceptor that attaches the
  bearer token and force-logs-out on 401.
- ✅ Routing: `ProtectedRoute` (auth-required, optional role gate) wraps every faculty/
  student page; unauthenticated or wrong-role access redirects appropriately.
- ✅ **Faculty pages**: dashboard (`FacultyDashboard.jsx` — Recharts pie of submission
  status + bar of average originality per assignment, top-plagiarism list, most-copied-
  sources list, recent-submissions table), `Assignments.jsx` (list + search + inline
  create form), `AssignmentDetail.jsx` (edit/delete, submissions table with status/search
  filters, checkbox multi-select feeding the comparison page), `ReportsSearch.jsx`
  (faculty-wide report search/filter UI over `GET /api/reports`), `InternetSources.jsx`
  (source-library admin: add from pasted text or URL, list indexed sources),
  `Comparison.jsx` (side-by-side paragraph view over `GET /api/submissions/{a}/compare/{b}`).
- ✅ **Student pages**: `StudentDashboard.jsx`, `StudentAssignments.jsx` (browse + search +
  upload-with-progress directly from the assignment card), `MySubmissions.jsx` (status/
  search filters).
- ✅ **Shared report page** (`SubmissionReport.jsx`, used by both roles): submission status/
  metadata, generate/regenerate report action, four `ScoreSeal`s (originality/internal/
  internet/AI), copied-from + internet-sources-matched summaries, full paragraph text
  color-coded by match type (rust=internal, brass=internet, violet=likely-AI), PDF
  report download, and (faculty only) a "compare with" shortcut into the comparison page.
- ✅ **Backend addition found missing during this phase and fixed**:
  `GET /api/submissions/{id}/file` (serves the original uploaded PDF/DOCX, same owner-or-
  owning-faculty auth as every other submission endpoint) — needed so the frontend can
  offer a file preview; nothing in Phases 1-5 exposed the raw file. Compile-checked clean.
- ⚠️ **Documented limitation, not silently dropped**: the spec asks for a PDF viewer with
  highlight *overlays* positioned on the rendered page (click a highlight → see page
  number). The extraction pipeline (Phase 2) never stored per-paragraph page number or
  bounding-box coordinates — only flat paragraph text — so true coordinate-based overlays
  aren't possible without a new extraction-side migration to capture that data. What's
  built instead: paragraph-level highlighting (same three color-coded categories) in a
  full-text view, which surfaces the same information without page-position overlay.
  Flagged here rather than faked. If overlays are wanted next, the fix is in extraction.py
  (capture `page_number`/bbox per paragraph) → a migration to store it → a real `react-pdf`
  overlay layer keyed on that data.
- ⚠️ **Not run against a live backend in this sandbox** — no Postgres/browser here, so this
  is `npm run build`-verified only, not click-tested against real data. Please test on your
  machine, in this order: `npm install` in `frontend/`, `npm run dev`, register a faculty
  + a student account, create an assignment as faculty, upload a submission as student,
  generate a report, confirm the highlight colors and score seals look right, then try the
  comparison flow (select two submissions from an assignment's table).

## Phase 7 — Testing, Logging, Polish 🟡 IN PROGRESS (handoff mid-debug — see note below)

- ✅ **Structured logging** (`app/core/logging.py`): human-readable text logs in
  development, one-JSON-object-per-line in production, both tagged with a
  per-request id via a `ContextVar`. Wired into `app/main.py`:
  a request-logging middleware (method/path/status/duration on every request,
  `X-Request-ID` response header) plus a global unhandled-exception handler
  (clean JSON 500 instead of an HTML traceback page, always logged with its
  request id). Key pipeline points now log explicitly: submission upload,
  extraction failure, embedding failure, and each stage of
  `report_generation.py`'s orchestration (internal/internet/AI check
  start/failure/finish). Noisy third-party loggers (`sqlalchemy.engine`,
  `transformers`, `httpx`, etc.) are capped at WARNING so they don't drown
  out app logs. Compile-checked clean (`python -m py_compile` across the
  whole backend, including this new module).
- ✅ **Backend test suite** (`backend/tests/`, pytest): `conftest.py` sets up a
  transactional-rollback fixture against a **real Postgres** test database
  (the models use Postgres-only `UUID`/`JSONB` column types, so SQLite can't
  run this schema — see the docstring at the top of `conftest.py`), plus an
  autouse fixture that replaces the two real ML calls (sentence-transformers
  embeddings, the AI-detection classifier) with small deterministic fakes so
  the whole suite runs offline/in seconds while still exercising every line
  of the real extraction → embedding-pipeline → FAISS →
  internal/internet-plagiarism → AI-detection → report-generation →
  routing code around them. Real `python-docx` is used to build upload
  fixtures in-memory (not mocked), so the actual DOCX extraction path is
  exercised for real. Covers: `test_auth.py` (register/login/me, duplicate
  email, wrong password, validation), `test_assignments.py` (CRUD, role
  enforcement, ownership checks, search), `test_submissions_and_reports.py`
  (upload → extract → embed happy path, bad-extension/empty/corrupt-file
  rejection, role enforcement, **the full internal-plagiarism pipeline**
  — two students submitting near-identical text correctly flags the second
  against the first with a 100% internal score and a correct "copied from"
  entry, an unrelated submission scores 0% — **AI-detection** via a marker
  string the fake classifier recognizes, report-status-gating (409 before
  `embedded`), PDF export (`%PDF` magic bytes), submission privacy, and
  faculty report search/filtering), `test_dashboard_and_sources.py`
  (internet-source ingestion + the full internet-plagiarism pipeline
  end-to-end, faculty/student dashboards, the comparison endpoint including
  its 409-before-both-reports-exist and faculty-only enforcement).
  `requirements-dev.txt` added (pytest + pytest-cov on top of
  `requirements.txt`); `pytest.ini` added.
  - ✅ **Actually run this session, against a real Postgres 16 instance**
    (this sandbox got Postgres + full network access, unlike earlier
    Phase 7 sessions): `pip install -r requirements.txt -r
    requirements-dev.txt` (heavy `sentence-transformers`/`transformers`
    installs skipped — confirmed via `grep` that nothing in `app/` imports
    them at module level, only inside the lazily-loaded functions the
    tests already mock, so the suite runs and covers the same code either
    way), then `pytest -v` → **37 passed, 1 currently-failing test
    deselected — see the "Known issue" callout right below this list**.
    Two other real issues were found and fixed in the process:
    1. `test_duplicate_email_rejected` used a 1-character `full_name`,
       which the registration schema's own validation correctly rejected
       (422) before the duplicate-email logic ever ran — a test-data bug,
       not an app bug. Fixed in `tests/test_auth.py`.
    2. `copied_from_summary()` / `internet_sources_summary()`
       (`app/services/internal_plagiarism.py` /
       `app/services/internet_plagiarism.py`) returned plain `dict`s that
       matched their response schemas field-for-field but weren't actual
       instances of those schema classes, which Pydantic v2 flags with a
       (harmless but noisy) serializer warning. Fixed by having both
       functions construct and return real `CopiedFromEntry` /
       `InternetSourceSummaryEntry` instances. Output is byte-identical;
       the warning is just gone.
    A new `tests/test_vector_index.py` was also added this session (real
    FAISS, no mocking — the file conftest.py's docstring already promised
    but that didn't exist yet). 6 of its 7 tests pass; the 7th is the
    known issue below.
- ✅ **Responsive design pass** (frontend): the sidebar was fixed-width and
  always visible with no mobile handling before this phase.
  `components/Layout.jsx` was rewritten as a proper off-canvas drawer
  (hamburger button + slide-out panel + backdrop) below the `lg:` breakpoint,
  with the original static sidebar kept for `lg:` and above. Every `<table>`
  (`MySubmissions`, `FacultyDashboard`, `ReportsSearch`, `InternetSources`,
  `AssignmentDetail`) is now wrapped in an `overflow-x-auto` container
  instead of breaking the page layout on narrow screens. ~10 hardcoded
  `grid-cols-2/3/4` layouts (both dashboards, `Register`, `Comparison`,
  `Assignments`, `InternetSources`) now collapse to a single column on
  mobile and step up at `sm:`/`lg:`. Several title-plus-action-buttons
  header rows (`SubmissionReport`, `AssignmentDetail`, `Assignments`,
  `StudentAssignments`) now stack vertically on mobile instead of
  overflowing horizontally.
  - ✅ **`npm install && npm run build` actually run this session**
    (network access available this time): 242 packages installed clean,
    `npm run build` → 778 modules transformed, no errors, `dist/`
    produced (755 kB main JS bundle before gzip / 220 kB after — Vite's
    normal "consider code-splitting" advisory for a chart-heavy SPA, not
    an error; see README section 17 if this is ever worth addressing).
  - ⚠️ **Still not click-tested in a real browser** — a clean build proves
    the code is structurally sound (imports resolve, JSX is valid, Tailwind
    classes compile), not that the mobile drawer/charts/forms *look*
    right. No browser is available in this sandbox. Please do a manual
    pass: `npm run dev`, open dev tools' device toolbar at phone width,
    and click through the drawer, both dashboards, and the report page.
- ✅ **README completion** (`docs/README.md`): added §16 Architecture
  Diagrams (system overview, upload→report sequence, entity-relationship
  overview — all ASCII, matching the style of the existing §2 diagram),
  §17 Deployment (server specs, step-by-step Docker Compose deployment,
  Nginx reverse-proxy config, backup guidance), and expanded §8
  Troubleshooting / §9 FAQ with entries for the new test suite and
  `npm install` network issues. §15 (Testing & Logging) rewritten to
  report the actual `pytest` run above instead of "not yet run".

**Handoff note**: this session picked up exactly where the previous one
stopped (README diagrams/FAQ/troubleshooting/deployment) and additionally
got real Postgres + full network access, which the last two Phase 7
sessions didn't have — so instead of only compile-checking the test suite
and frontend build, both were **actually executed**. 37 of 38 backend
tests pass; **one test is currently flaky/failing and needs debugging
next session** — see below. Stopped here at the user's explicit request
to guarantee a working handoff rather than risk running out of turn
budget mid-fix.

### 🔴 Known issue to pick up next session: `test_save_and_reload_preserves_search_results`

File: `backend/tests/test_vector_index.py` (new this session — a real-FAISS
unit test that `conftest.py`'s docstring already referenced but which
didn't exist until now; the other 6 tests in this file pass reliably).

**Symptom**: this one test — which adds 2 vectors, saves the FAISS index
to disk, drops the in-memory copy, and reloads it to confirm search
results survive a "restart" — fails. First failure mode seen: search
after reload returned an *unrelated* vector ID that was never added in
this test (e.g. id `25` or id `4`, both real Postgres-assigned
`paragraph_embeddings` primary keys from other test files' real
submission uploads). That pointed at cross-test contamination: this test
was reading/writing the **same shared `FAISS_INDEX_PATH`** that
`test_submissions_and_reports.py`'s real upload-pipeline tests also use
(the path is set once, session-wide, by `conftest.py`).

**Fix attempted**: added a `monkeypatch.setattr(vector_index,
"FAISS_INDEX_PATH", tmp_path / "test_vector_index.faiss")` to this file's
`clean_index` autouse fixture, giving every test in this file its own
private on-disk path so it can't collide with other files' writes.

**Result after that fix**: the "wrong vector ID" symptom is gone (progress
— confirms the shared-path theory was at least part of the problem), but
the test still fails: `after` now comes back completely **empty** (`[]`)
instead of the same two vectors as `before`. This means `save_index()` /
the reload path isn't finding the freshly-written file at the *patched*
path, or the write silently didn't happen — needs a debugging session to
pin down which. Things to check first, in order:
1. Whether `monkeypatch.setattr` on a `pathlib.Path` module-level global
   actually propagates into `save_index()`/`get_index()`'s reads of
   `FAISS_INDEX_PATH` the way expected (both functions reference it as a
   bare module-level name, which normally does pick up monkeypatched
   values — but confirm with a print/breakpoint right before
   `faiss.write_index(...)` and right after, printing
   `FAISS_INDEX_PATH`, `FAISS_INDEX_PATH.exists()`, and the file's byte
   size).
2. Whether `get_index()`'s **double-checked locking** (`if _index is
   None: with _lock: if _index is None: ...`) has a subtle bug — note the
   module uses a plain `threading.Lock()`, not an `RLock`; `save_index()`
   also acquires `_lock` before calling `get_index()` — if `_index` were
   ever `None` at that point, this would **deadlock** (a bug flagged as
   already-fixed earlier in this project's history for a similar
   RLock/deadlock issue — worth double-checking it hasn't regressed).
   Right now `_index` is never `None` when `save_index()` is called in
   this test (vectors were just added), so it doesn't appear to be an
   active deadlock, but it's adjacent code worth re-reading carefully.
3. Whether `faiss.write_index()` needs the target file to **not already
   exist**, or needs the parent directory in a specific state, that
   differs between the previously-passing shared-path version and the new
   per-test `tmp_path` version.
4. As a fallback if the root cause proves elusive: it's fine to simplify
   this specific test to construct a **fresh, separate `IndexIDMap2`
   instance directly** (bypassing the module-level singleton entirely —
   `faiss.write_index`/`faiss.read_index` round-tripped on a local
   variable) rather than exercising `vector_index.save_index()`'s global
   state, and cover the *singleton reload* behavior with a narrower,
   more surgical test instead. This would still give real, meaningful
   FAISS persistence coverage without fighting global mutable state.

**To reproduce**: `cd backend && pytest tests/test_vector_index.py -k
test_save_and_reload -v` (Postgres must be running — see §15 — even
though this particular test doesn't touch the DB, since `conftest.py`
imports `app.main` at module load time, which requires a reachable
`DATABASE_URL`).

**Workaround in place for this handoff**: every other test passes. The
full suite currently reports **37 passed, 1 deselected** when run as:
```
pytest -v --deselect tests/test_vector_index.py::test_save_and_reload_preserves_search_results
```
Do not delete or skip this test permanently — it's covering a real
persistence guarantee (`save()` must survive a process restart, per the
Phase 3 CHECKLIST entry above, which *was* verified working with
synthetic vectors during Phase 3's original development, so this is very
likely a test-isolation bug introduced this session, not a regression in
`vector_index.py` itself).

---

## Files created so far

```
# Phase 1
backend/app/config.py
backend/app/database.py
backend/app/models/__init__.py
backend/app/models/user.py
backend/app/core/security.py
backend/app/core/dependencies.py
backend/app/schemas/user.py
backend/app/api/routes/auth.py
backend/app/main.py
backend/requirements.txt
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/6193a9c2080d_create_users_table.py
backend/Dockerfile
backend/.dockerignore
backend/.env.example
docker-compose.yml
.gitignore
docs/README.md
docs/CHECKLIST.md (this file)

# Phase 2 (new/modified)
backend/app/models/assignment.py
backend/app/models/submission.py
backend/app/schemas/assignment.py
backend/app/schemas/submission.py
backend/app/services/extraction.py
backend/app/services/file_storage.py
backend/app/api/routes/assignments.py
backend/app/api/routes/submissions.py
backend/alembic/versions/3f651add4788_add_assignments_and_submissions_tables.py
backend/requirements.txt (updated: PyMuPDF, pdfplumber, python-docx, pytesseract, pdf2image, Pillow)
backend/app/main.py (updated: registered new routers)

# Phase 3 (new/modified)
backend/app/models/paragraph_embedding.py
backend/app/services/embeddings.py
backend/app/services/vector_index.py
backend/app/services/embedding_pipeline.py
backend/alembic/versions/6eea27ec63d2_add_paragraph_embeddings_table_and_.py
backend/app/models/submission.py (updated: EMBEDDING/EMBEDDED statuses, embedding_error column)
backend/app/schemas/submission.py (updated: embedding_error field)
backend/app/api/routes/submissions.py (updated: embedding pipeline chained onto upload,
  new GET /api/submissions/{id}/similar-paragraphs endpoint)
backend/app/config.py (updated: FAISS_INDEX_PATH setting)
backend/requirements.txt (updated: sentence-transformers, faiss-cpu)

# Phase 4 (new/modified, internal plagiarism only)
backend/app/models/report.py
backend/app/schemas/report.py
backend/app/services/internal_plagiarism.py
backend/app/api/routes/reports.py
backend/alembic/versions/5a7cb1b88041_add_reports_and_internal_matches_tables.py
backend/app/models/__init__.py (updated: registered Report/InternalMatch)
backend/app/config.py (updated: INTERNAL_SIMILARITY_THRESHOLD setting)
backend/app/main.py (updated: registered reports router)

# Phase 4b (new/modified, internet plagiarism)
backend/app/models/internet_source.py
backend/app/schemas/internet_source.py
backend/app/services/vector_index_sources.py
backend/app/services/source_ingestion.py
backend/app/services/internet_plagiarism.py
backend/app/services/report_generation.py (new: orchestrates internal + internet checks)
backend/app/api/routes/internet_sources.py
backend/scripts/seed_internet_sources.py
backend/alembic/versions/d14eb8117dc1_add_internet_sources_tables.py
backend/app/models/report.py (updated: added InternetMatch model + relationship)
backend/app/models/__init__.py (updated: registered InternetSource/InternetSourceParagraph/InternetMatch)
backend/app/schemas/report.py (updated: InternetMatchOut, InternetSourceSummaryEntry, ReportDetail fields)
backend/app/api/routes/reports.py (updated: uses report_generation.generate_full_report, includes internet_sources)
backend/app/services/internal_plagiarism.py (refactored: pure run_internal_check(), status/commit moved to orchestrator)
backend/app/config.py (updated: INTERNET_SIMILARITY_THRESHOLD, INTERNET_FAISS_INDEX_PATH)
backend/app/main.py (updated: registered internet_sources router)
backend/requirements.txt (updated: httpx)

# Phase 4c (new/modified, AI-generated-text detection)
backend/app/services/ai_detection.py
backend/alembic/versions/155f14e44913_add_ai_results_table_and_report_.py
backend/app/models/report.py (updated: added AILabel enum + AIResult model,
  Report.likely_ai_count/likely_human_count/uncertain_count columns + ai_results relationship)
backend/app/models/__init__.py (updated: registered AIResult/AILabel)
backend/app/config.py (updated: AI_DETECTION_MODEL_NAME, AI_LIKELY_THRESHOLD, AI_HUMAN_THRESHOLD)
backend/app/schemas/report.py (updated: AIResultOut, ReportOut counter fields, ReportDetail.ai_results)
backend/app/services/report_generation.py (updated: runs run_ai_check as a third orchestrated check)
backend/app/api/routes/reports.py (docstring only — no functional change needed)
backend/requirements.txt (updated: transformers)

# Phase 5 (new/modified, reports & dashboards backend)
backend/app/services/dashboard.py
backend/app/services/comparison.py
backend/app/services/report_pdf.py
backend/app/schemas/dashboard.py
backend/app/schemas/comparison.py
backend/app/api/routes/dashboard.py
backend/app/api/routes/reports.py (updated: added /api/reports search+filter,
  /api/submissions/{a}/compare/{b}, /api/submissions/{id}/report/pdf)
backend/app/api/routes/assignments.py (updated: ?search= query param)
backend/app/api/routes/submissions.py (updated: ?status_filter=&search= on both list endpoints)
backend/app/main.py (updated: registered dashboard router)
backend/requirements.txt (updated: reportlab)
```

# Phase 6 (new, frontend)
frontend/package.json, vite.config.js, tailwind.config.js, postcss.config.js, index.html,
  .env.example, .gitignore
frontend/src/main.jsx, App.jsx, index.css
frontend/src/api/client.js, auth.js, assignments.js, submissions.js, reports.js,
  dashboard.js, internetSources.js
frontend/src/context/AuthContext.jsx
frontend/src/components/Layout.jsx, ProtectedRoute.jsx, ScoreSeal.jsx, StatusBadge.jsx,
  Spinner.jsx, EmptyState.jsx, ErrorBanner.jsx
frontend/src/pages/Login.jsx, Register.jsx, NotFound.jsx
frontend/src/pages/faculty/FacultyDashboard.jsx, Assignments.jsx, AssignmentDetail.jsx,
  ReportsSearch.jsx, InternetSources.jsx, Comparison.jsx
frontend/src/pages/student/StudentDashboard.jsx, StudentAssignments.jsx, MySubmissions.jsx
frontend/src/pages/shared/SubmissionReport.jsx
backend/app/api/routes/submissions.py (updated: new GET /api/submissions/{id}/file endpoint
  so the frontend can preview/download the original uploaded file)

> Note: running this project outside Docker requires system packages `tesseract-ocr`
> and `poppler-utils` installed (see README > Installation). The Dockerfile will need
> these added too — tracked below.

- ✅ Added `tesseract-ocr` + `poppler-utils` to backend/Dockerfile's apt-get install
  (still not build-tested — no Docker daemon in this sandbox, see section above)

# Phase 7 (new/modified, testing + logging + responsive polish — IN PROGRESS, see note above)
backend/app/core/logging.py (new: TextFormatter/JsonFormatter, per-request ContextVar id)
backend/app/main.py (updated: configure_logging() at import time, request-logging
  middleware with X-Request-ID header, global unhandled-exception handler)
backend/app/services/report_generation.py (updated: logs each check's start/failure/finish)
backend/app/api/routes/submissions.py (updated: logs upload/extraction-failure/
  embedding-failure/pipeline-finished)
backend/tests/conftest.py (new: Postgres transactional-rollback fixture, deterministic
  fake embeddings + fake AI classifier, register_and_login/make_docx_bytes helpers)
backend/tests/test_auth.py (new)
backend/tests/test_assignments.py (new)
backend/tests/test_submissions_and_reports.py (new: full upload→report pipeline,
  internal + AI detection, PDF export, privacy, report search)
backend/tests/test_dashboard_and_sources.py (new: internet-source ingestion + internet
  plagiarism pipeline, both dashboards, comparison endpoint)
backend/requirements-dev.txt (new: pytest, pytest-cov)
backend/pytest.ini (new)
frontend/src/components/Layout.jsx (rewritten: responsive off-canvas mobile drawer nav)
frontend/src/pages/shared/SubmissionReport.jsx (updated: responsive header/grid)
frontend/src/pages/faculty/AssignmentDetail.jsx (updated: responsive headers, table scroll)
frontend/src/pages/faculty/Assignments.jsx (updated: responsive headers/grids)
frontend/src/pages/faculty/FacultyDashboard.jsx (updated: responsive grids, table scroll)
frontend/src/pages/faculty/ReportsSearch.jsx (updated: table scroll wrapper)
frontend/src/pages/faculty/InternetSources.jsx (updated: responsive grid, table scroll)
frontend/src/pages/faculty/Comparison.jsx (updated: responsive grid)
frontend/src/pages/student/MySubmissions.jsx (updated: table scroll wrapper)
frontend/src/pages/student/StudentDashboard.jsx (updated: responsive grids)
frontend/src/pages/student/StudentAssignments.jsx (updated: responsive card header)
frontend/src/pages/Register.jsx (updated: responsive grids)

# Phase 7 fixes (this session, found by actually running the test suite)
backend/tests/test_auth.py (fixed: test_duplicate_email_rejected used an
  invalid 1-char full_name, tripping schema validation before the
  duplicate-email check could run)
backend/app/services/internal_plagiarism.py (fixed: copied_from_summary()
  now returns real CopiedFromEntry instances instead of plain dicts,
  removing a Pydantic serializer warning)
backend/app/services/internet_plagiarism.py (fixed: internet_sources_summary()
  now returns real InternetSourceSummaryEntry instances instead of plain
  dicts, same fix as above)
backend/tests/test_vector_index.py (new: real-FAISS unit tests, no mocking;
  6/7 passing — see CHECKLIST Phase 7 "Known issue" for the 7th)
docs/README.md (updated: §15 rewritten with real pytest/npm results; new
  §16 Architecture Diagrams, §17 Deployment, §18 What's Next; §8/§9
  expanded with test-suite and npm-install troubleshooting entries)
