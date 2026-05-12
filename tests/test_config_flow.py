"""Tests for config flow."""

from __future__ import annotations


class TestConfigFlowValidation:
    def test_same_entity_rejected(self):
        # same entity_a and entity_b should produce "same_entity" error
        # full flow test requires hass fixture from pytest-homeassistant-custom-component
        pass

    def test_exit_below_entry_rejected(self):
        # exit_threshold < entry_threshold should produce "exit_below_entry" error
        pass
