#ifdef SENSOR_NODE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

// ---------- CONFIG ----------
#define MAX_CH 32
// ESP32-S3 touch pins are typically GPIO 1..14. Trim to what you actually wire.
// (Avoid any pins reserved by your board; start with 1..14 and remove as needed.)
int TOUCH_PINS[] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14};
const int NUM_CH = min((int)(sizeof(TOUCH_PINS)/sizeof(TOUCH_PINS[0])), MAX_CH);

// Filters
const float LPF_ALPHA = 0.2f;         // 0..1 (higher = snappier)
const float BASELINE_ADAPT = 0.0015f; // slow drift compensation
// Target send rate (Hz). Raise for more speed; 200–500 is practical.
const uint32_t TARGET_HZ = 250;

// ---------- Packet ----------
#pragma pack(push,1)
struct TouchPacket {
  uint8_t  ver;      // protocol version
  uint8_t  n;        // number of channels
  uint8_t  id[3];    // short ID (last 3 bytes of MAC)
  uint16_t seq;      // sequence (wraps)
  uint32_t ms;       // millis() at sender
  uint16_t v[MAX_CH];// filtered touch values (lower == more touch)
};
#pragma pack(pop)

TouchPacket pkt;
float baseline[MAX_CH];
float filt[MAX_CH];
uint16_t seq = 0;
uint8_t mac_sta[6];

// Broadcast peer FF:FF:FF:FF:FF:FF
static const uint8_t BCAST[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

void onSend(const uint8_t*, esp_now_send_status_t) {}

void initESPNow() {
  WiFi.mode(WIFI_STA);
  // (Optional) fix channel for robustness: set your AP to channel X and lock here
  // esp_wifi_set_promiscuous(true);
  // esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);
  // esp_wifi_set_promiscuous(false);

  if (esp_now_init() != ESP_OK) { Serial.println("ESP-NOW init failed"); while(1) delay(100); }
  esp_now_register_send_cb(onSend);

  esp_now_peer_info_t peer{};
  memcpy(peer.peer_addr, BCAST, 6);
  peer.ifidx   = WIFI_IF_STA;
  peer.channel = 0;
  peer.encrypt = false; // broadcast cannot be encrypted
  if (esp_now_add_peer(&peer) != ESP_OK) { Serial.println("Peer add failed"); while(1) delay(100); }
}

void setup() {
  #if ARDUINO_USB_CDC_ON_BOOT
    Serial.begin(115200);
  #else
    Serial.begin(115200);
  #endif
  delay(200);

  initESPNow();
  esp_read_mac(mac_sta, ESP_MAC_WIFI_STA);
  pkt.ver = 1;
  pkt.n   = NUM_CH;
  pkt.id[0] = mac_sta[3]; pkt.id[1] = mac_sta[4]; pkt.id[2] = mac_sta[5];

  // Baselines
  for (int i = 0; i < NUM_CH; i++) {
    long s = 0;
    for (int k = 0; k < 32; k++) { s += touchRead(TOUCH_PINS[i]); delay(3); }
    baseline[i] = s / 32.0f;
    filt[i] = baseline[i];
  }
}

void loop() {
  static uint32_t lastSend = 0;
  uint32_t now = millis();

  // Read & filter
  for (int i = 0; i < NUM_CH; i++) {
    int raw = touchRead(TOUCH_PINS[i]);  // lower = more touch
    filt[i] = (1.0f - LPF_ALPHA) * filt[i] + LPF_ALPHA * raw;
    baseline[i] = (1.0f - BASELINE_ADAPT) * baseline[i] + BASELINE_ADAPT * filt[i];
  }

  // Send at TARGET_HZ
  uint32_t periodMs = (TARGET_HZ > 0) ? (1000 / TARGET_HZ) : 0;
  if (periodMs == 0 || (now - lastSend) >= periodMs) {
    lastSend = now;
    pkt.ms = now;
    pkt.seq = seq++;
    for (int i = 0; i < NUM_CH; i++) {
      int v = (int)lroundf(filt[i]);
      if (v < 0) v = 0; if (v > 65535) v = 65535;
      pkt.v[i] = (uint16_t)v;
    }
    size_t len = sizeof(pkt.ver) + sizeof(pkt.n) + sizeof(pkt.id) + sizeof(pkt.seq) + sizeof(pkt.ms) + pkt.n*sizeof(uint16_t);
    esp_now_send(BCAST, (uint8_t*)&pkt, len);
  }

  // No delay = max sensor rate; keep wires short to avoid noise.
}


#endif