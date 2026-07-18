# Interview Management System — Implementation Plan

Branch: `feature/interview-tracking` (already created, no commits yet).

## Context

The user expects a heavy interview season ahead and wants to evolve Swiss Job Hunter's existing lightweight application tracker (Kanban status + free-form `JobEvent` timeline) into a real interview-management system. This was scoped through an extensive requirements session covering three tightly-coupled pieces: (1) a proper resume-version library that becomes the actual source of truth for the scoring/cover-letter/CV-tailoring pipeline (replacing the current flat `data/cv_{direction}.txt` files), (2) structured multi-round interview tracking (replacing the current fixed-enum `ApplicationEvent.INTERVIEW_1/INTERVIEW_2/TECHNICAL`, which doesn't scale to arbitrary round counts), and (3) per-round retrospectives with a personal STAR-story library and an LLM-powered "optimize this answer" coach, plus cross-job keyword search over past questions. This is a solo/local single-user deployment (not the hosted multi-tenant SaaS) — scope, defaults, and UI choices below assume that.

All scope and design decisions were confirmed directly with the user before planning began; this plan is execution detail only.

## Confirmed decisions going in

- Resume versions, Interview rounds, per-round retrospectives, STAR library, and cross-job question search are **all in scope for this pass** — no phased cut-down.
- `ResumeVersion` (DB-backed, supports PDF/DOCX/TXT upload with text extraction) becomes the actual data source for `load_cv_text(direction)` — not a side registry.
- STAR stories are a **standalone library**, independent of resumes/CV, structured as Situation/Task/Action/Result cards. When optimizing an answer, the **entire** library is passed to the LLM in one shot — no manual selection, no retrieval logic.
- Interviews are a **new first-class entity** (`interviews` table), not bolted onto the existing `JobEvent` enum. `JobEvent`/timeline stays untouched for non-interview events (recruiter calls, offers, rejections, notes).
- Retrospectives are captured **per interview round**, with structured fields (self-rating, went well, to improve, notes) plus a list of `question` + `my_answer` + LLM critique/optimized-answer per round.
- Cross-job keyword search over past questions/answers ships **in this pass** (simple SQL `LIKE`, no tagging system).
- Nav: RESUMES and STORIES are **sub-tabs nested inside a new top-level INTERVIEWS tab** (sub-nav: `UPCOMING | SEARCH | RESUMES | STORIES`), not separate top-level tabs.
- Frontend: new feature UI goes into **new files** under `ui/src/` — `App.jsx` (currently ~1382 lines, 100% inline styles, no split precedent) gets minimal wiring edits only.
- Marking an interview round's outcome as **Failed auto-sets `Job.status = REJECTED`**, mirroring the existing "key events auto-transition status" behavior (e.g. `OFFER_RECEIVED` → `OFFER`).
- Existing `data/cv_{direction}.txt` files are **auto-imported as v1 ResumeVersions on startup** (idempotent), so upgrading doesn't break the scoring pipeline.
- Alembic gets **properly set up** (baseline + this feature's migration) — it's already an unused dependency in `requirements.txt`; schema changes today rely entirely on `Base.metadata.create_all()`, which cannot alter existing tables (needed here to add `applications.resume_version_id`).

## Backend conventions to follow (verified in codebase)

- `server.py` is one flat file, DB imports inline per-handler, `with get_session() as session:` context manager (auto commit/rollback), `session.expunge(obj)` before any `await`ed LLM call so the detached object survives outside the session (pattern at server.py:954, 978, 1002).
- 404 → `HTTPException(404, "...")`, 400 → `HTTPException(400, "...")`. Typed Pydantic request bodies for the more structured endpoints (matches `TailorCVRequest` etc.).
- **No ORM cascade deletes anywhere** — every job-deletion site manually deletes child rows first (server.py:156-168 `DELETE /jobs/{id}`, server.py:752-799 `/run/purge-archived`). New `interviews`/`interview_questions` rows must be added to both sites.
- `llm/router.py` exposes `async def call_llm(user, system, max_tokens=1000, provider=None) -> tuple[str, str]` — reuse directly, don't reimplement provider routing.
- `llm/cv_tailor.py` is the template for any new LLM-calling module: system+user prompt construction, `raw[:N]` truncation, `call_llm(...)`, then fence-strip → regex-extract `{...}` → `json.loads` with a bracket-balance repair fallback. That JSON-repair idiom is currently duplicated in `analyzer/scorer.py:llm_score` (lines 311-345) — extract it into a shared helper (`llm/json_repair.py`) rather than copying it a third time.
- `db/models.py` — SQLAlchemy 2.x typed style (`Mapped[...]`), `str+PyEnum` classes stored via `Enum(FooEnum)` columns, `back_populates` relationship pairs. `db/__init__.py` only re-exports a subset of models (`Application, ApplicationStatus, Job, JobStatus, RawJob`) — new models don't need to be added there, just imported directly from `db.models` (matches how `JobEvent`/`CompanyInfo` are already handled).

## Frontend conventions to follow (verified in codebase)

- `ui/src/App.jsx`: top-level nav via `mainTab` state (`"board"|"tracker"`, rendered through a local `Tab` component) — add `"interviews"` as a third value.
- Job detail right panel: `rightTab` state (`detail|company|timeline|apply|tailor`) via `RTab`, flat hardcoded list of `<RTab id label/>` plus sibling `{rightTab==="x" && (...)}` blocks — add one more of each for `"interviews"`.
- Reuse metadata-lookup pattern (`STATUS_META`/`EVENT_META`, App.jsx:10-36) for new interview-type/outcome/format badges — don't invent a new theming approach.
- API base URL resolution (`window.__API_BASE_URL__ || import.meta.env.VITE_API_BASE_URL || "http://localhost:8765"`) currently inlined at App.jsx:6 — extract to `ui/src/api.js` so new files can import it instead of duplicating.
- `Timeline` component (App.jsx:236-327) is the template for any "list of records tied to a job, with an inline add-form" UI (interview rounds, questions) — self-contained fetch/state, refetch-after-write, no optimistic UI.
- TAILOR tab (App.jsx:654-667, 1255-1314) is the template for "click → LLM call → structured result → regenerate" (the AI-optimize-answer flow).
- No file-upload precedent exists anywhere (`type="file"`/`FormData` absent) — resume upload is genuinely new UI; no toast/alert component exists either — all async feedback goes through the existing `LogPane`/`addLog` mechanism.

---

## Progress

- [x] Phase 0 — Alembic + dependencies
- [ ] Phase 1 — DB schema
- [ ] Phase 2 — Core backend refactor
- [ ] Phase 3 — Resume version backend
- [ ] Phase 4 — Interview CRUD backend
- [ ] Phase 5 — Interview questions + AI-optimize backend
- [ ] Phase 6 — STAR story CRUD backend
- [ ] Phase 7 — Cross-job search + upcoming aggregation
- [ ] Phase 8 — Frontend scaffolding
- [ ] Phase 9 — InterviewsPage (upcoming + search + sub-nav)
- [ ] Phase 10 — JobInterviewsTab (rounds + retrospective + questions + AI-optimize)
- [ ] Phase 11 — Resume Versions UI
- [ ] Phase 12 — STAR Story Library UI
- [ ] Phase 13 — Verification pass

When starting a phase in a new session: mark it done here (`[x]`) only after its verification steps pass and the work is committed. Each phase should end with a git commit on `feature/interview-tracking` referencing the phase number/title, so later sessions can `git log`/`git diff` to see exactly what's landed instead of relying on this checklist alone.

### New-session prompt template

Paste this into a fresh session to work one phase at a time:

```
Repo: /mnt/d/projects/swiss-job-hunter, branch `feature/interview-tracking` (switch to it if not
already there — do not create a new branch).

Read docs/interview-tracking-plan.md in full — it's the implementation plan for a new interview-
management feature. First check the "Progress" checklist at the top of the file, then run
`git log --oneline -20` to confirm which phases are actually done and that the code matches the
checklist state.

Implement only the first unchecked `[ ]` phase in the Progress list (unless I specify a different
phase number in this message). Do not go ahead and implement later phases too, even if it seems
convenient. Strictly follow the "Backend conventions to follow" / "Frontend conventions to follow"
sections in the plan doc (they include concrete file:line references) — new code should look like
it already belongs in this repo, not like a different style bolted on.

When done:
1. Run that phase's verification steps (listed under the phase itself).
2. Commit the work on feature/interview-tracking with a message referencing "Phase N — <title>".
3. Edit docs/interview-tracking-plan.md and check off `[x] Phase N — <title>` in the Progress list.

If anything in the plan turns out to not match the actual code once you're deep in a phase, stop
and flag it rather than silently improvising around it — this plan was written without reading
every line of every affected file, so implementation-level details may be slightly off.
```

---

## Phase 0 — Alembic + dependencies

1. Add to `requirements.txt`: `pypdf>=4.2.0`, `python-docx>=1.1.0`, `python-multipart>=0.0.9` (required for FastAPI `UploadFile`/`Form`, currently absent). `alembic>=1.13.0` is already listed but unused.
2. `alembic init alembic`. In `alembic/env.py`: `target_metadata = Base.metadata` (from `db.models`), pull the DB URL from `config.settings.settings.database_url` instead of hardcoding, enable `render_as_batch=True` (SQLite-friendly for future column alters).
3. Baseline migration against an **empty throwaway DB** (so autogenerate emits full `CREATE TABLE`s instead of a no-op diff against the already-populated dev DB):
   ```bash
   DATABASE_URL=sqlite:///./data/_alembic_baseline_check.db alembic revision --autogenerate -m "baseline: existing schema"
   rm data/_alembic_baseline_check.db
   ```
4. Apply to the real dev DB without re-running SQL (tables already exist there): `alembic stamp head`.

## Phase 1 — DB schema (`db/models.py`)

New enums: `FileFormat` (pdf/docx/txt), `InterviewType` (phone_screen/technical/behavioral/onsite/final/other), `InterviewFormat` (video/phone/onsite), `InterviewOutcome` (pending/passed/failed/cancelled).

New tables:
- **`ResumeVersion`**: `direction` (nullable — `None` = the direction-less `data/cv.txt`), `label`, `original_filename`, `file_path`, `file_format`, `extracted_text`, `changelog`, `is_active`, `uploaded_at`. Index on `(direction, is_active)`. "Only one active per direction" enforced in the endpoint (deactivate siblings before activating), not a DB constraint.
- **`Interview`**: `job_id` FK, `round_number`, `interview_type`, `scheduled_at` (indexed), `interviewer_name`, `format`, `duration_minutes`, `prep_notes`, `outcome`, plus retrospective fields `self_rating` (1-5), `went_well`, `to_improve`, `notes`, timestamps. `back_populates` to `Job.interviews` (new relationship, ordered by `scheduled_at`) and to `InterviewQuestion.interview`. No `cascade=` kwarg — deletes are manual, matching repo convention.
- **`InterviewQuestion`**: `interview_id` FK, `question`, `my_answer`, `llm_feedback`, `optimized_answer`, `order_index` (avoid the reserved word `order`).
- **`StarStory`**: `title`, `tags` (comma-separated string), `situation`, `task`, `action`, `result`, timestamps. No relation to jobs/interviews.
- **`Application`**: add `resume_version_id` FK (nullable) + `resume_version` relationship.

Deleting a `ResumeVersion` that's `is_active` or referenced by an `Application` → 400, not silent null-out.

Feature migration:
```bash
alembic revision --autogenerate -m "add resume_versions, interviews, interview_questions, star_stories"
```
Review the generated file (should be 4 `CREATE TABLE` + 1 `ALTER TABLE applications ADD COLUMN resume_version_id`), then `alembic upgrade head`. This step is **not optional** for existing DBs — `create_all()` never alters existing tables, so skipping the migration leaves `resume_version_id` missing and any write to it errors at the DB layer.

## Phase 2 — Core backend refactor

- **`analyzer/scorer.py`**: rewrite `load_cv_text(direction=None)` to query the active `ResumeVersion` for that direction from the DB first; fall back to the legacy flat file (`data/cv_{direction}.txt` or `data/cv.txt`) if the DB hasn't been seeded yet (self-healing for CLI-only entry points, or a fresh test DB). Drop the unused `path=` param (grep confirms no caller passes it). `cli.py`'s no-direction call sites (`cli.py:179, 291`, both call `load_cv_text()` with `direction=None`) need no change — they'll resolve to the direction-less seeded version automatically.
- **New `db/seed.py`**: `seed_resume_versions_from_flat_files()` — idempotent; for `data/cv.txt` and every `data/cv_*.txt` (same glob server.py already uses at line 42 for direction auto-detection) with zero existing `ResumeVersion` rows for that direction, insert one as `label="v1"`, `is_active=True`.
- **`server.py`**: add `@app.on_event("startup")` calling `init_db()` then `seed_resume_versions_from_flat_files()`. Existing per-handler defensive `init_db()` calls stay as-is (harmless redundancy).
- **New `llm/json_repair.py`**: extract the fence-strip/brace-extract/bracket-repair idiom into `parse_llm_json(raw: str) -> dict`. Refactor `llm/cv_tailor.py:tailor_cv()` and `analyzer/scorer.py:llm_score()` to call it instead of each having their own copy.

## Phase 3 — Resume version backend

- **New `analyzer/resume_extract.py`**: `extract_text(file_bytes, file_format) -> str` using `pypdf.PdfReader` for PDF, `python-docx`'s `Document` (paragraphs + table cells) for DOCX, plain decode for TXT.
- **`server.py`** new endpoints: `GET /resume-versions?direction=`, `GET /resume-versions/{id}` (includes `extracted_text`, list endpoint omits it), `POST /resume-versions` (multipart upload: file + direction + label + changelog; derives `file_format` server-side from extension, not trusted from client; auto-activates if first version for that direction), `PATCH /resume-versions/{id}/activate` (deactivates siblings), `DELETE /resume-versions/{id}` (400 if active or referenced), `GET /resume-versions/{id}/download`. Files stored at `data/resumes/` (already covered by `.gitignore`'s blanket `data/` rule).

## Phase 4 — Interview CRUD backend

- **`server.py`**: `GET /jobs/{job_id}/interviews` (nested, includes questions — small volume, one fetch per tab-open like `Timeline`), `POST /jobs/{job_id}/interviews` (sets `job.status = INTERVIEWING` unconditionally, mirroring the existing `STATUS_MAP` pattern at server.py:1119-1134), `PATCH /interviews/{id}` (outcome → `failed` also sets `job.status = REJECTED`, per confirmed decision), `DELETE /interviews/{id}` (manually deletes its `InterviewQuestion` rows first).
- Update both existing cascade-delete sites (`DELETE /jobs/{job_id}` at server.py:156-168, `/run/purge-archived` at server.py:752-799) to also delete `InterviewQuestion` then `Interview` rows for the job before the job itself.

## Phase 5 — Interview questions + AI-optimize backend

- **New `llm/interview_coach.py`**: `optimize_answer(question, my_answer, stories: list[StarStory]) -> dict` — formats the full STAR library into the prompt, asks for JSON `{critique, optimized_answer, stories_used}`, uses `call_llm` + the new `parse_llm_json` helper. Mirrors `cv_tailor.py`'s structure exactly.
- **`server.py`**: `POST /interviews/{id}/questions`, `PATCH /interview-questions/{id}`, `DELETE /interview-questions/{id}`, and `POST /interview-questions/{id}/optimize-answer` — fetch question + all `StarStory` rows, `session.expunge()` both before the `await optimize_answer(...)` call (per the established detached-object pattern), then re-open a session to persist `llm_feedback`/`optimized_answer` back onto the question. Synchronous request/response, no SSE (matches `/run/tailor-cv`).

## Phase 6 — STAR story CRUD backend

- **`server.py`**: plain `GET/POST/PATCH/DELETE /star-stories` — no relation to jobs/interviews, no cascade concerns, simplest block in the feature.

## Phase 7 — Cross-job search + upcoming aggregation

- **`server.py`**: `GET /interview-questions/search?q=` (SQL `ILIKE` over `question`/`my_answer`, joined to `Interview`+`Job` for context, capped at 100 results). `GET /interviews/upcoming?include_past=false` (all interviews joined to jobs, sorted `scheduled_at` ascending with nulls last — mirrors how `GET /tracker` already aggregates `Job`+`Application`). `GET /jobs/{job_id}` (new — no single-job getter exists today; needed so "click a search/upcoming result" can resolve a full job record without refetching the whole list).

## Phase 8 — Frontend scaffolding

- **New `ui/src/api.js`**: extract the `API` base-URL constant; `App.jsx` line 6 becomes a one-line import.
- **New `ui/src/interviewMeta.js`**: `INTERVIEW_TYPE_META`/`INTERVIEW_OUTCOME_META`/`INTERVIEW_FORMAT_META`, same shape as existing `STATUS_META`/`EVENT_META`.
- **`App.jsx`** wiring: add `"interviews"` to the `mainTab` value set + header `Tab`; body-render branch dispatches to a new `InterviewsPage` component when `mainTab==="interviews"`; add a `selectJobById(id)` helper (fetches `GET /jobs/{id}`, sets `selected`, flips `mainTab` back to `"board"` and `rightTab` to `"interviews"` — used by click-through from search/upcoming results); add the `INTERVIEWS` `RTab` + its conditional content block delegating to a new `JobInterviewsTab` component.

## Phase 9 — `InterviewsPage` (upcoming + search + sub-nav)

- **New `ui/src/InterviewsPage.jsx`**: owns `interviewSubTab` state (`upcoming|search|resumes|stories`), local sub-tab row, dispatches to the four components below.
- **New `ui/src/UpcomingInterviews.jsx`**: fetches `GET /interviews/upcoming` on mount, flat list sorted by `scheduled_at`, badges via `interviewMeta.js`, click → `onSelectJob`.
- **New `ui/src/QuestionSearch.jsx`**: search input + explicit search button (no debounce, matches app's existing non-debounced style) hitting `GET /interview-questions/search`, results show question/answer snippet + job/company + click-through.

## Phase 10 — `JobInterviewsTab` (rounds + retrospective + questions + AI-optimize)

Largest UI chunk. **New `ui/src/JobInterviewsTab.jsx`**:
- Self-contained fetch of `GET /jobs/{jobId}/interviews` (refetch-after-write, modeled on `Timeline`).
- "+ ADD ROUND" collapsible form: type/format pill-pickers, scheduled-at, interviewer, duration, prep notes.
- Each round is an expandable card: retrospective fields (self-rating via the existing `Stars` component pattern, went_well/to_improve/notes textareas, outcome picker) saved via `PATCH /interviews/{id}`; nested question list, each with editable question/answer, an "AI 优化" button calling `POST /interview-questions/{id}/optimize-answer` (loading state keyed by question id, styled like TAILOR tab's suggestion cards once results land), and an "+ ADD QUESTION" mini-form.
- Creating/updating a round must trigger the same `fetchJobs()`/`fetchStats()` refresh `Timeline`'s `onRefresh` prop already triggers, so the job's status badge updates live on BOARD/TRACKER.

## Phase 11 — Resume Versions UI

**New `ui/src/ResumeVersions.jsx`**: direction picker (reuse `GET /directions`), version list with ACTIVATE/DELETE/DOWNLOAD, and an upload form (`<input type="file" accept=".pdf,.docx,.txt">` + label + changelog → `FormData` → `POST /resume-versions`). No upload precedent exists in this app — style it consistent with the existing bordered-button/monospace look. Feedback via `addLog`/`LogPane` only.

## Phase 12 — STAR Story Library UI

**New `ui/src/StarStoryLibrary.jsx`**: card grid, collapsed by default, expand → S/T/A/R textareas, "+ NEW STORY", plain CRUD against `/star-stories`.

## Phase 13 — Verification pass

`tests/` today is lightweight unit coverage only (dedup logic, settings parsing) — no DB-integration/API tests. Add small, cheap tests matching that style:
- A couple of `load_cv_text()` fallback-ordering tests (now the most load-bearing refactor, touched by 6+ call sites).
- Table-driven tests for `parse_llm_json` (fenced/unfenced/truncated JSON), since it's now shared by 3 modules.

Manual smoke-test checklist:
1. Fresh-DB simulation: delete `data/jobs.db*`, `alembic upgrade head`, start server → tables exist, `cv*.txt` auto-seed into `resume_versions` on first request.
2. Existing-DB simulation: keep current `data/jobs.db`, `alembic stamp head` then `alembic upgrade head` → no data loss, `applications.resume_version_id` present and NULL on old rows.
3. Full click-through: BOARD → job → INTERVIEWS tab → add round → add question → AI-optimize → status badge updates → TRACKER reflects it.
4. INTERVIEWS top tab: UPCOMING shows it, click-through works, SEARCH finds the question, RESUMES upload+activate reflected in a subsequent TAILOR CV call, STORIES entry gets referenced by a later optimize-answer call.
5. Delete a job with interviews attached → no orphaned `interview`/`interview_questions` rows, no FK error.
6. `pytest tests/` stays green throughout.

---

## Critical files
- `db/models.py`, `db/session.py`, `db/seed.py` (new)
- `server.py`
- `analyzer/scorer.py`, `analyzer/resume_extract.py` (new)
- `llm/cv_tailor.py`, `llm/interview_coach.py` (new), `llm/json_repair.py` (new)
- `requirements.txt`, `alembic.ini`/`alembic/` (new)
- `ui/src/App.jsx`, `ui/src/api.js` (new), `ui/src/interviewMeta.js` (new), `ui/src/InterviewsPage.jsx` (new), `ui/src/JobInterviewsTab.jsx` (new), `ui/src/ResumeVersions.jsx` (new), `ui/src/StarStoryLibrary.jsx` (new), `ui/src/UpcomingInterviews.jsx` (new), `ui/src/QuestionSearch.jsx` (new)
