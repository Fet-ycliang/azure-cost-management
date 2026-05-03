from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from azure_cost_mcp.databricks_mcp import DatabricksMcpClient, DatabricksMcpClientError

from .helpers import make_settings


class FakeTool:
    def __init__(self, name: str, input_schema: dict[str, Any] | None = None) -> None:
        self.name = name
        self.inputSchema = input_schema

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        if self.inputSchema is not None:
            payload["inputSchema"] = self.inputSchema
        return payload


class FakeContentItem:
    def __init__(self, value: str) -> None:
        self.value = value

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        return {"value": self.value}


class FakeToolResult:
    def __init__(self) -> None:
        self.isError = False
        self.structuredContent = {"answer": 42}
        self.content = [FakeContentItem("done")]


def test_is_configured_depends_on_server_url() -> None:
    assert DatabricksMcpClient(make_settings(databricks_mcp_server_url=None)).is_configured() is False
    assert DatabricksMcpClient(make_settings()).is_configured() is True


def test_call_configured_tool_requires_tool_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DatabricksMcpClient(make_settings())

    async def fake_list_tools() -> list[dict[str, str]]:
        return [{"name": "tool-a"}]

    monkeypatch.setattr(client, "list_tools", fake_list_tools)

    with pytest.raises(DatabricksMcpClientError, match="DATABRICKS_MCP_QUERY_TOOL_NAME"):
        asyncio.run(
            client.call_configured_tool(
                tool_name=None,
                env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
                purpose="databricks-query",
                arguments={},
            )
        )


def test_call_configured_tool_raises_when_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DatabricksMcpClient(make_settings())

    @asynccontextmanager
    async def fake_session():
        yield object()

    async def fake_list_tool_models(session: object) -> list[FakeTool]:
        return [FakeTool("tool-a")]

    monkeypatch.setattr(client, "_session", fake_session)
    monkeypatch.setattr(client, "_list_tool_models", fake_list_tool_models)

    with pytest.raises(DatabricksMcpClientError, match="找不到 tool 'tool-b'"):
        asyncio.run(
            client.call_configured_tool(
                tool_name="tool-b",
                env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
                purpose="databricks-query",
                arguments={},
            )
        )


def test_call_configured_tool_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DatabricksMcpClient(make_settings())
    called = {}

    class FakeSession:
        async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> FakeToolResult:
            called["tool_name"] = tool_name
            called["arguments"] = arguments
            return FakeToolResult()

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    async def fake_list_tool_models(session: object) -> list[FakeTool]:
        return [FakeTool("query_tool"), FakeTool("tag_tool")]

    monkeypatch.setattr(client, "_session", fake_session)
    monkeypatch.setattr(client, "_list_tool_models", fake_list_tool_models)

    result = asyncio.run(
        client.call_configured_tool(
            tool_name="query_tool",
            env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
            purpose="databricks-query",
            arguments={"sql": "select 1"},
        )
    )

    assert called == {"tool_name": "query_tool", "arguments": {"sql": "select 1"}}
    assert result == {
        "tool_name": "query_tool",
        "is_error": False,
        "structured_content": {"answer": 42},
        "content": [{"value": "done"}],
        "available_tools": ["query_tool", "tag_tool"],
    }


def test_call_configured_tool_maps_sql_to_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DatabricksMcpClient(make_settings(databricks_mcp_query_tool_name="execute_sql_read_only"))
    called = {}

    class FakeSession:
        async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> FakeToolResult:
            called["tool_name"] = tool_name
            called["arguments"] = arguments
            return FakeToolResult()

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    async def fake_list_tool_models(session: object) -> list[FakeTool]:
        return [
            FakeTool(
                "execute_sql_read_only",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                    },
                },
            )
        ]

    monkeypatch.setattr(client, "_session", fake_session)
    monkeypatch.setattr(client, "_list_tool_models", fake_list_tool_models)

    asyncio.run(
        client.call_configured_tool(
            tool_name="execute_sql_read_only",
            env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
            purpose="databricks-query",
            arguments={
                "sql": "select 1",
                "question": "ignored",
                "schema_name": "bronze",
            },
        )
    )

    assert called == {
        "tool_name": "execute_sql_read_only",
        "arguments": {"query": "select 1"},
    }


def test_call_configured_tool_rejects_question_only_for_sql_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DatabricksMcpClient(make_settings(databricks_mcp_query_tool_name="execute_sql_read_only"))

    @asynccontextmanager
    async def fake_session():
        yield object()

    async def fake_list_tool_models(session: object) -> list[FakeTool]:
        return [
            FakeTool(
                "execute_sql_read_only",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                    },
                },
            )
        ]

    monkeypatch.setattr(client, "_session", fake_session)
    monkeypatch.setattr(client, "_list_tool_models", fake_list_tool_models)

    with pytest.raises(DatabricksMcpClientError, match="不支援只傳入自然語言 question"):
        asyncio.run(
            client.call_configured_tool(
                tool_name="execute_sql_read_only",
                env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
                purpose="databricks-query",
                arguments={"question": "show costs"},
            )
        )


def test_list_tool_models_reads_all_pages() -> None:
    client = DatabricksMcpClient(make_settings())

    class FakePage:
        def __init__(self, tools: list[FakeTool], next_cursor: str | None) -> None:
            self.tools = tools
            self.nextCursor = next_cursor

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[str | None] = []

        async def list_tools(self, cursor: str | None = None) -> FakePage:
            self.calls.append(cursor)
            if cursor is None:
                return FakePage([FakeTool("page-1")], "next")
            return FakePage([FakeTool("page-2")], None)

    session = FakeSession()

    tools = asyncio.run(client._list_tool_models(session))

    assert [tool.name for tool in tools] == ["page-1", "page-2"]
    assert session.calls == [None, "next"]
