from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.models import Campaign, Stream, StreamOffer, SyncLog
from app.services.keitaro_sync import as_list, safe_payload


class CampaignService:
    def __init__(self, db: Session, client):
        self.db = db
        self.client = client

    @staticmethod
    def extract_id(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None

        if payload.get("id") is not None:
            return int(payload["id"])

        data = payload.get("data")
        if isinstance(data, dict) and data.get("id") is not None:
            return int(data["id"])

        return None

    async def create(self, data: dict) -> dict:
        now = datetime.now(timezone.utc)

        remote_payload = {
            "name": data["name"],
        }

        if data.get("alias"):
            remote_payload["alias"] = data["alias"]

        remote = await self.client.create_campaign(remote_payload)
        keitaro_id = self.extract_id(remote)

        if keitaro_id is None:
            raise ValueError(
                "Keitaro created a campaign but did not return its ID"
            )

        campaign = Campaign(
            keitaro_id=keitaro_id,
            name=data["name"],
            alias=data.get("alias"),
            state=(
                remote.get("state")
                if isinstance(remote, dict)
                else None
            ),
            domain_id=data["domain_id"],
            group_id=data["group_id"],
            traffic_source_id=data["traffic_source_id"],
            raw_payload=safe_payload(
                remote if isinstance(remote, dict) else {}
            ),
            is_present_in_keitaro=True,
            synced_at=now,
        )

        self.db.add(campaign)
        self.db.flush()

        # Сохраняем исходные параметры, чтобы можно было безопасно
        # повторить создание потоков после частичного сбоя.
        self.db.add(
            SyncLog(
                campaign_id=campaign.id,
                action="campaign_create",
                status="pending",
                request_payload=data,
                response_payload={
                    "keitaro_campaign_id": keitaro_id,
                    "remote_campaign": safe_payload(
                        remote if isinstance(remote, dict) else {}
                    ),
                },
            )
        )

        self.db.commit()
        self.db.refresh(campaign)

        return await self.complete(campaign.id)

    async def complete(self, campaign_id: int) -> dict:
        campaign = self.db.scalar(
            select(Campaign).where(Campaign.id == campaign_id)
        )

        if campaign is None:
            raise LookupError("Campaign not found")

        log = self.db.scalar(
            select(SyncLog)
            .where(
                SyncLog.campaign_id == campaign.id,
                SyncLog.action == "campaign_create",
            )
            .order_by(desc(SyncLog.id))
        )

        if log is None:
            raise ValueError("Campaign creation data was not found")

        if log.status == "success":
            return {
                "status": "success",
                "campaign": campaign,
                "streams": {
                    "geo": "already_created",
                    "offers": "already_created",
                },
                "message": "Campaign is already completed",
            }

        data = log.request_payload or {}

        geo_name = f"ADROBOT_GEO_{campaign.keitaro_id}"
        offers_name = f"ADROBOT_OFFERS_{campaign.keitaro_id}"

        result = {
            "metadata": "pending",
            "geo": "pending",
            "offers": "pending",
        }
        errors = []

        # Применяем и проверяем параметры кампании непосредственно
        # в Keitaro. При повторном complete операция безопасно повторяется.
        metadata = {
            "domain_id": data["domain_id"],
            "group_id": data["group_id"],
            "traffic_source_id": data["traffic_source_id"],
        }

        try:
            await self.client.update_campaign(
                campaign.keitaro_id,
                metadata,
            )

            verified_campaign = await self.client.get_campaign(
                campaign.keitaro_id
            )

            if not isinstance(verified_campaign, dict):
                raise ValueError(
                    "Keitaro returned an invalid campaign response"
                )

            mismatches = {}

            for key, expected in metadata.items():
                actual = verified_campaign.get(key)

                if actual is not None:
                    actual = int(actual)

                if actual != int(expected):
                    mismatches[key] = {
                        "expected": expected,
                        "actual": actual,
                    }

            if mismatches:
                raise ValueError(
                    f"Campaign metadata verification failed: {mismatches}"
                )

            campaign.domain_id = int(verified_campaign["domain_id"])
            campaign.group_id = int(verified_campaign["group_id"])
            campaign.traffic_source_id = int(
                verified_campaign["traffic_source_id"]
            )
            campaign.name = verified_campaign.get(
                "name", campaign.name
            )
            campaign.alias = verified_campaign.get("alias")
            campaign.state = verified_campaign.get(
                "state", campaign.state
            )
            campaign.raw_payload = safe_payload(verified_campaign)
            campaign.synced_at = datetime.now(timezone.utc)

            result["metadata"] = "verified"

        except Exception as exc:
            result["metadata"] = "error"
            errors.append({
                "step": "campaign_metadata",
                "error": str(exc)[:1000],
            })

        try:
            remote_streams = as_list(
                await self.client.get_campaign_streams(
                    campaign.keitaro_id
                )
            )
        except Exception as exc:
            log.status = "partial"
            log.error_message = str(exc)[:4000]
            log.response_payload = {
                **(log.response_payload or {}),
                "streams": result,
                "errors": errors + [{
                    "step": "get_campaign_streams",
                    "error": str(exc)[:1000],
                }],
            }
            self.db.commit()

            return {
                "status": "partial",
                "campaign": campaign,
                "streams": result,
                "message": "Cannot load existing streams from Keitaro",
                "errors": errors,
            }

        try:
            geo_payload = {
                "campaign_id": campaign.keitaro_id,
                "name": geo_name,
                "type": "regular",
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "filters": [
                    {
                        "name": "country",
                        "mode": "accept",
                        "payload": [data["geo_code"].upper()],
                    }
                ],
            }

            await self.ensure_stream(
                campaign,
                remote_streams,
                geo_payload,
                [],
            )
            result["geo"] = "created_or_existing"

        except Exception as exc:
            result["geo"] = "error"
            errors.append({
                "step": "geo_stream",
                "error": str(exc)[:1000],
            })

        try:
            offers_payload = {
                "campaign_id": campaign.keitaro_id,
                "name": offers_name,
                "type": "default",
                "schema": "landings",
                "offers": [
                    {
                        "offer_id": data["offer_id"],
                        "share": 100,
                        "state": "active",
                    }
                ],
            }

            await self.ensure_stream(
                campaign,
                remote_streams,
                offers_payload,
                offers_payload["offers"],
            )
            result["offers"] = "created_or_existing"

        except Exception as exc:
            result["offers"] = "error"
            errors.append({
                "step": "offers_stream",
                "error": str(exc)[:1000],
            })

        log.status = "partial" if errors else "success"
        log.error_message = str(errors)[:4000] if errors else None
        log.response_payload = {
            **(log.response_payload or {}),
            "streams": result,
            "errors": errors,
        }

        self.db.commit()
        self.db.refresh(campaign)

        return {
            "status": "partial" if errors else "success",
            "campaign": campaign,
            "streams": result,
            "errors": errors,
            "message": (
                "Campaign created with errors"
                if errors
                else "Campaign and streams created successfully"
            ),
        }

    async def ensure_stream(
        self,
        campaign: Campaign,
        remote_streams: list,
        payload: dict,
        remote_offers: list,
    ) -> Stream:
        stream_name = payload["name"]

        remote = next(
            (
                item for item in remote_streams
                if item.get("name") == stream_name
            ),
            None,
        )

        if remote is None:
            response = await self.client.create_stream(payload)
            remote = response if isinstance(response, dict) else {}

            stream_id = self.extract_id(remote)

            if stream_id is None:
                # POST мог завершиться успешно, но ответ не содержал ID.
                refreshed = as_list(
                    await self.client.get_campaign_streams(
                        campaign.keitaro_id
                    )
                )

                remote = next(
                    (
                        item for item in refreshed
                        if item.get("name") == stream_name
                    ),
                    None,
                )

                if remote is None:
                    raise ValueError(
                        f"Stream {stream_name} was not found after creation"
                    )

        stream_id = self.extract_id(remote)

        if stream_id is None:
            raise ValueError(
                f"Keitaro did not return ID for stream {stream_name}"
            )

        stream = self.db.scalar(
            select(Stream).where(Stream.keitaro_id == stream_id)
        )

        if stream is None:
            stream = Stream(
                keitaro_id=stream_id,
                campaign_id=campaign.id,
                name=stream_name,
            )
            self.db.add(stream)

        stream.campaign_id = campaign.id
        stream.name = stream_name
        stream.type = payload["type"]
        stream.stream_schema = payload["schema"]
        stream.action_type = payload.get("action_type")
        stream.action_payload = payload.get("action_payload")
        stream.filters = payload.get("filters", [])
        stream.enabled = True
        stream.is_present_in_keitaro = True
        stream.raw_payload = safe_payload(remote)
        stream.synced_at = datetime.now(timezone.utc)

        self.db.flush()

        if remote_offers:
            await self.save_stream_offers(stream, remote_offers)

        self.db.commit()
        self.db.refresh(stream)

        return stream

    async def save_stream_offers(
        self,
        stream: Stream,
        remote_offers: list,
    ) -> None:
        try:
            catalog = {
                int(item["id"]): item
                for item in as_list(await self.client.get_offers())
                if item.get("id") is not None
            }
        except Exception:
            catalog = {}

        for position, item in enumerate(remote_offers):
            offer_id = int(item["offer_id"])
            catalog_item = catalog.get(offer_id, {})
            remote_share = Decimal(str(item.get("share", 0)))

            offer = self.db.scalar(
                select(StreamOffer).where(
                    StreamOffer.stream_id == stream.id,
                    StreamOffer.keitaro_offer_id == offer_id,
                )
            )

            if offer is None:
                offer = StreamOffer(
                    stream_id=stream.id,
                    keitaro_offer_id=offer_id,
                    name=(
                        catalog_item.get("name")
                        or f"Offer {offer_id}"
                    ),
                    url=catalog_item.get("url"),
                    share=remote_share,
                    remote_share=remote_share,
                    synced_share=remote_share,
                    is_fixed=False,
                    is_deleted=False,
                    synced_is_fixed=False,
                    synced_is_deleted=False,
                    is_present_in_keitaro=True,
                )
                self.db.add(offer)
            else:
                offer.remote_share = remote_share
                offer.is_present_in_keitaro = True

                if offer.synced_share is None:
                    offer.synced_share = remote_share
                    offer.synced_is_fixed = offer.is_fixed
                    offer.synced_is_deleted = offer.is_deleted

            offer.name = catalog_item.get("name") or offer.name
            offer.url = catalog_item.get("url") or offer.url
            offer.remote_share = remote_share
            offer.remote_state = item.get("state")
            offer.position = position
            offer.is_present_in_keitaro = True
            offer.raw_payload = safe_payload(item)

        self.db.flush()

    def get_list(self, offset: int, limit: int) -> dict:
        total = self.db.scalar(
            select(func.count()).select_from(Campaign)
        ) or 0

        items = self.db.scalars(
            select(Campaign)
            .order_by(Campaign.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get(self, campaign_id: int) -> Campaign:
        campaign = self.db.scalar(
            select(Campaign).where(Campaign.id == campaign_id)
        )

        if campaign is None:
            raise LookupError("Campaign not found")

        return campaign

    async def update(self, campaign_id: int, data: dict) -> Campaign:
        campaign = self.get(campaign_id)

        payload = {
            key: value
            for key, value in data.items()
            if key in {
                "name",
                "alias",
                "domain_id",
                "group_id",
                "traffic_source_id",
            }
        }

        if not payload:
            return campaign

        await self.client.update_campaign(
            campaign.keitaro_id,
            payload,
        )

        verified = await self.client.get_campaign(
            campaign.keitaro_id
        )

        if not isinstance(verified, dict):
            raise ValueError(
                "Keitaro returned an invalid campaign response"
            )

        mismatches = {}

        for key, expected in payload.items():
            actual = verified.get(key)

            if key.endswith("_id"):
                if actual is not None:
                    actual = int(actual)
                if expected is not None:
                    expected = int(expected)

            if actual != expected:
                mismatches[key] = {
                    "expected": expected,
                    "actual": actual,
                }

        if mismatches:
            raise ValueError(
                f"Campaign update verification failed: {mismatches}"
            )

        for key in payload:
            setattr(campaign, key, verified.get(key))

        campaign.state = verified.get("state", campaign.state)
        campaign.raw_payload = safe_payload(verified)
        campaign.synced_at = datetime.now(timezone.utc)

        self.db.add(
            SyncLog(
                campaign_id=campaign.id,
                action="campaign_update",
                status="success",
                request_payload=payload,
                response_payload=safe_payload(verified),
            )
        )

        self.db.commit()
        self.db.refresh(campaign)

        return campaign

    async def delete(self, campaign_id: int) -> dict:
        campaign = self.get(campaign_id)

        await self.client.delete_campaign(campaign.keitaro_id)

        campaign.is_present_in_keitaro = False

        for stream in campaign.streams:
            stream.is_present_in_keitaro = False

            for offer in stream.offers:
                offer.is_present_in_keitaro = False

        self.db.add(
            SyncLog(
                campaign_id=campaign.id,
                action="campaign_delete",
                status="success",
            )
        )

        self.db.commit()

        return {
            "status": "success",
            "campaign_id": campaign.id,
            "keitaro_id": campaign.keitaro_id,
        }

    async def set_enabled(
        self,
        campaign_id: int,
        enabled: bool,
    ) -> Campaign:
        campaign = self.get(campaign_id)

        if enabled:
            await self.client.enable_campaign(campaign.keitaro_id)
            campaign.state = "active"
        else:
            await self.client.disable_campaign(campaign.keitaro_id)
            campaign.state = "disabled"

        campaign.synced_at = datetime.now(timezone.utc)

        self.db.add(
            SyncLog(
                campaign_id=campaign.id,
                action=(
                    "campaign_enable"
                    if enabled
                    else "campaign_disable"
                ),
                status="success",
            )
        )

        self.db.commit()
        self.db.refresh(campaign)

        return campaign
