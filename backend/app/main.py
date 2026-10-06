"""
FastAPI application entrypoint.
Run with: uvicorn app.main:app --reload
"""
import faulthandler
import logging
import signal

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import assignments, auth, dashboard, internet_sources, reports, submissions
from app.config import settings
from app.core.logging import Timer, configure_logging, new_request_id, request_id_ctx

configure_logging()  # must run before any other module logs anything
logger = logging.getLogger("app")

# Diagnostic-only: lets us get a live stack trace of every thread on demand
# (`docker compose exec backend kill -USR1 <pid>`) without restarting or
# instrumenting the process ahead of time. Dumps to stderr, which `docker
# compose logs` captures. This is how we're pinning down exactly which line
# a hung upload request is actually stuck on, instead of guessing at causes
# that keep turning out to not be it.
faulthandler.register(signal.SIGUSR1, all_threads=True)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered plagiarism & similarity checker for college assignments.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Assigns every request a short id (also echoed back as the
    `X-Request-ID` response header, so a frontend error report or a support
    ticket can be matched to the exact server-side log lines), and logs one
    line per request: method, path, status, duration. Request bodies are
    never logged — uploads and passwords pass through this middleware.
    """
    req_id = request.headers.get("x-request-id", new_request_id())
    token = request_id_ctx.set(req_id)
    try:
        with Timer() as t:
            response = await call_next(request)
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": t.elapsed_ms,
            },
        )
        response.headers["X-Request-ID"] = req_id
        return response
    except Exception:
        logger.exception(
            "request_failed",
            extra={"method": request.method, "path": request.url.path},
        )
        raise
    finally:
        request_id_ctx.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Last-resort handler: turns an unexpected exception into a clean 500 JSON
    body (instead of an HTML traceback page) and guarantees it's logged with
    its request id, even if no route-level handler caught it.
    """
    logger.error("unhandled_exception", exc_info=exc, extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again or contact support."},
    )

app.include_router(auth.router)
app.include_router(assignments.router)
app.include_router(submissions.router)
app.include_router(reports.router)
app.include_router(internet_sources.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def warm_up_native_libraries():
    """
    Forces the embedding model and both FAISS indexes to fully initialize
    right now, on the main thread, during startup — before any real request
    can reach them from a worker thread.

    Why this matters: native libraries like FAISS (OpenMP/BLAS) and PyTorch
    do lazy, one-time internal setup (spinning up their own native thread
    pools) the first time they're actually used, not at import time. That
    one-time setup is documented to be able to deadlock the native runtime
    itself if it happens to run on a thread OTHER than the process's main
    thread — and FastAPI runs sync routes (like the upload endpoint) in a
    worker thread, never the main thread. That mismatch is what was causing
    every upload to hang forever inside vector_index.get_index(), with
    nothing to catch or log, even with a guaranteed-fresh, uncorrupted FAISS
    index file. Note this is a plain `def`, not `async def` — FastAPI runs
    sync startup handlers to completion, on the main thread, before serving
    any requests, which is exactly the property we need here.

    By doing this exact same work once, here, on the main thread, all of
    that lazy native init is already done by the time a worker thread first
    calls get_model()/get_index() for a real request — it just reuses the
    already-initialized state instead of triggering first-time init from an
    unsafe thread.
    """
    from app.services import vector_index, vector_index_sources
    from app.services.embeddings import get_model

    logger.info("warming_up_native_libraries")
    get_model()
    vector_index.get_index()
    vector_index_sources.get_index()
    logger.info("native_libraries_warmed_up")
    cleanup_interrupted_submissions()


def cleanup_interrupted_submissions(db=None):
    """Marks any submissions interrupted during extraction or embedding as FAILED on startup."""
    from app.database import SessionLocal
    from app.models.submission import Submission, SubmissionStatus

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        interrupted = (
            db.query(Submission)
            .filter(Submission.status.in_([SubmissionStatus.EXTRACTING, SubmissionStatus.EMBEDDING]))
            .all()
        )
        for sub in interrupted:
            sub.status = SubmissionStatus.FAILED
            sub.error_message = "Server restarted while processing. Please retry."
        if interrupted:
            db.commit()
            logger.info("cleaned_up_interrupted_submissions", extra={"count": len(interrupted)})
    finally:
        if close_db:
            db.close()


@app.get("/api/health", tags=["system"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}
