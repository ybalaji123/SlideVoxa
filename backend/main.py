import os
import sys

# Global fix for Windows encoding issues in console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import presentations, auth

app = FastAPI(
    title="SlideVoxa API",
    description="AI-powered presentation narration engine",
    version="1.0.0",
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    # Cache static resources for a day to improve website loading speed
    if request.url.path.startswith(("/static", "/uploads")):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response

# Include routers
app.include_router(presentations.router)
app.include_router(auth.router)

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")
app.mount("/pages", StaticFiles(directory=os.path.join(frontend_path, "pages")), name="pages")

# Serve audio files from uploads
uploads_path = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")


@app.get("/")
def serve_landing():
    return FileResponse(os.path.join(frontend_path, "index.html"))


@app.get("/login")
def serve_login():
    return FileResponse(os.path.join(frontend_path, "pages", "login.html"))


@app.get("/dashboard")
def serve_dashboard():
    return FileResponse(os.path.join(frontend_path, "pages", "dashboard.html"))


@app.get("/upload")
def serve_upload():
    return FileResponse(os.path.join(frontend_path, "pages", "upload.html"))


@app.get("/present")
@app.get("/present/{presentation_id}")
def serve_present(presentation_id: str | None = None):
    return FileResponse(os.path.join(frontend_path, "pages", "present.html"))


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "SlideVoxa API"}
