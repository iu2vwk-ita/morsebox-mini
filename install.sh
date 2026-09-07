#!/bin/bash
# IU2VWK Morse Simulator — installazione su Raspberry Pi 4/5 (Raspberry Pi OS).
# Access point via hostapd + dnsmasq: NON tocca la rete Ethernet (niente
# conflitti con dhcpcd), l'SSH via cavo resta raggiungibile.
#   sudo bash install.sh
set -e
cd "$(dirname "$0")"

AP_SSID="IU2VWK-MORSE"
AP_PASS="morse1234"
WLAN="wlan0"

if [ "$(id -u)" -ne 0 ]; then
  echo "Esegui come root: sudo bash install.sh"
  exit 1
fi

echo "[1/6] Pacchetti…"
apt-get update -qq
apt-get install -y -qq avahi-daemon hostapd dnsmasq python3-rpi.gpio python3-gpiozero || true

echo "[2/6] Nome host -> iu2vwk-morse…"
if command -v raspi-config >/dev/null; then
  raspi-config nonint do_hostname iu2vwk-morse || true
else
  hostnamectl set-hostname iu2vwk-morse || true
fi
systemctl enable --now avahi-daemon || true

echo "[3/6] File in /opt/iu2vwk-morse…"
mkdir -p /opt/iu2vwk-morse
cp server.py display.py /opt/iu2vwk-morse/
rm -rf /opt/iu2vwk-morse/static
cp -r static /opt/iu2vwk-morse/

echo "[4/6] Servizio app (avvio automatico)…"
cp iu2vwk-morse.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now iu2vwk-morse

echo "[5/6] Access Point $AP_SSID (hostapd + dnsmasq)…"
# interfaccia Wi-Fi: una sola rete, AP fisso
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

# DHCP server leggero sulla rete AP (10.42.0.x), gateway 10.42.0.1
cat >/etc/dnsmasq.d/morseap <<EOF
interface=$WLAN
dhcp-range=10.42.0.10,10.42.0.100,255.255.255.0,12h
dhcp-option=3,10.42.0.1
dhcp-option=6,10.42.0.1
address=/#/10.42.0.1
no-resolv
EOF

# IP statico dell'AP su wlan0
cat >/etc/dhcpcd.conf <<EOF
interface $WLAN
static ip_address=10.42.0.1/24
nohook wpa_supplicant
EOF

# disabilita i servizi AP predefiniti che si metterebbero in mezzo
systemctl unmask hostapd || true
systemctl restart dnsmasq || true
systemctl enable --now hostapd || true
hostapd -B /etc/hostapd/hostapd.conf 2>/dev/null || true
ip addr add 10.42.0.1/24 dev $WLAN 2>/dev/null || true

echo "[6/6] Verifica…"
sleep 2
systemctl is-active iu2vwk-morse
echo
echo "Fatto! In sezione:"
echo "  1. Collega il telefono alla Wi-Fi $AP_SSID (password: $AP_PASS)"
echo "  2. Apri http://10.42.0.1  (oppure http://iu2vwk-morse.local)"
echo "L'SSH via cavo Ethernet resta attivo: hostname -I per l'IP."
