#include <SoftwareSerial.h>

SoftwareSerial espSerial(2, 3);

// Motor A
const int enA = 9;
const int in1 = 7;
const int in2 = 8;

// Motor B
const int enB = 6;
const int in3 = 5;
const int in4 = 4;

// HC-SR04
const int trigPin = 10;
const int echoPin = 11;

// Buzzer
const int buzzerPin = 12;

// Common-anode RGB LED channels. LOW turns a color on, HIGH turns it off.
const int greenLedPin = A0;
const int redLedPin = A1;

const int forwardSpeed = 120;
const int reverseSpeed = 110;
const int searchTurnSpeed = 140;
const int trackTurnSpeed = 140;
const float searchStopDistanceCm = 10.0;
const float searchResumeDistanceCm = 15.0;
const float motionStopDistanceCm = 20.0;
const float motionResumeDistanceCm = 25.0;
const unsigned long distanceReadIntervalMs = 60;
const unsigned long obstacleReportIntervalMs = 250;
const unsigned long obstacleBuzzerDurationMs = 3000;
const unsigned long commandTimeoutMs = 1000;
const unsigned long echoTimeoutUs = 25000;
const unsigned int buzzerAlertHz = 2400;

char currentCommand = 'S';
char pendingCommand = '\0';
bool receivingCommand = false;
bool searchThresholdMode = false;
float distanceCm = -1.0;
bool obstacleBlocked = false;
unsigned long lastCommandTime = 0;
unsigned long lastDistanceReadTime = 0;
unsigned long lastObstacleReportTime = 0;
unsigned long obstacleAlertStartedTime = 0;

bool isMotorCommand(char command);
bool isLedCommand(char command);
bool isThresholdModeCommand(char command);
void setTargetLed(bool targetFound);
float getActiveStopDistanceCm();
float getActiveResumeDistanceCm();

void setup() {
  Serial.begin(9600);

  // ESP32-CAM'den Arduino'ya gelen seri haberleşme
  espSerial.begin(115200);

  pinMode(enA, OUTPUT);
  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);

  pinMode(enB, OUTPUT);
  pinMode(in3, OUTPUT);
  pinMode(in4, OUTPUT);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW);

  pinMode(buzzerPin, OUTPUT);
  digitalWrite(buzzerPin, LOW);

  pinMode(greenLedPin, OUTPUT);
  pinMode(redLedPin, OUTPUT);
  setTargetLed(false);

  stopMotors();
}

void loop() {
  while (espSerial.available()) {
    char received = espSerial.read();

    if (received == '<') {
      receivingCommand = true;
      pendingCommand = '\0';
    } else if (receivingCommand && (
        isMotorCommand(received)
        || isLedCommand(received)
        || isThresholdModeCommand(received))) {
      pendingCommand = received;
    } else if (receivingCommand && received == '>') {
      if (pendingCommand != '\0') {
        if (isLedCommand(pendingCommand)) {
          setTargetLed(pendingCommand == 'G');
        } else if (isThresholdModeCommand(pendingCommand)) {
          searchThresholdMode = pendingCommand == 'Q';
        } else {
          bool commandChanged = currentCommand != pendingCommand;
          currentCommand = pendingCommand;
          lastCommandTime = millis();
          if (commandChanged) {
            Serial.print("Command: ");
            Serial.println(currentCommand);
          }
        }
      }
      receivingCommand = false;
      pendingCommand = '\0';
    } else if (receivingCommand) {
      receivingCommand = false;
      pendingCommand = '\0';
    }
  }

  unsigned long now = millis();

  if (now - lastDistanceReadTime >= distanceReadIntervalMs) {
    distanceCm = readDistanceCm();
    lastDistanceReadTime = now;

    if (distanceCm > 0) {
      bool wasObstacleBlocked = obstacleBlocked;
      float activeStopDistanceCm = getActiveStopDistanceCm();
      float activeResumeDistanceCm = getActiveResumeDistanceCm();
      if (obstacleBlocked) {
        obstacleBlocked = distanceCm < activeResumeDistanceCm;
      } else {
        obstacleBlocked = distanceCm <= activeStopDistanceCm;
      }

      if (!wasObstacleBlocked && obstacleBlocked) {
        obstacleAlertStartedTime = now;
      }

      if (
        obstacleBlocked != wasObstacleBlocked
        || now - lastObstacleReportTime >= obstacleReportIntervalMs
      ) {
        espSerial.print("<D:");
        espSerial.print(distanceCm, 1);
        espSerial.print(">");
        espSerial.print(obstacleBlocked ? "<B1>" : "<B0>");
        lastObstacleReportTime = now;
      }
    }


    Serial.print("Distance: ");
    if (distanceCm < 0) {
      Serial.println("no echo");
    } else {
      Serial.print(distanceCm);
      Serial.println(" cm");
    }
  }

  if (
      obstacleBlocked
      && now - obstacleAlertStartedTime < obstacleBuzzerDurationMs
  ) {
    tone(buzzerPin, buzzerAlertHz);
  } else {
    noTone(buzzerPin);
  }

  bool commandExpired = now - lastCommandTime > commandTimeoutMs;

  if (commandExpired || currentCommand == 'S') {
    stopMotors();
  } else if (currentCommand == 'B') {
    // Back away after a distance stop so the robot can resume searching.
    moveBackward(reverseSpeed);
  } else if (obstacleBlocked) {
    stopMotors();
  } else if (currentCommand == 'F') {
    // Target color found and path is clear.
    moveForward(forwardSpeed);
  } else if (currentCommand == 'L') {
    // Target visible on the left side; steer left to center it.
    rotateLeft(trackTurnSpeed);
  } else if (currentCommand == 'R') {
    // Target visible on the right side; steer right to center it.
    rotateRight(trackTurnSpeed);
  } else if (currentCommand == 'T') {
    // Search pulses use a constant speed for predictable turn angles.
    rotateLeft(searchTurnSpeed);
  } else {
    stopMotors();
  }
}

bool isMotorCommand(char command) {
  return (
    command == 'F' || command == 'L' || command == 'R'
    || command == 'S' || command == 'T' || command == 'B'
  );
}

bool isLedCommand(char command) {
  return command == 'G' || command == 'N';
}

bool isThresholdModeCommand(char command) {
  return command == 'Q' || command == 'W';
}

void setTargetLed(bool targetFound) {
  digitalWrite(greenLedPin, targetFound ? LOW : HIGH);
  digitalWrite(redLedPin, targetFound ? HIGH : LOW);
}

float getActiveStopDistanceCm() {
  if (searchThresholdMode) {
    return searchStopDistanceCm;
  }
  return motionStopDistanceCm;
}

float getActiveResumeDistanceCm() {
  if (searchThresholdMode) {
    return searchResumeDistanceCm;
  }
  return motionResumeDistanceCm;
}

float readDistanceCm() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duration = pulseIn(echoPin, HIGH, echoTimeoutUs);
  if (duration == 0) {
    return -1.0;
  }

  return duration * 0.0343 / 2.0;
}

void moveForward(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  digitalWrite(in1, HIGH);
  digitalWrite(in2, LOW);

  digitalWrite(in3, HIGH);
  digitalWrite(in4, LOW);
}

void moveBackward(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  digitalWrite(in1, LOW);
  digitalWrite(in2, HIGH);

  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
}

void rotateLeft(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  // Fiziksel yonler ters oldugu icin burada sol donusu mantiksal olarak duzeltiyoruz.
  // Sol donus icin sol motor ileri, sag motor geri suruluyor.
  digitalWrite(in1, HIGH);
  digitalWrite(in2, LOW);

  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
}

void rotateRight(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  // Fiziksel yonler ters oldugu icin burada sag donusu mantiksal olarak duzeltiyoruz.
  // Sag donus icin sol motor geri, sag motor ileri suruluyor.
  digitalWrite(in1, LOW);
  digitalWrite(in2, HIGH);

  digitalWrite(in3, HIGH);
  digitalWrite(in4, LOW);
}

void stopMotors() {
  analogWrite(enA, 0);
  analogWrite(enB, 0);

  digitalWrite(in1, LOW);
  digitalWrite(in2, LOW);

  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
}
