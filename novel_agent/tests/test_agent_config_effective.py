"""Tests for AgentConfigManager effective config resolution."""

import json
from pathlib import Path
import tempfile

import pytest

from novel_agent.agent_config import AgentConfigManager
from novel_agent.utils.llm_params import PROVIDER_SAFE_MAX_TOKENS


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


def test_set_global_config_caps_oversized_max_tokens(manager):
    manager.set_global_config(
        api_base="https://global.example.com/v1",
        api_key="global-key",
        model="global-model",
        temperature=0.31,
        max_tokens=18888,
    )

    effective = manager.get_global_config()

    assert effective.max_tokens == PROVIDER_SAFE_MAX_TOKENS


def test_update_agent_config_caps_oversized_max_tokens(manager):
    manager.update_config(
        "Communicator",
        use_global=False,
        api_base="https://agent.example.com/v1",
        api_key="agent-key",
        model="agent-model",
        temperature=0.88,
        max_tokens=8888,
    )

    effective = manager.get_effective_config("Communicator")

    assert effective.max_tokens == PROVIDER_SAFE_MAX_TOKENS


def test_loading_existing_config_files_caps_oversized_max_tokens(tmp_path):
    (tmp_path / "agent_configs.json").write_text(
        json.dumps(
            {
                "Communicator": {
                    "agent_name": "Communicator",
                    "use_global": False,
                    "api_base": "https://agent.example.com/v1",
                    "api_key": "agent-key",
                    "model": "agent-model",
                    "temperature": 0.7,
                    "max_tokens": 99999,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "global_api_config.json").write_text(
        json.dumps(
            {
                "configs": [
                    {
                        "id": "cfg1",
                        "name": "default",
                        "api_base": "https://global.example.com/v1",
                        "api_key": "global-key",
                        "models": ["global-model"],
                        "temperature": 0.7,
                        "max_tokens": 18888,
                        "created_at": "2026-03-25T00:00:00",
                    }
                ],
                "active_config_id": "cfg1",
                "active_model": "global-model",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = AgentConfigManager(config_dir=tmp_path)

    assert manager.get_config("Communicator").max_tokens == PROVIDER_SAFE_MAX_TOKENS
    assert manager.get_global_config().max_tokens == PROVIDER_SAFE_MAX_TOKENS
