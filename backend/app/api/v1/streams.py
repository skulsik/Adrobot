import inspect
from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.schemas.stream import OfferAdd, OfferUpdate
from app.services.offer_editor import (
    OfferEditorService,
    OfferEditorError,
)


router = APIRouter(tags=["Streams"])


async def execute(operation):
    try:
        result = operation()
        if inspect.isawaitable(result):
            return await result
        return result

    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    except (ValueError, OfferEditorError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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


@router.get("/campaigns/{campaign_id}/streams")
async def list_campaign_streams(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)
    return await execute(
        lambda: service.list_campaign_streams(campaign_id)
    )


@router.get("/streams/{stream_id}")
async def get_stream(
    stream_id: int,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)

    def operation():
        stream = service.get_stream(stream_id)
        return service.serialize_stream(stream)

    return await execute(operation)


@router.post("/streams/{stream_id}/refresh")
async def refresh_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = OfferEditorService(db, client)
    return await execute(
        lambda: service.refresh_stream(stream_id)
    )


@router.get("/streams/{stream_id}/offers/catalog")
async def offer_catalog(
    stream_id: int,
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = OfferEditorService(db, client)

    async def operation():
        service.get_stream(stream_id)
        from app.services.keitaro_sync import as_list

        catalog = as_list(await client.get_offers())

        existing = {
            offer.keitaro_offer_id
            for offer in service.get_offers(stream_id)
            if not offer.is_deleted
        }

        query = (q or "").strip().lower()

        result = []

        for item in catalog:
            offer_id = int(item["id"])

            if offer_id in existing:
                continue

            if query:
                searchable = " ".join([
                    str(item.get("name", "")),
                    str(item.get("url", "")),
                    str(offer_id),
                ]).lower()

                if query not in searchable:
                    continue

            result.append({
                "id": offer_id,
                "name": item.get("name") or f"Offer {offer_id}",
                "url": item.get("url"),
            })

        return result

    return await execute(operation)


@router.post("/streams/{stream_id}/offers")
async def add_offer(
    stream_id: int,
    data: OfferAdd,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = OfferEditorService(db, client)

    return await execute(
        lambda: service.add_offer_with_catalog(
            stream_id,
            data.offer_id,
        )
    )


@router.patch("/streams/{stream_id}/offers/{offer_id}")
async def update_offer(
    stream_id: int,
    offer_id: int,
    data: OfferUpdate,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)

    return await execute(
        lambda: service.update_offer(
            stream_id,
            offer_id,
            share=data.share,
            is_fixed=data.is_fixed,
        )
    )


@router.delete("/streams/{stream_id}/offers/{offer_id}")
async def delete_offer(
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)
    return await execute(
        lambda: service.delete_offer(stream_id, offer_id)
    )


@router.post("/streams/{stream_id}/offers/{offer_id}/restore")
async def restore_offer(
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)
    return await execute(
        lambda: service.restore_offer(stream_id, offer_id)
    )


@router.post("/streams/{stream_id}/apply")
async def apply_stream(
    stream_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
):
    service = OfferEditorService(db, client)

    return await execute(
        lambda: service.apply(stream_id)
    )


@router.post("/streams/{stream_id}/discard")
async def discard_stream(
    stream_id: int,
    db: Session = Depends(get_db),
):
    service = OfferEditorService(db, None)
    return await execute(
        lambda: service.discard(stream_id)
    )
