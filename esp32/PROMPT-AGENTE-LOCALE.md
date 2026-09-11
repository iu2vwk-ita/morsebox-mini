# Prompt da incollare a un agente IA locale (con accesso a filesystem e USB)

Sei un agente IA con accesso al filesystem e alle porte USB di questo PC.
Devi installare MicroPython su una scheda ESP32 collegata via USB, caricare il
progetto contenuto in `morsebox-esp32.zip` ed eseguire i test automatici.
Non chiedere conferma per i comandi: esegui e riporta l'esito. Se un comando
fallisce, diagnostica e prova le alternative indicate.

## Progetto

- Cartella `morsebox-esp32/` (dentro lo zip).
- App MicroPython: `main.py` al boot crea l'access point **`IU2VWK-MORSE`**
  (password `morse1234`), IP **10.42.0.1**, web server sulla porta **80**.
- Pinout: **DIT=GPIO32**, **DAH=GPIO33**, **STRAIGHT=GPIO14** (tutti `Pin.IN`
  con `PULL_UP`, contatti verso GND); **PIEZO=GPIO25,26,27** (PWM); MAX7219
  opzionale su **SCK=18, MOSI=23, CS=4** (disabilitato di default).
- `static/` è la web UI: **non modificarla**.
- `tests/selftest_device.py` è il test che gira **sulla board**.

## Fase 0 — estrai e prepara gli strumenti

```bash
unzip morsebox-esp32.zip
cd morsebox-esp32
python3 -m venv .venv && . .venv/bin/activate
pip install esptool mpremote
```

## Fase 1 — rileva porta seriale e chip

```bash
# Linux
ls /dev/ttyUSB* /dev/ttyACM*
# macOS
ls /dev/cu.*
# rileva il chip (sostituisci <PORTA>)
esptool.py --port <PORTA> chip_id
```

Se non compare nessuna porta: cambia cavo (deve essere un cavo **dati**, non
solo-ricarica), prova un'altra porta USB, oppure usa un adattatore USB-TTL su
TX/RX/GND. Su Linux, se il permesso è negato: `sudo chmod a+rw <PORTA>` o
aggiungi l'utente al gruppo `dialout`.

## Fase 2 — flasha MicroPython

Scegli il firmware in base al chip rilevato:

- ESP32 classico → `ESP32_GENERIC`
- ESP32-S3 → `ESP32_GENERIC_S3`
- ESP32-C3 → `ESP32_GENERIC_C3`

Scarica l'ultima `.bin` da <https://micropython.org/download/> e poi:

```bash
esptool.py --chip esp32 --port <PORTA> erase_flash
esptool.py --chip esp32 --port <PORTA> --baud 460800 write_flash -z 0x1000 <firmware>.bin
```

Se il flash fallisce, tieni premuto **BOOT** mentre colleghi la scheda e riprova.
Adatta `--chip` al chip reale (`esp32`, `esp32s3`, `esp32c3`).

## Fase 3 — deploy del progetto

```bash
bash deploy.sh <PORTA>
```

Verifica il contenuto della board:

```bash
mpremote connect <PORTA> fs ls
mpremote connect <PORTA> fs ls :static
```

## Fase 4 — self-test on-device

Disabilita l'autostart (così la REPL e la porta 80 sono libere), esegui il test,
poi ripristina `main.py`:

```bash
mpremote connect <PORTA> fs cp main.py :main.py.bak
mpremote connect <PORTA> fs rm :main.py
mpremote connect <PORTA> reset
sleep 3
mpremote connect <PORTA> run tests/selftest_device.py
mpremote connect <PORTA> fs cp main.py.bak :main.py
mpremote connect <PORTA> fs rm :main.py.bak
mpremote connect <PORTA> reset
```

Atteso in output una sequenza di righe `PASS` e in fondo:

```
PASS: N   FAIL: 0
```

Il test verifica: AP attivo e IP `10.42.0.1`, lettura GPIO a riposo, PWM
on/off e frequenza, HTTP (`/`, `/style.css`, `/app.js`, `/api/settings`, 404),
WebSocket (101 + `hello`) e la **decodifica Morse guidata dai paddle remoti**
(dit + dah → `A`).

## Fase 5 — report finale

Riporta in modo conciso:

- porta seriale usata e chip rilevato;
- firmware MicroPython usato;
- output completo del self-test;
- ogni eventuale `FAIL` con la causa;
- conferma che dopo il reset finale l'AP `IU2VWK-MORSE` è attivo.

## Criteri di successo

1. MicroPython installato e `main.py` ripristinato (parte al boot).
2. Self-test con `FAIL: 0` (oppure ogni FAIL spiegato).
3. AP `IU2VWK-MORSE` attivo dopo il reset.

## Cosa NON è testabile senza hardware

- I contatti fisici dei paddle/straight key e il suono reale del piezo.
- Il display MAX7219 se non collegato.

## Note

- Se il PC non ha Wi-Fi, non può unirsi all'AP: il self-test usa il loopback
  (`127.0.0.1`) sulla board stessa, quindi funziona comunque.
- Non modificare i file in `static/`: la UI deve restare identica all'originale.
