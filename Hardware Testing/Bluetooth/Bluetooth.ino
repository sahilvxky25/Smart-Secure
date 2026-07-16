#include <ArduinoBLE.h>

// Nordic UART Service (NUS)
BLEService uartService("6E400001-B5A3-F393-E0A9-E50E24DCCA9E"); 

// RX Characteristic (Phone -> Arduino). Increased max length to 128 bytes.
BLEStringCharacteristic rxCharacteristic("6E400002-B5A3-F393-E0A9-E50E24DCCA9E", BLEWrite | BLEWriteWithoutResponse, 128);

// TX Characteristic (Arduino -> Phone). Increased max length to 128 bytes.
BLEStringCharacteristic txCharacteristic("6E400003-B5A3-F393-E0A9-E50E24DCCA9E", BLENotify, 128);

void setup() {
  Serial.begin(115200);
  while (!Serial); 

  Serial.println("Arduino UNO Q - BLE 2-Way Chat Terminal");

  if (!BLE.begin()) {
    Serial.println("ERROR: Starting Bluetooth failed!");
    while (1); 
  }

  BLE.setLocalName("UNO_Q_Serial");
  BLE.setAdvertisedService(uartService);
  
  uartService.addCharacteristic(rxCharacteristic);
  uartService.addCharacteristic(txCharacteristic);
  
  BLE.addService(uartService);
  BLE.advertise();
  
  Serial.println("BLE UART active! Waiting for connection...");
}

void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.println("App connected successfully!");

    while (central.connected()) {
      
      // 1. PHONE -> COMPUTER: If the phone sends data, print it to the computer
      if (rxCharacteristic.written()) {
        Serial.print("Phone says: ");
        Serial.println(rxCharacteristic.value());
      }

      // 2. COMPUTER -> PHONE: If you type in the Serial Monitor, send it to the phone
      if (Serial.available()) {
        String pcMessage = Serial.readStringUntil('\n'); // Read until Enter is pressed
        pcMessage.trim(); // Remove extra hidden line-ending characters
        
        if (pcMessage.length() > 0) {
          txCharacteristic.writeValue(pcMessage); // Send to phone
          Serial.print("Sent to Phone: ");
          Serial.println(pcMessage);
        }
      }
      
    }
    Serial.println("App disconnected.");
  }
}