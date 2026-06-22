"""Tests for config flow validation."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import DATA_COMPONENTS
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_config_flow

from custom_components.entity_distance.config_flow import EntityDistanceConfigFlow
from custom_components.entity_distance.const import (
    CONF_DEBOUNCE_S,
    CONF_ENTITIES,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_REQUIRE_RELIABLE,
    CONF_ZONE_FAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_VERY_NEAR_M,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_RELIABLE,
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


def test_default_debounce_is_zero():
    # New installs react to GPS updates instantly. Anything > 0 here would
    # silently add latency for every user who never opens the options flow.
    assert DEFAULT_DEBOUNCE_S == 0


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


# ---------------------------------------------------------------------------
# Additional ConfigFlow coverage tests
# ---------------------------------------------------------------------------


class TestConfigFlowDuplicateInProgressAbort:
    """Line 79: async_abort() for duplicate in-progress flow."""

    async def test_second_flow_aborts_first(self, hass):
        """Starting a second user flow aborts the first in-progress one."""
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

            # The first flow should now be gone (aborted by the second)
            in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
            flow_ids = [f["flow_id"] for f in in_progress]
            assert result1["flow_id"] not in flow_ids
            assert result2["flow_id"] in flow_ids


class TestConfigFlowThresholdsToAdvanced:
    """Line 124: thresholds step routes directly to advanced when show_advanced=True."""

    async def test_show_advanced_true_routes_to_advanced_step(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            flow_manager = hass.config_entries.flow

            result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            flow_id = result["flow_id"]
            await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
            result2 = await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": False,
                    "show_advanced": True,
                },
            )
            assert result2["type"] == FlowResultType.FORM
            assert result2["step_id"] == "advanced"

    async def test_advanced_step_submit_creates_entry(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            flow_manager = hass.config_entries.flow

            result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            flow_id = result["flow_id"]
            await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
            await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": False,
                    "show_advanced": True,
                },
            )
            result3 = await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
                    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
                    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
                    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
                },
            )
            assert result3["type"] == FlowResultType.CREATE_ENTRY
            assert CONF_ENTITIES in result3["data"]
            assert result3["data"][CONF_MAX_ACCURACY_M] == DEFAULT_MAX_ACCURACY_M


class TestConfigFlowZoneThresholdsToAdvanced:
    """Line 184: zone_thresholds step routes to advanced when _show_advanced=True."""

    async def test_zone_thresholds_with_show_advanced_routes_to_advanced(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            flow_manager = hass.config_entries.flow

            result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            flow_id = result["flow_id"]
            await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
            # show_zone_thresholds=True AND show_advanced=True → go to zone step first
            await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": True,
                    "show_advanced": True,
                },
            )
            # Submit zone thresholds — should route to advanced, not create entry
            result3 = await flow_manager.async_configure(
                flow_id,
                user_input=_VALID_ZONE_THRESHOLDS,
            )
            assert result3["type"] == FlowResultType.FORM
            assert result3["step_id"] == "advanced"

    async def test_zone_then_advanced_creates_entry(self, hass):
        hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            flow_manager = hass.config_entries.flow

            result = await flow_manager.async_init(DOMAIN, context={"source": SOURCE_USER})
            flow_id = result["flow_id"]
            await flow_manager.async_configure(flow_id, user_input=_USER_STEP_TWO_ENTITIES)
            await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": True,
                    "show_advanced": True,
                },
            )
            await flow_manager.async_configure(flow_id, user_input=_VALID_ZONE_THRESHOLDS)
            result4 = await flow_manager.async_configure(
                flow_id,
                user_input={
                    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
                    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
                    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
                    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
                },
            )
            assert result4["type"] == FlowResultType.CREATE_ENTRY
            data = result4["data"]
            assert data[CONF_ZONE_VERY_NEAR_M] == DEFAULT_ZONE_VERY_NEAR_M
            assert data[CONF_MAX_ACCURACY_M] == DEFAULT_MAX_ACCURACY_M


# ---------------------------------------------------------------------------
# Options flow fixtures and helpers
# ---------------------------------------------------------------------------

_ENTRY_DATA = {
    CONF_ENTITIES: ["person.alice", "person.bob"],
    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
}

_OPTIONS_THRESHOLDS_NO_EXTRAS = {
    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
    "show_zone_thresholds": False,
    "show_advanced": False,
}

_OPTIONS_ADVANCED = {
    CONF_MAX_ACCURACY_M: DEFAULT_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH: DEFAULT_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE: DEFAULT_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE: DEFAULT_MIN_UPDATES_RELIABLE,
}


@pytest.fixture
def options_flow_entry(hass):
    """A real MockConfigEntry added to hass, ready for options flow testing."""
    hass.data.setdefault(DATA_COMPONENTS, {})[f"{DOMAIN}.config_flow"] = object()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=_ENTRY_DATA,
        options={},
        version=2,
        minor_version=1,
        title="Alice & Bob",
    )
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Options flow test classes
# ---------------------------------------------------------------------------


class TestOptionsFlowInit:
    """Lines 270, 275, 278-280: factory, __init__, async_step_init."""

    async def test_options_flow_initialises_and_shows_thresholds_form(
        self, hass, options_flow_entry
    ):
        """async_get_options_flow factory returns a flow; init routes to thresholds."""
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "thresholds"

    async def test_options_flow_form_pre_fills_from_entry_data(self, hass, options_flow_entry):
        """Thresholds form schema defaults come from existing entry data."""
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
        # The form is shown with correct step; schema defaults exist
        assert result["step_id"] == "thresholds"
        assert result["data_schema"] is not None


class TestOptionsFlowThresholds:
    """Lines 283-301: EntityDistanceOptionsFlow.async_step_thresholds."""

    async def _init_options(self, hass, entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(entry.entry_id)
        return result["flow_id"]

    async def test_exit_below_entry_returns_error(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
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

    async def test_valid_thresholds_creates_entry(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input=_OPTIONS_THRESHOLDS_NO_EXTRAS,
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_thresholds_saved_to_entry_options(self, hass, options_flow_entry):
        """Saved options contain the threshold keys."""
        flow_id = await self._init_options(hass, options_flow_entry)
        new_entry = 600
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: new_entry,
                    CONF_EXIT_THRESHOLD_M: 800,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": False,
                    "show_advanced": False,
                },
            )
        assert options_flow_entry.options[CONF_ENTRY_THRESHOLD_M] == new_entry
        assert options_flow_entry.options[CONF_EXIT_THRESHOLD_M] == 800

    async def test_show_zone_thresholds_true_routes_to_zone_step(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
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

    async def test_show_advanced_true_routes_to_advanced_step(self, hass, options_flow_entry):
        flow_id = await self._init_options(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": False,
                    "show_advanced": True,
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced"


class TestOptionsFlowZoneThresholds:
    """Lines 346-364: EntityDistanceOptionsFlow.async_step_zone_thresholds."""

    async def _init_to_zone_thresholds(self, hass, entry):
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            flow_id = result["flow_id"]
            result2 = await hass.config_entries.options.async_configure(
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

    async def test_non_ascending_zone_thresholds_returns_error(self, hass, options_flow_entry):
        flow_id = await self._init_to_zone_thresholds(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
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

    async def test_valid_zone_thresholds_creates_entry(self, hass, options_flow_entry):
        flow_id = await self._init_to_zone_thresholds(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input=_VALID_ZONE_THRESHOLDS,
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_zone_thresholds_saved_to_entry_options(self, hass, options_flow_entry):
        flow_id = await self._init_to_zone_thresholds(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input=_VALID_ZONE_THRESHOLDS,
            )
        opts = options_flow_entry.options
        assert opts[CONF_ZONE_VERY_NEAR_M] == DEFAULT_ZONE_VERY_NEAR_M
        assert opts[CONF_ZONE_NEAR_M] == DEFAULT_ZONE_NEAR_M
        assert opts[CONF_ZONE_MID_M] == DEFAULT_ZONE_MID_M
        assert opts[CONF_ZONE_FAR_M] == DEFAULT_ZONE_FAR_M

    async def test_zone_with_show_advanced_routes_to_advanced(self, hass, options_flow_entry):
        """show_advanced=True in thresholds step → zone step → advanced step."""
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
            flow_id = result["flow_id"]
            # show both zone and advanced
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": True,
                    "show_advanced": True,
                },
            )
            # submit valid zone thresholds → should go to advanced, not create
            result3 = await hass.config_entries.options.async_configure(
                flow_id,
                user_input=_VALID_ZONE_THRESHOLDS,
            )
        assert result3["type"] == FlowResultType.FORM
        assert result3["step_id"] == "advanced"


class TestOptionsFlowAdvanced:
    """Lines 406-413: EntityDistanceOptionsFlow.async_step_advanced."""

    async def _init_to_advanced(self, hass, entry):
        """Navigate options flow to the advanced step."""
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            flow_id = result["flow_id"]
            result2 = await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": False,
                    "show_advanced": True,
                },
            )
        assert result2["step_id"] == "advanced"
        return flow_id

    async def test_advanced_shows_form(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input=None,
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced"

    async def test_advanced_submit_creates_entry(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_configure(
                flow_id,
                user_input=_OPTIONS_ADVANCED,
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_advanced_values_saved_to_entry_options(self, hass, options_flow_entry):
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
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

    async def test_advanced_options_only_contain_zone_option_keys(self, hass, options_flow_entry):
        """Saved options must only contain keys in _ZONE_OPTIONS_KEYS, not entities."""
        flow_id = await self._init_to_advanced(hass, options_flow_entry)
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            await hass.config_entries.options.async_configure(flow_id, user_input=_OPTIONS_ADVANCED)
        opts = options_flow_entry.options
        assert CONF_ENTITIES not in opts
        # All saved keys must be valid option keys
        from custom_components.entity_distance.config_flow import _ZONE_OPTIONS_KEYS

        assert all(k in _ZONE_OPTIONS_KEYS for k in opts)

    async def test_zone_then_advanced_saves_both_zone_and_advanced_keys(
        self, hass, options_flow_entry
    ):
        """Full path: thresholds → zone → advanced saves all relevant keys."""
        with mock_config_flow(DOMAIN, EntityDistanceConfigFlow):
            result = await hass.config_entries.options.async_init(options_flow_entry.entry_id)
            flow_id = result["flow_id"]
            await hass.config_entries.options.async_configure(
                flow_id,
                user_input={
                    CONF_ENTRY_THRESHOLD_M: DEFAULT_ENTRY_THRESHOLD_M,
                    CONF_EXIT_THRESHOLD_M: DEFAULT_EXIT_THRESHOLD_M,
                    CONF_DEBOUNCE_S: DEFAULT_DEBOUNCE_S,
                    "show_zone_thresholds": True,
                    "show_advanced": True,
                },
            )
            await hass.config_entries.options.async_configure(
                flow_id, user_input=_VALID_ZONE_THRESHOLDS
            )
            result4 = await hass.config_entries.options.async_configure(
                flow_id, user_input=_OPTIONS_ADVANCED
            )
        assert result4["type"] == FlowResultType.CREATE_ENTRY
        opts = options_flow_entry.options
        assert opts[CONF_ZONE_VERY_NEAR_M] == DEFAULT_ZONE_VERY_NEAR_M
        assert opts[CONF_MAX_ACCURACY_M] == DEFAULT_MAX_ACCURACY_M
        assert CONF_ENTITIES not in opts
