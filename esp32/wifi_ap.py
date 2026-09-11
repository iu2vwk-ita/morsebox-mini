# Access point nativo ESP32: IU2VWK-MORSE.
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
        # stesso IP del Pi: i QR sul coperchio (http://10.42.0.1) restano validi
        ap.ifconfig((AP_IP, AP_NETMASK, AP_IP, AP_IP))
    except Exception:
        pass
    return ap
