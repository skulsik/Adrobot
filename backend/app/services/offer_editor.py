from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campaign, Stream, StreamOffer, SyncLog
from app.services.keitaro_sync import as_list, safe_payload
from app.services.offer_weights import (
    distribute,
    set_offer_weight,
    validate_total,
    WeightDistributionError,
)


class OfferEditorError(ValueError):
    pass


class OfferEditorService:
    def __init__(self, db: Session, client):
        self.db = db
        self.client = client

    def get_stream(self, stream_id: int) -> Stream:
        stream = self.db.scalar(
            select(Stream).where(Stream.id == stream_id)
        )

        if stream is None:
            raise LookupError("Stream not found")

        if not stream.is_present_in_keitaro:
            raise OfferEditorError(
                "Stream is absent in Keitaro"
            )

        return stream

    def get_offers(self, stream_id: int) -> list[StreamOffer]:
        self.get_stream(stream_id)

        return self.db.scalars(
            select(StreamOffer)
            .where(StreamOffer.stream_id == stream_id)
            .order_by(StreamOffer.position, StreamOffer.id)
        ).all()

    @staticmethod
    def is_dirty(offer: StreamOffer) -> bool:
        if offer.synced_share is None:
            return True

        return (
            Decimal(str(offer.share))
            != Decimal(str(offer.synced_share))
            or offer.is_fixed != offer.synced_is_fixed
            or offer.is_deleted != offer.synced_is_deleted
        )

    def serialize_offer(self, offer: StreamOffer) -> dict:
        return {
            "id": offer.id,
            "keitaro_offer_id": offer.keitaro_offer_id,
            "name": offer.name,
            "url": offer.url,
            "share": str(offer.share),
            "remote_share": (
                str(offer.remote_share)
                if offer.remote_share is not None
                else None
            ),
            "is_fixed": offer.is_fixed,
            "is_deleted": offer.is_deleted,
            "is_present_in_keitaro": offer.is_present_in_keitaro,
            "is_dirty": self.is_dirty(offer),
            "remote_state": offer.remote_state,
            "position": offer.position,
        }

    def serialize_stream(self, stream: Stream) -> dict:
        offers = self.db.scalars(
            select(StreamOffer)
            .where(StreamOffer.stream_id == stream.id)
            .order_by(StreamOffer.position, StreamOffer.id)
        ).all()

        return {
            "id": stream.id,
            "keitaro_id": stream.keitaro_id,
            "campaign_id": stream.campaign_id,
            "name": stream.name,
            "type": stream.type,
            "schema": stream.stream_schema,
            "action_type": stream.action_type,
            "action_payload": stream.action_payload,
            "filters": stream.filters,
            "enabled": stream.enabled,
            "is_present_in_keitaro": stream.is_present_in_keitaro,
            "offers": [
                self.serialize_offer(offer)
                for offer in offers
            ],
            "is_dirty": any(
                self.is_dirty(offer) for offer in offers
            ),
        }

    def list_campaign_streams(self, campaign_id: int) -> dict:
        campaign = self.db.scalar(
            select(Campaign).where(Campaign.id == campaign_id)
        )

        if campaign is None:
            raise LookupError("Campaign not found")

        streams = self.db.scalars(
            select(Stream)
            .where(
                Stream.campaign_id == campaign.id,
                Stream.is_present_in_keitaro.is_(True),
            )
            .order_by(Stream.position, Stream.id)
        ).all()

        return {
            "campaign_id": campaign.id,
            "keitaro_campaign_id": campaign.keitaro_id,
            "items": [
                self.serialize_stream(stream)
                for stream in streams
            ],
        }

    async def refresh_stream(self, stream_id: int) -> dict:
        stream = self.get_stream(stream_id)

        remote = await self.client.get_stream(stream.keitaro_id)

        if not isinstance(remote, dict):
            raise OfferEditorError(
                "Invalid stream response from Keitaro"
            )

        catalog = as_list(await self.client.get_offers())

        catalog_by_id = {
            int(item["id"]): item
            for item in catalog
            if item.get("id") is not None
        }

        stream.name = remote.get("name") or stream.name
        stream.type = remote.get("type")
        stream.stream_schema = remote.get("schema")
        stream.action_type = remote.get("action_type")
        stream.action_payload = remote.get("action_payload")
        stream.filters = remote.get("filters") or []
        stream.enabled = remote.get("state") == "active"
        stream.raw_payload = safe_payload(remote)
        stream.synced_at = datetime.now(timezone.utc)

        remote_offers = remote.get("offers") or []

        existing = {
            item.keitaro_offer_id: item
            for item in self.db.scalars(
                select(StreamOffer).where(
                    StreamOffer.stream_id == stream.id
                )
            ).all()
        }

        seen = set()

        for position, item in enumerate(remote_offers):
            offer_id = int(item["offer_id"])
            seen.add(offer_id)

            remote_share = Decimal(str(item.get("share", 0)))
            catalog_item = catalog_by_id.get(offer_id, {})

            offer = existing.get(offer_id)

            if offer is None:
                offer = StreamOffer(
                    stream_id=stream.id,
                    keitaro_offer_id=offer_id,
                    name=(
                        catalog_item.get("name")
                        or f"Offer {offer_id}"
                    ),
                    share=remote_share,
                    remote_share=remote_share,
                    is_fixed=False,
                    is_deleted=False,
                    synced_share=remote_share,
                    synced_is_fixed=False,
                    synced_is_deleted=False,
                )
                self.db.add(offer)
            else:
                offer.remote_share = remote_share
                offer.is_present_in_keitaro = True
                offer.remote_state = item.get("state")

                # Локальное состояние не перезаписываем.
                if catalog_item.get("name"):
                    offer.name = catalog_item["name"]

                if catalog_item.get("url"):
                    offer.url = catalog_item["url"]

            offer.remote_share = remote_share
            offer.remote_state = item.get("state")
            offer.is_present_in_keitaro = True
            offer.position = position
            offer.raw_payload = safe_payload(item)

            if catalog_item.get("url"):
                offer.url = catalog_item["url"]

        for offer_id, offer in existing.items():
            if offer_id not in seen:
                offer.is_present_in_keitaro = False

        self.db.commit()

        return self.serialize_stream(stream)

    def add_offer(self, stream_id: int, offer_id: int) -> dict:
        stream = self.get_stream(stream_id)

        existing = self.db.scalar(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream.id,
                StreamOffer.keitaro_offer_id == offer_id,
            )
        )

        if existing is not None:
            if existing.is_deleted:
                return self.restore_offer(stream_id, offer_id)

            raise OfferEditorError(
                "Offer already exists in this stream"
            )

        # Получаем оффер из каталога Keitaro.
        raise NotImplementedError(
            "Use add_offer_with_catalog"
        )

    async def add_offer_with_catalog(
        self,
        stream_id: int,
        offer_id: int,
    ) -> dict:
        stream = self.get_stream(stream_id)

        existing = self.db.scalar(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream.id,
                StreamOffer.keitaro_offer_id == offer_id,
            )
        )

        if existing is not None:
            if existing.is_deleted:
                return self.restore_offer(stream_id, offer_id)

            raise OfferEditorError(
                "Offer already exists in this stream"
            )

        catalog = as_list(await self.client.get_offers())

        item = next(
            (
                value for value in catalog
                if int(value.get("id", 0)) == offer_id
            ),
            None,
        )

        if item is None:
            raise LookupError("Offer not found in Keitaro catalog")

        offer = StreamOffer(
            stream_id=stream.id,
            keitaro_offer_id=offer_id,
            name=item.get("name") or f"Offer {offer_id}",
            url=item.get("url"),
            share=Decimal("0.00"),
            remote_share=None,
            is_fixed=False,
            is_deleted=False,
            is_present_in_keitaro=False,
            position=len(self.get_offers(stream_id)),
            raw_payload={},
            synced_share=None,
            synced_is_fixed=None,
            synced_is_deleted=None,
        )

        self.db.add(offer)
        self.db.flush()

        offers = self.get_offers(stream_id)

        try:
            distribute(offers)
        except WeightDistributionError as exc:
            self.db.rollback()
            raise OfferEditorError(str(exc)) from exc

        self.db.commit()

        return self.serialize_stream(stream)

    def update_offer(
        self,
        stream_id: int,
        offer_id: int,
        *,
        share=None,
        is_fixed=None,
    ) -> dict:
        self.get_stream(stream_id)

        offer = self.db.scalar(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream_id,
                StreamOffer.keitaro_offer_id == offer_id,
            )
        )

        if offer is None:
            raise LookupError("Offer not found")

        offers = self.get_offers(stream_id)

        try:
            if share is not None:
                set_offer_weight(offers, offer, share)

            if is_fixed is not None:
                offer.is_fixed = is_fixed
                distribute(offers)

        except WeightDistributionError as exc:
            self.db.rollback()
            raise OfferEditorError(str(exc)) from exc

        self.db.commit()

        return self.serialize_stream(
            self.get_stream(stream_id)
        )

    def delete_offer(
        self,
        stream_id: int,
        offer_id: int,
    ) -> dict:
        self.get_stream(stream_id)

        offer = self.db.scalar(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream_id,
                StreamOffer.keitaro_offer_id == offer_id,
            )
        )

        if offer is None:
            raise LookupError("Offer not found")

        if offer.is_deleted:
            raise OfferEditorError("Offer is already deleted")

        offer.is_deleted = True
        offer.share = Decimal("0.00")

        try:
            distribute(self.get_offers(stream_id))
        except WeightDistributionError as exc:
            self.db.rollback()
            raise OfferEditorError(str(exc)) from exc

        self.db.commit()

        return self.serialize_stream(
            self.get_stream(stream_id)
        )

    def restore_offer(
        self,
        stream_id: int,
        offer_id: int,
    ) -> dict:
        self.get_stream(stream_id)

        offer = self.db.scalar(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream_id,
                StreamOffer.keitaro_offer_id == offer_id,
            )
        )

        if offer is None:
            raise LookupError("Offer not found")

        if not offer.is_deleted:
            raise OfferEditorError("Offer is not deleted")

        offer.is_deleted = False

        try:
            distribute(self.get_offers(stream_id))
        except WeightDistributionError as exc:
            self.db.rollback()
            raise OfferEditorError(str(exc)) from exc

        self.db.commit()

        return self.serialize_stream(
            self.get_stream(stream_id)
        )

    def discard(self, stream_id: int) -> dict:
        self.get_stream(stream_id)

        offers = self.get_offers(stream_id)

        for offer in offers:
            if offer.synced_share is None:
                self.db.delete(offer)
                continue

            offer.share = offer.synced_share
            offer.is_fixed = bool(offer.synced_is_fixed)
            offer.is_deleted = bool(offer.synced_is_deleted)

        self.db.commit()

        return self.serialize_stream(
            self.get_stream(stream_id)
        )

    async def apply(self, stream_id: int) -> dict:
        stream = self.get_stream(stream_id)
        offers = self.get_offers(stream_id)

        try:
            validate_total(offers)
        except WeightDistributionError as exc:
            raise OfferEditorError(str(exc)) from exc

        payload_offers = [
            {
                "offer_id": offer.keitaro_offer_id,
                "share": float(offer.share),
                "state": "active",
            }
            for offer in offers
            if not offer.is_deleted
        ]

        # PUT заменяет массив offers целиком.
        await self.client.update_stream(
            stream.keitaro_id,
            {
                "offers": payload_offers,
            },
        )

        # Проверяем результат на стороне Keitaro.
        remote = await self.client.get_stream(stream.keitaro_id)

        remote_offers = remote.get("offers") or []

        remote_map = {
            int(item["offer_id"]): Decimal(str(item["share"]))
            for item in remote_offers
        }

        expected_map = {
            offer.keitaro_offer_id: Decimal(str(offer.share))
            for offer in offers
            if not offer.is_deleted
        }

        if remote_map != expected_map:
            raise OfferEditorError(
                "Keitaro offer verification failed"
            )

        for offer in offers:
            offer.synced_share = offer.share
            offer.synced_is_fixed = offer.is_fixed
            offer.synced_is_deleted = offer.is_deleted

            offer.is_present_in_keitaro = not offer.is_deleted

            if offer.is_deleted:
                offer.remote_share = Decimal("0.00")
                offer.remote_state = None
            else:
                offer.remote_share = offer.share
                offer.remote_state = "active"

        stream.raw_payload = safe_payload(remote)
        stream.synced_at = datetime.now(timezone.utc)

        self.db.add(
            SyncLog(
                campaign_id=stream.campaign_id,
                stream_id=stream.id,
                action="stream_offers_apply",
                status="success",
                request_payload={
                    "offers": payload_offers,
                },
                response_payload={
                    "verified_offers": len(remote_map),
                },
            )
        )

        self.db.commit()

        return self.serialize_stream(stream)
