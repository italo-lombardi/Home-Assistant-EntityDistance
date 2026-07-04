"""Tests for config flow validation."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import DATA_COMPONENTS
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_config_flow,
)

from custom_components.entity_distance.config_flow import EntityDistanceConfigFlow
from custom_components.entity_distance.const import (
    CONF_DEBOUNCE_S,
    CONF_ENTITIES,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_PROXIMITY_ZONE,
    CONF_REQUIRE_RELIABLE,
    CONF_ZONE_FAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_VERY_NEAR_M,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_RELIABLE,
    DEFAULT_PROXIMITY_ZONE,
    DEFAULT_REQUIRE_RELIABLE,
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

_DISTANCES_DEFAULTS = {
    CONF_PROXIMITY_ZONE: DEFAULT_PROXIMITY_ZONE,
    CONF_ZONE_VERY_NEAR_M: DEFAULT_ZONE_VERY_NEAR_M,
    CONF_ZONE_NEAR_M: DEFAULT_ZONE_NEAR_M,
    CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
    CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
    "show_advanced": False,
}

_OPTIONS_ADVANCED = {
    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
}


@pytest.fixture
def flow_manager(hass):
    """Return the config_entries flow manager with our handler registered."""
    hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
    with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
        yield hass.config_entries.flow


def test_default_debounce_is_zero():
    assert DEFAULT_DEBOUNCE_S == 0


def test_default_proximity_zone_is_very_near():
    assert DEFAULT_PROXIMITY_ZONE == "very_near"


class TestConfigFlowUserStep:
    async def test_too_few_entities_returns_error(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
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

    async def test_two_entities_advances_to_distances(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input=_USER_STEP_TWO_ENTITIES,
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "distances"

    async def test_three_entities_advances_to_distances(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"],
            user_input=_USER_STEP_THREE_ENTITIES,
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "distances"

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

    async def test_five_entities_advances_to_distances(self, flow_manager):
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
        assert result2["step_id"] == "distances"

    async def _init_to_distances(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        result2 = await flow_manager.async_configure(
            result["flow_id"], user_input=_USER_STEP_TWO_ENTITIES
        )
        assert result2["step_id"] == "distances"
        return result2["flow_id"]

    async def test_valid_distances_creates_entry(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        result = await flow_manager.async_configure(flow_id, user_input=_DISTANCES_DEFAULTS)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert CONF_ENTITIES in result["data"]

    async def test_show_advanced_key_not_in_entry_data(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        result = await flow_manager.async_configure(flow_id, user_input=_DISTANCES_DEFAULTS)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "show_advanced" not in result["data"]
        assert "_show_advanced" not in result["data"]

    async def test_show_advanced_true_routes_to_advanced(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        user_input = {**_DISTANCES_DEFAULTS, "show_advanced": True}
        result = await flow_manager.async_configure(flow_id, user_input=user_input)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced"

    async def test_zone_thresholds_not_ascending_returns_error(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_PROXIMITY_ZONE: "very_near",
                CONF_ZONE_VERY_NEAR_M: 500,
                CONF_ZONE_NEAR_M: 500,
                CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
                CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
                "show_advanced": False,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_n_greater_than_m_returns_error(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        result = await flow_manager.async_configure(
            flow_id,
            user_input={
                CONF_PROXIMITY_ZONE: "very_near",
                CONF_ZONE_VERY_NEAR_M: 100,
                CONF_ZONE_NEAR_M: 2500,
                CONF_ZONE_MID_M: 2000,
                CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
                "show_advanced": False,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_entry_contains_proximity_zone(self, flow_manager):
        flow_id = await self._init_to_distances(flow_manager)
        result = await flow_manager.async_configure(flow_id, user_input=_DISTANCES_DEFAULTS)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PROXIMITY_ZONE] == DEFAULT_PROXIMITY_ZONE

    async def test_three_entities_entry_contains_all_three(self, flow_manager):
        result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
        flow_id = result["flow_id"]
        await flow_manager.async_configure(flow_id, user_input=_USER_STEP_THREE_ENTITIES)
        result2 = await flow_manager.async_configure(flow_id, user_input=_DISTANCES_DEFAULTS)
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        entities = result2["data"][CONF_ENTITIES]
        assert set(entities) == {"person.alice", "person.bob", "person.carol"}


class TestConfigFlowDistancesToAdvanced:
    async def test_advanced_step_submit_creates_entry(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            flow_manager = hass.config_entries.flow
            result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            flow_id = result["flow_id"]
            await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
            await flow_manager.async_configure(
                flow_id,
                user_input={**_DISTANCES_DEFAULTS, "show_advanced": True},
            )
            result3 = await flow_manager.async_configure(flow_id, user_input=_OPTIONS_ADVANCED)
            assert result3["type"] == FlowResultType.CREATE_ENTRY
            assert CONF_ENTITIES in result3["data"]
            assert result3["data"][CONF_MAX_ACCURACY_M] == DEFAULT_MAX_ACCURACY_M


class TestConfigFlowDuplicateInProgressAbort:
    async def test_second_flow_aborts_first(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result1 = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_USER}
            )
            assert result1["type"] == FlowResultType.FORM
            result2 = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_USER}
            )
            assert result2["type"] == FlowResultType.FORM
            in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
            flow_ids = [f["flow_id"] for f in in_progress]
            assert result1["flow_id"] not in flow_ids
            assert result2["flow_id"] in flow_ids


# ---------------------------------------------------------------------------
# Options flow fixtures and helpers
# ---------------------------------------------------------------------------

_ENTRY_DATA = {
    CONF_ENTITIES: ["person.alice", "person.bob"],
    CONF_PROXIMITY_ZONE: DEFAULT_PROXIMITY_ZONE,
    CONF_ZONE_VERY_NEAR_M: DEFAULT_ZONE_VERY_NEAR_M,
    CONF_ZONE_NEAR_M: DEFAULT_ZONE_NEAR_M,
    CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
    CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
}


@pytest.fixture
def options_flow_entry(hass):
    hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_ENTRY_DATA,
        options={},
        version=3,
        minor_version=1,
        title="Alice & Bob",
    )
    entry.add_to_hass(hass)
    return entry


class TestOptionsFlowInit:
    async def test_options_flow_initialises_and_shows_distances_form(
        self, hass, options_flow_entry
    ):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "distances"

    async def test_options_flow_form_has_schema(self, hass, options_flow_entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
        assert result["step_id"] == "distances"
        assert result["data_schema"] is not None


class TestOptionsFlowDistances:
    async def _init_options(self, hass, entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(entry.entry_id)
        return result["flow_id"]

    async def test_valid_distances_creates_entry(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id, user_input=_DISTANCES_DEFAULTS
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_non_ascending_zones_returns_error(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_PROXIMITY_ZONE: "very_near",
                    CONF_ZONE_VERY_NEAR_M: 500,
                    CONF_ZONE_NEAR_M: 500,
                    CONF_ZONE_MID_M: DEFAULT_ZONE_MID_M,
                    CONF_ZONE_FAR_M: DEFAULT_ZONE_FAR_M,
                    "show_advanced": False,
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "zone_thresholds_not_ascending"

    async def test_proximity_zone_saved_to_options(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={**_DISTANCES_DEFAULTS, CONF_PROXIMITY_ZONE: "near"},
            )
        assert options_flow_entry.options[CONF_PROXIMITY_ZONE] == "near"

    async def test_show_advanced_true_routes_to_advanced_step(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input={**_DISTANCES_DEFAULTS, "show_advanced": True},
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced"

    async def test_entities_not_in_saved_options(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id, user_input=_DISTANCES_DEFAULTS
            )
        assert CONF_ENTITIES not in options_flow_entry.options


class TestOptionsFlowAdvanced:
    async def _init_to_advanced(self, hass, entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            flow_id = result["flow_id"]
            result2 = await hass.config_entries.options.async_configure(
                flow_id,
                user_input={**_DISTANCES_DEFAULTS, "show_advanced": True},
            )
        assert result2["step_id"] == "advanced"
        return flow_id

    async def test_advanced_shows_form(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(flow_id, user_input=None)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced"

    async def test_advanced_submit_creates_entry(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id, user_input=_OPTIONS_ADVANCED
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_advanced_values_saved_to_entry_options(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    CONF_MAX_ACCURACY_M: 300,
                    CONF_MAX_SPEED_KMH: 200,
                    CONF_REQUIRE_RELIABLE: True,
                    CONF_MIN_UPDATES_RELIABLE: 5,
                },
            )
        opts = options_flow_entry.options
        assert opts[CONF_MAX_ACCURACY_M] == 300
        assert opts[CONF_MAX_SPEED_KMH] == 200
        assert opts[CONF_REQUIRE_RELIABLE] is True
        assert opts[CONF_MIN_UPDATES_RELIABLE] == 5

    async def test_options_only_contain_zone_option_keys(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(flow_id, user_input=_OPTIONS_ADVANCED)
        opts = options_flow_entry.options
        assert CONF_ENTITIES not in opts
        from custom_components.entity_distance.config_flow import _ZONE_OPTIONS_KEYS

        assert all(k in _ZONE_OPTIONS_KEYS for k in opts)

    async def test_distances_and_advanced_saves_all_keys(self, hass, options_flow_entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
            flow_id = result["flow_id"]
            await hass.config_entries.options.async_configure(
                flow_id, user_input={**_DISTANCES_DEFAULTS, "show_advanced": True}
            )
            result3 = await hass.config_entries.options.async_configure(
                flow_id, user_input=_OPTIONS_ADVANCED
            )
        assert result3["type"] == FlowResultType.CREATE_ENTRY
        opts = options_flow_entry.options
        assert opts[CONF_ZONE_VERY_NEAR_M] == DEFAULT_ZONE_VERY_NEAR_M
        assert opts[CONF_MAX_ACCURACY_M] == DEFAULT_MAX_ACCURACY_M
        assert CONF_ENTITIES not in opts
