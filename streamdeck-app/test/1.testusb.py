import usb.core
import usb.util
import libusb_package

# Target the Stream Deck Plus specifically using its hardware IDs
VENDOR_ID = 0x0fd9
PRODUCT_ID = 0x0084

device = usb.core.find(
    idVendor=VENDOR_ID, 
    idProduct=PRODUCT_ID, 
    backend=libusb_package.get_libusb1_backend()
)

if device is None:
    print("Stream Deck Plus not found. Make sure it's plugged in.")
else:
    print(f"Targeting Device: Vendor {hex(device.idVendor)}, Product {hex(device.idProduct)}")
    print("=" * 50)
    
    for config in device:
        print(f"Configuration Value: {config.bConfigurationValue}")
        print(f"  Total Interfaces available: {config.bNumInterfaces}")
        
        for interface in config:
            print(f"  └── Interface Number: {interface.bInterfaceNumber}")
            print(f"      Interface Class: {interface.bInterfaceClass} (Subclass: {interface.bInterfaceSubClass})")
            
            for endpoint in interface:
                print(f"      ├── Endpoint Address: {hex(endpoint.bEndpointAddress)}")
                
                transfer_type = usb.util.endpoint_type(endpoint.bmAttributes)
                types = {
                    usb.util.ENDPOINT_TYPE_BULK: "BULK (High volume payload/Images)",
                    usb.util.ENDPOINT_TYPE_INTR: "INTERRUPT (Low latency/Button presses)",
                    usb.util.ENDPOINT_TYPE_ISO: "ISOCHRONOUS (Streaming video/audio)",
                    usb.util.ENDPOINT_TYPE_CTRL: "CONTROL (Setup commands)"
                }
                print(f"      │   ├── Type: {types.get(transfer_type, 'Unknown')}")
                
                direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
                dir_str = "IN (Device -> Host PC)" if direction == usb.util.ENDPOINT_IN else "OUT (Host PC -> Device)"
                print(f"      │   ├── Direction: {dir_str}")
                print(f"      │   └── Max Packet Size: {endpoint.wMaxPacketSize} bytes")