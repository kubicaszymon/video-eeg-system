# Sync marker firmware for the video-EEG accuracy test.
# Board: Raspberry Pi Pico 2 (RP2350), MicroPython.
# Save this file onto the Pico as  main.py  (so it auto-runs at power-on).
#
# What it does:
#   - GPIO 16 -> LED  (camera sees a flash)            [via 220 ohm to GND]
#   - GPIO 15 -> RIN1 (EEG sync input, Mini-DIN pin 3) [via 1 kohm series R]
#   Both pins go HIGH together, every INTERVAL_S seconds, for PULSE_MS ms.
#   The LED flash and the EEG 'Events' change are therefore the SAME instant
#   (within ~10 us) -> that shared instant is the ground-truth marker.
#
# PULSE_MS = 50 is deliberately longer than one video frame (33 ms @ 30 fps)
# so at least one frame is guaranteed to catch the LED fully lit.

from machine import Pin
import time

led = Pin(16, Pin.OUT, value=0)   # physical pin 21
aux = Pin(15, Pin.OUT, value=0)   # physical pin 20

PULSE_MS   = 50      # marker on-time (ms)  -- > one frame period @ 30 fps
INTERVAL_S = 5       # one marker every N seconds

# Boot indicator: 3 quick blinks so you know the firmware is alive.
for _ in range(3):
    led.value(1); time.sleep_ms(100)
    led.value(0); time.sleep_ms(100)
time.sleep_ms(500)

while True:
    led.value(1); aux.value(1)        # LED + RIN1 HIGH together
    time.sleep_ms(PULSE_MS)
    led.value(0); aux.value(0)        # both LOW together
    time.sleep(INTERVAL_S)
