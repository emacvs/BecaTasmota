# BecaTasmota
Home Assistant component for Beca thermostat with Tasmosta firmware

## Example configuration

```
- platform: mqtt
    name: "name_thermostat_sensor"
    state_topic: "mqtt_topic/tele/RESULT"

climate:
  - platform: becatasmota
    name: "name_thermostat"
    unique_id: unique_id_optional
    mqtt_topic: "mqtt_topic"
    value_sensor: sensor.name_thermostat_sensor
```
