#ifdef HUB_NODE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <vector>

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

struct NodeState {
  RXPacket pkt;
  uint32_t lastSeenMs;
  bool hasData;
};

static const uint32_t NODE_TIMEOUT_MS = 3000;
static const uint32_t SERIAL_PERIOD_MS = 50;

std::vector<NodeState> nodes;
portMUX_TYPE nodesMux = portMUX_INITIALIZER_UNLOCKED;
size_t nextNodeIndex = 0;

bool sameNodeId(const uint8_t a[3], const uint8_t b[3]) {
  return a[0] == b[0] && a[1] == b[1] && a[2] == b[2];
}

int findNodeIndexLocked(const uint8_t id[3]) {
  for (size_t i = 0; i < nodes.size(); i++) {
    if (sameNodeId(nodes[i].pkt.id, id)) return (int)i;
  }
  return -1;
}

void printPacket(const RXPacket& p) {
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

void pruneStaleNodesLocked(uint32_t now) {
  for (size_t i = 0; i < nodes.size();) {
    if ((uint32_t)(now - nodes[i].lastSeenMs) <= NODE_TIMEOUT_MS) {
      i++;
      continue;
    }

    nodes.erase(nodes.begin() + i);
    if (nextNodeIndex > i) nextNodeIndex--;
    if (nextNodeIndex >= nodes.size()) nextNodeIndex = 0;
  }
}

bool copyNextRoundRobinPacketLocked(RXPacket& out) {
  if (nodes.empty()) return false;
  if (nextNodeIndex >= nodes.size()) nextNodeIndex = 0;

  for (size_t tries = 0; tries < nodes.size(); tries++) {
    NodeState& node = nodes[nextNodeIndex];
    nextNodeIndex = (nextNodeIndex + 1) % nodes.size();

    if (!node.hasData) continue;

    out = node.pkt;
    return true;
  }

  return false;
}

void onRecv(const uint8_t* mac, const uint8_t* data, int len) {  
  const int baseLen = (int)(sizeof(uint32_t) + sizeof(uint8_t) * 3);
  const int radarLen = (int)(sizeof(float)*3 + sizeof(bool));
  (void)mac;

  if (len < baseLen + radarLen) return;

  const int expectedLen = baseLen + radarLen;
  if (len < expectedLen) return;

  RXPacket incoming{};

  int off = 0;
  memcpy((void*)incoming.id, data + off, 3); off += 3;
  memcpy((void*)&incoming.ms, data + off, sizeof(incoming.ms)); off += sizeof(incoming.ms);
  memcpy((void*)&incoming.distance, data + off, sizeof(incoming.distance)); off += sizeof(incoming.distance);
  memcpy((void*)&incoming.angle, data + off, sizeof(incoming.angle)); off += sizeof(incoming.angle);
  memcpy((void*)&incoming.speed, data + off, sizeof(incoming.speed)); off += sizeof(incoming.speed);
  memcpy((void*)&incoming.detected, data + off, sizeof(incoming.detected)); off += sizeof(incoming.detected);

  const uint32_t now = millis();

  portENTER_CRITICAL(&nodesMux);
  int nodeIndex = findNodeIndexLocked(incoming.id);
  if (nodeIndex >= 0) {
    NodeState& node = nodes[(size_t)nodeIndex];
    node.pkt = incoming;
    node.lastSeenMs = now;
    node.hasData = true;
  } else {
    NodeState node{};
    node.pkt = incoming;
    node.lastSeenMs = now;
    node.hasData = true;
    nodes.push_back(node);
  }
  portEXIT_CRITICAL(&nodesMux);
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
  static uint32_t nextSerialMs = 0;
  const uint32_t now = millis();

  if ((int32_t)(now - nextSerialMs) < 0) return;
  nextSerialMs = now + SERIAL_PERIOD_MS;

  RXPacket packetToPrint{};
  bool havePacket = false;

  portENTER_CRITICAL(&nodesMux);
  pruneStaleNodesLocked(now);
  havePacket = copyNextRoundRobinPacketLocked(packetToPrint);
  portEXIT_CRITICAL(&nodesMux);

  if (havePacket) printPacket(packetToPrint);
}

#endif
