#include <Arduino_RouterBridge.h> 
// PIR Motion Sensor Test Code for UNO Q

const int pirPin = 13;   // GPIO connected to PIR OUT
int motionState = 0;

void setup() {
  Serial.begin(9600);
  pinMode(pirPin, INPUT);
  Serial.println("PIR Sensor Initializing...");
  delay(2000);  // Sensor warm-up time
}

void loop() {

  motionState = digitalRead(pirPin);

  if (motionState == HIGH) {
    Serial.println("Motion");
  } 
  else {
    Serial.println("No_Motion");
  }

  delay(500);
}