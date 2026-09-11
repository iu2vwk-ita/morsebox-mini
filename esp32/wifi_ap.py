# Native ESP32 access point: IU2VWK-MORSE.
import network
import time
from config import AP_SSID, AP_PASS, AP_IP, AP_NETMASK, AP_CHANNEL


def start_ap():
    ap = network.WLAN(network.AP_IF)
    try:
        ap.active(False)
        time.sleep_ms(100)
    except Exception:
        pass
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASS,
              authmode=network.AUTH_WPA_WPA2_PSK, channel=AP_CHANNEL)
    try:
        # same IP as the Pi: the lid QR codes (http://10.42.0.1) stay valid
        ap.ifconfig((AP_IP, AP_NETMASK, AP_IP, AP_IP))
    except Exception:
        pass
    return ap
