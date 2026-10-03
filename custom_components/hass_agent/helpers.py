"""Helpers for the HASS.Agent integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


@callback
def async_get_hass_agent_device(hass: HomeAssistant, entry: ConfigEntry) -> dr.DeviceEntry | None:
    """Return the HASS.Agent device belonging to the config entry."""
    device_registry = dr.async_get(hass)
    return next(
        (
            device
            for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
            if (DOMAIN, entry.unique_id) in device.identifiers
        ),
        None,
    )
