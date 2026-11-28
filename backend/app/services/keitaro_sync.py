from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Stream, StreamOffer, SyncLog


PAGE_SIZE = 100


def as_list(payload: Any) -> list:
    """Приводит ответ API к списку объектов."""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "items", "campaigns", "offers", "streams"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

    raise ValueError("Unexpected list response from Keitaro")


def safe_payload(value: Any) -> Any:
    """Удаляет чувствительные поля перед сохранением JSON."""
    if isinstance(value, dict):
        return {
            key: safe_payload(item)
            for key, item in value.items()
            if key.lower() not in {
                "token",
                "api_key",
                "password",
                "secret",
            }
        }

    if isinstance(value, list):
        return [safe_payload(item) for item in value]

    return value


def decimal_value(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


class KeitaroSyncService:
    def __init__(self, db: Session, client):
        self.db = db
        self.client = client

    async def fetch_all_campaigns(self) -> list[dict]:
        """Загружает все кампании с учётом пагинации."""
        result = []
        offset = 0

        while True:
            page = as_list(
                await self.client.get_campaigns(
                    offset=offset,
                    limit=PAGE_SIZE,
                )
            )

            result.extend(page)

            if len(page) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        return result

    async def sync(self) -> dict:
        started_at = datetime.now(timezone.utc)

        counters = {
            "campaigns_created": 0,
            "campaigns_updated": 0,
            "streams_created": 0,
            "streams_updated": 0,
            "offers_created": 0,
            "offers_updated": 0,
        }

        failures = []

        try:
            remote_campaigns = await self.fetch_all_campaigns()
        except Exception as exc:
            self.db.rollback()
            self.db.add(
                SyncLog(
                    action="keitaro_sync",
                    status="error",
                    error_message=str(exc)[:4000],
                )
            )
            self.db.commit()
            raise

        # Справочник нужен для получения названий офферов.
        offer_catalog = {}

        try:
            remote_offers = as_list(await self.client.get_offers())

            offer_catalog = {
                int(offer["id"]): offer
                for offer in remote_offers
                if offer.get("id") is not None
            }
        except Exception as exc:
            failures.append({
                "type": "offer_catalog",
                "error": str(exc)[:1000],
            })

        seen_campaign_ids = set()
        successfully_synced_campaign_ids = set()

        for remote_campaign in remote_campaigns:
            try:
                keitaro_id = int(remote_campaign["id"])
                seen_campaign_ids.add(keitaro_id)

                remote_streams = as_list(
                    await self.client.get_campaign_streams(keitaro_id)
                )

                self.sync_campaign(
                    remote_campaign,
                    remote_streams,
                    offer_catalog,
                    counters,
                )

                successfully_synced_campaign_ids.add(keitaro_id)

            except Exception as exc:
                self.db.rollback()

                failures.append({
                    "campaign_id": remote_campaign.get("id"),
                    "error": str(exc)[:1000],
                })

                local_campaign = self.db.scalar(
                    select(Campaign).where(
                        Campaign.keitaro_id == remote_campaign.get("id")
                    )
                )

                self.db.add(
                    SyncLog(
                        campaign_id=(
                            local_campaign.id if local_campaign else None
                        ),
                        action="campaign_sync",
                        status="error",
                        error_message=str(exc)[:4000],
                    )
                )
                self.db.commit()

        # Кампании, отсутствующие в полном ответе Keitaro,
        # не удаляем — только отмечаем отсутствие.
        local_campaigns = self.db.scalars(
            select(Campaign)
        ).all()

        for campaign in local_campaigns:
            if campaign.keitaro_id not in seen_campaign_ids:
                campaign.is_present_in_keitaro = False

                for stream in campaign.streams:
                    stream.is_present_in_keitaro = False

                    for offer in stream.offers:
                        offer.is_present_in_keitaro = False

        self.db.commit()

        status = "success" if not failures else "partial"

        summary = {
            **counters,
            "campaigns_received": len(remote_campaigns),
            "campaigns_synced": len(successfully_synced_campaign_ids),
            "failures": failures,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }

        self.db.add(
            SyncLog(
                action="keitaro_sync",
                status=status,
                response_payload=summary,
            )
        )
        self.db.commit()

        return {
            "status": status,
            **summary,
        }

    def sync_campaign(
        self,
        remote: dict,
        remote_streams: list,
        offer_catalog: dict,
        counters: dict,
    ) -> None:
        now = datetime.now(timezone.utc)
        keitaro_id = int(remote["id"])

        campaign = self.db.scalar(
            select(Campaign).where(
                Campaign.keitaro_id == keitaro_id
            )
        )

        if campaign is None:
            campaign = Campaign(
                keitaro_id=keitaro_id,
                name=remote.get("name") or f"Campaign {keitaro_id}",
            )
            self.db.add(campaign)
            self.db.flush()
            counters["campaigns_created"] += 1
        else:
            counters["campaigns_updated"] += 1

        campaign.name = remote.get("name") or campaign.name
        campaign.alias = remote.get("alias")
        campaign.state = remote.get("state")
        campaign.domain_id = remote.get("domain_id")
        campaign.group_id = remote.get("group_id")
        campaign.traffic_source_id = remote.get("traffic_source_id")
        campaign.raw_payload = safe_payload(remote)
        campaign.is_present_in_keitaro = True
        campaign.synced_at = now

        existing_streams = {
            stream.keitaro_id: stream
            for stream in self.db.scalars(
                select(Stream).where(
                    Stream.campaign_id == campaign.id
                )
            ).all()
        }

        seen_stream_ids = set()

        for position, remote_stream in enumerate(remote_streams):
            stream_id = int(remote_stream["id"])
            seen_stream_ids.add(stream_id)

            stream = existing_streams.get(stream_id)

            if stream is None:
                stream = Stream(
                    keitaro_id=stream_id,
                    campaign_id=campaign.id,
                    name=remote_stream.get("name") or f"Stream {stream_id}",
                )
                self.db.add(stream)
                self.db.flush()
                counters["streams_created"] += 1
            else:
                counters["streams_updated"] += 1

            stream.name = (
                remote_stream.get("name")
                or stream.name
            )
            stream.type = remote_stream.get("type")
            stream.stream_schema = remote_stream.get("schema")
            stream.action_type = remote_stream.get("action_type")
            stream.action_payload = remote_stream.get("action_payload")
            stream.filters = remote_stream.get("filters") or []
            stream.position = remote_stream.get("position", position)
            stream.enabled = remote_stream.get("state") == "active"
            stream.raw_payload = safe_payload(remote_stream)
            stream.is_present_in_keitaro = True
            stream.synced_at = now

            self.sync_stream_offers(
                stream,
                remote_stream.get("offers") or [],
                offer_catalog,
                counters,
            )

        # Потоки, которых больше нет в Keitaro.
        for stream_id, stream in existing_streams.items():
            if stream_id not in seen_stream_ids:
                stream.is_present_in_keitaro = False

                for offer in stream.offers:
                    offer.is_present_in_keitaro = False

        self.db.add(
            SyncLog(
                campaign_id=campaign.id,
                action="campaign_sync",
                status="success",
                response_payload={
                    "keitaro_id": keitaro_id,
                    "streams_received": len(remote_streams),
                },
            )
        )

        self.db.commit()

    def sync_stream_offers(
        self,
        stream: Stream,
        remote_offers: list,
        offer_catalog: dict,
        counters: dict,
    ) -> None:
        existing_offers = {
            offer.keitaro_offer_id: offer
            for offer in self.db.scalars(
                select(StreamOffer).where(
                    StreamOffer.stream_id == stream.id
                )
            ).all()
        }

        seen_offer_ids = set()

        for position, remote_offer in enumerate(remote_offers):
            offer_id = int(remote_offer["offer_id"])
            seen_offer_ids.add(offer_id)

            catalog_offer = offer_catalog.get(offer_id, {})
            existing = existing_offers.get(offer_id)

            remote_share = decimal_value(
                remote_offer.get("share")
            )

            name = (
                catalog_offer.get("name")
                or (
                    existing.name
                    if existing is not None
                    else f"Offer {offer_id}"
                )
            )

            if existing is None:
                existing = StreamOffer(
                    stream_id=stream.id,
                    keitaro_offer_id=offer_id,
                    name=name,
                    share=remote_share,
                    remote_share=remote_share,
                    synced_share=remote_share,
                    is_fixed=False,
                    is_deleted=False,
                    synced_is_fixed=False,
                    synced_is_deleted=False,
                    is_present_in_keitaro=True,
                )
                self.db.add(existing)
                counters["offers_created"] += 1
            else:
                # Локальный share, is_fixed и is_deleted сохраняем.
                counters["offers_updated"] += 1
                existing.name = name

            existing.remote_share = remote_share
            existing.remote_state = remote_offer.get("state")
            existing.is_present_in_keitaro = True
            existing.position = position

            if catalog_offer.get("url"):
                existing.url = catalog_offer["url"]

            existing.raw_payload = safe_payload(remote_offer)

        # Не удаляем отсутствующие офферы, а отмечаем их отсутствие.
        for offer_id, offer in existing_offers.items():
            if offer_id not in seen_offer_ids:
                offer.is_present_in_keitaro = False
