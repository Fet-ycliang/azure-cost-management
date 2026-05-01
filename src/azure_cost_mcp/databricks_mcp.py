"""Databricks MCP server proxy client。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import Settings


class DatabricksMcpClientError(RuntimeError):
    """Databricks MCP 代理相關錯誤。"""


class DatabricksMcpClient:
    """以 MCP client 連線遠端 Databricks MCP server。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        """是否已設定遠端 Databricks MCP server。"""
        return bool(self._settings.databricks_mcp_server_url)

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出遠端 Databricks MCP tools。"""
        async with self._session() as session:
            tools = await self._list_tool_models(session)
        return [tool.model_dump(mode="json") for tool in tools]

    async def call_configured_tool(
        self,
        *,
        tool_name: str | None,
        env_var_name: str,
        purpose: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """呼叫已由設定指定的遠端 Databricks MCP tool。"""
        if not tool_name:
            available_tools = []
            if self.is_configured():
                available_tools = [tool["name"] for tool in await self.list_tools()]
            available_tools_text = (
                ", ".join(available_tools) if available_tools else "(no tools discovered)"
            )
            raise DatabricksMcpClientError(
                f"{purpose} 需要設定 {env_var_name}。目前可見 Databricks MCP tools: "
                f"{available_tools_text}"
            )

        async with self._session() as session:
            tools = await self._list_tool_models(session)
            available_tools = [tool.name for tool in tools]
            if tool_name not in available_tools:
                raise DatabricksMcpClientError(
                    f"Databricks MCP server 上找不到 tool '{tool_name}'。可用 tools: "
                    f"{', '.join(available_tools) if available_tools else '(none)'}"
                )
            result = await session.call_tool(tool_name, arguments=arguments)

        return {
            "tool_name": tool_name,
            "is_error": result.isError,
            "structured_content": result.structuredContent,
            "content": [item.model_dump(mode="json") for item in result.content],
            "available_tools": available_tools,
        }

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        server_url = self._settings.databricks_mcp_server_url
        if not server_url:
            raise DatabricksMcpClientError(
                "DATABRICKS_MCP_SERVER_URL 尚未設定，無法透過 Databricks MCP server 代理工具。"
            )

        headers = {}
        if self._settings.databricks_mcp_bearer_token:
            headers["Authorization"] = (
                f"Bearer {self._settings.databricks_mcp_bearer_token}"
            )

        timeout = httpx.Timeout(
            self._settings.databricks_mcp_timeout_seconds,
            read=self._settings.databricks_mcp_timeout_seconds * 5,
        )
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(
                server_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

    async def _list_tool_models(self, session: ClientSession) -> list[Any]:
        tools = []
        cursor: str | None = None
        while True:
            page = await session.list_tools(cursor=cursor)
            tools.extend(page.tools)
            cursor = page.nextCursor
            if not cursor:
                break
        return tools
