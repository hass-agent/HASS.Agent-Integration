"""Config flow for HASS.Agent."""

import json
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HASS.Agent."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL  # or other suitable class

    def __init__(self) -> None:
        """Initialize the flow."""
        self._device_name: str = ""
        self._data: dict[str, Any] = {}

    async def async_step_mqtt(self, discovery_info: MqttServiceInfo) -> FlowResult:
        """Handle MQTT discovery."""
        # Defensive extraction of device_name from topic
        try:
            device_name = discovery_info.topic.split("hass.agent/devices/")[1]
        except IndexError:
            _LOGGER.error(
                "Received MQTT topic in unexpected format: %s", discovery_info.topic
            )
            return self.async_abort(reason="invalid_topic")

        try:
            payload = json.loads(discovery_info.payload)
        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to parse MQTT payload: %s", err)
            return self.async_abort(reason="invalid_payload")

        serial_number = payload.get("serial_number")
        if not serial_number:
            _LOGGER.error("No serial_number in MQTT discovery payload")
            return self.async_abort(reason="invalid_payload")

        _LOGGER.debug(
            "Discovered device '%s' with serial number %s", device_name, serial_number
        )

        # Check for existing entries with this serial number to avoid duplicates
        await self.async_set_unique_id(serial_number)
        self._abort_if_unique_id_configured()

        self._device_name = device_name
        self._data = {
            "device": payload.get("device", {}),
            "apis": payload.get("apis", {}),
        }

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm device addition."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._device_name,
                data=self._data,
            )

        self.context["title_placeholders"] = {"name": self._device_name}
        self._set_confirm_only()

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self._device_name},
        )
