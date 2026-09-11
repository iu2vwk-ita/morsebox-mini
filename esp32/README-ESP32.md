# MorseBox Mini — versione ESP32 / MicroPython

Port della versione Raspberry Pi su **ESP32 classico** con **MicroPython**.
La web UI è **identica** a quella del Pi: gli stessi file `static/index.html`,
`static/style.css`, `static/app.js` vengono serviti senza modifiche, e il
protocollo WebSocket è lo stesso.

## Cosa fa

- L'ESP32 crea l'access point **`IU2VWK-MORSE`** (password `morse1234`).
- Web server HTTP + WebSocket sulla porta **80**, IP **10.42.0.1**
  (stesso IP del Pi: i QR sul coperchio continuano a funzionare).
- Keyer iambic A / B + straight, 5–60 WPM, reverse DX/SX, decoder CW in testo.
- Sidetone **PWM hardware a latenza zero** su 1–3 piezo, nessuna pipeline audio.
- Display MAX7219 8x8 opzionale.

## Pinout

| Funzione | GPIO | Modo |
|---|---|---|
| DIT | 32 | `Pin.IN, PULL_UP` (contatto verso GND) |
| DAH | 33 | `Pin.IN, PULL_UP` (contatto verso GND) |
| STRAIGHT | 14 | `Pin.IN, PULL_UP` (contatto verso GND) |
| PIEZO 1 | 25 | `machine.PWM` |
| PIEZO 2 | 26 | `machine.PWM` |
| PIEZO 3 | 27 | `machine.PWM` |
| MAX7219 SCK | 18 | SPI hardware VSPI |
| MAX7219 MOSI | 23 | SPI hardware VSPI |
| MAX7219 CS | 4 | uscita |

I tre piezo suonano insieme: basta collegarne anche uno solo.
I contatti dei tasti vanno verso GND; i pull-up sono interni all'ESP32.

## Requisiti

- ESP32 (WROOM-32) con firmware MicroPython recente (≥ 1.20).
- `mpremote` sul PC: `pip install mpremote`.

Se l'ESP32 non ha MicroPython, flashalo con esptool:

```bash
esptool.py --chip esp32 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash -z 0x1000 \
  ESP32_GENERIC-20240602-v1.23.0.bin
```

## Deploy

```bash
bash deploy.sh                 # porta auto
bash deploy.sh /dev/ttyUSB0    # porta esplicita
```

Lo script copia i `.py` nella root dell'ESP32, crea `/static` con la web UI e
fa il reset. Al boot parte `main.py`.

## Test (senza hardware)

La logica è verificabile su PC con CPython, usando stub di `uasyncio`/`time`:

```bash
python3 tests/test_all.py
```

Copre: keyer iambic A/B, reverse, straight, decoder, handshake WebSocket,
encode/decode frame, parsing HTTP, rotte e path traversal.

## Uso

1. Alimenta la scheda, attendi qualche secondo.
2. Dal telefono unisciti alla Wi-Fi **`IU2VWK-MORSE`** (password `morse1234`).
   Il telefono dirà "senza internet": è normale, resta su quella rete.
3. Apri **`http://10.42.0.1`**.
4. Keya con il paddle, il tasto straight, i paddle touch o la tastiera
   (`Z` / `X` / barra spaziatrice).

## Configurazione

In `config.py`:

- `DISPLAY_ENABLED = True` per attivare la matrice MAX7219 (default `False`).
- `BUZZER_MODE = "passive"` per i piezo (default). `"active"` per buzzer con
  oscillatore (pilotaggio DC on/off).
- `AP_SSID` / `AP_PASS` / `AP_IP` per cambiare rete.

Le impostazioni di WPM, tono, volume, modo e reverse sono salvate in
`settings.json` e persistono tra i riavvii.

## Differenze rispetto alla versione Pi

| | Raspberry Pi | ESP32 MicroPython |
|---|---|---|
| Concorrenza | thread | singolo event loop `uasyncio` |
| Web server | `http.server` + WS custom | socket nativi `uasyncio` + WS custom |
| AP | hostapd + dnsmasq | `network.WLAN(AP_IF)` nativo |
| IP AP | 10.42.0.1 | 10.42.0.1 |
| Hostname mDNS | `iu2vwk-morse.local` | non disponibile (usa l'IP) |
| Deploy | `install.sh` + systemd | `deploy.sh` + `main.py` |
| Decoder audio da mic | sì (opzionale) | **no** (escluso) |

## Note tecniche

- Il keyer gira a tick ~1 ms e usa `time.ticks_ms()`: il jitter del loop non
  accumula, perché ogni elemento è calcolato dall'istante corrente.
- Il sidetone è acceso/spento direttamente dallo stato key tramite
  `machine.PWM`: nessun buffer audio, nessun ritardo percepibile.
- `hub.broadcast()` non blocca mai il keyer: ogni client WebSocket ha una coda;
  un client lento viene scartato senza fermare il tasto.
