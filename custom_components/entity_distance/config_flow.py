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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_NEAR,
    CONF_DEBOUNCE_S,
    CONF_ENTITIES,
    CONF_GRACE_WINDOW_S,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_PROXIMITY_ZONE,
    CONF_REQUIRE_RELIABLE,
    CONF_RESYNC_HOLD_S,
    CONF_RESYNC_SILENCE_S,
    CONF_ZONE_FAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_VERY_NEAR_M,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_GRACE_WINDOW_S,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_RELIABLE,
    DEFAULT_PROXIMITY_ZONE,
    DEFAULT_REQUIRE_RELIABLE,
    DEFAULT_RESYNC_HOLD_S,
    DEFAULT_RESYNC_SILENCE_S,
    DEFAULT_ZONE_FAR_M,
    DEFAULT_ZONE_MID_M,
    DEFAULT_ZONE_NEAR_M,
    DEFAULT_ZONE_VERY_NEAR_M,
    DOMAIN,
    MAX_GRACE_WINDOW_S,
    MAX_GROUP_ENTITIES,
    MAX_RESYNC_HOLD_S,
    MAX_RESYNC_SILENCE_S,
    MIN_GRACE_WINDOW_S,
    MIN_RESYNC_HOLD_S,
    MIN_RESYNC_SILENCE_S,
)

ENTITY_DOMAINS = ["person", "device_tracker", "sensor", "zone"]
_CONF_SHOW_ADVANCED = "show_advanced"

# Keys persisted in options (not entry.data) — CONF_ENTITIES lives in entry.data, not here.
_ZONE_OPTIONS_KEYS = {
    CONF_PROXIMITY_ZONE,
    CONF_DEBOUNCE_S,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_REQUIRE_RELIABLE,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_GRACE_WINDOW_S,
    CONF_RESYNC_SILENCE_S,
    CONF_RESYNC_HOLD_S,
    CONF_ZONE_VERY_NEAR_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_FAR_M,
}

_PROXIMITY_ZONE_OPTIONS = [
    BUCKET_VERY_NEAR,
    BUCKET_NEAR,
    BUCKET_MID,
    BUCKET_FAR,
]


def _entry_title(entities: list[str]) -> str:
    names = [e.split(".")[-1].replace("_", " ").title() for e in entities]
    return " & ".join(names)


def _distances_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ZONE_VERY_NEAR_M,
                default=defaults.get(CONF_ZONE_VERY_NEAR_M, DEFAULT_ZONE_VERY_NEAR_M),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=50000,
                    unit_of_measurement="m",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_ZONE_NEAR_M,
                default=defaults.get(CONF_ZONE_NEAR_M, DEFAULT_ZONE_NEAR_M),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=50000,
                    unit_of_measurement="m",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_ZONE_MID_M,
                default=defaults.get(CONF_ZONE_MID_M, DEFAULT_ZONE_MID_M),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=100000,
                    unit_of_measurement="m",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_ZONE_FAR_M,
                default=defaults.get(CONF_ZONE_FAR_M, DEFAULT_ZONE_FAR_M),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=200000,
                    unit_of_measurement="m",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_PROXIMITY_ZONE,
                default=defaults.get(CONF_PROXIMITY_ZONE, DEFAULT_PROXIMITY_ZONE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_PROXIMITY_ZONE_OPTIONS,
                    mode=SelectSelectorMode.LIST,
                    translation_key="proximity_zone",
                )
            ),
            vol.Required(_CONF_SHOW_ADVANCED, default=False): BooleanSelector(),
        }
    )


def _validate_distances(user_input: dict) -> dict:
    """Return errors dict (empty = valid)."""
    vn = user_input[CONF_ZONE_VERY_NEAR_M]
    n = user_input[CONF_ZONE_NEAR_M]
    m = user_input[CONF_ZONE_MID_M]
    f = user_input[CONF_ZONE_FAR_M]
    if not (vn < n < m < f):
        return {"base": "zone_thresholds_not_ascending"}
    return {}


class EntityDistanceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        for flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            if flow["flow_id"] != self.flow_id:
                self.hass.config_entries.flow.async_abort(flow["flow_id"])
        errors = {}
        if user_input is not None:
            raw = user_input.get(CONF_ENTITIES, [])
            entities: list[str] = list(raw) if isinstance(raw, (list, tuple)) else []

            if len(entities) < 2:
                errors["base"] = "too_few_entities"
            elif len(set(entities)) != len(entities):
                errors["base"] = "duplicate_entities"
            elif len(entities) > MAX_GROUP_ENTITIES:
                errors["base"] = "too_many_entities"
            else:
                uid = f"{DOMAIN}_{'__'.join(sorted(entities))}"
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                self._data.update(user_input)
                return await self.async_step_distances()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITIES): EntitySelector(
                        EntitySelectorConfig(domain=ENTITY_DOMAINS, multiple=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_distances(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = _validate_distances(user_input)
            if not errors:
                show_advanced = user_input.pop(_CONF_SHOW_ADVANCED, False)
                self._data.update(user_input)
                if show_advanced:
                    return await self.async_step_advanced()
                entities = self._data[CONF_ENTITIES]
                clean = {k: v for k, v in self._data.items() if not k.startswith("_")}
                return self.async_create_entry(title=_entry_title(entities), data=clean)

        return self.async_show_form(
            step_id="distances",
            data_schema=_distances_schema(self._data),
            errors=errors,
        )

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            entities = self._data[CONF_ENTITIES]
            clean = {k: v for k, v in self._data.items() if not k.startswith("_")}
            return self.async_create_entry(title=_entry_title(entities), data=clean)

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
                    vol.Required(CONF_DEBOUNCE_S, default=DEFAULT_DEBOUNCE_S): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=60,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_GRACE_WINDOW_S, default=DEFAULT_GRACE_WINDOW_S
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_GRACE_WINDOW_S,
                            max=MAX_GRACE_WINDOW_S,
                            unit_of_measurement="s",
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
                    vol.Required(
                        CONF_RESYNC_SILENCE_S, default=DEFAULT_RESYNC_SILENCE_S
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_RESYNC_SILENCE_S,
                            max=MAX_RESYNC_SILENCE_S,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_RESYNC_HOLD_S, default=DEFAULT_RESYNC_HOLD_S): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_RESYNC_HOLD_S,
                            max=MAX_RESYNC_HOLD_S,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
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
        return await self.async_step_distances(user_input)

    async def async_step_distances(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = _validate_distances(user_input)
            if not errors:
                show_advanced = user_input.pop(_CONF_SHOW_ADVANCED, False)
                self._data.update(user_input)
                if show_advanced:
                    return await self.async_step_advanced()
                return self.async_create_entry(
                    title="",
                    data={k: v for k, v in self._data.items() if k in _ZONE_OPTIONS_KEYS},
                )

        return self.async_show_form(
            step_id="distances",
            data_schema=_distances_schema(self._data),
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
                    vol.Required(
                        CONF_GRACE_WINDOW_S,
                        default=self._data.get(CONF_GRACE_WINDOW_S, DEFAULT_GRACE_WINDOW_S),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_GRACE_WINDOW_S,
                            max=MAX_GRACE_WINDOW_S,
                            unit_of_measurement="s",
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
                    vol.Required(
                        CONF_RESYNC_SILENCE_S,
                        default=self._data.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_RESYNC_SILENCE_S,
                            max=MAX_RESYNC_SILENCE_S,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_RESYNC_HOLD_S,
                        default=self._data.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_RESYNC_HOLD_S,
                            max=MAX_RESYNC_HOLD_S,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
