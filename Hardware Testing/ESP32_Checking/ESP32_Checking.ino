// ESP32 Basic Checking / Test Code

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("================================");
  Serial.println("ESP32 CHECKING PROGRAM");
  Serial.println("================================");

  // Chip information
  
}

void loop() {
  // Most ESP32 development boards use GPIO 2 for the built-in LED
  pinMode(2, OUTPUT);

  digitalWrite(2, HIGH);
  Serial.println("LED ON");
  delay(1000);

  digitalWrite(2, LOW);
  Serial.println("LED OFF");
  delay(1000);
  Serial.print("Chip Model: ");
  Serial.println(ESP.getChipModel());

  Serial.print("Chip Revision: ");
  Serial.println(ESP.getChipRevision());

  Serial.print("CPU Frequency: ");
  Serial.print(ESP.getCpuFreqMHz());
  Serial.println(" MHz");

  Serial.print("Flash Size: ");
  Serial.print(ESP.getFlashChipSize() / (1024 * 1024));
  Serial.println(" MB");

  Serial.print("Free Heap: ");
  Serial.print(ESP.getFreeHeap());
  Serial.println(" bytes");

  Serial.println("--------------------------------");
  Serial.println("ESP32 is working!");
  Serial.println("Built-in LED test starting...");
}
