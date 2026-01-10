#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <SPI.h>
#include <MFRC522.h>
#include <time.h>

// ==================== PINOS ====================
#define SS_ENTRADA D4
#define SS_SAIDA   D0
#define RST_PIN    D2
#define PIR_PIN    D1

MFRC522 rfidEntrada(SS_ENTRADA, RST_PIN);
MFRC522 rfidSaida(SS_SAIDA, RST_PIN);

// ==================== WIFI ====================
const char* ssid = "felipe lindo";
const char* pass = "felipesousa123";

// ==================== FIREBASE ====================
const char* firebaseHost = "controle-de-acesso-iot-default-rtdb.firebaseio.com";
const int httpsPort = 443;

WiFiClientSecure client;

// ==================== REGRAS DE ACESSO ====================
const String UID_AUTORIZADO = "73C0F71B";
const String UID_BLOQUEADO  = "C2514920";

// ==================== CONTROLE ====================
const unsigned long COOLDOWN_RFID = 1200;
const unsigned long COOLDOWN_PIR  = 3000;

unsigned long lastEntrada = 0;
unsigned long lastSaida   = 0;
unsigned long lastPIR     = 0;

// ==================== ESTADO ====================
int ocupacaoAtual = 0;
const int LIMITE_OCUPACAO = 10;

// ===================== HORÁRIO ==================
// Adicione isso antes do setup()
const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = -10800; // -3 horas * 3600
const int   daylightOffset_sec = 0;

// ==================== FUNÇÕES AUX ====================
String uidToString(MFRC522 &rfid) {
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

String getIsoTime() {
  time_t now = time(nullptr);
  struct tm* timeinfo = localtime(&now);
  char buffer[25];
  // Formata: 2024-12-17T15:00:11
  strftime(buffer, 25, "%Y-%m-%dT%H:%M:%S", timeinfo); 
  return String(buffer);
}

bool sendFirebase(String path, String payload, String method) {
  if (!client.connect(firebaseHost, httpsPort)) {
    Serial.println("Falha ao conectar ao Firebase");
    return false;
  }

  if (!path.endsWith(".json")) path += ".json";

  client.print(method + " " + path + " HTTP/1.1\r\n");
  client.print("Host: " + String(firebaseHost) + "\r\n");
  client.print("User-Agent: ESP8266\r\n");
  client.print("Connection: close\r\n");
  client.print("Content-Type: application/json\r\n");
  client.print("Content-Length: " + String(payload.length()) + "\r\n\r\n");
  client.print(payload);

  // 🔥 ESPERA A RESPOSTA DO FIREBASE
  unsigned long timeout = millis();
  while (client.available() == 0) {
    if (millis() - timeout > 3000) {
      Serial.println("Timeout Firebase");
      client.stop();
      return false;
    }
  }

  // DEBUG (opcional, mas recomendo agora)
  while (client.available()) {
    String line = client.readStringUntil('\n');
    Serial.println(line);
  }

  client.stop();
  return true;
}

// ==================== FIREBASE HELPERS ====================
void atualizarEstado(String ts) { // <--- MUDOU AQUI
  String json =
    "{"
    "\"ocupacao_atual\":" + String(ocupacaoAtual) + ","
    "\"limite_ocupacao\":" + String(LIMITE_OCUPACAO) + ","
    "\"alerta_ativo\":" + String(ocupacaoAtual > LIMITE_OCUPACAO ? "true" : "false") + ","
    "\"ultima_atualizacao\":\"" + ts + "\"" // <--- Note as aspas extras (\") para string JSON
    "}";
  sendFirebase("/estado", json, "PUT");
}

void atualizarPresenca(String uid, bool dentro, String ts) { // <--- MUDOU AQUI
  String json =
    "{"
    "\"dentro\":" + String(dentro ? "true" : "false") + ","
    "\"timestamp\":\"" + ts + "\"" // <--- Note as aspas extras (\")
    "}";
  sendFirebase("/presenca/" + uid, json, "PUT");
}

void registrarEvento(String uid, String leitor, bool permitido, bool fraudulento, String ts) { // <--- MUDOU AQUI
  String json =
    "{"
    "\"timestamp\":\"" + ts + "\"," // <--- Note as aspas extras (\")
    "\"cartao\":\"" + uid + "\","
    "\"acesso_permitido\":" + String(permitido ? "true" : "false") + ","
    "\"acesso_negado\":" + String(!permitido ? "true" : "false") + ","
    "\"fraudulento\":" + String(fraudulento ? "true" : "false") + ","
    "\"leitor\":\"" + leitor + "\","
    "\"ocupacao_apos_evento\":" + String(ocupacaoAtual) +
    "}";
  sendFirebase("/eventos", json, "POST");
}

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);
  SPI.begin();

  rfidEntrada.PCD_Init();
  rfidSaida.PCD_Init();

  pinMode(PIR_PIN, INPUT);

  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  client.setInsecure();
  Serial.println("\nSistema iniciado.");

  // Adicione isso DENTRO do void setup(), logo após conectar no WiFi
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("Sincronizando relógio NTP...");
  // Espera básica para pegar o horário
  while (time(nullptr) < 1000) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("\nRelógio Sincronizado!");
}

// ==================== LOOP ====================
void loop() {
  // Agora usamos a função de tempo formatada em vez de millis()
  String agoraStr = getIsoTime();

  // ===== PIR =====
  if (digitalRead(PIR_PIN) == HIGH && millis() - lastPIR > COOLDOWN_PIR) {
    lastPIR = millis();
    Serial.println("[SENSOR PIR] Movimento detectado!"); // <--- MENSAGEM PEDIDA
    // Note as aspas escapadas no JSON manual aqui
    sendFirebase("/movimentos", "{\"timestamp\":\"" + agoraStr + "\"}", "POST");
  }

  // ===== ENTRADA =====
  if (rfidEntrada.PICC_IsNewCardPresent() && rfidEntrada.PICC_ReadCardSerial()) {
    if (millis() - lastEntrada > COOLDOWN_RFID) {
      String uid = uidToString(rfidEntrada);
      bool permitido = (uid == UID_AUTORIZADO);
      // É fraudulento APENAS se o cartão for igual ao cartão bloqueado
      bool fraudulento = (uid == UID_BLOQUEADO);

      // <--- MENSAGENS PEDIDAS
      Serial.print("[ENTRADA] Cartão: "); Serial.println(uid);
      if (permitido) {
        Serial.println(">>> ACESSO PERMITIDO <<<");
        ocupacaoAtual++;
        atualizarPresenca(uid, true, agoraStr);
      } else {
        Serial.println("!!! ACESSO NEGADO !!!");
      }
      
      registrarEvento(uid, "entrada", permitido, fraudulento, agoraStr);
      atualizarEstado(agoraStr);
      lastEntrada = millis();
    }
    rfidEntrada.PICC_HaltA();
  }

  // ===== SAÍDA =====
  if (rfidSaida.PICC_IsNewCardPresent() && rfidSaida.PICC_ReadCardSerial()) {
    if (millis() - lastSaida > COOLDOWN_RFID) {
      String uid = uidToString(rfidSaida);
      
      // <--- MENSAGENS PEDIDAS
      Serial.print("[SAIDA] Cartão: "); Serial.println(uid);
      Serial.println(">>> SAIDA REGISTRADA <<<");

      if (ocupacaoAtual > 0) {
        ocupacaoAtual--;
        atualizarPresenca(uid, false, agoraStr);
      }

      registrarEvento(uid, "saida", true, false, agoraStr);
      atualizarEstado(agoraStr);
      lastSaida = millis();
    }
    rfidSaida.PICC_HaltA();
  }
}
