"""Async Python library for Kitchen BLE scale."""

import asyncio
import logging
from typing import Optional, Callable, Any, Union

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

# Логгер только для отладки, по умолчанию ничего не выводит
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)

# UUIDs из вашего ESPHome конфига
SCALE_SERVICE_UUID = "0000ffb0-0000-1000-8000-00805f9b34fb"
SCALE_WEIGHT_CHAR_UUID = "0000ffb2-0000-1000-8000-00805f9b34fb"

# Константы для парсинга
WEIGHT_PACKET_HEADER = b'\xAC\x40'
WEIGHT_BYTE_OFFSET = 4
WEIGHT_BYTE_LENGTH = 3

class KitchenScale:
    """Kitchen BLE scale interface."""
    
    def __init__(self, address_or_ble_device: Union[str, BLEDevice]):
        """Initialize scale with address or BLEDevice."""
        if isinstance(address_or_ble_device, BLEDevice):
            self.address = address_or_ble_device.address
            self.ble_device = address_or_ble_device
        else:
            self.address = address_or_ble_device
            self.ble_device = None
            
        self.client: Optional[BleakClient] = None
        self._weight: float = 0.0
        self._callback: Optional[Callable[[str, Any], None]] = None
        self._loop = asyncio.get_event_loop()
        
    def set_callback(self, callback: Callable[[str, Any], None]) -> None:
        """Set callback for data updates."""
        self._callback = callback
        
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle incoming weight notifications."""
        try:
            if len(data) >= 7 and data[:2] == WEIGHT_PACKET_HEADER:
                # Извлекаем 24-битное значение веса
                raw_weight = (data[WEIGHT_BYTE_OFFSET] << 16) | \
                            (data[WEIGHT_BYTE_OFFSET + 1] << 8) | \
                            data[WEIGHT_BYTE_OFFSET + 2]
                weight_grams = raw_weight / 1000.0
                
                self._weight = weight_grams
                if self._callback:
                    self._callback("weight", weight_grams)
        except Exception:
            pass
    
    def _disconnected_callback(self, client: BleakClient) -> None:
        """Handle disconnection."""
        self.client = None
        if self._callback:
            self._callback("disconnected", None)
    
    async def async_connect(self) -> bool:
        """Connect to scale and enable notifications."""
        try:
            if not self.ble_device:
                # Уменьшаем таймаут сканирования для быстроты
                self.ble_device = await BleakScanner.find_device_by_address(
                    self.address, timeout=3.0
                )
                if not self.ble_device:
                    return False
            
            self.client = BleakClient(
                self.ble_device,
                disconnected_callback=self._disconnected_callback
            )
            
            # Уменьшаем таймаут подключения
            await self.client.connect(timeout=8.0)
            
            # Включаем уведомления
            await self.client.start_notify(
                SCALE_WEIGHT_CHAR_UUID,
                self._notification_handler
            )
            
            if self._callback:
                self._callback("connected", None)
            
            return True
            
        except Exception:
            self.client = None
            return False
    
    async def async_disconnect(self) -> None:
        """Disconnect from scale."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(SCALE_WEIGHT_CHAR_UUID)
                await self.client.disconnect()
            except Exception:
                pass
            finally:
                self.client = None
                if self._callback:
                    self._callback("disconnected", None)
    
    @property
    def weight(self) -> float:
        """Current weight in grams."""
        return self._weight
    
    @property
    def connected(self) -> bool:
        """Connection status."""
        return self.client is not None and self.client.is_connected
    
    @staticmethod
    async def discover_devices(timeout: float = 3.0) -> list[BLEDevice]:
        """Discover nearby kitchen scales."""
        devices = []
        
        def detection_callback(device: BLEDevice, advertisement_data):
            if advertisement_data and advertisement_data.service_uuids:
                if SCALE_SERVICE_UUID in advertisement_data.service_uuids:
                    devices.append(device)
        
        scanner = BleakScanner(detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        
        return devices