# IU2VWK MorseBox Mini - ESP32 / MicroPython entry point.
#
# On boot: bring up the access point, init paddle/piezo, start the event loop
# with keyer + web server (+ MAX7219 display if enabled).
import gc
import uasyncio as asyncio
from machine import freq, WDT

import config
from wifi_ap import start_ap
from settings import Settings
from hub import Hub
from gpio import Paddle
from sidetone import Sidetone
from keyer import Keyer
from exercise import Exercise
from webserver import WebServer


def main():
    try:
        freq(240000000)          # 240 MHz: more headroom for the 1 ms tick
    except Exception:
        pass
    gc.collect()

    ap = start_ap()
    print("AP '%s' at http://%s" % (config.AP_SSID, ap.ifconfig()[0]))

    # Hardware watchdog: if the event loop ever hangs, the board reboots
    # instead of freezing forever.
    try:
        wdt = WDT(timeout=10000)
    except Exception:
        wdt = None

    settings = Settings()
    hub = Hub()
    paddle = Paddle()

    sidetone = Sidetone(config.BUZZ_PINS, freq=settings.get()["tone"],
                        mode=config.BUZZER_MODE)
    sidetone.set_volume(settings.get()["volume"])
    print("Piezo PWM:", config.BUZZ_PINS,
          "ok" if sidetone._ok else "not found")

    screen = None
    if config.LCD_ENABLED:
        try:
            import lcd1602
            screen = lcd1602.Screen()
            print("LCD1602 I2C display active")
        except Exception as e:
            print("LCD not initialized:", e)
            screen = None
    elif config.DISPLAY_ENABLED:
        try:
            import display
            screen = display.Screen()
            print("MAX7219 display active")
        except Exception as e:
            print("Display not initialized:", e)
            screen = None

    def on_settings(data):
        if screen:
            screen.set_wpm(data.get("wpm", 20))
            if hasattr(screen, "set_mode"):
                screen.set_mode(data.get("mode", "iambic-b"))
        sidetone.set_freq(data.get("tone", 650))
        sidetone.set_volume(data.get("volume", 70))

    on_settings(settings.get())

    exercise = Exercise(settings, hub, sidetone=sidetone, screen=screen)
    keyer = Keyer(paddle, settings, hub, sidetone=sidetone, screen=screen,
                  exercise=exercise)
    server = WebServer(settings, hub, paddle, on_settings=on_settings)

    async def wdt_task():
        while True:
            if wdt:
                wdt.feed()
            await asyncio.sleep(1)

    async def runner():
        asyncio.create_task(keyer.run())
        asyncio.create_task(exercise.run())
        asyncio.create_task(server.start())
        if wdt:
            asyncio.create_task(wdt_task())
        if screen:
            asyncio.create_task(screen.run())
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass


main()
