from typing import Any

import httpx
from pydantic import SecretStr

from app.integrations.keitaro.exceptions import (
    KeitaroAPIError,
    KeitaroConfigurationError,
    KeitaroConnectionError,
    KeitaroInvalidResponseError,
    KeitaroTimeoutError,
)


class KeitaroClient:
    def __init__(
        self,
        base_url: str,
        api_key: SecretStr | None,
        timeout: float = 15.0,
    ):
        self._api_key = api_key

        headers = {
            "Accept": "application/json",
        }

        if api_key:
            headers["Api-Key"] = api_key.get_secret_value()

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        if not self._api_key:
            raise KeitaroConfigurationError(
                "Keitaro API key is not configured"
            )

        try:
            response = await self._client.request(
                method=method,
                url=path.lstrip("/"),
                params=params,
                json=json,
            )

        except httpx.TimeoutException as exc:
            raise KeitaroTimeoutError(
                "Keitaro API request timed out"
            ) from exc

        except httpx.RequestError as exc:
            raise KeitaroConnectionError(
                "Cannot connect to Keitaro API"
            ) from exc

        if not response.is_success:
            raise KeitaroAPIError(response.status_code)

        # DELETE и некоторые POST-запросы могут вернуть 204.
        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroInvalidResponseError(
                "Keitaro API returned invalid JSON"
            ) from exc

    # ---------------------------------------------------------
    # Campaigns
    # ---------------------------------------------------------

    async def get_campaigns(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> Any:
        return await self.request(
            "GET",
            "/campaigns",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    async def get_campaign(self, campaign_id: int) -> Any:
        return await self.request(
            "GET",
            f"/campaigns/{campaign_id}",
        )

    async def create_campaign(
        self,
        payload: dict[str, Any],
    ) -> Any:
        return await self.request(
            "POST",
            "/campaigns",
            json=payload,
        )

    async def update_campaign(
        self,
        campaign_id: int,
        payload: dict[str, Any],
    ) -> Any:
        return await self.request(
            "PUT",
            f"/campaigns/{campaign_id}",
            json=payload,
        )

    async def delete_campaign(self, campaign_id: int) -> None:
        await self.request(
            "DELETE",
            f"/campaigns/{campaign_id}",
        )

    async def enable_campaign(self, campaign_id: int) -> Any:
        return await self.request(
            "POST",
            f"/campaigns/{campaign_id}/enable",
        )

    async def disable_campaign(self, campaign_id: int) -> Any:
        return await self.request(
            "POST",
            f"/campaigns/{campaign_id}/disable",
        )

    # ---------------------------------------------------------
    # Streams
    # ---------------------------------------------------------

    async def get_campaign_streams(
        self,
        campaign_id: int,
    ) -> Any:
        return await self.request(
            "GET",
            f"/campaigns/{campaign_id}/streams",
        )

    async def get_stream(self, stream_id: int) -> Any:
        return await self.request(
            "GET",
            f"/streams/{stream_id}",
        )

    async def create_stream(
        self,
        payload: dict[str, Any],
    ) -> Any:
        return await self.request(
            "POST",
            "/streams",
            json=payload,
        )

    async def update_stream(
        self,
        stream_id: int,
        payload: dict[str, Any],
    ) -> Any:
        return await self.request(
            "PUT",
            f"/streams/{stream_id}",
            json=payload,
        )

    async def delete_stream(self, stream_id: int) -> None:
        await self.request(
            "DELETE",
            f"/streams/{stream_id}",
        )

    async def enable_stream(self, stream_id: int) -> Any:
        return await self.request(
            "POST",
            f"/streams/{stream_id}/enable",
        )

    async def disable_stream(self, stream_id: int) -> Any:
        return await self.request(
            "POST",
            f"/streams/{stream_id}/disable",
        )

    # ---------------------------------------------------------
    # Read-only dictionaries
    # ---------------------------------------------------------

    async def get_offers(self) -> Any:
        return await self.request("GET", "/offers")

    async def get_offer(self, offer_id: int) -> Any:
        return await self.request(
            "GET",
            f"/offers/{offer_id}",
        )

    async def get_domains(self) -> Any:
        return await self.request("GET", "/domains")

    async def get_groups(self) -> Any:
        return await self.request(
            "GET",
            "/groups",
            params={"type": "campaigns"},
        )

    async def get_traffic_sources(self) -> Any:
        return await self.request("GET", "/traffic_sources")
