#!/usr/bin/env python3
"""
Hardware Test Suite for Raspberry Pi 4B Alarm System
====================================================

Run this before using alarm_rpi.py to verify all hardware is working.
"""

import sys
import subprocess
import time
from pathlib import Path


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def test_gpio_buzzer(pin=17):
    """Test buzzer on GPIO pin."""
    print(f"\n{Colors.BLUE}[TEST] GPIO Buzzer on Pin {pin}{Colors.END}")
    
    try:
        import RPi.GPIO as GPIO
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        
        print("  → Turning buzzer ON...")
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(1)
        
        print("  → Turning buzzer OFF...")
        GPIO.output(pin, GPIO.LOW)
        
        GPIO.cleanup()
        print(f"{Colors.GREEN}✓ GPIO buzzer works!{Colors.END}")
        return True
    
    except Exception as e:
        print(f"{Colors.RED}✗ GPIO buzzer failed: {e}{Colors.END}")
        return False


def test_pwm_buzzer(pin=17, freq=1000):
    """Test PWM buzzer tone."""
    print(f"\n{Colors.BLUE}[TEST] PWM Buzzer (Tone Test){Colors.END}")
    
    try:
        import RPi.GPIO as GPIO
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        
        pwm = GPIO.PWM(pin, freq)
        
        print(f"  → Playing {freq} Hz tone...")
        pwm.start(70)  # 70% duty cycle
        time.sleep(1)
        pwm.stop()
        
        GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()
        print(f"{Colors.GREEN}✓ PWM buzzer works!{Colors.END}")
        return True
    
    except Exception as e:
        print(f"{Colors.RED}✗ PWM buzzer failed: {e}{Colors.END}")
        return False


def test_usb_camera():
    """Test USB camera with OpenCV."""
    print(f"\n{Colors.BLUE}[TEST] USB Camera{Colors.END}")
    
    try:
        import cv2
        
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print(f"{Colors.RED}✗ Camera not accessible{Colors.END}")
            return False
        
        # Try to grab a frame
        ret, frame = cap.read()
        if not ret:
            print(f"{Colors.RED}✗ Cannot read from camera{Colors.END}")
            cap.release()
            return False
        
        h, w = frame.shape[:2]
        print(f"  → Camera resolution: {w}x{h}")
        
        cap.release()
        print(f"{Colors.GREEN}✓ USB camera works!{Colors.END}")
        return True
    
    except Exception as e:
        print(f"{Colors.RED}✗ Camera test failed: {e}{Colors.END}")
        return False


def test_mediapipe():
    """Test MediaPipe library."""
    print(f"\n{Colors.BLUE}[TEST] MediaPipe (Face Detection){Colors.END}")
    
    try:
        import mediapipe as mp
        
        mp_face_mesh = mp.solutions.face_mesh
        print("  → Initializing face mesh...")
        
        with mp_face_mesh.FaceMesh() as face_mesh:
            print("  → MediaPipe ready for eye detection")
        
        print(f"{Colors.GREEN}✓ MediaPipe works!{Colors.END}")
        return True
    
    except Exception as e:
        print(f"{Colors.RED}✗ MediaPipe test failed: {e}{Colors.END}")
        return False


def test_microphone():
    """Test INMP441 microphone via ALSA."""
    print(f"\n{Colors.BLUE}[TEST] INMP441 Microphone{Colors.END}")
    
    try:
        # First, list devices
        print("  → ALSA recording devices:")
        result = subprocess.run(['arecord', '-l'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        
        for line in result.stdout.split('\n'):
            if 'card' in line.lower() or 'device' in line.lower():
                print(f"    {line}")
        
        # Try to record
        print("  → Recording 2-second test audio...")
        output_file = "/tmp/test_mic.wav"
        
        result = subprocess.run([
            'arecord', '-D', 'plughw:1,0',
            '-r', '16000', '-c', '1', '-f', 'S16_LE',
            '-d', '2',
            output_file
        ], timeout=5, capture_output=True)
        
        if result.returncode == 0 and Path(output_file).exists():
            size = Path(output_file).stat().st_size
            print(f"  → Recording saved: {size} bytes")
            Path(output_file).unlink()
            print(f"{Colors.GREEN}✓ Microphone works!{Colors.END}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠ Recording failed. Check INMP441 connection and ALSA config.{Colors.END}")
            return False
    
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}✗ Microphone test timed out{Colors.END}")
        return False
    except Exception as e:
        print(f"{Colors.YELLOW}⚠ Microphone test skipped: {e}{Colors.END}")
        print(f"    (Make sure INMP441 is connected and ALSA is configured)")
        return None


def test_pygame_display():
    """Test pygame display initialization."""
    print(f"\n{Colors.BLUE}[TEST] Display (Pygame/Touch LCD){Colors.END}")
    
    try:
        import pygame
        import os
        
        # Try to initialize with framebuffer
        old_driver = os.environ.get('SDL_VIDEODRIVER')
        os.environ['SDL_VIDEODRIVER'] = 'fbcon'
        
        pygame.init()
        screen = pygame.display.set_mode((480, 320))
        screen.fill((0, 0, 100))
        pygame.display.flip()
        time.sleep(0.5)
        
        pygame.quit()
        
        if old_driver:
            os.environ['SDL_VIDEODRIVER'] = old_driver
        
        print(f"{Colors.GREEN}✓ Display initialized!{Colors.END}")
        return True
    
    except Exception as e:
        print(f"{Colors.YELLOW}⚠ Display test skipped: {e}{Colors.END}")
        print(f"    (This is OK if no display is connected)")
        return None


def test_i2s_interface():
    """Check if I2S interface is enabled."""
    print(f"\n{Colors.BLUE}[TEST] I2S Interface{Colors.END}")
    
    try:
        with open('/boot/config.txt', 'r') as f:
            config = f.read()
        
        i2s_enabled = 'dtparam=i2s=on' in config
        i2s_overlay = 'dtoverlay=i2s-gpio' in config
        
        if i2s_enabled:
            print(f"  ✓ I2S parameter enabled")
        else:
            print(f"  ✗ I2S parameter NOT enabled")
        
        if i2s_overlay:
            print(f"  ✓ I2S GPIO overlay configured")
        else:
            print(f"  ⚠ I2S GPIO overlay not configured")
        
        if i2s_enabled or i2s_overlay:
            print(f"{Colors.GREEN}✓ I2S interface ready!{Colors.END}")
            return True
        else:
            print(f"{Colors.YELLOW}⚠ I2S may not be enabled. Run setup_rpi_hardware.sh{Colors.END}")
            return False
    
    except Exception as e:
        print(f"{Colors.RED}✗ I2S check failed: {e}{Colors.END}")
        return False


def test_python_packages():
    """Check all required Python packages."""
    print(f"\n{Colors.BLUE}[TEST] Python Package Dependencies{Colors.END}")
    
    required_packages = {
        'cv2': 'opencv-python',
        'mediapipe': 'mediapipe',
        'numpy': 'numpy',
        'pygame': 'pygame',
        'RPi': 'RPi.GPIO',
    }
    
    all_ok = True
    for module, package_name in required_packages.items():
        try:
            __import__(module)
            print(f"  ✓ {package_name}")
        except ImportError:
            print(f"  ✗ {package_name} NOT installed")
            all_ok = False
    
    if all_ok:
        print(f"{Colors.GREEN}✓ All packages installed!{Colors.END}")
    else:
        print(f"{Colors.YELLOW}⚠ Missing packages. Run: pip3 install <package-name>{Colors.END}")
    
    return all_ok


def test_speech_recognition():
    """Test speech recognition capability."""
    print(f"\n{Colors.BLUE}[TEST] Speech Recognition{Colors.END}")
    
    try:
        import speech_recognition as sr
        print(f"  ✓ SpeechRecognition library available")
        print(f"{Colors.GREEN}✓ Speech recognition ready!{Colors.END}")
        return True
    except ImportError:
        print(f"{Colors.YELLOW}⚠ SpeechRecognition not installed{Colors.END}")
        print(f"    Run: pip3 install SpeechRecognition")
        return False


def test_systemd_service():
    """Check if systemd service would work."""
    print(f"\n{Colors.BLUE}[TEST] Systemd Service Setup{Colors.END}")
    
    service_path = Path('/etc/systemd/system/alarm.service')
    
    if service_path.exists():
        print(f"  ✓ Service file exists at {service_path}")
        return True
    else:
        print(f"  ⚠ Service file not found")
        print(f"    You can create it with: setup_rpi_hardware.sh")
        return None


def run_all_tests():
    """Run all hardware tests."""
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"  RPi Alarm System - Hardware Test Suite")
    print(f"{'='*60}{Colors.END}")
    
    tests = [
        ("Python Packages", test_python_packages),
        ("I2S Interface", test_i2s_interface),
        ("GPIO Buzzer", test_gpio_buzzer),
        ("PWM Buzzer (Tone)", test_pwm_buzzer),
        ("USB Camera", test_usb_camera),
        ("MediaPipe", test_mediapipe),
        ("Microphone (INMP441)", test_microphone),
        ("Display (Pygame)", test_pygame_display),
        ("Speech Recognition", test_speech_recognition),
        ("Systemd Service", test_systemd_service),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{Colors.RED}✗ Unexpected error: {e}{Colors.END}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}{Colors.END}")
    
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)
    
    for test_name, result in results:
        if result is True:
            status = f"{Colors.GREEN}✓ PASS{Colors.END}"
        elif result is False:
            status = f"{Colors.RED}✗ FAIL{Colors.END}"
        else:
            status = f"{Colors.YELLOW}⚠ SKIP{Colors.END}"
        
        print(f"  {status}  {test_name}")
    
    print(f"\n  Total: {Colors.GREEN}{passed} passed{Colors.END}, "
          f"{Colors.RED}{failed} failed{Colors.END}, "
          f"{Colors.YELLOW}{skipped} skipped{Colors.END}")
    
    if failed == 0:
        print(f"\n{Colors.GREEN}✓ All critical tests passed! You can run alarm_rpi.py{Colors.END}\n")
        return 0
    else:
        print(f"\n{Colors.RED}✗ Some tests failed. See above for details.{Colors.END}\n")
        return 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test suite interrupted by user.{Colors.END}\n")
        sys.exit(1)
