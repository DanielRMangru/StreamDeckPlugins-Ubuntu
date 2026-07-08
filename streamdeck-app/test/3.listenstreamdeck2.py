import usb.core
import usb.util
import libusb_package
import sys

VENDOR_ID = 0x0fd9
PRODUCT_ID = 0x0084
ENDPOINT_IN = 0x81
INTERFACE_NUM = 0

dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=libusb_package.get_libusb1_backend())
if dev is None:
    print("Stream Deck Plus not found.")
    sys.exit(1)

try:
    if dev.is_kernel_driver_active(INTERFACE_NUM):
        dev.detach_kernel_driver(INTERFACE_NUM)
    usb.util.claim_interface(dev, INTERFACE_NUM)
    print("Decoder Ready. Interact with Keys or Dials (Ctrl+C to exit)...")
    print("=" * 60)

    while True:
        try:
            data = dev.read(ENDPOINT_IN, 512, timeout=1000)
            if not data:
                continue

            # Identify Event Header Type
            header = list(data[:3])

            # --- KEY BUTTON HANDLER ---
            if header == [1, 0, 8]:
                # Look across the key registers (bytes 4 to 11)
                for key_idx, byte_val in enumerate(data[4:12], start=1):
                    if byte_val == 1:
                        print(f"[BUTTON] Key {key_idx} -> PRESSED")
                    elif len(data) > 4 and data[4] == 0 and all(b == 0 for b in data[5:12]):
                        # Shortcut print for clean release logs
                        print("[BUTTON] All Keys Released")
                        break

            # --- DIAL ROTATION & DIAL PRESS HANDLER ---
            elif header == [1, 3, 5]:
                dial_pressed = data[4] == 1
                if dial_pressed:
                    print("[DIAL CLK] A Dial is being pressed down.")
                
                # Check Dial 1 to Dial 4 offsets (Bytes 5 to 8)
                for dial_idx, byte_val in enumerate(data[5:9], start=1):
                    if byte_val != 0:
                        # Convert 8-bit unsigned to signed int for rotation direction
                        delta = byte_val if byte_val < 128 else byte_val - 256
                        direction = "Clockwise" if delta > 0 else "Counter-Clockwise"
                        print(f"[DIAL ROTATE] Dial {dial_idx} -> Turned {direction} (Steps: {abs(delta)})")

            # --- TOUCH STRIP SCREEN HANDLER ---
            elif header == [1, 2, 14]:
                print(f"[TOUCH SCREEN] Event Detected: {list(data[4:14])}")

        except usb.core.USBTimeoutError:
            continue

except KeyboardInterrupt:
    print("\nClosing down.")
finally:
    usb.util.release_interface(dev, INTERFACE_NUM)
    try:
        dev.attach_kernel_driver(INTERFACE_NUM)
    except Exception:
        pass