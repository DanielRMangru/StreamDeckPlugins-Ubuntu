import io
import sys
import time
import signal
import threading
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager

# ---------------------------------------------------------------------------
# Key Constants
# ---------------------------------------------------------------------------

KEY_INDEX      = 0          # Hardware button 1 (0-indexed)
KEY_W          = 120
KEY_H          = 120
HOLD_THRESHOLD = 0.8        # seconds held before triggering HOLD state
RELEASE_LINGER = 0.6        # seconds to show "Bye" before returning to IDLE

# ---------------------------------------------------------------------------
# Button States
# ---------------------------------------------------------------------------
#
#   IDLE  ──press──>  PRESSED  ──hold──>  HELD
#     ^                  |                  |
#     └──── (auto) ───  RELEASED  <─────────┘
#                (on release from either PRESSED or HELD)

STATES = {
    #  state      bg_color           text      text_color
    "IDLE":     ((30,  80,  220),   "Ready",   (255, 255, 255)),
    "PRESSED":  ((40,  180,  60),   "Hello",   (255, 255, 255)),
    "HELD":     ((220, 120,   0),   "Ouch",    (255, 255, 255)),
    "RELEASED": ((200,  40,  40),   "Bye",     (255, 255, 255)),
}

# Current state + press timestamp
button_state     = "IDLE"
_press_time      = 0.0
_hold_thread     = None
_state_lock      = threading.Lock()

# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------

def make_key_image(state: str) -> bytes:
    """Render a 120×120 JPEG for the given button state."""
    bg_color, text, text_color = STATES[state]

    img  = Image.new("RGB", (KEY_W, KEY_H), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Subtle inner border for depth
    border_color = tuple(max(0, c - 40) for c in bg_color)
    draw.rectangle([3, 3, KEY_W - 4, KEY_H - 4], outline=border_color, width=3)

    # State label (large, centred)
    try:
        font_main  = ImageFont.load_default(size=24)
        font_state = ImageFont.load_default(size=12)
    except Exception:
        font_main = font_state = ImageFont.load_default()

    # Main text
    bbox = draw.textbbox((0, 0), text, font=font_main)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((KEY_W - tw) // 2, (KEY_H - th) // 2 - 8),
              text, fill=text_color, font=font_main)

    # Small state badge at bottom
    badge = state.upper()
    sbbox = draw.textbbox((0, 0), badge, font=font_state)
    sw    = sbbox[2] - sbbox[0]
    draw.text(((KEY_W - sw) // 2, KEY_H - 24),
              badge, fill=(*text_color[:3],), font=font_state)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def push_image(deck, state: str):
    """Render and send key image to the device."""
    img_bytes = make_key_image(state)
    try:
        deck.set_key_image(KEY_INDEX, img_bytes)
    except Exception as e:
        print(f"[KEY] Warning: image write failed ({e})")


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

def set_state(deck, new_state: str):
    global button_state
    with _state_lock:
        button_state = new_state
    print(f"[KEY1] → {new_state}")
    push_image(deck, new_state)


def _hold_watcher(deck):
    """Background thread: fires HELD state if button is still pressed."""
    time.sleep(HOLD_THRESHOLD)
    with _state_lock:
        still_pressed = (button_state == "PRESSED")
    if still_pressed:
        set_state(deck, "HELD")


def _release_linger(deck):
    """Background thread: returns to IDLE after showing RELEASED briefly."""
    time.sleep(RELEASE_LINGER)
    with _state_lock:
        still_released = (button_state == "RELEASED")
    if still_released:
        set_state(deck, "IDLE")


# ---------------------------------------------------------------------------
# Key callback
# ---------------------------------------------------------------------------

def key_callback(deck, key, pressed):
    global _press_time, _hold_thread

    if key != KEY_INDEX:
        return

    if pressed:
        # ── PRESS ──────────────────────────────────────────────────────────
        _press_time = time.time()
        set_state(deck, "PRESSED")

        # Spawn hold watcher
        t = threading.Thread(target=_hold_watcher, args=(deck,), daemon=False)
        _hold_thread = t
        t.start()

    else:
        # ── RELEASE ────────────────────────────────────────────────────────
        held_duration = time.time() - _press_time
        print(f"[KEY1] Released after {held_duration:.2f}s")

        set_state(deck, "RELEASED")

        # Return to IDLE after linger
        threading.Thread(target=_release_linger, args=(deck,),
                         daemon=False).start()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

decks = DeviceManager().enumerate()
if not decks:
    print("No Stream Deck devices found.")
    sys.exit(1)

deck = decks[0]
deck.open()
deck.reset()

# Draw initial IDLE state
push_image(deck, "IDLE")
print("Button Controls Ready!")
print(f"  Key 1:  press=green/Hello  |  hold={HOLD_THRESHOLD}s=orange/Ouch")
print(f"          release=red/Bye ({RELEASE_LINGER}s) → blue/Ready")
print("Press Ctrl+C to exit.")
print("=" * 60)

deck.set_key_callback(key_callback)

# ---------------------------------------------------------------------------
# Signal handling & main loop
# ---------------------------------------------------------------------------

def _shutdown(signum, frame):
    print(f"\nSignal {signum} — shutting down cleanly.")
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting...")
finally:
    try:
        deck.set_key_callback(None)
    except Exception:
        pass
    try:
        deck.reset()
    except Exception:
        pass
    try:
        deck.close()
    except Exception:
        pass
    print("Device closed.")
