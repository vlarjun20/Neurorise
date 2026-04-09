#!/usr/bin/env python3
"""
Integrated Alarm with Camera Eye Detection & Voice Commands (Raspberry Pi 4B)
─────────────────────────────────────────────────────────────────────────────
Hardware:
- USB 2.0 Microphone (automatic detection)
- USB Camera
- Bluetooth Speaker (wireless audio output)

Features:
- Set alarm time via terminal input
- At alarm time: opens camera and monitors eye status
- If eyes are OPEN → automatically stops alarm
- Voice commands: "stop alarm", "snooze X minutes"
- Alarm plays on Bluetooth speaker for 15 seconds when alarm fires
- Repeats every 15-second interval until stopped
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import threading
import subprocess
import os
from datetime import datetime, timedelta
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ALARM_DURATION = 15         # seconds the alarm sounds per ring cycle
RING_GAP = 15               # seconds pause between ring cycles
VOICE_TIMEOUT = 5           # seconds to wait for voice input
VOICE_PHRASE_LIMIT = 5      # max seconds of speech to process
BT_SPEAKER_NAME = "rpi-speaker"  # Bluetooth speaker device name (adjust if needed)
USB_MIC_INDEX = None        # USB mic device index (auto-detect, set manually if needed)
ENABLE_EYE_DETECTION = True # Set to False to skip camera eye detection
# ──────────────────────────────────────────────────────────────────────────────

# Eye Detection Setup
mp_face_mesh = mp.solutions.face_mesh
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]
EAR_THRESHOLD = 0.22

# Shared state
alarm_active = threading.Event()
snooze_event = threading.Event()
stop_event = threading.Event()
eye_open_event = threading.Event()
snooze_minutes = 0
lock = threading.Lock()
current_eye_status = "NO FACE"


def find_usb_mic_index():
    """
    Auto-detect USB microphone device index.
    Returns index or None if not found.
    """
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        print("  [Mic] Available audio devices:")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"    {i}: {info['name']}")
                # Look for USB device
                if 'usb' in info['name'].lower():
                    print(f"  [Mic] Using USB device: {info['name']}")
                    p.terminate()
                    return i
        p.terminate()
    except Exception as e:
        print(f"  [Mic] Error detecting USB mic: {e}")
    return None


def play_alarm_bluetooth(duration):
    """
    Play alarm sound on Bluetooth speaker for `duration` seconds.
    Uses text-to-speech or simple beep pattern.
    """
    end_time = time.time() + duration
    
    try:
        # Try using pyttsx3 for text-to-speech (if available)
        import pyttsx3
        engine = pyttsx3.init()
        engine.say("Alarm is ringing")
        engine.runAndWait()
    except ImportError:
        # Fallback: Use system beep routed to Bluetooth
        print("  [Alarm] Playing tone on Bluetooth speaker...")
        try:
            # Play a simple alert tone using for loop
            for i in range(duration):
                if stop_event.is_set() or snooze_event.is_set() or eye_open_event.is_set():
                    break
                # Generate beep using paplay or espeak
                subprocess.run(["paplay", "-d", BT_SPEAKER_NAME, "-s", "800", "/dev/zero"],
                              timeout=0.5, capture_output=True)
                time.sleep(0.5)
        except Exception as e:
            print(f"  [Alarm] Error playing on Bluetooth: {e}")
            # Just print alarm indicator
            for i in range(duration):
                if stop_event.is_set() or snooze_event.is_set() or eye_open_event.is_set():
                    break
                print("  🔊 ALARM 🔊")
                time.sleep(1)
    
    # Monitor for stop/snooze/eye-open during remaining time
    while time.time() < end_time:
        if stop_event.is_set() or snooze_event.is_set() or eye_open_event.is_set():
            return
        time.sleep(0.1)


def init_gpio():
    """Initialize GPIO (stub for backward compatibility)."""
    pass


def cleanup_gpio():
    """Cleanup GPIO (stub for backward compatibility)."""
    pass



def eye_aspect_ratio(landmarks, eye_pts, w, h):
    """Calculate eye aspect ratio from MediaPipe landmarks."""
    pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in eye_pts]
    A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    return (A + B) / (2.0 * C)


def camera_eye_monitor():
    """
    Monitor camera for eye status.
    Sets eye_open_event if eyes are detected as OPEN.
    Displays camera feed on small LCD window.
    """
    global current_eye_status
    
    cap = cv2.VideoCapture(0)
    
    with mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as face_mesh:

        while alarm_active.is_set() and not stop_event.is_set() and not snooze_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            status = "NO FACE"
            color = (128, 128, 128)

            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                left_ear  = eye_aspect_ratio(lm, LEFT_EYE, w, h)
                right_ear = eye_aspect_ratio(lm, RIGHT_EYE, w, h)
                avg_ear   = (left_ear + right_ear) / 2.0

                if avg_ear < EAR_THRESHOLD:
                    status = "CLOSED"
                    color  = (0, 0, 255)
                else:
                    status = "OPEN"
                    color  = (0, 255, 0)
                    eye_open_event.set()
                    print("\n  >>> EYE STATUS: OPEN - Stopping alarm automatically!")

                cv2.putText(frame, f"EAR: {avg_ear:.2f}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            cv2.putText(frame, f"EYE: {status}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            
            cv2.imshow("Alarm - Eye Monitor", frame)
            
            with lock:
                current_eye_status = status

            if cv2.waitKey(1) & 0xFF == ord('q'):
                stop_event.set()
                break

    cap.release()
    cv2.destroyAllWindows()


def record_audio_snippet(duration=3, output_file="/tmp/voice_cmd.wav"):
    """
    Record audio from USB microphone using arecord.
    Returns path to recorded file or None if failed.
    """
    cmd = [
        "arecord",
        "-r", "16000",
        "-c", "1",
        "-f", "S16_LE",
        "-d", str(duration),
        output_file
    ]
    try:
        result = subprocess.run(cmd, timeout=duration + 2, capture_output=True)
        if result.returncode == 0:
            return output_file
    except Exception as e:
        print(f"  [Voice] Recording error: {e}")
    return None


def transcribe_audio_with_google(audio_file):
    """
    Transcribe audio using Google Speech Recognition.
    Requires: pip install google-cloud-speech (offline) or 
    fallback to simpler keyword matching if offline only.
    """
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio).lower()
        print(f"  [Voice] Heard: \"{text}\"")
        return text
    except Exception as e:
        print(f"  [Voice] Transcription error: {e}")
    return None


def listen_for_command():
    """Capture one voice command and return the text (lowercase), or None."""
    print("  [Voice] Recording for 3 seconds...")
    audio_file = record_audio_snippet(duration=3)
    if audio_file is None:
        return None
    
    text = transcribe_audio_with_google(audio_file)
    try:
        os.remove(audio_file)
    except:
        pass
    return text


def voice_listener():
    """Background thread: continuously listens for voice commands while alarm rings."""
    global snooze_minutes
    
    print("  [Voice] Listener ready. Say 'stop alarm' or 'snooze <N> minutes'.")

    while alarm_active.is_set() and not stop_event.is_set() and not eye_open_event.is_set():
        text = listen_for_command()
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
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "fifteen": 15, "twenty": 20, "thirty": 30,
    }
    for word, num in word_to_num.items():
        if word in text:
            return num
    for token in text.split():
        if token.isdigit():
            return int(token)
    return None


def alarm_ring_loop():
    """
    Play alarm for 15 s, pause 15 s, repeat — until stopped, snoozed, or eyes open.
    Runs camera monitor in parallel if ENABLE_EYE_DETECTION is True.
    """
    # Start camera monitoring in background if enabled
    if ENABLE_EYE_DETECTION:
        camera_thread = threading.Thread(target=camera_eye_monitor, daemon=True)
        camera_thread.start()

    cycle = 1
    while not stop_event.is_set() and not snooze_event.is_set() and not eye_open_event.is_set():
        print(f"\n  ** RING cycle {cycle} — Bluetooth speaker playing for {ALARM_DURATION}s **")
        play_alarm_bluetooth(ALARM_DURATION)

        if stop_event.is_set() or snooze_event.is_set() or eye_open_event.is_set():
            break

        print(f"  ** Pause {RING_GAP}s before next ring **")
        for _ in range(RING_GAP * 10):
            if stop_event.is_set() or snooze_event.is_set() or eye_open_event.is_set():
                break
            time.sleep(0.1)
        cycle += 1


def run_alarm_sequence():
    """Fire the alarm: start buzzer, voice listener, and eye monitor together."""
    global snooze_minutes

    alarm_active.set()
    stop_event.clear()
    snooze_event.clear()
    eye_open_event.clear()
    snooze_minutes = 0

    # Start voice listener in background
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()

    # Run the ring loop (includes camera monitor)
    alarm_ring_loop()

    alarm_active.clear()

    with lock:
        if snooze_event.is_set():
            return snooze_minutes
        else:
            return 0


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


def get_time_input_terminal():
    """
    Simple terminal-based time input.
    Returns time string "HH:MM" or None if cancelled.
    """
    while True:
        alarm_input = input("\n  Enter alarm time (HH:MM, 24-hr format) or 'q' to quit: ").strip()
        
        if alarm_input.lower() == 'q':
            return None
        
        parts = alarm_input.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            print("  Invalid format. Use HH:MM (e.g., 07:30)")
            continue
        
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            print("  Invalid time. Hours: 0-23, Minutes: 0-59")
            continue
        
        return f"{h:02d}:{m:02d}"


def main():
    """Main alarm loop."""
    global USB_MIC_INDEX
    try:
        # Auto-detect USB microphone
        print("\n  Detecting hardware...")
        if USB_MIC_INDEX is None:
            USB_MIC_INDEX = find_usb_mic_index()
            if USB_MIC_INDEX is None:
                print("  [Mic] Warning: USB microphone not auto-detected. Voice commands may not work.")
                print("  [Mic] Connect USB microphone and try again, or set USB_MIC_INDEX manually.\n")
        
        # Get alarm time via terminal input
        alarm_time = get_time_input_terminal()
        if alarm_time is None:
            print("\n  Alarm setup cancelled.")
            return
        
        wait_for_alarm(alarm_time)
        
        while True:
            print("\n========== ALARM RINGING ==========")
            snoozed = run_alarm_sequence()
            
            if snoozed > 0:
                snooze_end_time = (datetime.now() + timedelta(minutes=snoozed)).strftime('%H:%M:%S')
                print(f"\n  Snoozed for {snoozed} minute(s). Will ring again at {snooze_end_time}.\n")
                snooze_end = time.time() + snoozed * 60
                while time.time() < snooze_end:
                    time.sleep(1)
            else:
                print("\n  Alarm stopped. Goodbye!")
                break

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
