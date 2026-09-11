# IU2VWK MorseBox Mini - ESP32 / MicroPython configuration
#
# Pin mapping chosen for a classic ESP32 (WROOM-32), avoiding:
#   6-11      -> SPI flash
#   34-39     -> input only, NO internal pull-up
#   0/2/12/15 -> strapping pins
#   1/3       -> UART0 (REPL serial)
#
# Paddle (contacts to GND, internal pull-up enabled, active low):
#   DIT      GPIO32
#   DAH      GPIO33
#   STRAIGHT GPIO14
#
# Piezo (hardware LEDC PWM, all driven together):
#   PIEZO1   GPIO25
#   PIEZO2   GPIO26
#   PIEZO3   GPIO27
#
# Optional MAX7219 display (hardware VSPI):
#   SCK      GPIO18
#   MOSI     GPIO23
#   CS       GPIO4

# ------------------------------------------------------------------ paddle
DIT_PIN = 32
DAH_PIN = 33
KEY_PIN = 14

# ------------------------------------------------------------------ piezo
BUZZ_PINS = (25, 26, 27)
BUZZER_MODE = "passive"          # "passive" = piezo PWM, "active" = DC on/off

# ------------------------------------------------------------------ MAX7219 display
DISPLAY_ENABLED = False          # True if the MAX7219 matrix is connected
DISPLAY_SCK = 18
DISPLAY_MOSI = 23
DISPLAY_CS = 4
DISPLAY_MODULES = 4              # 4 x 8x8 = 32 columns

# ------------------------------------------------------------------ LCD1602 I2C
LCD_ENABLED = True               # True if the LCD1602 with I2C backpack is connected
LCD_I2C_ID = 0
LCD_SDA = 21                     # GPIO21 -> SDA
LCD_SCL = 22                     # GPIO22 -> SCL
LCD_ADDR = 0x27                  # PCF8574T = 0x27, PCF8574A = 0x3F
LCD_COLS = 16
LCD_ROWS = 2

# ------------------------------------------------------------------ OLED SSD1306
# 0.96"/1.3" I2C OLED (128x64). Tried first; falls back to the LCD1602.
OLED_ENABLED = True              # True if an SSD1306 I2C OLED is connected
OLED_I2C_ID = 0
OLED_SDA = 21                    # same I2C bus as the LCD1602
OLED_SCL = 22
OLED_ADDR = 0x3C                 # 0x3C / 0x3D (auto-detected on the bus too)
OLED_WIDTH = 128
OLED_HEIGHT = 64

# ------------------------------------------------------------------ access point
AP_SSID = "IU2VWK-MORSE"
AP_PASS = "morse1234"
AP_IP = "10.42.0.1"              # same IP as the Pi: the lid QR codes stay valid
AP_NETMASK = "255.255.255.0"
AP_CHANNEL = 6
HTTP_PORT = 80

# ------------------------------------------------------------------ keyer
HOLD_TIMEOUT_MS = 2500           # forget remote paddles that stop reporting
SETTINGS_FILE = "settings.json"
TONE_MIN = 500                   # sidetone range (Hz)
TONE_MAX = 1000

# ------------------------------------------------------------------ boot message
# Scrolled on the LCD (or MAX7219) once at startup. Set to "" to disable.
BOOT_TITLE = ""                          # optional fixed first line
BOOT_MESSAGE = "IU2VWK MORSE BOX - batti SOS per iniziare"
BOOT_HELP = ""                           # optional second scrolled message
BOOT_SPEED_MS = 90                       # scroll step in ms (lower = faster)

DEFAULTS = {"wpm": 20, "reverse": False, "mode": "iambic-b",
            "tone": 650, "buzzer": False, "volume": 70}
