"""Config flow for DE BLE Kitchen Scale integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SCALE_SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

class DEBleKitchenScaleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DE BLE Kitchen Scale."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered device: %s", discovery_info)
        
        # Проверяем, что это наши весы по UUID сервиса
        if SCALE_SERVICE_UUID not in discovery_info.service_uuids:
            return self.async_abort(reason="not_supported_device")
        
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        
        self._discovery_info = discovery_info
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            
            # При добавлении устройства показываем название "Kitchen Scale (KT630LB)"
            return self.async_create_entry(
                title="Kitchen Scale (KT630LB)",
                data={
                    CONF_ADDRESS: address,
                },
            )

        # Собираем все обнаруженные весы
        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.address in current_addresses:
                continue
            if SCALE_SERVICE_UUID in discovery_info.service_uuids:
                self._discovered_devices[discovery_info.address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Создаем список для выбора
        devices = {
            address: f"KT630LB ({address})"  # Показываем модель в списке
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(devices)
            }),
        )