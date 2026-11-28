from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import get_db
from app.api.v1.keitaro import router as keitaro_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.streams import router as streams_router
from app.integrations.keitaro.client import KeitaroClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = KeitaroClient(
        base_url=settings.keitaro_base_url,
        api_key=settings.keitaro_api_key,
        timeout=settings.keitaro_timeout,
    )

    app.state.keitaro_client = client

    yield

    await client.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Advertising campaign management system",
    lifespan=lifespan,
)

app.include_router(
    keitaro_router,
    prefix="/api/v1",
)


app.include_router(
    campaigns_router,
    prefix="/api/v1",
)


app.include_router(
    streams_router,
    prefix="/api/v1",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "adrobot-backend",
    }


@app.get("/api/v1/health")
def api_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )
