"""The HASS.Agent integration."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from contextlib import suppress
import json
import logging
from pathlib import Path
import requests
from typing import Any, cast
from .views import MediaPlayerThumbnailView

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.mqtt.subscription import (
    async_prepare_subscribe_topics,
    async_subscribe_topics,
    async_unsubscribe_topics,
)
from homeassistant.const import (
    CONF_ID,
    CONF_NAME, 
    CONF_URL, 
    Platform, 
    SERVICE_RELOAD,
)
from homeassistant.core import HomeAssistant, callback, ServiceCall, async_get_hass
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify    

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

_logger = logging.getLogger(__name__)

async def update_device_info(hass: HomeAssistant, entry: ConfigEntry, new_device_info):
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name=new_device_info["device"]["name"],
        manufacturer=new_device_info["device"]["manufacturer"],
        model=new_device_info["device"]["model"],
        sw_version=new_device_info["device"]["sw_version"],
    )

async def async_wait_for_mqtt_client(hass: HomeAssistant) -> bool:
    """Wait for the MQTT client to become available.
    Waits when mqtt set up is in progress,
    It is not needed that the client is connected.
    Returns True if the mqtt client is available.
    Returns False when the client is not available.
    """
    if not mqtt_config_entry_enabled(hass):
        return False

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    if entry.state == ConfigEntryState.LOADED:
        return True

    state_reached_future: asyncio.Future[bool]
    if DATA_MQTT_AVAILABLE not in hass.data:
        hass.data[DATA_MQTT_AVAILABLE] = state_reached_future = asyncio.Future()
    else:
        state_reached_future = hass.data[DATA_MQTT_AVAILABLE]
        if state_reached_future.done():
            return state_reached_future.result()

    try:
        async with async_timeout.timeout(AVAILABILITY_TIMEOUT):
            # Await the client setup or an error state was received
            return await state_reached_future
    except asyncio.TimeoutError:
        return False

async def handle_apis_changed(hass: HomeAssistant, entry: ConfigEntry, apis):
    _logger.debug("api changed for: %s", entry.unique_id)
    if apis is not None:

        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.unique_id)}
        )

        media_player = apis.get("media_player", False)
        is_media_player_loaded = hass.data[DOMAIN][entry.entry_id]["loaded"]["media_player"]

        notifications = apis.get("notifications", False)
        is_notifications_loaded = hass.data[DOMAIN][entry.entry_id]["loaded"]["notifications"]

        if media_player and is_media_player_loaded is False:
            _logger.debug("loading media player for device: %s [%s]", device.name, entry.unique_id)
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

            hass.data[DOMAIN][entry.entry_id]["loaded"]["media_player"] = True
        else:
            if is_media_player_loaded:
                _logger.debug("unloading media player for device: %s [%s]", device.name, entry.unique_id)
                await hass.config_entries.async_forward_entry_unload(
                    entry, Platform.MEDIA_PLAYER
                )

                hass.data[DOMAIN][entry.entry_id]["loaded"]["media_player"] = False

        if notifications and is_notifications_loaded is False:
            _logger.debug("loading notifications for device: %s [%s]", device.name, entry.unique_id)

            hass.async_create_task(
                discovery.async_load_platform(
                    hass,
                    Platform.NOTIFY,
                    DOMAIN,
                    {CONF_ID: entry.entry_id, CONF_NAME: device.name},
                    {},
                )
            )
            hass.data[DOMAIN][entry.entry_id]["loaded"]["notifications"] = True
        else:
            if is_notifications_loaded:
                _logger.debug("unloading notifications for device: %s [%s]", device.name, entry.unique_id)
                await hass.config_entries.async_unload_platforms(
                    entry, [Platform.NOTIFY]
                )

                hass.data[DOMAIN][entry.entry_id]["loaded"]["notifications"] = False

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HASS.Agent from a config entry."""

    _logger.debug("setting up device from config entry: %s [%s]", entry.data["device"]["name"], entry.unique_id)

    hass.data.setdefault(DOMAIN, {})

    hass.data[DOMAIN].setdefault(
        entry.entry_id,
        {
            "internal_mqtt": {},
            "apis": {},
            "thumbnail": None,
            "loaded": {"media_player": False, "notifications": False},
        },
    )

    url = entry.data.get(CONF_URL, None)

    if url is not None:

        def get_device_info():
            return requests.get(f"{url}/info", timeout=60)

        response = await hass.async_add_executor_job(get_device_info)

        response_json = response.json()

        await update_device_info(hass, entry, response_json)

        apis = {
            "notifications": True,
            "media_player": False,  # unsupported for the moment
        }

        hass.async_create_background_task(handle_apis_changed(hass, entry, apis))
        hass.data[DOMAIN][entry.entry_id]["apis"] = apis

    else:
        device_name = entry.data["device"]["name"]

        sub_state = hass.data[DOMAIN][entry.entry_id]["internal_mqtt"]

        @callback
        async def updated(message: ReceiveMessage):
            payload = json.loads(message.payload)
            cached = hass.data[DOMAIN][entry.entry_id]["apis"]
            apis = payload["apis"]

            await update_device_info(hass, entry, payload)

            if cached != apis:
                hass.async_create_background_task(handle_apis_changed(hass, entry, apis), "hass.agent-mqtt")
                hass.data[DOMAIN][entry.entry_id]["apis"] = apis

        sub_state = async_prepare_subscribe_topics(
            hass,
            sub_state,
            {
                f"{entry.unique_id}-apis": {
                    "topic": f"hass.agent/devices/{device_name}",
                    "msg_callback": updated,
                    "qos": 0,
                }
            },
        )

        await async_subscribe_topics(hass, sub_state)

        hass.data[DOMAIN][entry.entry_id]["internal_mqtt"] = sub_state

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    deviceName = entry.data["device"]["name"]

    _logger.debug("unloading device: %s [%s]", deviceName, entry.unique_id)

    # known issue: notify does not always unload

    loaded = hass.data[DOMAIN][entry.entry_id].get("loaded", None)

    if loaded is not None:
        notifications = loaded.get("notifications", False)
        media_player = loaded.get("media_player", False)

        if notifications:
            if unload_ok := await hass.config_entries.async_unload_platforms(
                entry, [Platform.NOTIFY]
            ):
                _logger.debug("unloaded notifications for: %s [%s]", deviceName, entry.unique_id)

        if media_player:
            if unload_ok := await hass.config_entries.async_unload_platforms(
                entry, [Platform.MEDIA_PLAYER]
            ):
                _logger.debug("unloaded media player for: %s [%s]", deviceName, entry.unique_id)
    else:
        _logger.warning("config entry (%s) with has no apis loaded?", entry.unique_id)

    url = entry.data.get(CONF_URL, None)
    if url is None:
        async_unsubscribe_topics(
            hass, hass.data[DOMAIN][entry.entry_id]["internal_mqtt"]
        )

    hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up hass_agent integration."""

    _logger.debug("integration setup start")

    hass.http.register_view(MediaPlayerThumbnailView(hass))

    # Make sure MQTT integration is enabled and the client is available
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _logger.error("MQTT integration is not available")
        return False
    
    # async def _handle_reload(service):
    #     """Handle reload service call."""
    #     _logger.info("Service %s.reload called: reloading integration", DOMAIN)

    #     current_entries = hass.config_entries.async_entries(DOMAIN)

    #     reload_tasks = [
    #         hass.config_entries.async_reload(entry.entry_id)
    #         for entry in current_entries
    #     ]

    #     await asyncio.gather(*reload_tasks)

    # hass.services.async_register(
    #     DOMAIN,
    #     SERVICE_RELOAD,
    #     _handle_reload,
    # )

    return True
