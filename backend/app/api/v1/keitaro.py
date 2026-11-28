from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.keitaro_sync import KeitaroSyncService

from app.api.dependencies import get_keitaro_client
from app.integrations.keitaro.client import KeitaroClient
from app.integrations.keitaro.exceptions import (
    KeitaroAPIError,
    KeitaroConfigurationError,
    KeitaroConnectionError,
    KeitaroInvalidResponseError,
    KeitaroTimeoutError,
)


router = APIRouter(
    prefix="/keitaro",
    tags=["Keitaro"],
)


async def execute_request(operation):
    try:
        return await operation()

    except KeitaroConfigurationError:
        raise HTTPException(
            status_code=503,
            detail="Keitaro integration is not configured",
        )

    except KeitaroTimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Keitaro API request timed out",
        )

    except KeitaroConnectionError:
        raise HTTPException(
            status_code=502,
            detail="Cannot connect to Keitaro API",
        )

    except KeitaroAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Keitaro API returned HTTP {exc.status_code}",
        )

    except KeitaroInvalidResponseError:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from Keitaro API",
        )


@router.get("/campaigns")
async def get_campaigns(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    return await execute_request(
        lambda: client.get_campaigns(offset, limit)
    )


@router.get("/offers")
async def get_offers(
    client: KeitaroClient = Depends(get_keitaro_client),
):
    return await execute_request(client.get_offers)


@router.get("/domains")
async def get_domains(
    client: KeitaroClient = Depends(get_keitaro_client),
):
    return await execute_request(client.get_domains)


@router.get("/groups")
async def get_groups(
    client: KeitaroClient = Depends(get_keitaro_client),
):
    return await execute_request(client.get_groups)


@router.get("/traffic-sources")
async def get_traffic_sources(
    client: KeitaroClient = Depends(get_keitaro_client),
):
    return await execute_request(client.get_traffic_sources)


@router.post("/sync")
async def sync_keitaro(
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = KeitaroSyncService(db, client)
    return await execute_request(service.sync)
