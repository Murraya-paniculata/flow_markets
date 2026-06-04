"""Phase 6.1：FLOW_MARKETS_MODE / APP_FLOW_MARKETS_MODE 切换。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings, get_settings
from app.crews.flows.flow_markets import FlowMarketsCrew, create_flow_markets_crew_for_run
from app.crews.flows.flow_markets_mode import (
    FLOW_MARKETS_MODE_FULL,
    FLOW_MARKETS_MODE_TECHNICAL_ONLY,
    flow_markets_metrics_flow_name,
    get_flow_markets_mode,
    is_flow_markets_full_mode,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_default_technical_only() -> None:
    s = Settings(_env_file=None)
    assert s.flow_markets_mode == FLOW_MARKETS_MODE_TECHNICAL_ONLY
    assert is_flow_markets_full_mode() is False
    assert flow_markets_metrics_flow_name() == "flow_markets"


def test_flow_markets_mode_from_flow_markets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOW_MARKETS_MODE", "full")
    monkeypatch.delenv("APP_FLOW_MARKETS_MODE", raising=False)
    get_settings.cache_clear()
    assert get_flow_markets_mode() == FLOW_MARKETS_MODE_FULL
    assert is_flow_markets_full_mode() is True
    assert flow_markets_metrics_flow_name() == "flow_markets_full"


def test_app_flow_markets_mode_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_FLOW_MARKETS_MODE", "full")
    get_settings.cache_clear()
    assert get_flow_markets_mode() == FLOW_MARKETS_MODE_FULL


@patch("app.crews.flows.flow_markets.is_flow_markets_full_mode", return_value=False)
@patch("app.crews.flows.flow_markets.Crew")
def test_create_crew_technical_only(
    mock_crew_cls: MagicMock,
    _mock_full: MagicMock,
) -> None:
    flow = MagicMock(spec=FlowMarketsCrew)
    flow.technical_analyst.return_value = MagicMock()
    mock_crew_cls.return_value = MagicMock()
    with patch(
        "app.crews.flows.flow_markets._standalone_technical_task",
        return_value=MagicMock(),
    ) as mock_task:
        crew, name = create_flow_markets_crew_for_run(flow)
    assert name == "flow_markets"
    flow.crew.assert_not_called()
    mock_task.assert_called_once_with(flow)
    mock_crew_cls.assert_called_once()


@patch("app.crews.flows.flow_markets.is_flow_markets_full_mode", return_value=True)
def test_create_crew_full(_mock_full: MagicMock) -> None:
    flow = MagicMock(spec=FlowMarketsCrew)
    with patch("app.crews.flows.flow_markets._create_upstream_crew") as mock_up:
        up_crew = MagicMock()
        mock_up.return_value = up_crew
        from app.crews.flows.flow_markets import create_flow_markets_crew_for_run

        crew, name = create_flow_markets_crew_for_run(flow)
    assert crew is up_crew
    assert name == "flow_markets_full_upstream"
    mock_up.assert_called_once_with(flow)


@patch("app.crews.flows.flow_markets.Crew")
def test_flow_markets_crew_composition_technical_only(
    mock_crew_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_FLOW_MARKETS_MODE", "technical_only")
    get_settings.cache_clear()
    mock_crew_cls.return_value = MagicMock()
    flow = FlowMarketsCrew()
    flow.crew()
    kwargs = mock_crew_cls.call_args.kwargs
    assert len(kwargs["agents"]) == 1
    assert len(kwargs["tasks"]) == 1


@patch("app.crews.flows.flow_markets.Crew")
def test_flow_markets_crew_composition_full(
    mock_crew_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_FLOW_MARKETS_MODE", "full")
    get_settings.cache_clear()
    mock_crew_cls.return_value = MagicMock()
    flow = FlowMarketsCrew()
    from app.crews.flows.flow_markets import _create_upstream_crew, _create_downstream_crew

    _create_upstream_crew(flow)
    up_kwargs = mock_crew_cls.call_args.kwargs
    assert len(up_kwargs["agents"]) == 4
    assert len(up_kwargs["tasks"]) == 4

    mock_crew_cls.return_value = MagicMock()
    _create_downstream_crew(flow)
    down_kwargs = mock_crew_cls.call_args.kwargs
    assert len(down_kwargs["agents"]) == 3
    assert len(down_kwargs["tasks"]) == 3
