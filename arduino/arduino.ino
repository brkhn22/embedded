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

const int forwardSpeed = 120;
const int rotateSpeed = 180;
const int rotateKickSpeed = 230;
const unsigned long rotateKickDurationMs = 180;
const float stopDistanceCm = 20.0;
const float resumeDistanceCm = 25.0;
const unsigned long distanceReadIntervalMs = 60;
const unsigned long commandTimeoutMs = 1000;
const unsigned long echoTimeoutUs = 25000;

char currentCommand = 'S';
char pendingCommand = '\0';
bool receivingCommand = false;
float distanceCm = -1.0;
bool obstacleBlocked = false;
bool rotating = false;
unsigned long lastCommandTime = 0;
unsigned long lastDistanceReadTime = 0;
unsigned long rotateStartTime = 0;

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

  stopMotors();
}

void loop() {
  while (espSerial.available()) {
    char received = espSerial.read();

    if (received == '<') {
      receivingCommand = true;
      pendingCommand = '\0';
    } else if (receivingCommand && (
        received == 'F' || received == 'L' || received == 'S')) {
      pendingCommand = received;
    } else if (receivingCommand && received == '>') {
      if (pendingCommand != '\0') {
        currentCommand = pendingCommand;
        lastCommandTime = millis();
        Serial.print("Command: ");
        Serial.println(currentCommand);
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
      if (obstacleBlocked) {
        obstacleBlocked = distanceCm < resumeDistanceCm;
      } else {
        obstacleBlocked = distanceCm <= stopDistanceCm;
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

  bool commandExpired = now - lastCommandTime > commandTimeoutMs;

  if (commandExpired || currentCommand == 'S' || obstacleBlocked) {
    stopMotors();
    rotating = false;
  } else if (currentCommand == 'F') {
    // Target color found and path is clear.
    moveForward(forwardSpeed);
    rotating = false;
  } else if (currentCommand == 'L') {
    // Target color not found; rotate to search.
    if (!rotating) {
      rotateStartTime = now;
      rotating = true;
    }
    int speed = rotateSpeed;
    if (now - rotateStartTime < rotateKickDurationMs) {
      speed = rotateKickSpeed;
    }
    rotateLeft(speed);
  } else {
    stopMotors();
    rotating = false;
  }
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

void rotateLeft(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  // Sol motor geri
  digitalWrite(in1, LOW);
  digitalWrite(in2, HIGH);

  // Sağ motor ileri
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
