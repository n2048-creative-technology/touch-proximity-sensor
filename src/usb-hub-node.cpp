#ifdef HUB_NODE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

#pragma pack(push,1)
struct RXPacket {
  uint32_t ms;       // millis() at sender
  uint8_t  id[3];   // MAC address // hash
  float distance;  // mm
  float angle;     // degrees
  float speed;     // cm/s (unknown; 0 if not provided)
  bool detected;    // whether the target is detected (distance > 0)
};
#pragma pack(pop)

volatile bool pktReady = false;
RXPacket pkt;
uint8_t lastSender[6];

void onRecv(const uint8_t* mac, const uint8_t* data, int len) {  
  const int baseLen = (int)(sizeof(uint32_t) + sizeof(uint8_t) * 3);
  const int radarLen = (int)(sizeof(float)*3 + sizeof(bool));
  if (len < baseLen + radarLen) return;

  const int expectedLen = baseLen + radarLen;
  if (len < expectedLen) return;

  memset((void*)&pkt, 0, sizeof(pkt));
  pkt.ms = millis();

  int off = 0;
  memcpy((void*)pkt.id, data + off, 3); off += 3;
  memcpy((void*)&pkt.ms, data + off, sizeof(pkt.ms)); off += sizeof(pkt.ms);
  memcpy((void*)&pkt.distance, data + off, sizeof(pkt.distance)); off += sizeof(pkt.distance);
  memcpy((void*)&pkt.angle, data + off, sizeof(pkt.angle)); off += sizeof(pkt.angle);
  memcpy((void*)&pkt.speed, data + off, sizeof(pkt.speed)); off += sizeof(pkt.speed);
  memcpy((void*)&pkt.detected, data + off, sizeof(pkt.detected)); off += sizeof(pkt.detected);
  pktReady = true;
}

void setup() {
  Serial.begin(9600);  // HIGH baud for highest throughput to Max
  delay(200);

  WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) { Serial.println("ESP-NOW init failed"); while(1) delay(100); }
  esp_now_register_recv_cb(onRecv);

  // Print our MAC for debugging
  uint8_t mac[6]; esp_read_mac(mac, ESP_MAC_WIFI_STA);
  Serial.printf("HUB_MAC %02X:%02X:%02X:%02X:%02X:%02X\n", mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
}

void loop() {
  if (!pktReady) return;
  noInterrupts();
  RXPacket p = pkt;
  uint8_t m[6]; memcpy(m, lastSender, 6);
  pktReady = false;
  interrupts();

  // CSV: touch,<mac>,<id3>,<seq>,<ms>,<n>,v1,v2,...,vn\n
  // mac as 12 hex chars (no colons) keeps it compact
  char macbuf[13];
  snprintf(macbuf, sizeof(macbuf), "%02X%02X%02X%02X%02X%02X", m[0],m[1],m[2],m[3],m[4],m[5]);

  Serial.printf("%02X%02X%02X,", p.id[0], p.id[1], p.id[2]);
  Serial.print(p.ms);
  Serial.print(',');  
  Serial.print(p.distance);
  Serial.print(',');
  Serial.print(p.angle);
  Serial.print(',');
  Serial.print(p.speed);
  Serial.print(',');
  Serial.print(p.detected);

  Serial.print('\n');
}

#endif
