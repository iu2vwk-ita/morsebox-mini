# IU2VWK MorseBox Mini — configurazione ESP32 / MicroPython
#
# Mappatura pin scelta per ESP32 classico (WROOM-32), evitando:
#   6-11   -> flash SPI
#   34-39  -> solo input, SENZA pull-up interno
#   0/2/12/15 -> strapping pin
#   1/3    -> UART0 (seriale REPL)
#
# Paddle (contatti verso GND, pull-up interno attivo, attivi bassi):
#   DIT      GPIO32
#   DAH      GPIO33
#   STRAIGHT GPIO14
#
# Piezo (PWM hardware LEDC, pilotati insieme):
#   PIEZO1   GPIO25
#   PIEZO2   GPIO26
#   PIEZO3   GPIO27
#
# Display MAX7219 opzionale (SPI hardware VSPI):
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

# ------------------------------------------------------------------ display MAX7219
DISPLAY_ENABLED = False          # True se hai collegato la matrice MAX7219
DISPLAY_SCK = 18
DISPLAY_MOSI = 23
DISPLAY_CS = 4
DISPLAY_MODULES = 4              # 4 x 8x8 = 32 colonne

# ------------------------------------------------------------------ LCD1602 I2C
LCD_ENABLED = True               # True se hai collegato l'LCD1602 con backpack I2C
LCD_I2C_ID = 0
LCD_SDA = 21                     # GPIO21 -> SDA
LCD_SCL = 22                     # GPIO22 -> SCL
LCD_ADDR = 0x27                  # PCF8574T = 0x27, PCF8574A = 0x3F
LCD_COLS = 16
LCD_ROWS = 2

# ------------------------------------------------------------------ access point
AP_SSID = "IU2VWK-MORSE"
AP_PASS = "morse1234"
AP_IP = "10.42.0.1"              # stesso IP del Pi: i QR sul coperchio restano validi
AP_NETMASK = "255.255.255.0"
AP_CHANNEL = 6
HTTP_PORT = 80

# ------------------------------------------------------------------ keyer
HOLD_TIMEOUT_MS = 2500           # dimentica i paddle remoti che non si fanno vivi
SETTINGS_FILE = "settings.json"

DEFAULTS = {"wpm": 20, "reverse": False, "mode": "iambic-b",
            "tone": 650, "buzzer": False, "volume": 70}
