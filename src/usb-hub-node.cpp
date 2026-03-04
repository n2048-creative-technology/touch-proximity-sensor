#ifdef HUB_NODE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

#pragma pack(push,1)
struct TouchPacket {
  uint8_t  ver;
  uint8_t  n;
  uint8_t  id[3];
  uint16_t seq;
  uint32_t ms;
  uint16_t v[32];

    //radar:
  float distance;  // mm
  float angle;     // degrees
  float speed;     // cm/s (unknown; 0 if not provided)
  int16_t x;       // mm
  int16_t y;       // mm
  bool detected;
};
#pragma pack(pop)

volatile bool pktReady = false;
TouchPacket pkt;
uint8_t lastSender[6];

void onRecv(const uint8_t* mac, const uint8_t* data, int len) {  
  const int baseLen = (int)(sizeof(uint8_t) + sizeof(uint8_t) + 3 + sizeof(uint16_t) + sizeof(uint32_t));
  const int radarLen = (int)(sizeof(float) + sizeof(float) + sizeof(float) + sizeof(int16_t) + sizeof(int16_t) + sizeof(bool));
  if (len < baseLen + radarLen) return;

  const uint8_t n = data[1];
  if (n > 32) return;

  const int expectedLen = baseLen + (int)n * (int)sizeof(uint16_t) + radarLen;
  if (len < expectedLen) return;

  memset((void*)&pkt, 0, sizeof(pkt));
  pkt.ver = data[0];
  pkt.n = n;

  int off = 2;
  memcpy((void*)pkt.id, data + off, 3); off += 3;
  memcpy((void*)&pkt.seq, data + off, sizeof(pkt.seq)); off += sizeof(pkt.seq);
  memcpy((void*)&pkt.ms, data + off, sizeof(pkt.ms)); off += sizeof(pkt.ms);
  memcpy((void*)pkt.v, data + off, (size_t)pkt.n * sizeof(uint16_t)); off += (int)pkt.n * (int)sizeof(uint16_t);
  memcpy((void*)&pkt.distance, data + off, sizeof(pkt.distance)); off += sizeof(pkt.distance);
  memcpy((void*)&pkt.angle, data + off, sizeof(pkt.angle)); off += sizeof(pkt.angle);
  memcpy((void*)&pkt.speed, data + off, sizeof(pkt.speed)); off += sizeof(pkt.speed);
  memcpy((void*)&pkt.x, data + off, sizeof(pkt.x)); off += sizeof(pkt.x);
  memcpy((void*)&pkt.y, data + off, sizeof(pkt.y)); off += sizeof(pkt.y);
  memcpy((void*)&pkt.detected, data + off, sizeof(pkt.detected));

  memcpy((void*)lastSender, mac, 6);
  pktReady = true;
}

void setup() {
  Serial.begin(921600);  // HIGH baud for highest throughput to Max
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
  TouchPacket p = pkt;
  uint8_t m[6]; memcpy(m, lastSender, 6);
  pktReady = false;
  interrupts();

  // CSV: touch,<mac>,<id3>,<seq>,<ms>,<n>,v1,v2,...,vn\n
  // mac as 12 hex chars (no colons) keeps it compact
  char macbuf[13];
  snprintf(macbuf, sizeof(macbuf), "%02X%02X%02X%02X%02X%02X", m[0],m[1],m[2],m[3],m[4],m[5]);

  Serial.print("touch,");
  Serial.print(macbuf);
  Serial.print(',');
  Serial.printf("%02X%02X%02X,", p.id[0], p.id[1], p.id[2]);
  Serial.print(p.seq);
  Serial.print(',');
  Serial.print(p.ms);
  Serial.print(',');
  Serial.print((int)p.n);
  for (int i = 0; i < p.n && i < 32; i++) {
    Serial.print(',');
    Serial.print((int)p.v[i]);
  }

    Serial.print(',');  
  // Radar data (if provided)
  if (p.detected) {
    Serial.print("radar,1,");
    Serial.print(p.distance);
    Serial.print(',');
    Serial.print(p.angle);
    Serial.print(',');
    Serial.print(p.speed);
    Serial.print(',');
    Serial.print(p.x);
    Serial.print(',');
    Serial.print(p.y);
  }
  else {
    Serial.print("radar,0,0.0,0.0,0.0,0.0,0.0");
  }   

  Serial.print('\n');
}

#endif
