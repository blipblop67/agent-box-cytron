from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, scheduler
from .routes import router
from .auth_routes import router as auth_router
from .gmail_routes import router as gmail_router
from .drive_routes import router as drive_router
from .flow_routes import router as flow_router
from .settings_routes import router as settings_router
from .schedule_routes import router as schedule_router
from .template_routes import router as template_router
from .telegram_routes import router as telegram_router
from .update_routes import router as update_router
from .account_routes import router as account_router
from .conversation_routes import router as conversation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Agent Hub", version="0.1.0", lifespan=lifespan)

# The flow builder UI is served from this same process, reachable over the LAN
# from any device - keep CORS open on the local network rather than trying to
# guess every device's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")
app.include_router(gmail_router, prefix="/api")
app.include_router(drive_router, prefix="/api")
app.include_router(flow_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(schedule_router, prefix="/api")
app.include_router(template_router, prefix="/api")
app.include_router(telegram_router, prefix="/api")
app.include_router(update_router, prefix="/api")
app.include_router(account_router, prefix="/api")
app.include_router(conversation_router, prefix="/api")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Serve the built frontend (see frontend/README.md - `npm run build`, then copy
# frontend/dist here) as a single-page app: any path that isn't a real static
# asset falls back to index.html so client-side routing (/flows, /flows/:id,
# ...) works on a hard refresh, not just in-app navigation. Registered last so
# it never shadows the /api routes above.
FRONTEND_DIST = Path(__file__).parent / "static"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
