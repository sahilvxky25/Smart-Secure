// Arduino UNO Q Ultrasonic Sensor Test (HC-SR04)
#include <Arduino_RouterBridge.h>   // needed for Serial/Monitor support on UNO Q
                                     // (safe to leave in even on core 0.55+, where it's redundant)

#define TRIG_PIN 9   // remapped to a valid UNO Q digital pin
#define ECHO_PIN 10  // remapped to a valid UNO Q digital pin

long duration;
float distance;

void setup() {
  Bridge.begin();          // initializes MCU-side bridge on UNO Q
  Serial.begin(9600);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  Serial.println("Ultrasonic Sensor Test Started...");
}

void loop() {
  // Ensure trigger is LOW
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  // Send 10 µs pulse
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Measure echo duration
  duration = pulseIn(ECHO_PIN, HIGH);

  // Calculate distance (cm)
  distance = duration * 0.0343 / 2;

  // Print result
  Serial.print("Distance: ");
  Serial.print(distance);
  Serial.println(" cm");

  delay(500);
}