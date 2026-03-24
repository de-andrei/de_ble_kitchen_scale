"""Constants for DE BLE Kitchen Scale integration."""
from datetime import timedelta

DOMAIN = "de_ble_kitchen_scale"

# Device info
DEVICE_MANUFACTURER = "Nutridays"
DEVICE_MODEL = "KT630LB"

# Service UUIDs
SCALE_SERVICE_UUID = "0000ffb0-0000-1000-8000-00805f9b34fb"
SCALE_WEIGHT_CHAR_UUID = "0000ffb2-0000-1000-8000-00805f9b34fb"

# Update intervals
SCAN_INTERVAL = timedelta(seconds=30)
CONNECT_TIMEOUT = 13

# Packet parsing
WEIGHT_PACKET_HEADER = b'\xAC\x40'
WEIGHT_BYTE_OFFSET = 4
WEIGHT_BYTE_LENGTH = 3
