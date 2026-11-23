"""A read-only VE-X (Village Energy) customer API client.

Every call is a GET with the `apiKey` header, sent with exactly that name (VE-X once
matched it case-sensitively; aiohttp keeps the case). Paths and the security context
follow Village's public OpenAPI ("Customer Authorisation" endpoints).
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class VexError(Exception):
    """VE-X did not answer usefully (network, 5xx, 429, bad JSON)."""


class VexAuthError(VexError):
    """VE-X refused the key or the customer (401/403)."""


class VexClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str, customer_id: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._ctx = f"Voltello/CUSTOMERS/Individual/{customer_id}"
        self._customer_id = customer_id

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.get(
                self._base + path, params=params, headers={"apiKey": self._key, "Accept": "*/*"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise VexAuthError(f"VE-X refused the request ({resp.status})")
                if resp.status != 200:
                    raise VexError(f"VE-X answered {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise VexError(str(err) or type(err).__name__) from err

    async def service_points(self) -> dict[str, Any]:
        return await self._get(f"/get/customer/energy/electricity/servicepoints/{self._ctx}",
                               {"customerId": self._customer_id})

    async def der(self, service_point_id: str) -> dict[str, Any]:
        return await self._get(f"/get/customer/energy/electricity/servicepoints/{service_point_id}/der/{self._ctx}",
                               {"servicePointId": service_point_id})

    async def detail(self, service_point_id: str) -> dict[str, Any]:
        """Service-point detail with the control log (the polled call)."""
        return await self._get(f"/get/customer/energy/electricity/servicepoints/{service_point_id}/{self._ctx}",
                               {"servicePointId": service_point_id, "includeControlLogInfo": "true"})
