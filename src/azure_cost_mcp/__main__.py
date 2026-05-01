"""Azure Cost MCP 啟動入口。"""

from __future__ import annotations

import argparse

from .config import get_settings
from .server import create_mcp_server


def build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    settings = get_settings()

    parser = argparse.ArgumentParser(description="啟動 Azure Cost MCP server。")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=settings.mcp_transport,
        help="指定 MCP 傳輸模式。",
    )
    parser.add_argument(
        "--host",
        default=settings.mcp_host,
        help="指定 Streamable HTTP 綁定主機位址。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.mcp_port,
        help="指定 Streamable HTTP 綁定埠號。",
    )
    parser.add_argument(
        "--path",
        default=settings.mcp_streamable_http_path,
        help="指定 Streamable HTTP MCP 路徑。",
    )
    return parser


def main() -> None:
    """啟動 Azure Cost MCP server。"""
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings().model_copy(
        update={
            "mcp_transport": args.transport,
            "mcp_host": args.host,
            "mcp_port": args.port,
            "mcp_streamable_http_path": args.path,
        }
    )

    server = create_mcp_server(settings=settings)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
