#include <Arduino_RouterBridge.h>   // required for Serial/Monitor support on UNO Q
#include <Servo.h>

Servo myServo;
int targetAngle = 60;
int stepDelay = 30;  // ms between each degree step

void setup() {
  Bridge.begin();          // initializes the MCU-side bridge on UNO Q
  myServo.attach(9);        // signal pin -> D9
  myServo.write(0);
  delay(500);
}

void loop() {
  for (int angle = 0; angle <= targetAngle; angle++) {
    myServo.write(angle);
    delay(stepDelay);
  }

  delay(1000);

  for (int angle = targetAngle; angle >= 0; angle--) {
    myServo.write(angle);
    delay(stepDelay);
  }

  delay(1000);
}