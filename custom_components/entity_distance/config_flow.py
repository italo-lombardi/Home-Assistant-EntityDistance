from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from .const import (
    CONF_DEBOUNCE_S,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
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

ENTITY_DOMAINS = ["person", "device_tracker", "sensor", "zone"]
_CONF_SHOW_ADVANCED = "show_advanced"
_CONF_SHOW_ZONE_THRESHOLDS = "show_zone_thresholds"

_ZONE_OPTIONS_KEYS = {
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_DEBOUNCE_S,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_ZONE_VERY_NEAR_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_FAR_M,
}


class EntityDistanceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        # Abort any other in-progress flow for this handler so pressing X and
        # restarting works cleanly instead of hitting already_in_progress.
        for flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            if flow["flow_id"] != self.flow_id:
                self.hass.config_entries.flow.async_abort(flow["flow_id"])
        errors = {}
        if user_input is not None:
            entity_a = user_input[CONF_ENTITY_A]
            entity_b = user_input[CONF_ENTITY_B]

            if entity_a == entity_b:
                errors["base"] = "same_entity"
            else:
                pair = tuple(sorted([entity_a, entity_b]))
                await self.async_set_unique_id(f"{DOMAIN}_{pair[0]}_{pair[1]}")
                self._abort_if_unique_id_configured()

                self._data.update(user_input)
                return await self.async_step_thresholds()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY_A): EntitySelector(
                        EntitySelectorConfig(domain=ENTITY_DOMAINS)
                    ),
                    vol.Required(CONF_ENTITY_B): EntitySelector(
                        EntitySelectorConfig(domain=ENTITY_DOMAINS)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_thresholds(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input[CONF_EXIT_THRESHOLD_M] < user_input[CONF_ENTRY_THRESHOLD_M]:
                errors["base"] = "exit_below_entry"
            else:
                show_advanced = user_input.pop(_CONF_SHOW_ADVANCED, False)
                show_zone = user_input.pop(_CONF_SHOW_ZONE_THRESHOLDS, False)
                self._data.update(user_input)
                if show_zone:
                    self._data["_show_advanced"] = show_advanced
                    return await self.async_step_zone_thresholds()
                if show_advanced:
                    return await self.async_step_advanced()
                entity_a = self._data[CONF_ENTITY_A]
                entity_b = self._data[CONF_ENTITY_B]
                a_name = entity_a.split(".")[-1].replace("_", " ").title()
                b_name = entity_b.split(".")[-1].replace("_", " ").title()
                clean = {k: v for k, v in self._data.items() if not k.startswith("_")}
                return self.async_create_entry(
                    title=f"{a_name} & {b_name}",
                    data=clean,
                )

        return self.async_show_form(
            step_id="thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENTRY_THRESHOLD_M, default=DEFAULT_ENTRY_THRESHOLD_M
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_EXIT_THRESHOLD_M, default=DEFAULT_EXIT_THRESHOLD_M
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_DEBOUNCE_S, default=DEFAULT_DEBOUNCE_S): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=60,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(_CONF_SHOW_ZONE_THRESHOLDS, default=False): BooleanSelector(),
                    vol.Required(_CONF_SHOW_ADVANCED, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_zone_thresholds(self, user_input=None):
        errors = {}
        if user_input is not None:
            vn = user_input[CONF_ZONE_VERY_NEAR_M]
            n = user_input[CONF_ZONE_NEAR_M]
            m = user_input[CONF_ZONE_MID_M]
            f = user_input[CONF_ZONE_FAR_M]
            if not (vn < n < m < f):
                errors["base"] = "zone_thresholds_not_ascending"
            else:
                show_advanced = self._data.pop("_show_advanced", False)
                self._data.update(user_input)
                if show_advanced:
                    return await self.async_step_advanced()
                entity_a = self._data[CONF_ENTITY_A]
                entity_b = self._data[CONF_ENTITY_B]
                a_name = entity_a.split(".")[-1].replace("_", " ").title()
                b_name = entity_b.split(".")[-1].replace("_", " ").title()
                clean = {k: v for k, v in self._data.items() if not k.startswith("_")}
                return self.async_create_entry(
                    title=f"{a_name} & {b_name}",
                    data=clean,
                )

        return self.async_show_form(
            step_id="zone_thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ZONE_VERY_NEAR_M, default=DEFAULT_ZONE_VERY_NEAR_M
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(CONF_ZONE_NEAR_M, default=DEFAULT_ZONE_NEAR_M): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(CONF_ZONE_MID_M, default=DEFAULT_ZONE_MID_M): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(CONF_ZONE_FAR_M, default=DEFAULT_ZONE_FAR_M): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=200000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            entity_a = self._data[CONF_ENTITY_A]
            entity_b = self._data[CONF_ENTITY_B]
            a_name = entity_a.split(".")[-1].replace("_", " ").title()
            b_name = entity_b.split(".")[-1].replace("_", " ").title()
            clean = {k: v for k, v in self._data.items() if not k.startswith("_")}
            return self.async_create_entry(
                title=f"{a_name} & {b_name}",
                data=clean,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_ACCURACY_M, default=DEFAULT_MAX_ACCURACY_M
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=1000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_MAX_SPEED_KMH, default=DEFAULT_MAX_SPEED_KMH): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=2000,
                            unit_of_measurement="km/h",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_REQUIRE_RELIABLE, default=DEFAULT_REQUIRE_RELIABLE
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_MIN_UPDATES_RELIABLE, default=DEFAULT_MIN_UPDATES_RELIABLE
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=20, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EntityDistanceOptionsFlow()


class EntityDistanceOptionsFlow(config_entries.OptionsFlow):
    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_init(self, user_input=None):
        self._data = dict(self.config_entry.data)
        self._data.update(self.config_entry.options)
        return await self.async_step_thresholds(user_input)

    async def async_step_thresholds(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input[CONF_EXIT_THRESHOLD_M] < user_input[CONF_ENTRY_THRESHOLD_M]:
                errors["base"] = "exit_below_entry"
            else:
                show_advanced = user_input.pop(_CONF_SHOW_ADVANCED, False)
                show_zone = user_input.pop(_CONF_SHOW_ZONE_THRESHOLDS, False)
                self._data.update(user_input)
                if show_zone:
                    self._data["_show_advanced"] = show_advanced
                    return await self.async_step_zone_thresholds()
                if show_advanced:
                    return await self.async_step_advanced()
                return self.async_create_entry(
                    title="",
                    data={k: v for k, v in self._data.items() if k in _ZONE_OPTIONS_KEYS},
                )

        return self.async_show_form(
            step_id="thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENTRY_THRESHOLD_M,
                        default=self._data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_EXIT_THRESHOLD_M,
                        default=self._data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_DEBOUNCE_S,
                        default=self._data.get(CONF_DEBOUNCE_S, DEFAULT_DEBOUNCE_S),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=60,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(_CONF_SHOW_ZONE_THRESHOLDS, default=False): BooleanSelector(),
                    vol.Required(_CONF_SHOW_ADVANCED, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_zone_thresholds(self, user_input=None):
        errors = {}
        if user_input is not None:
            vn = user_input[CONF_ZONE_VERY_NEAR_M]
            n = user_input[CONF_ZONE_NEAR_M]
            m = user_input[CONF_ZONE_MID_M]
            f = user_input[CONF_ZONE_FAR_M]
            if not (vn < n < m < f):
                errors["base"] = "zone_thresholds_not_ascending"
            else:
                show_advanced = self._data.pop("_show_advanced", False)
                self._data.update(user_input)
                if show_advanced:
                    return await self.async_step_advanced()
                return self.async_create_entry(
                    title="",
                    data={k: v for k, v in self._data.items() if k in _ZONE_OPTIONS_KEYS},
                )

        return self.async_show_form(
            step_id="zone_thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ZONE_VERY_NEAR_M,
                        default=self._data.get(CONF_ZONE_VERY_NEAR_M, DEFAULT_ZONE_VERY_NEAR_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_ZONE_NEAR_M,
                        default=self._data.get(CONF_ZONE_NEAR_M, DEFAULT_ZONE_NEAR_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_ZONE_MID_M,
                        default=self._data.get(CONF_ZONE_MID_M, DEFAULT_ZONE_MID_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_ZONE_FAR_M,
                        default=self._data.get(CONF_ZONE_FAR_M, DEFAULT_ZONE_FAR_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=200000, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="",
                data={k: v for k, v in self._data.items() if k in _ZONE_OPTIONS_KEYS},
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_ACCURACY_M,
                        default=self._data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=1000,
                            unit_of_measurement="m",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_SPEED_KMH,
                        default=self._data.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=2000,
                            unit_of_measurement="km/h",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_REQUIRE_RELIABLE,
                        default=self._data.get(CONF_REQUIRE_RELIABLE, DEFAULT_REQUIRE_RELIABLE),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_MIN_UPDATES_RELIABLE,
                        default=self._data.get(
                            CONF_MIN_UPDATES_RELIABLE, DEFAULT_MIN_UPDATES_RELIABLE
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=20, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
