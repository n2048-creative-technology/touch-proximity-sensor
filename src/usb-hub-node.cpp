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
};
#pragma pack(pop)

volatile bool pktReady = false;
TouchPacket pkt;
uint8_t lastSender[6];

void onRecv(const uint8_t* mac, const uint8_t* data, int len) {
  if (len < (int)(sizeof(uint8_t)*2 + 3 + sizeof(uint16_t) + sizeof(uint32_t))) return;
  memcpy((void*)&pkt, data, min(len, (int)sizeof(TouchPacket)));
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
  Serial.print('\n');
}

#endif