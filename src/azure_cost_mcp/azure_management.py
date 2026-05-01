"""Azure 管理平面共用 API helper。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential

from .config import Settings

MANAGEMENT_SCOPE = "https://management.azure.com/.default"


class AzureManagementApiError(RuntimeError):
    """Azure 管理平面 API 呼叫失敗。"""


class AzureManagementApiClient:
    """Azure 管理平面 API 基底 client。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200, 204),
    ) -> dict[str, Any] | None:
        credential = DefaultAzureCredential()
        try:
            token = await credential.get_token(MANAGEMENT_SCOPE)
        finally:
            await credential.close()

        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            base_url=self._settings.azure_management_base_url,
            headers=headers,
            timeout=httpx.Timeout(60.0, read=120.0),
        ) as client:
            response = await client.request(method, url, params=params, json=json_body)

        if response.status_code not in expected_statuses:
            raise AzureManagementApiError(self._format_error(response))

        if response.status_code == 204 or not response.content:
            return None

        return response.json()

    @staticmethod
    def _format_error(response: httpx.Response) -> str:
        message = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                error_code = error.get("code")
                error_message = error.get("message")
                if error_code and error_message:
                    message = f"{error_code}: {error_message}"
                elif error_message:
                    message = str(error_message)
            elif "message" in payload:
                message = str(payload["message"])

        request = response.request
        return (
            f"Azure management API request failed with status {response.status_code} "
            f"for {request.method} {request.url}. {message}"
        )
