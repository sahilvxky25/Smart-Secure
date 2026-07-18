const int vibPin = 12; // You can keep it on 12
int lastState = LOW;

void setup() {
  Serial.begin(9600);
  pinMode(vibPin, INPUT);
  Serial.println("System Ready. Waiting for vibration...");
}

void loop() {
  int currentState = digitalRead(vibPin);

  // If the sensor is triggered (spring touches the pin)
  if (currentState == HIGH) {
    int bounceCount = 0;
    unsigned long startTime = millis();

    // Open a 200-millisecond listening window
    while (millis() - startTime < 200) {
      int reading = digitalRead(vibPin);
      
      // Count every time the spring hits the pin (goes from LOW to HIGH)
      if (reading == HIGH && lastState == LOW) {
        bounceCount++;
      }
      lastState = reading;
    }

    // Print the intensity score based on how many bounces occurred
    Serial.print("Vibration Intensity (Bounces): ");
    Serial.println(bounceCount);

    // Filter normal events from vigorous events
    if (bounceCount > 10) { // You will need to tune this threshold number
      Serial.println("ALARM: VIGOROUS SHOCK DETECTED!");
    } else {
      Serial.println("Normal movement ignored.");
    }
    Serial.println("-------------------------");
    
    // Tiny delay before resetting
    delay(500); 
  }
}