"""Azure 驗證模式 helper。"""

from __future__ import annotations

from typing import Any

from azure.identity.aio import (
    AzureCliCredential,
    ClientSecretCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)

from .config import Settings


def create_azure_credential(settings: Settings) -> Any:
    """依設定建立 Azure credential。"""
    if settings.azure_cost_auth_mode == "azure-cli":
        return AzureCliCredential()

    if settings.azure_cost_auth_mode == "service-principal":
        missing = [
            name
            for name, value in (
                ("AZURE_TENANT_ID", settings.azure_tenant_id),
                ("AZURE_CLIENT_ID", settings.azure_client_id),
                ("AZURE_CLIENT_SECRET", settings.azure_client_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "service-principal 模式缺少必要設定："
                + ", ".join(missing)
            )
        return ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
        )

    if settings.azure_cost_auth_mode == "managed-identity":
        kwargs = {}
        if settings.azure_managed_identity_client_id:
            kwargs["client_id"] = settings.azure_managed_identity_client_id
        return ManagedIdentityCredential(**kwargs)

    return DefaultAzureCredential()


def create_m365_credential(settings: Settings) -> Any:
    """建立 M365 平台專用 credential。

    若 M365_SP_CLIENT_ID / M365_SP_CLIENT_SECRET / M365_COST_MANAGEMENT_TENANT
    三個欄位均已設定，使用 dw_fabric_ap SP；否則退回 create_azure_credential()。
    """
    if (
        settings.m365_sp_client_id
        and settings.m365_sp_client_secret
        and settings.m365_cost_management_tenant
    ):
        return ClientSecretCredential(
            tenant_id=settings.m365_cost_management_tenant,
            client_id=settings.m365_sp_client_id,
            client_secret=settings.m365_sp_client_secret,
        )
    return create_azure_credential(settings)
