import json
import logging
from typing import Any
from contextlib import suppress

from http import HTTPStatus
import requests

import re

from homeassistant.components.notify import (
    ATTR_TITLE,
    ATTR_TITLE_DEFAULT,
    ATTR_DATA,
    BaseNotificationService,
    NotifyEntity,
    NotifyEntityFeature,
)

from homeassistant.components import media_source, mqtt

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.network import NoURLAvailableError, get_url

from homeassistant.const import (
    CONF_ID,
    CONF_NAME,
    CONF_URL,
)

from .const import (
    CONF_DEFAULT_NOTIFICATION_TITLE,
    CONF_DEVICE_NAME,
    DOMAIN,
)

_logger = logging.getLogger(__name__)

CAMERA_PROXY_REGEX = re.compile(r"\/api\/camera_proxy\/camera\.(.*)")


async def async_resolve_image(hass: HomeAssistant, image: str):
    """Resolve an image to an url HASS.Agent can download it from, if needed"""

    camera_proxy_match = CAMERA_PROXY_REGEX.match(image)

    if camera_proxy_match is not None:
        camera = hass.states.get(f"camera.{camera_proxy_match.group(1)}")

        if camera is not None:
            external_url = None
            with suppress(NoURLAvailableError):  # external_url not configured
                external_url = get_url(hass, allow_internal=False)

            if external_url is not None:
                access_token = camera.attributes["access_token"]
                return f"{external_url}{image}?token={access_token}"

    elif media_source.is_media_source_id(image):
        sourced_media = await media_source.async_resolve_media(hass, image)
        return media_source.async_process_play_media_url(hass, sourced_media.url)

    return None


async def async_build_payload(hass: HomeAssistant, message: str, title: str, data):
    """Build the notification payload HASS.Agent expects"""

    if data is None:
        data = dict()

    image = data.get("image", None)

    if image is not None:
        new_url = await async_resolve_image(hass, image)

        if new_url is not None:
            data.update({"image": new_url})

    return {"message": message, "title": title, "data": data}


async def async_send_payload(hass: HomeAssistant, entry: ConfigEntry, device_name: str, payload):
    """Send the notification payload to the device, through MQTT or its local API"""

    _logger.debug("Sending notification")

    url = entry.data.get(CONF_URL, None)

    if url is None:
        await mqtt.async_publish(
            hass,
            f"hass.agent/notifications/{device_name}",
            json.dumps(payload),
        )
    else:
        try:

            def send_request(url, data):
                """Sends the json request"""
                return requests.post(url, json=data, timeout=10)

            response = await hass.async_add_executor_job(send_request, f"{url}/notify", payload)

            _logger.debug("Checking result")

            if response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
                _logger.error(
                    "Server error. Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.BAD_REQUEST:
                _logger.error(
                    "Client error (bad request). Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.NOT_FOUND:
                _logger.debug(
                    "Server error (not found). Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
                _logger.error(
                    "Server error (method not allowed). Response %d",
                    response.status_code,
                )
            elif response.status_code == HTTPStatus.REQUEST_TIMEOUT:
                _logger.debug(
                    "Server error (request timeout). Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.NOT_IMPLEMENTED:
                _logger.error(
                    "Server error (not implemented). Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.SERVICE_UNAVAILABLE:
                _logger.error(
                    "Server error (service unavailable). Response %d",
                    response.status_code,
                )
            elif response.status_code == HTTPStatus.GATEWAY_TIMEOUT:
                _logger.error(
                    "Network error (gateway timeout). Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            elif response.status_code == HTTPStatus.OK:
                _logger.debug(
                    "Success. Response %d: %s",
                    response.status_code,
                    response.reason,
                )
            else:
                _logger.debug("Unknown response %d: %s", response.status_code, response.reason)
        except Exception as ex:
            _logger.debug("Error sending message: %s", ex)


def get_service(hass, config, discovery_info=None):
    """Get the HASS Agent notification service."""

    entry_id = discovery_info.get(CONF_ID, None)

    return HassAgentNotificationService(
        hass,
        discovery_info[CONF_DEVICE_NAME],
        discovery_info[CONF_NAME],
        entry_id,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Set up the notify entity from a config entry."""

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.unique_id)})

    if device is None:
        return False

    async_add_entities([HassAgentNotifyEntity(entry.unique_id, entry.entry_id, device)])

    return True


class HassAgentNotificationService(BaseNotificationService):
    """Implementation of the HASS Agent notification service"""

    def __init__(self, hass, device_name, service_name, entry_id):
        """Initialize the service."""
        self._service_name = service_name
        self._device_name = device_name
        self._entry_id = entry_id
        self._hass = hass

    async def async_send_message(self, message: str, **kwargs: Any):
        """Send the message to the provided resource."""
        _logger.debug("Preparing notification")

        entry = self.hass.config_entries.async_get_entry(self._entry_id)

        title = kwargs.get(ATTR_TITLE, entry.options[CONF_DEFAULT_NOTIFICATION_TITLE])

        payload = await async_build_payload(self.hass, message, title, kwargs.get(ATTR_DATA, None))

        await async_send_payload(self.hass, entry, self._device_name, payload)


class HassAgentNotifyEntity(NotifyEntity):
    """Implementation of the HASS.Agent notify entity

    Note: the send_message action only carries a message and a title, so images,
          actions and inputs remain available through the notify service only.
    """

    _attr_has_entity_name = True
    _attr_name = "Notifications"
    _attr_icon = "mdi:bell"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, unique_id, entry_id, device: dr.DeviceEntry):
        """Initialize the entity."""
        self._entry_id = entry_id
        self._device_identifier = unique_id
        self._attr_unique_id = f"notify_{unique_id}"
        self._attr_device_info = {
            "identifiers": device.identifiers,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
        }

    @property
    def _device_name(self):
        """Return the device's current name, which its notification topic is based on"""

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, self._device_identifier)})

        return device.name if device is not None else None

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send the message to the device."""
        _logger.debug("Preparing notification")

        entry = self.hass.config_entries.async_get_entry(self._entry_id)

        if title is None:
            title = entry.options.get(CONF_DEFAULT_NOTIFICATION_TITLE, ATTR_TITLE_DEFAULT)

        device_name = self._device_name

        if device_name is None:
            _logger.error("Device of '%s' is gone, dropping notification", self.entity_id)
            return

        payload = await async_build_payload(self.hass, message, title, None)

        await async_send_payload(self.hass, entry, device_name, payload)
