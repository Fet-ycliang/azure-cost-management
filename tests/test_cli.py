from __future__ import annotations

from types import SimpleNamespace

import pytest

from azure_cost_mcp import __main__ as cli

from .helpers import make_settings


def test_build_parser_uses_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(
        mcp_transport="streamable-http",
        mcp_host="0.0.0.0",
        mcp_port=9000,
        mcp_streamable_http_path="/custom",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    parser = cli.build_parser()
    args = parser.parse_args([])

    assert args.transport == "streamable-http"
    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.path == "/custom"


def test_main_builds_server_from_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_settings = make_settings()
    server = SimpleNamespace(run_args=[])
    captured = {}

    def fake_create_mcp_server(*, settings):
        captured["settings"] = settings

        def run(*, transport: str) -> None:
            server.run_args.append(transport)

        return SimpleNamespace(run=run)

    monkeypatch.setattr(cli, "get_settings", lambda: base_settings)
    monkeypatch.setattr(cli, "create_mcp_server", fake_create_mcp_server)
    monkeypatch.setattr(
        "sys.argv",
        [
            "azure-cost-mcp",
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--port",
            "9100",
            "--path",
            "/alt",
        ],
    )

    cli.main()

    assert captured["settings"].mcp_transport == "streamable-http"
    assert captured["settings"].mcp_host == "0.0.0.0"
    assert captured["settings"].mcp_port == 9100
    assert captured["settings"].mcp_streamable_http_path == "/alt"
    assert server.run_args == ["streamable-http"]
