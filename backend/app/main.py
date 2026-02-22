from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, videos, jobs, highlights

app = FastAPI(title="BBall Highlight Generator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
