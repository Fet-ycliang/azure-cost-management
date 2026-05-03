from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from azure_cost_mcp.models import (
    ConnectionValidationParams,
    DateRangeOptions,
    DatabricksQueryParams,
    DatabricksQuerySource,
    RequiredTagsOptions,
)


def test_date_range_requires_both_dates() -> None:
    with pytest.raises(ValidationError, match="必須同時提供"):
        DateRangeOptions(start_date=date(2026, 1, 1))


def test_date_range_rejects_reverse_window() -> None:
    with pytest.raises(ValidationError, match="不可晚於"):
        DateRangeOptions(
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 1),
        )


def test_date_range_resolves_explicit_and_relative_windows() -> None:
    explicit = DateRangeOptions(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    relative = DateRangeOptions(lookback_days=7)

    assert explicit.resolved_window() == (date(2026, 1, 1), date(2026, 1, 31))
    start_date, end_date = relative.resolved_window()
    assert (end_date - start_date).days == 6


def test_required_tags_are_stripped_and_deduplicated() -> None:
    options = RequiredTagsOptions(required_tag_keys=[" Department ", "Owner", "Department"])

    assert options.required_tag_keys == ["Department", "Owner"]


def test_required_tags_reject_empty_values() -> None:
    with pytest.raises(ValidationError, match="至少需要一個非空字串"):
        RequiredTagsOptions(required_tag_keys=["", " "])


def test_databricks_query_requires_payload() -> None:
    with pytest.raises(ValidationError, match="至少提供 question、sql 或 arguments"):
        DatabricksQueryParams()

    params = DatabricksQueryParams(question="成本趨勢")

    assert params.question == "成本趨勢"
    assert params.query_source is DatabricksQuerySource.AMORTIZED


def test_connection_validation_params_accept_subscriptions() -> None:
    params = ConnectionValidationParams(subscriptions=["sub-a", "sub-b"])

    assert params.subscriptions == ["sub-a", "sub-b"]
