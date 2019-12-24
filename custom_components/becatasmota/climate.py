import asyncio
import json
import logging
import os.path

import voluptuous as vol

from homeassistant.components.climate import ClimateDevice, PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL,
    HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY, HVAC_MODE_AUTO,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_FAN_MODE,
    HVAC_MODES, ATTR_HVAC_MODE)
from homeassistant.const import (
    CONF_NAME, STATE_ON, STATE_UNKNOWN, ATTR_TEMPERATURE,
    PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE)
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity
from . import COMPONENT_ABS_DIR, Helper

from .TuyaMcu import getTimeToSetMCU

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "BecaTasmota Climate"

CONF_UNIQUE_ID = 'unique_id'
MQTT_TOPIC = "mqtt_topic"
CONF_VALUE_SENSOR = 'value_sensor'

SUPPORT_FLAGS = (
    SUPPORT_TARGET_TEMPERATURE
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(MQTT_TOPIC): cv.string,
    vol.Required(CONF_VALUE_SENSOR): cv.entity_id,
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the IR Climate platform."""
    async_add_entities([BecaTasmotaClimate(
        hass, config
    )])

class BecaTasmotaClimate(ClimateDevice, RestoreEntity):
    def __init__(self, hass, config):
        self.hass = hass
        self._unique_id = config.get(CONF_UNIQUE_ID)
        self._name = config.get(CONF_NAME)
        self._mqtt_topic = config.get(MQTT_TOPIC)
        self._value_sensor = config.get(CONF_VALUE_SENSOR)

        self._min_temperature = 5
        self._max_temperature = 35
        self._precision = 0.5

        self._operation_modes = [HVAC_MODE_OFF, HVAC_MODE_HEAT]

        self._target_temperature = self._min_temperature
        self._hvac_mode = HVAC_MODE_OFF
        self._last_on_operation = None

        self._current_temperature = None

        self._unit = hass.config.units.temperature_unit
        self._support_flags = SUPPORT_FLAGS

        self._temp_lock = asyncio.Lock()
        self._on_by_remote = False

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()
    
        last_state = await self.async_get_last_state()
        
        if last_state is not None:
            self._hvac_mode = last_state.state
            self._target_temperature = last_state.attributes['temperature']

            if 'last_on_operation' in last_state.attributes:
                self._last_on_operation = last_state.attributes['last_on_operation']

        if self._value_sensor:
            async_track_state_change(self.hass, self._value_sensor, 
                                     self._async_value_sensor_changed)

            value_sensor_state = self.hass.states.get(self._value_sensor)
            if value_sensor_state and value_sensor_state.state != STATE_UNKNOWN:
                self._async_update_value_sensor(value_sensor_state)
        
        await self.set_termostat_time()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def state(self):
        """Return the current state."""
        if self._on_by_remote:
            return STATE_ON
        if self.hvac_mode != HVAC_MODE_OFF:
            return self.hvac_mode
        return HVAC_MODE_OFF

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def min_temp(self):
        """Return the polling state."""
        return self._min_temperature
        
    @property
    def max_temp(self):
        """Return the polling state."""
        return self._max_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._precision

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._operation_modes

    @property
    def hvac_mode(self):
        """Return hvac mode ie. heat, cool."""
        return self._hvac_mode

    @property
    def last_on_operation(self):
        """Return the last non-idle operation ie. heat, cool."""
        return self._last_on_operation

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return []

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return None

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    @property
    def device_state_attributes(self) -> dict:
        """Platform specific attributes."""
        return {
            'last_on_operation': self._last_on_operation,
        }

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)  
        temperature = kwargs.get(ATTR_TEMPERATURE)
          
        if temperature is None:
            return
            
        if temperature < self._min_temperature or temperature > self._max_temperature:
            _LOGGER.warning('The temperature value is out of min/max range') 
            return

        if self._precision == PRECISION_WHOLE:
            self._target_temperature = round(temperature)
        else:
            self._target_temperature = round(temperature, 1)
        
        if not self._hvac_mode.lower() == HVAC_MODE_OFF:
            await self.set_termostat_target_temperature(temperature)

        await self.async_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        self._hvac_mode = hvac_mode
        
        if not hvac_mode == HVAC_MODE_OFF:
            self._last_on_operation = hvac_mode
            
        await self.set_termostat_on_off(hvac_mode)
        await self.async_update_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        await self.async_update_ha_state()

    async def async_turn_off(self):
        """Turn off."""
        await self.async_set_hvac_mode(HVAC_MODE_OFF)
        
    async def async_turn_on(self):
        """Turn on."""
        if self._last_on_operation is not None:
            await self.async_set_hvac_mode(self._last_on_operation)
        else:
            await self.async_set_hvac_mode(self._operation_modes[1])

    async def _async_value_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature sensor changes."""
        if new_state is None:
            return

        self._async_update_value_sensor(new_state)
        await self.async_update_ha_state()

    @callback
    def _async_update_value_sensor(self, state):
        """Update thermostat with latest state from value sensor."""
        try:
            if state.state != STATE_UNKNOWN:
                payload = json.loads(state.state)["TuyaReceived"]
                if 'DpId' in payload:
                    if payload["DpId"] == 3:
                        self._async_update_current_temp(payload["DpIdData"])
                    
                    elif payload["DpId"] == 2:
                        self._async_update_target_temp(payload["DpIdData"])
                    
                    elif payload["DpId"] == 1:
                        self._async_update_hvac_mode(payload["DpIdData"])
                        
        except ValueError as ex:
            _LOGGER.error("Unable to update from value sensor: %s", ex)
            
    
    @callback
    def _async_update_current_temp(self, DpIdData):
        """Update thermostat with latest state from temperature sensor."""
        try:
            self._current_temperature = float(int(DpIdData, 16))/2
        except ValueError as ex:
            _LOGGER.error("Unable to update from temperature sensor: %s", ex)
            
    @callback
    def _async_update_target_temp(self, DpIdData):
        """Update thermostat with latest target temperature from temperature sensor."""
        try:
            self._target_temperature = float(int(DpIdData, 16))/2
        except ValueError as ex:
            _LOGGER.error("Unable to update from temperature sensor: %s", ex)
    
    @callback
    def _async_update_hvac_mode(self, DpIdData):
        """Update thermostat with latest hvac_mode from temperature sensor."""
        state = int(DpIdData)
        try:
            self._hvac_mode = HVAC_MODE_HEAT if state == 1 else HVAC_MODE_OFF
            if not self._hvac_mode == HVAC_MODE_OFF:
                self._last_on_operation = self._hvac_mode
                
        except ValueError as ex:
            _LOGGER.error("Unable to update hvac from temperature sensor: %s", ex)
            
    async def set_termostat_target_temperature(self, target_temperature):
        service_data = {
                'topic': self._mqtt_topic + '/cmnd/TuyaSend2',
                'payload': "2,%f" % (target_temperature*2)
            }
        await self.hass.services.async_call(
               'mqtt', 'publish', service_data)
        
    async def set_termostat_on_off(self, state):
        if state != HVAC_MODE_OFF:
            payload = "on"
        else: 
            payload = "off" 
                       
        service_data = {
                'topic': self._mqtt_topic + '/cmnd/POWER1',
                'payload': payload
            }
        await self.hass.services.async_call(
               'mqtt', 'publish', service_data)
        
    async def set_termostat_time(self):
        payload = getTimeToSetMCU()
        service_data = {
                'topic': self._mqtt_topic + '/cmnd/SerialSend5',
                'payload': payload
            }
        await self.hass.services.async_call(
               'mqtt', 'publish', service_data)