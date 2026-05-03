from __future__ import annotations

import pytest

from azure_cost_mcp import auth as auth_module

from .helpers import make_settings


def test_create_azure_credential_uses_azure_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(auth_module, "AzureCliCredential", lambda: sentinel)

    credential = auth_module.create_azure_credential(
        make_settings(azure_cost_auth_mode="azure-cli")
    )

    assert credential is sentinel


def test_create_azure_credential_requires_service_principal_settings() -> None:
    with pytest.raises(
        ValueError,
        match="AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET",
    ):
        auth_module.create_azure_credential(
            make_settings(
                azure_cost_auth_mode="service-principal",
                azure_tenant_id=None,
                azure_client_id=None,
                azure_client_secret=None,
            )
        )


def test_create_azure_credential_builds_service_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}
    sentinel = object()

    def fake_client_secret_credential(
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> object:
        captured.update(
            {
                "tenant_id": tenant_id,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )
        return sentinel

    monkeypatch.setattr(auth_module, "ClientSecretCredential", fake_client_secret_credential)

    credential = auth_module.create_azure_credential(
        make_settings(
            azure_cost_auth_mode="service-principal",
            azure_tenant_id="tenant-id",
            azure_client_id="client-id",
            azure_client_secret="client-secret",
        )
    )

    assert credential is sentinel
    assert captured == {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": "client-secret",
    }


@pytest.mark.parametrize(
    ("client_id", "expected_kwargs"),
    [
        (None, {}),
        ("mi-client-id", {"client_id": "mi-client-id"}),
    ],
)
def test_create_azure_credential_builds_managed_identity(
    monkeypatch: pytest.MonkeyPatch,
    client_id: str | None,
    expected_kwargs: dict[str, str],
) -> None:
    calls: list[dict[str, str]] = []
    sentinel = object()

    def fake_managed_identity_credential(**kwargs) -> object:
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(auth_module, "ManagedIdentityCredential", fake_managed_identity_credential)

    credential = auth_module.create_azure_credential(
        make_settings(
            azure_cost_auth_mode="managed-identity",
            azure_managed_identity_client_id=client_id,
        )
    )

    assert credential is sentinel
    assert calls == [expected_kwargs]


def test_create_azure_credential_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(auth_module, "DefaultAzureCredential", lambda: sentinel)

    credential = auth_module.create_azure_credential(make_settings(azure_cost_auth_mode="default"))

    assert credential is sentinel
