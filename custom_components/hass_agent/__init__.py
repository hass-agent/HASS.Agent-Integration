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

from .const import DOMAIN, CONF_ORIGINAL_DEVICE_NAME, CONF_DEVICE_NAME

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


async def handle_apis_changed(hass: HomeAssistant, entry: ConfigEntry, apis):
    _logger.debug("api changed for: %s", entry.unique_id)
    if apis is not None:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, entry.unique_id)})

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
                _logger.debug(
                    "unloading media player for device: %s [%s]",
                    device.name,
                    entry.unique_id,
                )
                await hass.config_entries.async_forward_entry_unload(entry, Platform.MEDIA_PLAYER)

                hass.data[DOMAIN][entry.entry_id]["loaded"]["media_player"] = False

        if notifications and is_notifications_loaded is False:
            _logger.debug(
                "loading notifications for device: %s [%s]",
                device.name,
                entry.unique_id,
            )

            original_device_name = entry.data.get(CONF_ORIGINAL_DEVICE_NAME, device.name)

            hass.async_create_task(
                discovery.async_load_platform(
                    hass,
                    Platform.NOTIFY,
                    DOMAIN,
                    {
                        CONF_ID: entry.entry_id,
                        CONF_NAME: original_device_name, # Note(Amadeo): CONF_NAME decides of "nofity.<device>" name, needs to be set to the original one
                        CONF_DEVICE_NAME: device.name, # Note(Amadeo): since CONF_NAME is used for the old name, we need to pass on the changed name for MQTT notify call
                    },
                    {},
                )
            )
            hass.data[DOMAIN][entry.entry_id]["loaded"]["notifications"] = True
        else:
            if is_notifications_loaded:
                # _logger.debug("unloading notifications for device: %s [%s]", device.name, entry.unique_id)
                # await hass.config_entries.async_unload_platforms(entry, [Platform.NOTIFY])
                # NOTE(Amadeo): disabled due to "ValueError: Config entry was never loaded!" error

                hass.data[DOMAIN][entry.entry_id]["loaded"]["notifications"] = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HASS.Agent from a config entry."""

    _logger.debug("setting up device from config entry: %s [%s]", entry.title, entry.unique_id)

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

        hass.async_create_background_task(handle_apis_changed(hass, entry, apis), "hass.agent-api")
        hass.data[DOMAIN][entry.entry_id]["apis"] = apis

    else:
        device_name = entry.data["device"]["name"]

        sub_state = hass.data[DOMAIN][entry.entry_id]["internal_mqtt"]

        @callback
        async def updated(message: ReceiveMessage):
            if not message.payload:
                _logger.debug("received empty update message on '%s', ignoring", message.topic)
                return

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

    _logger.debug("unloading device: %s [%s]", entry.title, entry.unique_id)

    # known issue: notify does not always unload
    # NOTE(Amadeo): unloading NOTIFY platform always fails, same happens for example for https://github.com/home-assistant/core/blob/dd7f7be6adee76f2add98dcca8d3ff87bceabf70/homeassistant/components/nfandroidtv/__init__.py
    loaded = hass.data[DOMAIN][entry.entry_id].get("loaded", None)

    if loaded is not None:
        notifications = loaded.get("notifications", False)
        media_player = loaded.get("media_player", False)

        # if notifications:
        #     if unload_ok := await hass.config_entries.async_unload_platforms(entry, [Platform.NOTIFY]):
        #         _logger.debug("unloaded notifications for: %s [%s]", entry.title, entry.unique_id)
        # NOTE(Amadeo): disabled due to "ValueError: Config entry was never loaded!" error

        if media_player:
            if unload_ok := await hass.config_entries.async_unload_platforms(entry, [Platform.MEDIA_PLAYER]):
                _logger.debug("unloaded media player for: %s [%s]", entry.title, entry.unique_id)
    else:
        _logger.warning("config entry (%s) with has no apis loaded?", entry.unique_id)

    url = entry.data.get(CONF_URL, None)
    if url is None:
        async_unsubscribe_topics(hass, hass.data[DOMAIN][entry.entry_id]["internal_mqtt"])

    hass.data[DOMAIN].pop(entry.entry_id)

    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up hass_agent integration."""

    _logger.debug("integration setup start")

    hass.http.register_view(MediaPlayerThumbnailView(hass))

    return True
