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
const int searchTurnSpeed = 150;
const int trackTurnSpeed = 130;
const int turnKickSpeed = 180;
const unsigned long turnKickDurationMs = 150;
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
unsigned long lastCommandTime = 0;
unsigned long lastDistanceReadTime = 0;
unsigned long turnStartTime = 0;
char lastTurnCommand = 'S';

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
        received == 'F' || received == 'L' || received == 'R'
        || received == 'S' || received == 'T')) {
      pendingCommand = received;
    } else if (receivingCommand && received == '>') {
      if (pendingCommand != '\0') {
        bool commandChanged = currentCommand != pendingCommand;
        currentCommand = pendingCommand;
        lastCommandTime = millis();
        if (commandChanged) {
          Serial.print("Command: ");
          Serial.println(currentCommand);
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
  bool targetTrackingCommand = (
    currentCommand == 'F'
    || currentCommand == 'L'
    || currentCommand == 'R'
  );
  bool shouldStopForObstacle = targetTrackingCommand && obstacleBlocked;

  if (commandExpired || currentCommand == 'S' || shouldStopForObstacle) {
    stopMotors();
    lastTurnCommand = 'S';
  } else if (currentCommand == 'F') {
    // Target color found and path is clear.
    moveForward(forwardSpeed);
    lastTurnCommand = 'S';
  } else if (currentCommand == 'L') {
    // Target visible on the left side; steer left to center it.
    int speed = beginTurnIfNeeded(now, 'L', trackTurnSpeed);
    rotateLeft(speed);
  } else if (currentCommand == 'R') {
    // Target visible on the right side; steer right to center it.
    int speed = beginTurnIfNeeded(now, 'R', trackTurnSpeed);
    rotateRight(speed);
  } else if (currentCommand == 'T') {
    // No target visible; spin to search.
    int speed = beginTurnIfNeeded(now, 'T', searchTurnSpeed);
    rotateLeft(speed);
  } else {
    stopMotors();
    lastTurnCommand = 'S';
  }
}

int beginTurnIfNeeded(unsigned long now, char turnCommand, int baseSpeed) {
  if (lastTurnCommand != turnCommand) {
    turnStartTime = now;
    lastTurnCommand = turnCommand;
  }

  if (now - turnStartTime < turnKickDurationMs) {
    return turnKickSpeed;
  }

  return baseSpeed;
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

void rotateRight(int speed) {
  analogWrite(enA, speed);
  analogWrite(enB, speed);

  // Sol motor ileri
  digitalWrite(in1, HIGH);
  digitalWrite(in2, LOW);

  // Sağ motor geri
  digitalWrite(in3, LOW);
  digitalWrite(in4, HIGH);
}

void stopMotors() {
  analogWrite(enA, 0);
  analogWrite(enB, 0);

  digitalWrite(in1, LOW);
  digitalWrite(in2, LOW);

  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
}
