#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <SPI.h>
#include <MFRC522.h>

// ==================== Pinos ====================
// RFID Entrada (Leitor 1)
#define SS_ENTRADA  D4   // SDA leitor 1
// RFID Saída (Leitor 2)
#define SS_SAIDA    D0   // SDA leitor 2
// RST compartilhado
#define RST_PIN     D2
// PIR
#define PIR_PIN     D1

MFRC522 rfidEntrada(SS_ENTRADA, RST_PIN);
MFRC522 rfidSaida(SS_SAIDA, RST_PIN);

// ==================== WiFi ====================
const char* ssid = "felipe lindo";
const char* pass = "felipesousa123";

// ==================== Firebase RTDB ====================
const char* firebaseHost = "controle-de-acesso-e53cf-default-rtdb.firebaseio.com";
const int   httpsPort    = 443;

WiFiClientSecure client;

// ==================== Lógica de acesso ====================
const String UID_TAG  = "73C0F71B";  // tag autorizada (entrada)
const String UID_CARD = "C2514920";  // cartão negado

const unsigned long COOLDOWN_RFID_MS = 1200;
const unsigned long PIR_COOLDOWN_MS  = 3000;

unsigned long lastEntradaEvent = 0;
unsigned long lastSaidaEvent   = 0;
unsigned long lastMovimento    = 0;

int contadorPermitido  = 0;
int contadorNegado     = 0;
int contadorMovimento  = 0;

// ==================== Funções auxiliares ====================

String uidToString(MFRC522 &rfid) {
  String s = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) s += "0";
    s += String(rfid.uid.uidByte[i], HEX);
  }
  s.toUpperCase();
  return s;
}

// Envia requisição HTTPS simples para o Firebase RTDB
bool sendToFirebase(const String& path, const String& json, const String& method = "POST") {
  if (!client.connect(firebaseHost, httpsPort)) {
    Serial.println("Falha ao conectar ao Firebase");
    return false;
  }

  // Caminho precisa terminar com .json
  String url = path;
  if (!url.endsWith(".json")) {
    url += ".json";
  }

  Serial.println("Enviando para Firebase: " + url);
  Serial.println("Payload: " + json);

  // Monta requisição HTTP
  client.print(method + " " + url + " HTTP/1.1\r\n");
  client.print("Host: ");
  client.print(firebaseHost);
  client.print("\r\n");
  client.print("User-Agent: ESP8266\r\n");
  client.print("Connection: close\r\n");
  client.print("Content-Type: application/json\r\n");
  client.print("Content-Length: ");
  client.print(json.length());
  client.print("\r\n\r\n");
  client.print(json);

  // Opcional: ler resposta
  int timeout = 3000;
  unsigned long start = millis();
  while (client.available() == 0) {
    if (millis() - start > timeout) {
      Serial.println(">> Timeout de resposta do Firebase");
      client.stop();
      return false;
    }
  }

  while (client.available()) {
    String line = client.readStringUntil('\n');
    Serial.println(line);
  }

  client.stop();
  Serial.println(">> Envio concluído.\n");
  return true;
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  SPI.begin();

  rfidEntrada.PCD_Init();
  rfidSaida.PCD_Init();

  pinMode(PIR_PIN, INPUT);

  Serial.println("\n=== CONTROLE DE ACESSO (2x RFID + PIR + Firebase) ===");
  Serial.print("Conectando ao WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("\nWiFi conectado!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  // NÃO verificar certificado (mais simples para testes)
  client.setInsecure();

  Serial.println("Sistema pronto.");
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  unsigned long agora = millis();

  // --------------- PIR (movimento) ---------------
  int movimento = digitalRead(PIR_PIN);
  if (movimento == HIGH && (agora - lastMovimento > PIR_COOLDOWN_MS)) {
    contadorMovimento++;
    lastMovimento = agora;
Serial.println("Movimento detectado!");
// Envia evento de movimento para Firebase (append em /movimentos)
    String payload = "{";
    payload += "\"contador\": " + String(contadorMovimento) + ",";
    payload += "\"timestamp\": " + String(agora / 1000);
    payload += "}";

    sendToFirebase("/movimentos", payload, "POST");
  }

  // --------------- RFID ENTRADA ---------------
  if (rfidEntrada.PICC_IsNewCardPresent() && rfidEntrada.PICC_ReadCardSerial()) {
    if (agora - lastEntradaEvent > COOLDOWN_RFID_MS) {
      String uid = uidToString(rfidEntrada);
      Serial.print("\n[ENTRADA] UID lido: ");
      Serial.println(uid);

      int acesso_status = 0;
      int fraude = 0;

      if (uid == UID_TAG) {
        acesso_status = 1;
        contadorPermitido++;
        Serial.println(">>> ENTRADA PERMITIDA");
      } else if (uid == UID_CARD) {
        acesso_status = 2;
        contadorNegado++;
        Serial.println(">>> ENTRADA NEGADA (CARTÃO BLOQUEADO)");
      } else {
        acesso_status = 2;
        contadorNegado++;
        fraude = 1;
        Serial.println(">>> ENTRADA NEGADA (UID DESCONHECIDO)");
      }

      // Monta JSON para Firebase
      String payload = "{";
      payload += "\"tipo\":\"entrada\",";
      payload += "\"uid\":\"" + uid + "\",";
      payload += "\"acesso\":" + String(acesso_status) + ",";
      payload += "\"fraude\":" + String(fraude) + ",";
      payload += "\"contadorPermitido\":" + String(contadorPermitido) + ",";
      payload += "\"contadorNegado\":" + String(contadorNegado) + ",";
      payload += "\"timestamp\":" + String(agora / 1000);
      payload += "}";

      // Salva como novo registro em /entrada
      sendToFirebase("/entrada", payload, "POST");

      // Atualiza nó /contadores
      String contadoresJson = "{";
      contadoresJson += "\"permitidos\":" + String(contadorPermitido) + ",";
      contadoresJson += "\"negados\":" + String(contadorNegado) + ",";
      contadoresJson += "\"movimentos\":" + String(contadorMovimento);
      contadoresJson += "}";

      sendToFirebase("/contadores", contadoresJson, "PUT");

      lastEntradaEvent = agora;
    }

    rfidEntrada.PICC_HaltA();
    rfidEntrada.PCD_StopCrypto1();
  }

  // --------------- RFID SAÍDA ---------------
  if (rfidSaida.PICC_IsNewCardPresent() && rfidSaida.PICC_ReadCardSerial()) {
    if (agora - lastSaidaEvent > COOLDOWN_RFID_MS) {
      String uid = uidToString(rfidSaida);
      Serial.print("\n[SAÍDA] UID lido: ");
      Serial.println(uid);

      // Aqui estou considerando que toda saída é permitida
      int acesso_status = 1;

      String payload = "{";
      payload += "\"tipo\":\"saida\",";
      payload += "\"uid\":\"" + uid + "\",";
      payload += "\"acesso\":" + String(acesso_status) + ",";
      payload += "\"timestamp\":" + String(agora / 1000);
      payload += "}";

      // Salva como novo registro em /saida
      sendToFirebase("/saida", payload, "POST");

      lastSaidaEvent = agora;
    }

    rfidSaida.PICC_HaltA();
    rfidSaida.PCD_StopCrypto1();
  }
}