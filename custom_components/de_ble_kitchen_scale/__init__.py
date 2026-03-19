"""DE BLE Kitchen Scale integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components import bluetooth

from .const import (
    DOMAIN,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    SCAN_INTERVAL,
)
from .kitchenscale_ble import KitchenScale

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DE BLE Kitchen Scale from a config entry."""
    address = entry.data[CONF_ADDRESS]
    
    coordinator = KitchenScaleCoordinator(hass, address, entry.entry_id)
    await coordinator.async_setup()
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    @callback
    def _device_seen(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Мгновенная реакция на появление весов."""
        _LOGGER.debug("Весы %s обнаружены, запускаю подключение...", address)
        # Немедленно запускаем подключение, не ждем интервала
        hass.async_create_task(coordinator.async_connect_now())

    # Регистрируем callback на все время работы интеграции
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _device_seen,
            {"address": address, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )
    
    async def _async_shutdown(event):
        await coordinator.async_shutdown()
    
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown)
    )
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    
    return unload_ok

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the DE BLE Kitchen Scale integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

class KitchenScaleCoordinator:
    """Coordinator for Kitchen Scale BLE."""
    
    def __init__(self, hass: HomeAssistant, address: str, entry_id: str) -> None:
        """Initialize coordinator."""
        self.hass = hass
        self.address = address
        self.entry_id = entry_id
        self.scale: KitchenScale | None = None
        self._connected = False
        self._weight = 0.0
        self._cancel_scan: callable | None = None
        self._connecting = False
        self._shutdown = False
        
    async def async_setup(self) -> None:
        """Set up coordinator."""
        self.scale = KitchenScale(self.address)
        self.scale.set_callback(self._handle_update)
        
        await self._register_device()
        
        # Запускаем периодическое сканирование (каждые 30 секунд)
        self._cancel_scan = async_track_time_interval(
            self.hass, self._try_connect, SCAN_INTERVAL
        )
        
        # Не делаем сразу несколько попыток, полагаемся на callback
        
    async def async_connect_now(self) -> None:
        """Немедленная попытка подключения при появлении устройства."""
        if self._connected or self._connecting or self._shutdown:
            return

        self._connecting = True
        _LOGGER.debug("Немедленное подключение к %s", self.address)
        
        try:
            # Отменяем следующий плановый скан, чтобы не мешал
            if self._cancel_scan:
                self._cancel_scan()
                self._cancel_scan = None

            if self.scale:
                success = await self.scale.async_connect()
                if not success:
                    self._connecting = False
                    # Если не вышло, перезапускаем плановое сканирование
                    self._restart_periodic_scan()
                # Если успешно, _connecting сбросится в _handle_update
        except Exception as e:
            _LOGGER.debug("Немедленное подключение не удалось: %s", e)
            self._connecting = False
            self._restart_periodic_scan()

    def _restart_periodic_scan(self) -> None:
        """Перезапустить плановое сканирование."""
        from homeassistant.helpers.event import async_track_time_interval
        
        if self._shutdown:
            return
            
        if not self._cancel_scan:
            self._cancel_scan = async_track_time_interval(
                self.hass, self._try_connect, SCAN_INTERVAL
            )
        
    async def _register_device(self) -> None:
        """Register device in device registry."""
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.entry_id,
            identifiers={(DOMAIN, self.address)},
            name="Kitchen Scale",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
            connections={(dr.CONNECTION_BLUETOOTH, self.address)},
        )
    
    @callback
    def _handle_update(self, source: str, data: Any) -> None:
        """Handle updates from scale."""
        if source == "weight":
            self._weight = data
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_update", "weight", data
            )
        elif source == "connected":
            self._connected = True
            self._connecting = False
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_update", "connected", None
            )
        elif source == "disconnected":
            self._connected = False
            self._connecting = False
            # Сбрасываем вес при отключении
            self._weight = 0.0
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_update", "disconnected", None
            )
            # Отправляем обновление веса, чтобы сенсор показал 0
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_update", "weight", 0.0
            )
    
    async def _try_connect(self, now=None) -> None:
        """Try to connect to scale (плановое сканирование)."""
        if self._shutdown or self._connected or self._connecting:
            return
            
        self._connecting = True
        
        try:
            if self.scale:
                success = await self.scale.async_connect()
                if not success:
                    self._connecting = False
        except Exception:
            self._connecting = False
    
    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        self._shutdown = True
        
        if self._cancel_scan:
            self._cancel_scan()
            self._cancel_scan = None
        
        if self.scale:
            if self.scale.connected:
                await self.scale.async_disconnect()
            self.scale = None
    
    @property
    def weight(self) -> float:
        """Current weight."""
        return self._weight
    
    @property
    def connected(self) -> bool:
        """Connection status."""
        return self._connected
