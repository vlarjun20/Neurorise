#!/usr/bin/env python3
"""
Raspberry Pi Voice-Controlled Alarm with LED Indicator
-------------------------------------------------------
- Set alarm time via input
- LED blinks for 15 seconds when alarm fires
- Repeats every 15-second interval until stopped
- Voice commands: "stop alarm", "snooze X minutes"
"""

import RPi.GPIO as GPIO
import time
import threading
import speech_recognition as sr
from datetime import datetime, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────
LED_PIN = 18                # GPIO pin for LED (BCM numbering)
BLINK_DURATION = 15         # seconds the LED blinks per ring cycle
BLINK_INTERVAL = 0.15       # on/off toggle speed for LED
RING_GAP = 15               # seconds pause between ring cycles
VOICE_TIMEOUT = 5           # seconds to wait for voice input
VOICE_PHRASE_LIMIT = 5      # max seconds of speech to process
# ──────────────────────────────────────────────────────────────────────────────

# Shared state
alarm_active = threading.Event()
snooze_event = threading.Event()
stop_event = threading.Event()
snooze_minutes = 0
lock = threading.Lock()


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.output(LED_PIN, GPIO.LOW)


def blink_led(duration):
    """Blink the LED rapidly for `duration` seconds or until stop/snooze."""
    end_time = time.time() + duration
    state = False
    while time.time() < end_time:
        if stop_event.is_set() or snooze_event.is_set():
            GPIO.output(LED_PIN, GPIO.LOW)
            return
        state = not state
        GPIO.output(LED_PIN, GPIO.HIGH if state else GPIO.LOW)
        time.sleep(BLINK_INTERVAL)
    GPIO.output(LED_PIN, GPIO.LOW)


def listen_for_command(recognizer, mic):
    """Capture one voice command and return the text (lowercase), or None."""
    try:
        with mic as source:
            audio = recognizer.listen(source, timeout=VOICE_TIMEOUT,
                                      phrase_time_limit=VOICE_PHRASE_LIMIT)
        text = recognizer.recognize_google(audio).lower()
        print(f"  [Voice] Heard: \"{text}\"")
        return text
    except (sr.UnknownValueError, sr.WaitTimeoutError):
        return None
    except sr.RequestError as e:
        print(f"  [Voice] API error: {e}")
        return None


def voice_listener():
    """Background thread: continuously listens for voice commands while alarm rings."""
    global snooze_minutes
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    # Calibrate once for ambient noise
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)

    print("  [Voice] Listener ready. Say 'stop alarm' or 'snooze <N> minutes'.")

    while alarm_active.is_set() and not stop_event.is_set():
        text = listen_for_command(recognizer, mic)
        if text is None:
            continue

        # ── STOP ──────────────────────────────────────────────────────────
        if "stop" in text:
            print("  >>> STOP command received.")
            stop_event.set()
            return

        # ── SNOOZE ────────────────────────────────────────────────────────
        if "snooze" in text or "snooz" in text:
            minutes = parse_snooze_minutes(text)
            if minutes and minutes > 0:
                with lock:
                    snooze_minutes = minutes
                print(f"  >>> SNOOZE command received: {minutes} minute(s).")
                snooze_event.set()
                return
            else:
                print("  [Voice] Could not parse snooze duration. Try: 'snooze 5 minutes'.")


def parse_snooze_minutes(text):
    """Extract the number of minutes from a snooze command string."""
    # Handle spoken number words
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "fifteen": 15, "twenty": 20, "thirty": 30,
    }
    for word, num in word_to_num.items():
        if word in text:
            return num
    # Handle digit numbers
    for token in text.split():
        if token.isdigit():
            return int(token)
    return None


def alarm_ring_loop():
    """Blink LED for 15 s, pause 15 s, repeat — until stopped or snoozed."""
    cycle = 1
    while not stop_event.is_set() and not snooze_event.is_set():
        print(f"\n  ** RING cycle {cycle} — LED blinking for {BLINK_DURATION}s **")
        blink_led(BLINK_DURATION)

        if stop_event.is_set() or snooze_event.is_set():
            break

        print(f"  ** Pause {RING_GAP}s before next ring **")
        for _ in range(RING_GAP * 10):          # check every 0.1 s
            if stop_event.is_set() or snooze_event.is_set():
                break
            time.sleep(0.1)
        cycle += 1


def run_alarm_sequence():
    """Fire the alarm: start LED blinking + voice listener together."""
    global snooze_minutes

    alarm_active.set()
    stop_event.clear()
    snooze_event.clear()
    snooze_minutes = 0

    # Start voice listener in background
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()

    # Run the ring loop (blocks until stopped/snoozed)
    alarm_ring_loop()

    alarm_active.clear()
    GPIO.output(LED_PIN, GPIO.LOW)

    # Return snooze minutes (0 means alarm was stopped, >0 means snoozed)
    with lock:
        return snooze_minutes if snooze_event.is_set() else 0


def wait_for_alarm(alarm_time_str):
    """Block until the target HH:MM time arrives (today or next day)."""
    hour, minute = map(int, alarm_time_str.split(":"))
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
        print(f"  (Alarm is for tomorrow: {target.strftime('%Y-%m-%d %H:%M')})")

    print(f"\n  Alarm set for {target.strftime('%H:%M')}. Waiting...")
    while datetime.now() < target:
        time.sleep(1)


def main():
    setup_gpio()

    try:
        alarm_input = input("Enter alarm time (HH:MM, 24-hr format): ").strip()
        # Basic validation
        parts = alarm_input.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            print("Invalid format. Use HH:MM (e.g. 07:30)")
            return
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            print("Invalid time. Hours: 0-23, Minutes: 0-59")
            return

        wait_for_alarm(alarm_input)

        while True:
            print("\n========== ALARM RINGING ==========")
            snoozed = run_alarm_sequence()

            if snoozed > 0:
                print(f"\n  Snoozed for {snoozed} minute(s). Will ring again at "
                      f"{(datetime.now() + timedelta(minutes=snoozed)).strftime('%H:%M:%S')}.\n")
                # Wait for snooze duration (check every second so Ctrl+C works)
                snooze_end = time.time() + snoozed * 60
                while time.time() < snooze_end:
                    time.sleep(1)
            else:
                print("\n  Alarm stopped. Goodbye!")
                break

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    finally:
        GPIO.output(LED_PIN, GPIO.LOW)
        GPIO.cleanup()


if __name__ == "__main__":
    main()
