// SPDX-License-Identifier: none
#include "RadarSensor.h"

// Set to 1 to print framing counters and sample bytes once per second
#ifndef RADAR_DEBUG_FRAMING
#define RADAR_DEBUG_FRAMING 1
#endif

RadarSensor::RadarSensor(uint8_t rxPin_, uint8_t txPin_)
  : rxPin(rxPin_), txPin(txPin_), radarSerial(Serial1) {}

void RadarSensor::begin(unsigned long baud) {
  radarSerial.begin(baud, SERIAL_8N1, rxPin, txPin);
}

// Parse frames:
// - FD F8 | status | w1 | w2 | w3 | w4 (LE)  -> 11 bytes total
// - AA FF 03 00 | 24 bytes payload | 55 CC   -> 32 bytes total
bool RadarSensor::update() {
  static uint8_t fd_frame[11];
  static uint8_t fd_idx = 0;
  static uint8_t aa_data[26];
  static uint8_t aa_idx = 0;
  static enum { SYNC, FD_WAIT_F8, FD_READ, AA_READ } state = SYNC;
  static uint8_t prev = 0;
  static uint8_t last4[4] = {0};

  bool data_updated = false;
#if RADAR_DEBUG_FRAMING
  static uint32_t rx_bytes = 0;
  static uint32_t cnt_fd_f8 = 0;
  static uint32_t cnt_aa_ff03_00 = 0;
  static unsigned long last_report = 0;
#endif

  while (radarSerial.available()) {
    uint8_t b = radarSerial.read();
    uint8_t prev_b = prev;
    prev = b;

#if RADAR_DEBUG_FRAMING
    rx_bytes++;
#endif
    // Keep sliding byte history for header detection.
    last4[0] = last4[1];
    last4[1] = last4[2];
    last4[2] = last4[3];
    last4[3] = b;

    if (prev_b == 0xFD && b == 0xF8) {
#if RADAR_DEBUG_FRAMING
      cnt_fd_f8++;
#endif
    }
    if (last4[0] == 0xAA && last4[1] == 0xFF && last4[2] == 0x03 && last4[3] == 0x00) {
#if RADAR_DEBUG_FRAMING
      cnt_aa_ff03_00++;
#endif
    }


    // Header detection in SYNC
    if (state == SYNC) {
      if (prev_b == 0xFD && b == 0xF8) {
        fd_frame[0] = 0xFD; fd_frame[1] = 0xF8; fd_idx = 2; state = FD_READ;
        continue;
      }
      if (last4[0] == 0xAA && last4[1] == 0xFF && last4[2] == 0x03 && last4[3] == 0x00) {
        aa_idx = 0; state = AA_READ;
        continue;
      }
    }

    // FD F8 payload
    if (state == FD_READ) {
      fd_frame[fd_idx++] = b;
      if (fd_idx >= sizeof(fd_frame)) {
        data_updated = parseFDFrame(&fd_frame[2]);
        state = SYNC; fd_idx = 0;
      }
      continue;
    }

    // AA FF 03 00 payload + tail
    if (state == AA_READ) {
      aa_data[aa_idx++] = b;

      if (aa_idx >= sizeof(aa_data)) {
        // Expect tail 55 CC
        if (aa_data[24] == 0x55 && aa_data[25] == 0xCC) {
          data_updated = parseAAFrame(aa_data);
        }
        state = SYNC; aa_idx = 0;
      }
      continue;
    }
    }

#if RADAR_DEBUG_FRAMING
  if (millis() - last_report >= 1000) {
    last_report = millis();
    Serial.print("RADAR RX bytes/s=");
    Serial.print(rx_bytes);
    Serial.print(" fd_f8=");
    Serial.print(cnt_fd_f8);
    Serial.print(" aa_ff_03_00=");
    Serial.println(cnt_aa_ff03_00);
    rx_bytes = 0;
    cnt_fd_f8 = 0;
    cnt_aa_ff03_00 = 0;
  }
#endif

  return data_updated;
}

bool RadarSensor::parseFDFrame(const uint8_t *payload9) {
  uint8_t status = payload9[0];
  if ((status & 0x40) == 0) return false;
  uint16_t w1 = (uint16_t)(payload9[1] | (payload9[2] << 8));
  uint16_t w2 = (uint16_t)(payload9[3] | (payload9[4] << 8));
  uint16_t w3 = (uint16_t)(payload9[5] | (payload9[6] << 8));
  uint16_t w4 = (uint16_t)(payload9[7] | (payload9[8] << 8));
  const int SIG_BASE = 2056, SIG_TOL = 12;
  if (abs((int)w3 - SIG_BASE) > SIG_TOL || abs((int)w4 - SIG_BASE) > SIG_TOL) return false;
  #ifndef BASE_X
  #define BASE_X 2056
  #endif
  #ifndef BASE_Y
  #define BASE_Y 3080
  #endif
  int16_t dx = (int16_t)((int)w1 - BASE_X);
  int16_t dy = (int16_t)((int)w2 - BASE_Y);
  float dist_mm = sqrtf((float)dx * dx + (float)dy * dy);
  float angle_deg = atan2f((float)dy, (float)dx) * 180.0f / PI;
  target.x = dx; target.y = dy; target.distance = dist_mm; target.angle = angle_deg; target.speed = 0.0f; target.detected = true;
  return true;
}

bool RadarSensor::parseAAFrame(const uint8_t *data24) {
  // First target is 8 bytes
  uint16_t rx = (uint16_t)(data24[0] | (data24[1] << 8));
  uint16_t ry = (uint16_t)(data24[2] | (data24[3] << 8));
  uint16_t rspd = (uint16_t)(data24[4] | (data24[5] << 8));
  // uint16_t rdist = (uint16_t)(data24[6] | (data24[7] << 8)); // raw range if needed

  // Signed magnitude (bit15 sign)
  auto sm_to_i16 = [](uint16_t v) -> int16_t {
    int16_t mag = (int16_t)(v & 0x7FFF);
    return (v & 0x8000) ? (int16_t)(-mag) : mag;
  };
  int16_t x = sm_to_i16(rx);
  int16_t y = sm_to_i16(ry);
  int16_t sp = sm_to_i16(rspd);

  float dist_mm = sqrtf((float)x * x + (float)y * y);
  float angle_deg = atan2f((float)y, (float)x) * 180.0f / PI;

  target.x = x; target.y = y; target.distance = dist_mm; target.angle = angle_deg; target.speed = sp / 10.0f; target.detected = (x!=0 || y!=0);
  return true;
}

RadarTarget RadarSensor::getTarget() {
  return target;
}
