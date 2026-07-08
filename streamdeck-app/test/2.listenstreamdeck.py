import usb.core
import usb.util
import libusb_package
import sys

VENDOR_ID = 0x0fd9
PRODUCT_ID = 0x0084
ENDPOINT_IN = 0x81
INTERFACE_NUM = 0

# Locate the device
dev = usb.core.find(
    idVendor=VENDOR_ID, 
    idProduct=PRODUCT_ID, 
    backend=libusb_package.get_libusb1_backend()
)

if dev is None:
    print("Stream Deck Plus not found.")
    sys.exit(1)

try:
    # 1. Detach kernel driver if Ubuntu claimed it automatically (e.g., as a generic HID)
    if dev.is_kernel_driver_active(INTERFACE_NUM):
        dev.detach_kernel_driver(INTERFACE_NUM)
        print("Detached kernel driver from interface.")

    # 2. Claim control over the interface
    usb.util.claim_interface(dev, INTERFACE_NUM)
    print("Claimed device interface. Listening for hardware inputs (Press Ctrl+C to stop)...")
    print("=" * 60)

    # 3. Read loop
    while True:
        try:
            # Read up to 512 bytes with a 1000ms (1 second) timeout
            data = dev.read(ENDPOINT_IN, 512, timeout=1000)
            
            # Convert raw byte array to hex strings for readable patterns
            hex_data = [hex(b) for b in data]
            print(f"Raw Byte Array (Length {len(data)}): {list(data)[:16]}...")
            print(f"Hex Representation              : {hex_data[:16]}...")
            print("-" * 60)
            
        except usb.core.USBTimeoutError:
            # Timeout happens if no buttons are pressed within the window; just keep looping
            continue

except KeyboardInterrupt:
    print("\nStopping listener...")
finally:
    # 4. Clean up and release control back to the OS
    usb.util.release_interface(dev, INTERFACE_NUM)
    try:
        dev.attach_kernel_driver(INTERFACE_NUM)
        print("Re-attached kernel driver safely.")
    except Exception:
        pass