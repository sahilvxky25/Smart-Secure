// Combined Test: KY-024 Hall Sensor + MC-38 Door Sensor
#include <Arduino_RouterBridge.h> 
#define HALL_DO_PIN 25
#define HALL_AO_PIN 26
#define DOOR_PIN 8

void setup() {
  Serial.begin(9600);

  pinMode(HALL_DO_PIN, INPUT);
  pinMode(DOOR_PIN, INPUT_PULLUP);

  Serial.println("System Initializing...");
  delay(2000);
}

void loop() {

  // ---- KY-024 Hall Sensor ----
  int hallDigital = digitalRead(HALL_DO_PIN);
  int hallAnalog = analogRead(HALL_AO_PIN);

  // ---- MC-38 Door Sensor ----
  int doorState = digitalRead(DOOR_PIN);

  // ---- Output Section ----
  Serial.println("----- SENSOR STATUS -----");

  // Hall Sensor Digital
  if (hallDigital == LOW) {
    Serial.println("Magnet Detected (Digital)");
  } else {
    Serial.println("No Magnet (Digital)");
  }

  // Hall Sensor Analog
  Serial.print("Magnetic Field Strength (Analog): ");
  Serial.println(hallAnalog);

  // Door Sensor
  if (doorState == LOW) {
    Serial.println("Door: CLOSED");
  } else {
    Serial.println("Door: OPEN");
  }

  Serial.println("--------------------------\n");

  delay(500);
}