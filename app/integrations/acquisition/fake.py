from __future__ import annotations

from app.integrations.acquisition.base import AcquisitionChannel


def fake_channel() -> AcquisitionChannel:
    return AcquisitionChannel(
        channel_key="fake",
        channel_name="Fake acquisition channel",
        status="disabled",
        tier="planned",
        description="Test-only placeholder channel.",
        enabled=False,
        planned_version="test",
    )
