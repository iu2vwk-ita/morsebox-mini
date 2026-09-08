# MorseBox Mini — Trainer CW via WiFi

Un keyer Morse in una scatola. Un Raspberry Pi (4, 5, Zero 2 W o simili) espone
una pagina web sulla propria rete WiFi. Collegati alla rete, apri la pagina,
trasmetti con un paddle vero o con quello touch sullo schermo, e rileggi la tua
manipolazione come testo. Il sidetone esce diretto dai pin GPIO a latenza zero,
su fino a tre buzzer piezo insieme.

Nessuna dipendenza. Solo Python 3, funziona subito. Niente paddle sottomano?
Il modo touch va benissimo lo stesso.

![MorseBox assemblato](box.png)

## Cosa fa

* Iambico A / B e tasto verticale, 5–60 WPM, scambio paddle (DX⇄SX)
* Testo decodificato in diretta sulla pagina web e sull'optional matrice LED MAX7219
* Tono del sidetone (400–4000 Hz) e volume dalla pagina, su 1–3 piezo insieme
  (`--buzz-pins 24,25,12`)
* Manipola con paddle, tasto verticale, paddle touch o tastiera
  (`Z` / `X` / spazio)

![Interfaccia web](screenshot-ui.png)

## Apri la pagina web

Il Pi fa da access point. Niente router di casa, niente internet.

1. Accendi la scatola, aspetta una trentina di secondi
2. Collegati al WiFi **`IU2VWK-MORSE`** (password `morse1234`). Il telefono dirà
   «connesso senza internet»: è normale, resta lì
3. Apri **`http://10.42.0.1`**

Sul coperchio ci sono due QR: **WIFI** collega alla rete, **APP** apre la pagina.
A casa la scatola funziona anche via Ethernet sulla porta 80.

## Hardware

* Raspberry Pi (4, 5, Zero 2 W o simili) con alimentatore e microSD
  con Raspberry Pi OS Lite a 64 bit
* Paddle o tasto verticale cablati sul connettore GPIO. Contatti verso GND,
  le pull-up interne fanno il resto, nessun componente extra
* Da 1 a 3 buzzer piezo passivi (moduli KY-006 a 3 pin)
* Matrice LED MAX7219 8x8 opzionale. Mostra WPM più testo decodificato in diretta

### Cablaggio (numeri BCM, contatti tasti verso GND)

| Funzione | GPIO | Pin |
|----------|------|-----|
| DIT (paddle) | 17 | 11 |
| DAH (paddle) | 27 | 13 |
| Tasto verticale | 22 | 15 |
| GND | — | 6, 9, 14… |
| Segnale piezo 1 | 24 | 18 |
| Segnale piezo 2 | 25 | 22 |
| Segnale piezo 3 | 12 | 32 |
| MAX7219 DIN / CLK / CS | 10 / 11 / 8 | 19 / 23 / 24 |

Ogni modulo KY-006: `S` al suo pin di segnale, `+` (centrale) a 5V (pin 2/4),
`−` a GND. Tutti i pin `5V` sono un'unica linea e tutti i pin `GND` pure, quindi
i fili di alimentazione si possono condividere. Ogni `S` vuole il suo GPIO.
Il modo buzzer di default è `passive`. Hai invece un buzzer attivo che suona
da solo? Avvia con `--buzzer-mode active`.

<img src="piezo.png" alt="I tre piezo cablati" width="751">

## Installazione

```bash
sudo apt install git -y
git clone <this-repo> morsebox
cd morsebox
sudo bash install.sh
```

Imposta l'hostname a `iu2vwk-morse`, installa il servizio di avvio automatico e
attiva l'access point `IU2VWK-MORSE` (password `morse1234`, cambiala in cima a
`install.sh` se vuoi). Da lì in poi, accendere = trainer acceso.

Tre buzzer:

```bash
# /etc/systemd/system/iu2vwk-morse.service
ExecStart=/usr/bin/python3 /opt/iu2vwk-morse/server.py --port 80 --buzz-pins 24,25,12
sudo systemctl daemon-reload && sudo systemctl restart iu2vwk-morse
```

## Versione B — speaker DAC + AUX (branch `vB-dac-sine`, idea di Gianluca)

Seno su altoparlante con inviluppo 4 ms anti-click + AUX per il sidetone.
Il piezo GPIO resta il timing (zero latenza per chi manipola), lo speaker
è un monitor ambiente con ~30-80 ms di ritardo: a 60 WPM non si manipola
ascoltando lo speaker, si manipola sul piezo.

```bash
git checkout vB-dac-sine
python3 server.py --port 80 --speaker
# DAC/USB o HAT I2S: prima lista i device, poi scegli
aplay -l
python3 server.py --port 80 --speaker --speaker-device plughw:CARD=sndrpihifiberry,DEV=0
```

Wiring: DAC/jack -> ampli PAM8403/PAM8302 -> altoparlante 4/8 ohm 3 W.
AUX in parallelo allo speaker con partitore 1k/470 ohm + 10 uF in serie.
Stessi tono/volume della pagina (si applicano a piezo + speaker insieme).
Senza `--speaker` il comportamento è identico a `main`: niente si rompe.

## Scatola e materiale per la fiera

* `qr-1-wifi.png` / `qr-2-pagina.png`. I QR **WIFI** e **APP** per il coperchio
* `qr-1-wifi.dxf` / `qr-2-pagina.dxf`. Stessi QR come geometria da 2 mm per
  incisione laser in Autodesk Inventor
* `screenshot-ui-phone.png`. Come si presenta la pagina sul telefono
* `Morse Code BOX.3mf`. La scatola vera e propria, pronta da stampare in 3D

73 de IU2VWK · Angelo — https://iu2vwk.com

Grazie a Panko per l'ispirazione e per l'originale [Simple CW Keyer](https://github.com/Panko74/Simple-CW-Keyer).
