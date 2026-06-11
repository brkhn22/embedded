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

int forwardSpeed = 120;
int rotateSpeed = 90;

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

  stopMotors();
}

void loop() {
  if (espSerial.available()) {
    char cmd = espSerial.read();

    Serial.println(cmd);

    if (cmd == 'F') {
      // Mavi görüldü, ileri git
      moveForward(forwardSpeed);
    }

    else if (cmd == 'L') {
      // Mavi yok, kendi etrafında yavaşça dönerek ara
      rotateLeft(rotateSpeed);
    }

    else if (cmd == 'S') {
      // Dur
      stopMotors();
    }
  }
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