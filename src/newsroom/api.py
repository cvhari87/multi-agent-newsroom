"""FastAPI backend — exposes the newsroom pipeline and story data."""

import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from newsroom import db, orchestrator
from newsroom.console import configure_console

load_dotenv()
configure_console()

# Track in-flight runs so we don't launch duplicates
_active_lock = threading.Lock()
_active_run: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Clean up orphaned runs on startup (e.g. after --reload kills a thread)."""
    cleaned = db.cleanup_orphaned_runs()
    if cleaned:
        print(f"[!] Cleaned up {cleaned} orphaned run(s) from previous server instance")
    yield


app = FastAPI(title="Multi-Agent Newsroom", version="0.1.0", lifespan=lifespan)

# Allow the Vite dev server and production build to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_in_background(run_id: str) -> None:
    """Execute the pipeline; update global state when done."""
    global _active_run
    try:
        orchestrator._run_pipeline(run_id)
    except orchestrator.RunCancelledError:
        pass  # already marked cancelled in DB
    except Exception as exc:
        db.fail_run(run_id, f"{type(exc).__name__}: {exc}")
    finally:
        with _active_lock:
            _active_run = None


# ------------------------------------------------------------------
# POST /api/run — trigger a new pipeline run
# ------------------------------------------------------------------
@app.post("/api/run", status_code=202)
def trigger_run(background_tasks: BackgroundTasks) -> dict:
    global _active_run
    with _active_lock:
        if _active_run is not None:
            return {"run_id": _active_run, "status": "already_running"}
        import uuid

        run_id = str(uuid.uuid4())
        db.create_run(run_id)
        _active_run = run_id

    background_tasks.add_task(_run_in_background, run_id)
    return {"run_id": run_id, "status": "running"}


# ------------------------------------------------------------------
# POST /api/run/{run_id}/cancel — cancel a running pipeline
# ------------------------------------------------------------------
@app.post("/api/run/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    global _active_run
    cancelled = db.cancel_run(run_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run not found or not running")
    # Clear the active run lock so a new run can start
    with _active_lock:
        if _active_run == run_id:
            _active_run = None
    return {"run_id": run_id, "status": "cancelled"}


# ------------------------------------------------------------------
# GET /api/runs — list all runs, newest first
# ------------------------------------------------------------------
@app.get("/api/runs")
def get_runs() -> dict:
    return {"runs": db.list_runs()}


# ------------------------------------------------------------------
# GET /api/stories — stories from the latest completed run
# ------------------------------------------------------------------
@app.get("/api/stories")
def get_stories(tag: str | None = None, run_id: str | None = None) -> dict:
    return {"stories": db.list_stories(run_id=run_id, tag=tag)}


# ------------------------------------------------------------------
# GET /api/stories/{story_id} — full story detail
# ------------------------------------------------------------------
@app.get("/api/stories/{story_id}")
def get_story(story_id: str) -> dict:
    story = db.get_story(story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


# ------------------------------------------------------------------
# Serve frontend static files in production
# ------------------------------------------------------------------
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
