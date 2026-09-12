#!/bin/bash
# IU2VWK Morse Simulator - install on Raspberry Pi 4/5 (Raspberry Pi OS).
# Access point via hostapd + dnsmasq: it does NOT touch the Ethernet network
# (no conflicts with dhcpcd), so SSH over cable stays reachable.
#   sudo bash install.sh
set -e
cd "$(dirname "$0")"

AP_SSID="IU2VWK-MORSE"
AP_PASS="morse1234"
WLAN="wlan0"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

echo "[1/6] Packages..."
apt-get update -qq
apt-get install -y -qq avahi-daemon hostapd dnsmasq python3-rpi.gpio python3-gpiozero || true

echo "[2/6] Hostname -> iu2vwk-morse..."
if command -v raspi-config >/dev/null; then
  raspi-config nonint do_hostname iu2vwk-morse || true
else
  hostnamectl set-hostname iu2vwk-morse || true
fi
systemctl enable --now avahi-daemon || true

echo "[3/6] Files in /opt/iu2vwk-morse..."
mkdir -p /opt/iu2vwk-morse
cp server.py display.py exercise.py reflex.py easter.py audio.py morse.py \
   /opt/iu2vwk-morse/
rm -rf /opt/iu2vwk-morse/static
cp -r static /opt/iu2vwk-morse/

echo "[4/6] App service (autostart)..."
cp iu2vwk-morse.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now iu2vwk-morse

echo "[5/6] Access Point $AP_SSID (hostapd + dnsmasq)..."
# Wi-Fi interface: a single network, fixed AP
cat >/etc/hostapd/hostapd.conf <<EOF
interface=$WLAN
driver=nl80211
ssid=$AP_SSID
hw_mode=g
channel=6
wpa=2
wpa_passphrase=$AP_PASS
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF
sed -i 's|^#\?DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

# Lightweight DHCP server on the AP network (10.42.0.x), gateway 10.42.0.1
cat >/etc/dnsmasq.d/morseap <<EOF
interface=$WLAN
dhcp-range=10.42.0.10,10.42.0.100,255.255.255.0,12h
dhcp-option=3,10.42.0.1
dhcp-option=6,10.42.0.1
address=/#/10.42.0.1
no-resolv
EOF

# Static AP IP on wlan0
cat >/etc/dhcpcd.conf <<EOF
interface $WLAN
static ip_address=10.42.0.1/24
nohook wpa_supplicant
EOF

# disable the default AP services that would get in the way
systemctl unmask hostapd || true
systemctl restart dnsmasq || true
systemctl enable --now hostapd || true
hostapd -B /etc/hostapd/hostapd.conf 2>/dev/null || true
ip addr add 10.42.0.1/24 dev $WLAN 2>/dev/null || true

echo "[6/6] Check..."
sleep 2
systemctl is-active iu2vwk-morse
echo
echo "Done! At the booth:"
echo "  1. Join the phone to the Wi-Fi $AP_SSID (password: $AP_PASS)"
echo "  2. Open http://10.42.0.1  (or http://iu2vwk-morse.local)"
echo "SSH over Ethernet stays active: hostname -I for the IP."
