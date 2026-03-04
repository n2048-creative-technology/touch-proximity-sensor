#ifndef RADARSENSOR_H
#define RADARSENSOR_H

#include <Arduino.h>
#include <HardwareSerial.h>

typedef struct RadarTarget {
  float distance;  // mm
  float angle;     // degrees
  float speed;     // cm/s (unknown; 0 if not provided)
  int16_t x;       // mm
  int16_t y;       // mm
  bool detected;
} RadarTarget;

class RadarSensor {
  public:
    RadarSensor(uint8_t rxPin, uint8_t txPin);
    void begin(unsigned long baud = 256000);
    bool update();
    RadarTarget getTarget(); // No index, only first target
  private:
    uint8_t rxPin;
    uint8_t txPin;
    HardwareSerial &radarSerial;
    RadarTarget target;  // single target
    bool parseFDFrame(const uint8_t *payload9);
    bool parseAAFrame(const uint8_t *data24);
};

#endif
