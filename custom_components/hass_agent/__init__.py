"""The HASS.Agent integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "hass_agent"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Empty setup for HASS.Agent."""
    _LOGGER.debug("Setting up hass_agent integration")
    # Subscribe to MQTT topic here or do other startup logic if needed
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Empty setup for HASS.Agent entries."""
    _LOGGER.debug("Setting up hass_agent entry: %s", entry.entry_id)
    # Forward setup to platforms if any, e.g.:
    # hass.config_entries.async_forward_entry_setup(entry, "sensor")
    # For now, just return True
    return True
