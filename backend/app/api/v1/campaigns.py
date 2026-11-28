from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_keitaro_client
from app.integrations.keitaro.client import KeitaroClient
from app.integrations.keitaro.exceptions import (
    KeitaroAPIError,
    KeitaroConfigurationError,
    KeitaroConnectionError,
    KeitaroInvalidResponseError,
    KeitaroTimeoutError,
)
from app.schemas.campaign import (
    CampaignCreate,
    CampaignUpdate,
)
from app.services.campaign_service import CampaignService


router = APIRouter(
    prefix="/campaigns",
    tags=["Campaigns"],
)


async def execute(operation):
    try:
        return await operation()

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

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


@router.get("")
def list_campaigns(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return CampaignService(db, None).get_list(offset, limit)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.create(data.model_dump())
    )


@router.post("/{campaign_id}/complete")
async def complete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.complete(campaign_id)
    )


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    try:
        return CampaignService(db, None).get(campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.update(
            campaign_id,
            data.model_dump(exclude_unset=True),
        )
    )


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.delete(campaign_id)
    )


@router.post("/{campaign_id}/enable")
async def enable_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.set_enabled(campaign_id, True)
    )


@router.post("/{campaign_id}/disable")
async def disable_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = CampaignService(db, client)

    return await execute(
        lambda: service.set_enabled(campaign_id, False)
    )
