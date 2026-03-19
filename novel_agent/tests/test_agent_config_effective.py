"""Tests for AgentConfigManager effective config resolution."""

from pathlib import Path
import tempfile

import pytest

from novel_agent.agent_config import AgentConfigManager


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield AgentConfigManager(config_dir=Path(temp_dir))


def _set_global(manager: AgentConfigManager):
    manager.set_global_config(
        api_base="https://global.example.com/v1",
        api_key="global-key",
        model="global-model",
        temperature=0.31,
        max_tokens=2048,
    )


def test_effective_config_uses_global_when_use_global_enabled(manager):
    _set_global(manager)
    manager.update_config(
        "Communicator",
        use_global=True,
        api_base="https://agent.example.com/v1",
        api_key="agent-key",
        model="agent-model",
        temperature=0.88,
        max_tokens=1234,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is True
    assert effective.api_base == "https://global.example.com/v1"
    assert effective.api_key == "global-key"
    assert effective.model == "global-model"
    assert effective.temperature == pytest.approx(0.31)
    assert effective.max_tokens == 2048


def test_effective_config_fills_missing_fields_from_global_for_override(manager):
    _set_global(manager)
    manager.update_config(
        "Communicator",
        use_global=False,
        api_base="https://agent.example.com/v1",
        api_key="",
        model="",
        temperature=0.72,
        max_tokens=1666,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is False
    assert effective.api_base == "https://agent.example.com/v1"
    assert effective.api_key == "global-key"
    assert effective.model == "global-model"
    assert effective.temperature == pytest.approx(0.72)
    assert effective.max_tokens == 1666


def test_effective_config_preserves_complete_override(manager):
    _set_global(manager)
    manager.update_config(
        "Communicator",
        use_global=False,
        api_base="https://agent.example.com/v1",
        api_key="agent-key",
        model="agent-model",
        temperature=0.91,
        max_tokens=1999,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is False
    assert effective.api_base == "https://agent.example.com/v1"
    assert effective.api_key == "agent-key"
    assert effective.model == "agent-model"
    assert effective.temperature == pytest.approx(0.91)
    assert effective.max_tokens == 1999


def test_effective_config_without_global_keeps_original_override(manager):
    manager.update_config(
        "Communicator",
        use_global=False,
        api_base="https://agent.example.com/v1",
        api_key="",
        model="agent-model",
        temperature=0.65,
        max_tokens=1888,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is False
    assert effective.api_base == "https://agent.example.com/v1"
    assert effective.api_key == ""
    assert effective.model == "agent-model"
    assert effective.temperature == pytest.approx(0.65)
    assert effective.max_tokens == 1888


def test_effective_config_use_global_falls_back_to_agent_model_when_global_model_empty(manager):
    manager.set_global_config(
        api_base="https://global.example.com/v1",
        api_key="global-key",
        model="",
        temperature=0.31,
        max_tokens=2048,
    )
    manager.update_config(
        "Communicator",
        use_global=True,
        api_base="https://agent.example.com/v1",
        api_key="",
        model="agent-model",
        temperature=0.88,
        max_tokens=1234,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is True
    assert effective.api_base == "https://global.example.com/v1"
    assert effective.api_key == "global-key"
    assert effective.model == "agent-model"
    assert effective.temperature == pytest.approx(0.88)
    assert effective.max_tokens == 1234


def test_effective_config_override_still_fills_key_when_global_model_empty(manager):
    manager.set_global_config(
        api_base="https://global.example.com/v1",
        api_key="global-key",
        model="",
        temperature=0.31,
        max_tokens=2048,
    )
    manager.update_config(
        "Communicator",
        use_global=False,
        api_base="https://agent.example.com/v1",
        api_key="",
        model="kimi-k2.5",
        temperature=0.72,
        max_tokens=1666,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is False
    assert effective.api_base == "https://agent.example.com/v1"
    assert effective.api_key == "global-key"
    assert effective.model == "kimi-k2.5"
    assert effective.temperature == pytest.approx(0.72)
    assert effective.max_tokens == 1666


def test_effective_config_prefers_api_config_id_credentials_over_global(manager):
    _set_global(manager)
    selected = manager.add_api_config(
        name="Routin",
        api_base="https://api.routin.ai/v1",
        api_key="routin-key",
        models=["kimi-k2.5"],
    )

    manager.update_config(
        "Communicator",
        use_global=False,
        api_config_id=selected.id,
        api_base="",
        api_key="",
        model="",
        temperature=0.77,
        max_tokens=3333,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.use_global is False
    assert effective.api_base == "https://api.routin.ai/v1"
    assert effective.api_key == "routin-key"
    assert effective.model == "kimi-k2.5"
    assert effective.temperature == pytest.approx(0.77)
    assert effective.max_tokens == 3333


def test_effective_config_keeps_selected_model_with_api_config_id(manager):
    _set_global(manager)
    selected = manager.add_api_config(
        name="Doubao",
        api_base="https://api.doubao.example/v1",
        api_key="doubao-key",
        models=["doubao-seed-2.0-code", "doubao-lite"],
    )

    manager.update_config(
        "Communicator",
        use_global=False,
        api_config_id=selected.id,
        api_base="",
        api_key="",
        model="doubao-seed-2.0-code",
        temperature=0.66,
        max_tokens=4096,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.api_base == "https://api.doubao.example/v1"
    assert effective.api_key == "doubao-key"
    assert effective.model == "doubao-seed-2.0-code"
