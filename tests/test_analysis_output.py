"""Phase 5.5：save=true 写 output/ 与 should_write_output_artifacts。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.analysis_output import (
    should_write_output_artifacts,
    write_analyze_save_artifacts,
    write_structure_only_artifacts,
)


def test_should_write_output_artifacts_only_explicit_true() -> None:
    assert should_write_output_artifacts(save=True) is True
    assert should_write_output_artifacts(save=False) is False
    assert should_write_output_artifacts(save=None) is False


def test_write_structure_only_artifacts(tmp_path: Path) -> None:
    payload = {"meta": {"symbol": "BTCUSDT"}}
    paths = write_structure_only_artifacts(
        symbol="BTCUSDT",
        structure_payload=payload,
        multi_tf=False,
        interval="1h",
        project_root=tmp_path,
    )
    assert len(paths) == 1
    assert paths[0].startswith("output/")
    written = tmp_path / paths[0]
    assert written.exists()
    assert "BTCUSDT" in written.name
    assert written.name.endswith("_structure.json")


@pytest.mark.asyncio
async def test_analyze_endpoint_save_writes_structure_no_ai() -> None:
    fake_payload = {"meta": {"symbol": "BTCUSDT"}}
    fake_result = type(
        "R",
        (),
        {
            "report_content": "# 结构",
            "structure_payload": fake_payload,
            "multi_tf": False,
        },
    )()

    with (
        patch(
            "app.api.v1.flow_markets.run_structure_only",
            return_value=(fake_result, ""),
        ),
        patch(
            "app.api.v1.flow_markets.write_structure_only_artifacts",
            return_value=["output/BTCUSDT_1h_test_structure.json"],
        ) as mock_write,
    ):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/flow-markets/analyze",
                json={
                    "user_query": "结构",
                    "symbol": "BTCUSDT",
                    "no_ai": True,
                    "save": True,
                },
                headers={"X-API-Key": "dev-no-key"},
            )

    assert r.status_code == 200, r.text
    mock_write.assert_called_once()
    data = r.json()["data"]
    assert data["output_files"] == ["output/BTCUSDT_1h_test_structure.json"]


def test_write_analyze_save_artifacts_mocked_deliverable(tmp_path: Path) -> None:
    deliverable = MagicMock()
    deliverable.model_dump.return_value = {"brief": "test"}

    fake_snap = MagicMock()
    fake_snap.model_dump.return_value = {"structure": True}

    with (
        patch(
            "app.services.analysis_output.build_chan_structure_snapshot",
            return_value=fake_snap,
        ),
        patch(
            "app.services.analysis_output.format_trader_display",
            return_value="trader text",
        ),
    ):
        paths = write_analyze_save_artifacts(
            symbol="ETHUSDT",
            timeframe="4h",
            lookback=100,
            deliverable=deliverable,
            multi_tf=False,
            project_root=tmp_path,
        )

    assert len(paths) == 3
    for rel in paths:
        assert (tmp_path / rel).exists()
