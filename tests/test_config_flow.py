"""Tests for config flow validation."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import DATA_COMPONENTS
import pytest
from pytest_homeassistant_custom_component.common import mock_config_flow

from custom_components.entity_distance.config_flow import EntityDistanceConfigFlow
from custom_components.entity_distance.const import (
    CONF_DEBOUNCE_S,
    CONF_ENTITIES,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_ZONE_FAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_VERY_NEAR_M,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_ZONE_FAR_M,
    DEFAULT_ZONE_MID_M,
    DEFAULT_ZONE_NEAR_M,
    DEFAULT_ZONE_VERY_NEAR_M,
    DOMAIN,
)

_USER_STEP_TWO_ENTITIES = {
    CONF_ENTITIES: ["person.alice", "person.bob"],
}

_USER_STEP_THREE_ENTITIES = {
    CONF_ENTITIES: ["person.alice", "person.bob", "person.carol"],
}

_THRESHOLDS_NO_EXTRAS = {
    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
    "show_zone_thresholds": False,
    "show_advanced": False,
}

_VALID_ZONE_THRESHOLDS = {
    CONF_ZONE_VERY_NEAR_M: DEFAULT_ZONE_VERY_NEAR_M,
    CONF_ZONE_NEAR_M: DEFAULT_ZONE_NEAR_M,
    CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
    CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
}


@pytest.fixture
def flow_manager(hass):
    """Return the config_entries flow manager with our handler registered."""
    hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
    with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
        yield hass.config_entries.flow


class TestConfigFlowUserStep:
    async def test_too_few_entities_returns_error(self, flow_manager):
        result = await flow_manager.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input={CONF_ENTITIES: ["person.alice"]},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"]["base"] == "too_few_entities"

    async def test_duplicate_entities_returns_error(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input={CONF_ENTITIES: ["person.alice", "person.alice"]},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"]["base"] == "duplicate_entities"

    async def test_two_entities_advances_to_thresholds(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input=_USER_STEP_TWO_ENTITIES,
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "thresholds"

    async def test_three_entities_advances_to_thresholds(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input=_USER_STEP_THREE_ENTITIES,
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "thresholds"

    async def test_too_many_entities_returns_error(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input={
                CONF_ENTITIES: [
                    "person.a",
                    "person.b",
                    "person.c",
                    "person.d",
                    "person.e",
                    "person.f",
                ]
            },
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"]["base"] == "too_many_entities"

    async def test_five_entities_advances_to_thresholds(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input={
                CONF_ENTITIES: [
                    "person.a",
                    "person.b",
                    "person.c",
                    "person.d",
                    "person.e",
                ]
            },
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "thresholds"

    async def _init_to_thresholds(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"], user_input=_USER_STEP_TWO_ENTITIES
        )
        assert result2["step_id"] == "thresholds"
        return result2["flow_id"]

    async def test_exit_below_entry_returns_error(self, flow_manager):
        flow_id = await self._init_to_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ENTRY_THRESHOLD_M: 500,
                CONF_EXIT_THRESHOLD_M: 300,
                CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                "show_zone_thresholds": False,
                "show_advanced": False,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "exit_below_entry"

    async def test_show_zone_thresholds_false_creates_entry(self, flow_manager):
        flow_id = await self._init_to_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input=_THRESHOLDS_NO_EXTRAS,
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_ENTITIES in result["data"]

    async def test_show_advanced_key_not_in_entry_data(self, flow_manager):
        flow_id = await self._init_to_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input=_THRESHOLDS_NO_EXTRAS,
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "_show_advanced" not in result["data"]
        assert "show_advanced" not in result["data"]
        assert "show_zone_thresholds" not in result["data"]

    async def test_show_zone_thresholds_true_routes_to_zone_step(self, flow_manager):
        flow_id = await self._init_to_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                "show_zone_thresholds": True,
                "show_advanced": False,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zone_thresholds"


class TestConfigFlowZoneThresholdsStep:
    async def _init_to_zone_thresholds(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        flow_id = result["flow_id"]
        await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
        result2 = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                "show_zone_thresholds": True,
                "show_advanced": False,
            },
        )
        assert result2["step_id"] == "zone_thresholds"
        return flow_id

    async def test_equal_vn_n_returns_not_ascending_error(self, flow_manager):
        flow_id = await self._init_to_zone_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ZONE_VERY_NEAR_M: 500,
                CONF_ZONE_NEAR_M: 500,
                CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
                CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_n_greater_than_m_returns_not_ascending_error(self, flow_manager):
        flow_id = await self._init_to_zone_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ZONE_VERY_NEAR_M: 100,
                CONF_ZONE_NEAR_M: 2500,
                CONF_ZONE_MID_M: 2000,
                CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_m_greater_than_f_returns_not_ascending_error(self, flow_manager):
        flow_id = await self._init_to_zone_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_ZONE_VERY_NEAR_M: 100,
                CONF_ZONE_NEAR_M: 500,
                CONF_ZONE_MID_M: 12000,
                CONF_ZONE_FAR_M: 10000,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_valid_ascending_thresholds_creates_entry(self, flow_manager):
        flow_id = await self._init_to_zone_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input=_VALID_ZONE_THRESHOLDS,
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        data = result["data"]
        assert data[CONF_ZONE_VERY_NEAR_M] == DEFAULT_ZONE_VERY_NEAR_M
        assert data[CONF_ZONE_NEAR_M] == DEFAULT_ZONE_NEAR_M
        assert data[CONF_ZONE_MID_M] == DEFAULT_ZONE_MID_M
        assert data[CONF_ZONE_FAR_M] == DEFAULT_ZONE_FAR_M

    async def test_show_advanced_key_absent_from_created_entry(self, flow_manager):
        flow_id = await self._init_to_zone_thresholds(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input=_VALID_ZONE_THRESHOLDS,
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "_show_advanced" not in result["data"]
        assert "show_advanced" not in result["data"]

    async def test_three_entities_entry_contains_all_three(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        flow_id = result["flow_id"]
        await flow_manager.async_configure(flow_id, user_input=_USER_STEP_THREE_ENTITIES)
        result2 = await flow_manager.async_configure(flow_id, user_input=_THRESHOLDS_NO_EXTRAS)
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        entities = result2["data"][CONF_ENTITIES]
        assert set(entities) == {"person.alice", "person.bob", "person.carol"}
