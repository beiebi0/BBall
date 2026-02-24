from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, videos, jobs, highlights
from app.config import settings

app = FastAPI(title="BBall Highlight Generator", version="0.1.0")

cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(videos.router, prefix="/videos", tags=["videos"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(highlights.router, prefix="/highlights", tags=["highlights"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
