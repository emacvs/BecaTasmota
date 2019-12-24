import asyncio
import binascii
from distutils.version import StrictVersion
import json
import logging
import os.path
import requests
import struct
import voluptuous as vol

from homeassistant.const import (
    ATTR_FRIENDLY_NAME, __version__ as current_ha_version)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'becatasmota'
VERSION = '0.0.1'
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "emanuelecavestri/BecaTasmota/{}/"
    "custom_components/becatasmota/manifest.json")
REMOTE_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "emanuelecavestri/BecaTasmota/{}/"
    "custom_components/becatasmota/")
COMPONENT_ABS_DIR = os.path.dirname(
    os.path.abspath(__file__))

CONF_CHECK_UPDATES = 'check_updates'
CONF_UPDATE_BRANCH = 'update_branch'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_CHECK_UPDATES, default=True): cv.boolean,
        vol.Optional(CONF_UPDATE_BRANCH, default='master'): vol.In(
            ['master', 'rc'])
    })
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    """Set up the BecaTasmota component."""
    conf = config.get(DOMAIN)

    if conf is None:
        return True

    check_updates = conf[CONF_CHECK_UPDATES]
    update_branch = conf[CONF_UPDATE_BRANCH]

    async def _check_updates(service):
        await _update(hass, update_branch)

    async def _update_component(service):
        await _update(hass, update_branch, True)

    hass.services.async_register(DOMAIN, 'check_updates', _check_updates)
    hass.services.async_register(DOMAIN, 'update_component', _update_component)

    if check_updates:
        await _update(hass, update_branch, False, False)

    return True

async def _update(hass, branch, do_update=False, notify_if_latest=True):
    try:
        request = requests.get(MANIFEST_URL.format(branch), stream=True, timeout=10)
    except:
        _LOGGER.error("An error occurred while checking for updates. "
                      "Please check your internet connection.")
        return

    if request.status_code != 200:
        _LOGGER.error("Invalid response from the server while "
                      "checking for a new version")
        return

    data = request.json()
    min_ha_version = data['homeassistant']
    last_version = data['updater']['version']
    release_notes = data['updater']['releaseNotes']

    if StrictVersion(last_version) <= StrictVersion(VERSION):
        if notify_if_latest:
            hass.components.persistent_notification.async_create(
                "You're already using the latest version!", title='BecaTasmota')
        return

    if StrictVersion(current_ha_version) < StrictVersion(min_ha_version):
        hass.components.persistent_notification.async_create(
            "There is a new version of BecaTasmota integration, but it is **incompatible** "
            "with your system. Please first update Home Assistant.", title='BecaTasmota')
        return

    if do_update is False:
        hass.components.persistent_notification.async_create(
            "A new version of BecaTasmota integration is available ({}). "
            "Call the ``becatasmota.update_component`` service to update "
            "the integration. \n\n **Release notes:** \n{}"
            .format(last_version, release_notes), title='BecaTasmota')
        return

    # Begin update
    files = data['updater']['files']
    has_errors = False

    for file in files:
        try:
            source = REMOTE_BASE_URL.format(branch) + file
            dest = os.path.join(COMPONENT_ABS_DIR, file)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            Helper.downloader(source, dest)
        except:
            has_errors = True
            _LOGGER.error("Error updating %s. Please update the file manually.", file)

    if has_errors:
        hass.components.persistent_notification.async_create(
            "There was an error updating one or more files of BecaTasmota. "
            "Please check the logs for more information.", title='BecaTasmota')
    else:
        hass.components.persistent_notification.async_create(
            "Successfully updated to {}. Please restart Home Assistant."
            .format(last_version), title='BecaTasmota')

class Helper():
    @staticmethod
    def downloader(source, dest):
        req = requests.get(source, stream=True, timeout=10)

        if req.status_code == 200:
            with open(dest, 'wb') as fil:
                for chunk in req.iter_content(1024):
                    fil.write(chunk)
        else:
            raise Exception("File not found")
