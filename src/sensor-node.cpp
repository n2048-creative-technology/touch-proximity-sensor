#ifdef SENSOR_NODE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include "RD03D.h"

#define RADAR_RX_PIN 1
#define RADAR_TX_PIN 2

RD03D radar(RADAR_RX_PIN, RADAR_TX_PIN); // ESP RX/TX pins connected to sensor TX/RX

// ---------- Packet ----------
#pragma pack(push,1)
struct TXPacket {
  uint32_t ms;       // millis() at sender
  uint8_t  id[3];   // MAC address
  float distance;  // mm
  float angle;     // degrees
  float speed;     // cm/s (unknown; 0 if not provided)
  bool detected;    // whether the target is detected (distance > 0)
};

const int baseLen = (int)(sizeof(uint32_t) + sizeof(uint8_t) * 3);
const int radarLen = (int)(sizeof(float)*3 + sizeof(bool));

#pragma pack(pop)

TXPacket pkt;
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
  Serial.begin(9600);
  delay(200);

  initESPNow();
  esp_read_mac(mac_sta, ESP_MAC_WIFI_STA);
  
  pkt.id[0] = mac_sta[3]; 
  pkt.id[1] = mac_sta[4]; 
  pkt.id[2] = mac_sta[5];

  delay(200);

  btStop();
  radar.initialize(); 

  delay(100);
}



void loop() {

  static uint32_t lastSend = 0;


  // Plot information, We display data a bit less oftern
  if ( millis() > lastSend){

      static TargetData*  tgt = radar.getTarget();  

    // Call the task method frequently to check for new frames.
    radar.tasks();

    lastSend = millis() + 100;   // Update next tick every 0.1 second

    // Check if Target is detected, then display the values.
    if(tgt->isValid()){
      tgt->printInfo();   // Display target information over serial
      pkt.distance = tgt->distance;
      pkt.angle = tgt->angle;
      pkt.speed = tgt->speed;
      pkt.detected = true;

      // Serialize packed payload so radar fields are placed right after the n touch values.
  
    }
    else {
      Serial.println("No target detected");

      pkt.distance = 0;
      pkt.angle = 0;
      pkt.speed = 0;
      pkt.detected = false;
    }


      pkt.ms = millis(); 
      
      uint8_t tx[baseLen + radarLen]; // id + ms + distance + angle + speed + detected 
      int off = 0;
      memcpy(tx + off, pkt.id, 3); off += 3;
      memcpy(tx + off, &pkt.ms, sizeof(pkt.ms)); off += sizeof(pkt.ms);
      memcpy(tx + off, &pkt.distance, sizeof(pkt.distance)); off += sizeof(pkt.distance);
      memcpy(tx + off, &pkt.angle, sizeof(pkt.angle)); off += sizeof(pkt.angle);
      memcpy(tx + off, &pkt.speed, sizeof(pkt.speed)); off += sizeof(pkt.speed);
      memcpy(tx + off, &pkt.detected, sizeof(pkt.detected)); off += sizeof(pkt.detected);

      esp_now_send(BCAST, tx, off);
  }  
}


#endif
