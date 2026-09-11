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
from reflex import Reflex
from easter import EasterEgg
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
    # instead of freezing forever. Armed only AFTER init (see below): if boot
    # ever took more than 10 s it would otherwise reboot in a loop.
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
    # Display: try the OLED first, then the LCD1602, then the MAX7219 matrix.
    # The oled module is imported ONLY if the I2C bus actually answers at
    # 0x3C/0x3D, so with no OLED there is no RAM cost at all.
    if config.OLED_ENABLED:
        try:
            from machine import I2C, Pin
            bus = I2C(config.OLED_I2C_ID, scl=Pin(config.OLED_SCL),
                      sda=Pin(config.OLED_SDA), freq=400000)
            found = bus.scan()
            if 0x3C in found or 0x3D in found:
                import oled
                screen = oled.Screen(bus)
                print("SSD1306 OLED display active")
            else:
                try:
                    bus.deinit()
                except Exception:
                    pass
                print("OLED not present")
        except Exception as e:
            print("OLED not initialized:", e)
            screen = None
    if screen is None and config.LCD_ENABLED:
        try:
            import lcd1602
            screen = lcd1602.Screen()
            print("LCD1602 I2C display active")
        except Exception as e:
            print("LCD not initialized:", e)
            screen = None
    if screen is None and config.DISPLAY_ENABLED:
        try:
            import display
            screen = display.Screen()
            print("MAX7219 display active")
        except Exception as e:
            print("Display not initialized:", e)
            screen = None

    def on_settings(data):
        try:
            if screen:
                screen.set_wpm(data.get("wpm", 20))
                if hasattr(screen, "set_mode"):
                    screen.set_mode(data.get("mode", "iambic-b"))
        except Exception:
            pass
        try:
            sidetone.set_freq(data.get("tone", 650))
            sidetone.set_volume(data.get("volume", 70))
        except Exception:
            pass

    def on_clear():
        if screen and hasattr(screen, "clear_text"):
            try:
                screen.clear_text()
            except Exception:
                pass

    on_settings(settings.get())
    gc.collect()
    print("free RAM:", gc.mem_free())

    exercise = Exercise(settings, hub, sidetone=sidetone, screen=screen)
    reflex = Reflex(settings, hub, sidetone=sidetone, screen=screen)
    easter = EasterEgg(settings, sidetone=sidetone, screen=screen)
    keyer = Keyer(paddle, settings, hub, sidetone=sidetone, screen=screen,
                  exercise=exercise, easter=easter, reflex=reflex)
    server = WebServer(settings, hub, paddle, on_settings=on_settings,
                       on_clear=on_clear)

    # Arm the watchdog now that init is done.
    try:
        wdt = WDT(timeout=10000)
    except Exception:
        wdt = None

    async def wdt_task():
        while True:
            if wdt:
                wdt.feed()
            try:
                settings.flush()     # persist the last debounced change
            except Exception:
                pass
            await asyncio.sleep(1)

    async def runner():
        asyncio.create_task(keyer.run())
        asyncio.create_task(exercise.run())
        asyncio.create_task(reflex.run())
        asyncio.create_task(easter.run())
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
