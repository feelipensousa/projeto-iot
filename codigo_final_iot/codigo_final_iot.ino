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
String UIDS_AUTORIZADOS[] = {"73C0F71B", "4349F01B", "92F5D421"};
const int QTD_AUTORIZADOS = 3;
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
const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = -10800; 
const int   daylightOffset_sec = 0;

// ==================== FUNÇÕES AUXILIARES ====================

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
  strftime(buffer, 25, "%Y-%m-%dT%H:%M:%S", timeinfo); 
  return String(buffer);
}

bool verificarAutorizacao(String uidLido) {
  for (int i = 0; i < QTD_AUTORIZADOS; i++) {
    if (UIDS_AUTORIZADOS[i] == uidLido) return true;
  }
  return false;
}

// Função Firebase
void sendFirebase(String path, String payload, String method) {
  Serial.print(">> Enviando para Firebase... ");
  
  if (!client.connect(firebaseHost, httpsPort)) {
    Serial.println("[ERRO] Falha conexão WiFi/SSL");
    return;
  }

  if (!path.endsWith(".json")) path += ".json";

  client.print(method + " " + path + " HTTP/1.1\r\n");
  client.print("Host: " + String(firebaseHost) + "\r\n");
  client.print("User-Agent: ESP8266\r\n");
  client.print("Connection: close\r\n");
  client.print("Content-Type: application/json\r\n");
  client.print("Content-Length: " + String(payload.length()) + "\r\n\r\n");
  client.print(payload);

  unsigned long timeout = millis();
  while (client.available() == 0) {
    if (millis() - timeout > 3000) {
      Serial.println("[ERRO] Timeout na resposta");
      client.stop();
      return;
    }
  }

  String responseLine = client.readStringUntil('\n');
  if (responseLine.indexOf("200 OK") > 0) {
    Serial.println("[OK] Sucesso! (200)");
  } else {
    Serial.print("[ALERTA] Resposta estranha: ");
    Serial.println(responseLine);
  }
  
  while (client.available()) client.read(); 
  client.stop();
}

void atualizarEstado(String ts) {
  String json =
    "{"
    "\"ocupacao_atual\":" + String(ocupacaoAtual) + ","
    "\"limite_ocupacao\":" + String(LIMITE_OCUPACAO) + ","
    "\"alerta_ativo\":" + String(ocupacaoAtual > LIMITE_OCUPACAO ? "true" : "false") + ","
    "\"ultima_atualizacao\":\"" + ts + "\""
    "}";
  sendFirebase("/estado", json, "PUT");
}

void atualizarPresenca(String uid, bool dentro, String ts) {
  String json =
    "{"
    "\"dentro\":" + String(dentro ? "true" : "false") + ","
    "\"timestamp\":\"" + ts + "\""
    "}";
  sendFirebase("/presenca/" + uid, json, "PUT");
}

void registrarEvento(String uid, String leitor, bool permitido, bool fraudulento, String ts) {
  String json =
    "{"
    "\"timestamp\":\"" + ts + "\","
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
  Serial.print("\nConectando WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  client.setInsecure();
  Serial.println("\nWiFi Conectado!");

  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("Sincronizando NTP...");
  while (time(nullptr) < 1000) delay(1000);
  Serial.println("Relógio OK!");

  Serial.println("Calibrando Sensor PIR (aguarde 5s)...");
  delay(5000);
  Serial.println("Sistema Pronto. Passe o cartão.");
}

// ==================== LOOP ====================
void loop() {
  String agoraStr = getIsoTime();

  // ===== 1. SENSOR PIR (PRIORIDADE) =====
  if (digitalRead(PIR_PIN) == HIGH) {
    if (millis() - lastPIR > COOLDOWN_PIR) {
      lastPIR = millis();
      Serial.println("\n[SENSOR PIR] >>> MOVIMENTO DETECTADO! <<<");
      sendFirebase("/movimentos", "{\"timestamp\":\"" + agoraStr + "\"}", "POST");
    }
  }

  // ===== 2. ENTRADA =====
  if (rfidEntrada.PICC_IsNewCardPresent() && rfidEntrada.PICC_ReadCardSerial()) {
    if (millis() - lastEntrada > COOLDOWN_RFID) {
      String uid = uidToString(rfidEntrada);
      bool permitido = verificarAutorizacao(uid);
      bool fraudulento = (uid == UID_BLOQUEADO); // Fraude se for o cartão bloqueado

      Serial.print("\n[ENTRADA] Cartão Lido: "); Serial.println(uid);

      if (permitido) {
        if (uid == "73C0F71B") Serial.println(">>> ACESSO PERMITIDO (Admin) <<<");
        else Serial.println("!!! ACESSO AUTORIZADO (Visitante) !!!");

        ocupacaoAtual++;
        Serial.print("STATUS: Sala com "); Serial.print(ocupacaoAtual); Serial.println(" pessoas.");
        
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

  // ===== 3. SAÍDA (Lógica Atualizada para Fraude) =====
  if (rfidSaida.PICC_IsNewCardPresent() && rfidSaida.PICC_ReadCardSerial()) {
    if (millis() - lastSaida > COOLDOWN_RFID) {
      String uid = uidToString(rfidSaida);
      
      Serial.print("\n[SAIDA] Cartão Lido: "); Serial.println(uid);

      // --- NOVA LÓGICA DE FRAUDE NA SAÍDA ---
      // Retorna TRUE se:
      // 1. O cartão for o BLOQUEADO (C2514920)
      //    OU
      // 2. A ocupação for 0 (ninguém dentro, mas cartão passando na saída)
      bool fraudulento = (uid == UID_BLOQUEADO) || (ocupacaoAtual == 0);

      if (ocupacaoAtual > 0) {
        ocupacaoAtual--;
        Serial.println(">>> SAIDA REGISTRADA <<<");
        Serial.print("STATUS: Sala com "); Serial.print(ocupacaoAtual); Serial.println(" pessoas.");
        
        atualizarPresenca(uid, false, agoraStr);
      } else {
        Serial.println("⚠️ ALERTA: Saída registrada mas o contador já estava em 0! (Inconsistência)");
        Serial.print("STATUS: Sala permanece com 0 pessoas.");
      }

      // Agora passamos a variável 'fraudulento' calculada acima
      // Note que 'permitido' na saída geralmente é true (catraca livre pra sair), 
      // mas o campo fraudulento marcará o alerta.
      registrarEvento(uid, "saida", true, fraudulento, agoraStr);
      
      atualizarEstado(agoraStr);
      lastSaida = millis();
    }
    rfidSaida.PICC_HaltA();
  }
}