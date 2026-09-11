# IU2VWK MorseBox Mini — entry point ESP32 / MicroPython.
#
# Al boot: alza l'access point, inizializza paddle/piezo, avvia l'event loop
# con keyer + web server (+ display MAX7219 se abilitato).
import gc
import uasyncio as asyncio
from machine import freq

import config
from wifi_ap import start_ap
from settings import Settings
from hub import Hub
from gpio import Paddle
from sidetone import Sidetone
from keyer import Keyer
from webserver import WebServer


def main():
    try:
        freq(240000000)          # 240 MHz: piu' margine per il tick da 1 ms
    except Exception:
        pass
    gc.collect()

    ap = start_ap()
    print("AP '%s' su http://%s" % (config.AP_SSID, ap.ifconfig()[0]))

    settings = Settings()
    hub = Hub()
    paddle = Paddle()

    sidetone = Sidetone(config.BUZZ_PINS, freq=settings.get()["tone"],
                        mode=config.BUZZER_MODE)
    sidetone.set_volume(settings.get()["volume"])
    print("Piezo PWM:", config.BUZZ_PINS, "ok" if sidetone._ok else "assenti")

    screen = None
    if config.LCD_ENABLED:
        try:
            import lcd1602
            screen = lcd1602.Screen()
            print("Display LCD1602 I2C attivo")
        except Exception as e:
            print("LCD non inizializzato:", e)
            screen = None
    elif config.DISPLAY_ENABLED:
        try:
            import display
            screen = display.Screen()
            print("Display MAX7219 attivo")
        except Exception as e:
            print("Display non inizializzato:", e)
            screen = None

    def on_settings(data):
        if screen:
            screen.set_wpm(data.get("wpm", 20))
            if hasattr(screen, "set_mode"):
                screen.set_mode(data.get("mode", "iambic-b"))
        sidetone.set_freq(data.get("tone", 650))
        sidetone.set_volume(data.get("volume", 70))

    on_settings(settings.get())

    keyer = Keyer(paddle, settings, hub, sidetone=sidetone, screen=screen)
    server = WebServer(settings, hub, paddle, on_settings=on_settings)

    async def runner():
        asyncio.create_task(keyer.run())
        asyncio.create_task(server.start())
        if screen:
            asyncio.create_task(screen.run())
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass


main()
