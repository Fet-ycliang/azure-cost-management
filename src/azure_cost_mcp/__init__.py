"""Azure Cost MCP 套件匯出。"""

from .__main__ import main
from .server import create_mcp_server

__all__ = ["create_mcp_server", "main"]
