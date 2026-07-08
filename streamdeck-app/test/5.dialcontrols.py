import io
import sys
import subprocess
import threading
import time
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices.StreamDeck import TouchscreenEventType

# ---------------------------------------------------------------------------
# Hardware State
# ---------------------------------------------------------------------------

current_brightness = 50
is_display_on = True
saved_brightness = 50

# Speaker (dial 4 / index 3)
current_volume = 50
is_muted = False

# Microphone (dial 3 / index 2)
current_mic_volume = 75
is_mic_muted = False

# ---------------------------------------------------------------------------
# Timer State  (dial 2 / index 1)
# ---------------------------------------------------------------------------

TIMER_STATES = ("IDLE", "SET", "RUNNING", "PAUSED", "DONE")

timer_seconds    = 0       # remaining seconds (counts down)
timer_set_total  = 0       # the full duration that was set (for progress bar)
timer_state      = "IDLE"  # one of TIMER_STATES
timer_lock       = threading.Lock()
_timer_thread    = None

# Hold-to-reset tracking for dial 1 button
_dial1_press_time = 0.0
HOLD_THRESHOLD    = 0.8    # seconds

# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------

last_click_time  = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
DEBOUNCE_COOLDOWN = 0.3

# ---------------------------------------------------------------------------
# LCD Strip Constants  (800 × 100 px, 4 zones of 200 px each)
# ---------------------------------------------------------------------------

SCREEN_WIDTH  = 800
SCREEN_HEIGHT = 100
SEGMENT_WIDTH = 200

ZONE_COLOR = {
    0: (0,   120, 255),   # Brightness – blue
    1: (255, 140,   0),   # Timer      – amber
    2: (200,  50, 200),   # Mic        – purple
    3: (0,   200, 100),   # Volume     – green
}

screen_canvas = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), color=(15, 15, 15))

# Keep a module-level deck reference so the timer thread can redraw
_deck = None


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _base_segment(dial_index):
    """Return a blank dark segment + draw handle."""
    seg  = Image.new("RGB", (SEGMENT_WIDTH, SCREEN_HEIGHT), color=(20, 20, 20))
    draw = ImageDraw.Draw(seg)
    return seg, draw


def _fonts():
    try:
        return (ImageFont.load_default(size=13),
                ImageFont.load_default(size=15),
                ImageFont.load_default(size=19),
                ImageFont.load_default(size=11))
    except Exception:
        f = ImageFont.load_default()
        return f, f, f, f


def _divider(draw):
    draw.line([SEGMENT_WIDTH - 1, 0, SEGMENT_WIDTH - 1, SCREEN_HEIGHT],
              fill=(40, 40, 40))


def _tap_hint(draw, font_small):
    draw.text((SEGMENT_WIDTH - 52, SCREEN_HEIGHT - 16), "[ tap ]",
              fill=(55, 55, 55), font=font_small)


def _progress_bar(draw, x1, y1, x2, y2, pct, color, bg=(40, 40, 40)):
    draw.rectangle([x1, y1, x2, y2], fill=bg)
    fill_w = int((x2 - x1) * max(0.0, min(1.0, pct)))
    if fill_w > 0:
        draw.rectangle([x1, y1, x1 + fill_w, y2], fill=color)


def draw_dial_indicator(dial_index, label, percentage, active=True, muted=False):
    """Generic progress-bar segment for brightness / mic / volume."""
    global screen_canvas
    accent  = ZONE_COLOR.get(dial_index, (80, 80, 80))
    x_start = dial_index * SEGMENT_WIDTH
    seg, draw = _base_segment(dial_index)
    fl, fv, _, fs = _fonts()

    draw.text((15, 10), label, fill=(150, 150, 150), font=fl)

    if not active or muted:
        bar_color  = (100, 30, 30) if muted else (50, 50, 50)
        val_text   = "MUTED"        if muted else "OFF"
        text_color = (255, 100, 100) if muted else (100, 100, 100)
    else:
        bar_color  = accent
        val_text   = f"{percentage}%"
        text_color = (255, 255, 255)

    draw.text((15, 30), val_text, fill=text_color, font=fv)
    _progress_bar(draw, 15, 65, 185, 77,
                  percentage / 100.0 if (active and not muted) else 0.0,
                  bar_color)
    _tap_hint(draw, fs)
    _divider(draw)
    screen_canvas.paste(seg, (x_start, 0))


def draw_timer_segment():
    """Dedicated renderer for the timer zone (segment index 1)."""
    global screen_canvas, timer_seconds, timer_set_total, timer_state

    x_start = 1 * SEGMENT_WIDTH
    seg, draw = _base_segment(1)
    fl, fv, ft, fs = _fonts()
    accent = ZONE_COLOR[1]

    with timer_lock:
        secs   = timer_seconds
        total  = timer_set_total
        state  = timer_state

    # --- Label + status badge ---
    draw.text((15, 8), "TIMER", fill=(150, 150, 150), font=fl)

    badge_map = {
        "IDLE":    ("IDLE",  (80,  80,  80)),
        "SET":     ("SET",   (80, 140, 255)),
        "RUNNING": ("▶ RUN", accent),
        "PAUSED":  ("⏸",     (200, 160,  0)),
        "DONE":    ("✓DONE", (255,  60,  60)),
    }
    badge_text, badge_color = badge_map.get(state, ("?", (80, 80, 80)))
    draw.text((SEGMENT_WIDTH - 65, 8), badge_text, fill=badge_color, font=fl)

    # --- Time display ---
    h  = secs // 3600
    m  = (secs % 3600) // 60
    s  = secs % 60
    time_str = f"{h:02d}:{m:02d}:{s:02d}"

    # Center the time string
    bbox = draw.textbbox((0, 0), time_str, font=ft)
    tw   = bbox[2] - bbox[0]
    tx   = (SEGMENT_WIDTH - tw) // 2

    if state == "DONE":
        t_color = (255, 60, 60)
    elif state in ("RUNNING", "PAUSED"):
        t_color = (255, 255, 255)
    else:
        t_color = (140, 140, 140)

    draw.text((tx, 30), time_str, fill=t_color, font=ft)

    # --- Progress bar (depleting) ---
    if total > 0 and state in ("RUNNING", "PAUSED", "DONE"):
        pct = secs / total
    elif state == "SET":
        pct = 1.0
    else:
        pct = 0.0

    bar_color = (255, 60, 60) if state == "DONE" else accent
    _progress_bar(draw, 15, 67, 185, 77, pct, bar_color)

    # Hold hint when running/paused
    if state in ("RUNNING", "PAUSED", "SET"):
        draw.text((15, SCREEN_HEIGHT - 16), "hold=reset",
                  fill=(55, 55, 55), font=fs)
    elif state == "IDLE":
        _tap_hint(draw, fs)

    _divider(draw)
    screen_canvas.paste(seg, (x_start, 0))


def update_hardware_display(deck):
    """JPEG-encode the 800×100 canvas and push it to the LCD strip."""
    global screen_canvas
    buf = io.BytesIO()
    screen_canvas.save(buf, format="JPEG", quality=95)
    jpeg_bytes = buf.getvalue()
    try:
        deck.set_touchscreen_image(jpeg_bytes, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
    except Exception as e:
        print(f"[DISPLAY] Warning: touchscreen write failed ({e})")


def redraw_all(deck):
    """Repaint every zone and flush."""
    draw_dial_indicator(0, "BRIGHTNESS", current_brightness, active=is_display_on)
    draw_timer_segment()
    draw_dial_indicator(2, "MIC",    current_mic_volume, active=True, muted=is_mic_muted)
    draw_dial_indicator(3, "VOLUME", current_volume,     active=True, muted=is_muted)
    update_hardware_display(deck)


# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------

def safe_set_brightness(deck, level):
    """set_brightness silently ignores Linux feature-report errors."""
    try:
        deck.set_brightness(level)
    except Exception as e:
        print(f"[BRIGHTNESS] Warning: could not set hardware brightness ({e})")


def run_amixer(command_args):
    try:
        subprocess.run(["amixer", "-q"] + command_args, check=True)
    except Exception as e:
        print(f"[AMIXER] Error: {e}")


# Alert sound candidates – tried in order, first success wins
_ALERT_SOUND_FILE = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
_ALERT_SOUNDS = [
    ("pw-play",      [_ALERT_SOUND_FILE]),                           # PipeWire (confirmed)
    ("gst-play-1.0", [_ALERT_SOUND_FILE]),                           # GStreamer
    ("ffplay",       ["-nodisp", "-autoexit", _ALERT_SOUND_FILE]),   # FFmpeg
    ("paplay",       [_ALERT_SOUND_FILE]),                           # PulseAudio
]


def play_alert_sound():
    """Play the system alarm sound. Tries each candidate and prints what happens."""
    print("[SOUND] Attempting alert sound...")
    for cmd, args in _ALERT_SOUNDS:
        try:
            result = subprocess.run(
                [cmd] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                print(f"[SOUND] \u2713 Played via {cmd}")
                return
            else:
                print(f"[SOUND] {cmd} failed (rc={result.returncode}): {result.stderr.strip()}")
        except FileNotFoundError:
            print(f"[SOUND] {cmd} not found, skipping")
        except Exception as e:
            print(f"[SOUND] {cmd} error: {e}")
    # Last-resort: terminal bell
    print("[SOUND] Falling back to terminal bell")
    sys.stdout.write("\a")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Timer logic
# ---------------------------------------------------------------------------

def _fmt(secs):
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _timer_thread_fn(deck):
    """Background countdown thread. Exits when timer is stopped or hits 0."""
    global timer_seconds, timer_state, _timer_thread

    while True:
        time.sleep(1)
        with timer_lock:
            if timer_state != "RUNNING":
                break
            timer_seconds -= 1
            if timer_seconds <= 0:
                timer_seconds = 0
                timer_state   = "DONE"
                print(f"[TIMER] ✓ Done!")
                threading.Thread(target=play_alert_sound, daemon=False).start()

        draw_timer_segment()
        update_hardware_display(deck)

        with timer_lock:
            if timer_state in ("DONE", "PAUSED", "IDLE"):
                break

    _timer_thread = None


def timer_adjust(deck, ticks):
    """Rotate dial: each tick = ±30 seconds (only when not running)."""
    global timer_seconds, timer_set_total, timer_state

    with timer_lock:
        if timer_state == "RUNNING":
            return  # ignore rotation while running
        timer_seconds = max(0, min(5999, timer_seconds + ticks * 30))
        if timer_seconds > 0:
            timer_state    = "SET"
            timer_set_total = timer_seconds
        else:
            timer_state    = "IDLE"
            timer_set_total = 0

    print(f"[TIMER] Set to {_fmt(timer_seconds)}")
    draw_timer_segment()
    update_hardware_display(deck)


def timer_start_stop(deck):
    """Toggle between RUNNING and PAUSED (or start from SET)."""
    global timer_state, _timer_thread

    with timer_lock:
        state = timer_state
        secs  = timer_seconds

    if state == "IDLE":
        return  # nothing set yet

    if state in ("SET", "PAUSED"):
        if secs <= 0:
            return
        with timer_lock:
            timer_state = "RUNNING"
        print(f"[TIMER] ▶ Started  ({_fmt(secs)} remaining)")
        t = threading.Thread(target=_timer_thread_fn, args=(deck,), daemon=True)
        _timer_thread = t
        t.start()

    elif state == "RUNNING":
        with timer_lock:
            timer_state = "PAUSED"
        print(f"[TIMER] ⏸ Paused  ({_fmt(secs)} remaining)")

    elif state == "DONE":
        timer_reset(deck)
        return

    draw_timer_segment()
    update_hardware_display(deck)


def timer_reset(deck):
    """Reset timer back to 00:00:00 (IDLE)."""
    global timer_seconds, timer_set_total, timer_state

    with timer_lock:
        timer_state    = "IDLE"
        timer_seconds  = 0
        timer_set_total = 0

    print("[TIMER] ↺ Reset")
    draw_timer_segment()
    update_hardware_display(deck)


# ---------------------------------------------------------------------------
# Control functions (brightness / volume / mic)
# ---------------------------------------------------------------------------

def change_device_brightness(deck, delta=0, toggle_off=False):
    global current_brightness, is_display_on, saved_brightness

    if toggle_off:
        if is_display_on:
            saved_brightness   = current_brightness
            current_brightness = 0
            is_display_on      = False
            print("[BRIGHTNESS] Display Toggled: OFF")
        else:
            current_brightness = saved_brightness
            is_display_on      = True
            print(f"[BRIGHTNESS] Display Toggled: ON ({current_brightness}%)")
    else:
        if not is_display_on:
            is_display_on = True
        current_brightness = max(10, min(100, current_brightness + delta))
        print(f"[BRIGHTNESS] Level: {current_brightness}%")

    safe_set_brightness(deck, current_brightness)
    draw_dial_indicator(0, "BRIGHTNESS", current_brightness, active=is_display_on)
    update_hardware_display(deck)


def handle_system_volume(deck, delta=0, toggle_mute=False):
    global current_volume, is_muted

    if toggle_mute:
        is_muted = not is_muted
        run_amixer(["set", "Master", "toggle"])
        print(f"[VOLUME] Mute → {'MUTED' if is_muted else 'ON'}")
    else:
        is_muted       = False
        current_volume = max(0, min(100, current_volume + delta))
        direction      = f"{abs(delta)}%+" if delta > 0 else f"{abs(delta)}%-"
        run_amixer(["set", "Master", direction])
        print(f"[VOLUME] Level: {current_volume}%")

    draw_dial_indicator(3, "VOLUME", current_volume, active=True, muted=is_muted)
    update_hardware_display(deck)


def handle_mic_volume(deck, delta=0, toggle_mute=False):
    global current_mic_volume, is_mic_muted

    if toggle_mute:
        is_mic_muted = not is_mic_muted
        run_amixer(["set", "Capture", "toggle"])
        print(f"[MIC] Mute → {'MUTED' if is_mic_muted else 'ON'}")
    else:
        is_mic_muted      = False
        current_mic_volume = max(0, min(100, current_mic_volume + delta))
        direction          = f"{abs(delta)}%+" if delta > 0 else f"{abs(delta)}%-"
        run_amixer(["set", "Capture", direction])
        print(f"[MIC] Level: {current_mic_volume}%")

    draw_dial_indicator(2, "MIC", current_mic_volume, active=True, muted=is_mic_muted)
    update_hardware_display(deck)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def dial_change_callback(deck, dial, b_pressed, rotation):
    global last_click_time, _dial1_press_time

    # --- Rotation ---
    if rotation != 0:
        if dial == 0:
            change_device_brightness(deck, delta=rotation * 5)
        elif dial == 1:
            timer_adjust(deck, rotation)
        elif dial == 2:
            handle_mic_volume(deck, delta=rotation * 2)
        elif dial == 3:
            handle_system_volume(deck, delta=rotation * 2)
        return

    # --- Button press/release ---
    if dial == 1:
        # Timer: hold-to-reset on release, short-press = start/stop
        if b_pressed:
            _dial1_press_time = time.time()
        else:
            held = time.time() - _dial1_press_time
            if held >= HOLD_THRESHOLD:
                timer_reset(deck)
            else:
                timer_start_stop(deck)
        return

    # Other dials: debounced short-press toggle
    if b_pressed:
        now = time.time()
        if dial == 0 and (now - last_click_time[0]) > DEBOUNCE_COOLDOWN:
            change_device_brightness(deck, toggle_off=True)
            last_click_time[0] = now
        elif dial == 2 and (now - last_click_time[2]) > DEBOUNCE_COOLDOWN:
            handle_mic_volume(deck, toggle_mute=True)
            last_click_time[2] = now
        elif dial == 3 and (now - last_click_time[3]) > DEBOUNCE_COOLDOWN:
            handle_system_volume(deck, toggle_mute=True)
            last_click_time[3] = now


def touchscreen_callback(deck, event_type, value):
    """
    Touch zone map:
      Zone 0 – BRIGHTNESS  → display off/on
      Zone 1 – TIMER       → start/stop  (no hold detection on touch)
      Zone 2 – MIC         → mic mute toggle
      Zone 3 – VOLUME      → speaker mute toggle
    """
    if event_type != TouchscreenEventType.SHORT:
        return

    x    = value.get("x", 0)
    zone = x // SEGMENT_WIDTH
    now  = time.time()

    if zone == 0 and (now - last_click_time[0]) > DEBOUNCE_COOLDOWN:
        print("[TOUCH] Zone 0 – display toggle")
        change_device_brightness(deck, toggle_off=True)
        last_click_time[0] = now

    elif zone == 1 and (now - last_click_time[1]) > DEBOUNCE_COOLDOWN:
        print("[TOUCH] Zone 1 – timer start/stop")
        timer_start_stop(deck)
        last_click_time[1] = now

    elif zone == 2 and (now - last_click_time[2]) > DEBOUNCE_COOLDOWN:
        print("[TOUCH] Zone 2 – mic mute toggle")
        handle_mic_volume(deck, toggle_mute=True)
        last_click_time[2] = now

    elif zone == 3 and (now - last_click_time[3]) > DEBOUNCE_COOLDOWN:
        print("[TOUCH] Zone 3 – volume mute toggle")
        handle_system_volume(deck, toggle_mute=True)
        last_click_time[3] = now


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

decks = DeviceManager().enumerate()
if not decks:
    print("No Stream Decks found.")
    sys.exit(1)

_deck = decks[0]
_deck.open()
_deck.reset()

safe_set_brightness(_deck, current_brightness)
redraw_all(_deck)

print("System Dashboard Running. Look at your Stream Deck screen!")
print("  Dial 1: Brightness    Dial 2: Timer    Dial 3: Mic    Dial 4: Volume")
print("  Dial 2: rotate=set time | push=start/stop | hold=reset")
print("  Tap LCD zones to toggle: [Display] [Timer] [Mic Mute] [Vol Mute]")
print("Press Ctrl+C to exit.")
print("=" * 70)

_deck.set_dial_callback(dial_change_callback)
_deck.set_touchscreen_callback(touchscreen_callback)

import signal

def _shutdown(signum, frame):
    """Handle SIGTERM / SIGINT — avoids reentrant stdout by writing to stderr."""
    import os
    os.write(2, f"\nSignal {signum} received — shutting down cleanly.\n".encode())
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nClosing display loops safely.")
finally:
    # Stop callbacks first so the reader thread doesn't fire into a dying device
    try:
        _deck.set_dial_callback(None)
        _deck.set_touchscreen_callback(None)
    except Exception:
        pass
    # Wait for any in-flight sound thread to finish (non-daemon, so join is implicit)
    try:
        _deck.reset()
    except Exception:
        pass
    try:
        _deck.close()
    except Exception:
        pass
    print("Device closed.")