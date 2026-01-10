import telebot
import requests
import time
import threading
import io
import matplotlib.pyplot as plt

# ================= CONFIGURAÇÕES =================
# 1. Token do Supervisor (Pode ser o mesmo ou outro bot)
TOKEN = "8465625783:AAEAQm0N9cZnbumMpO6-1HSkJT6CjlwKyiw"

# 2. Seu ID numérico do Telegram (SEGURANÇA CRÍTICA)
# O bot só responderá a você. Explico abaixo como pegar esse número.
ID_SUPERVISOR = 2056650757 

# 3. URL do Firebase (Base, sem o .json no final aqui)
URL_BASE = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com"

bot = telebot.TeleBot(TOKEN)

# ================= SUA FUNÇÃO DE ANÁLISE =================
def gerar_analise_dados():
    # ... Sua lógica de gerar gráficos aqui ...
    # Exemplo rápido para não quebrar o código:
    plt.figure()
    plt.text(0.5, 0.5, "Gráfico do Supervisor", ha='center')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ================= SEGURANÇA =================
def eh_supervisor(mensagem):
    if mensagem.from_user.id == ID_SUPERVISOR:
        return True
    bot.reply_to(mensagem, "⛔ Acesso Negado.")
    return False

# ================= COMANDOS =================

@bot.message_handler(commands=['start'])
def menu(mensagem):
    if not eh_supervisor(mensagem): return
    bot.reply_to(mensagem, "👮‍♂️ **Painel Supervisor**\nMonitoramento de Fraude: ON ✅\nUse: /ocupacao ou /analise")

@bot.message_handler(commands=['ocupacao'])
def ver_ocupacao(mensagem):
    if not eh_supervisor(mensagem): return
    
    try:
        # Pega dados direto de /estado.json
        resp = requests.get(URL_ESTADO)
        if resp.status_code == 200:
            dados = resp.json()
            # O JSON retorna direto: {"ocupacao_atual": 1, ...}
            qtd = dados.get('ocupacao_atual', 0)
            limite = dados.get('limite_ocupacao', 10)
            
            bot.reply_to(mensagem, f"👥 **Ocupação Atual:** {qtd} / {limite}")
        else:
            bot.reply_to(mensagem, "⚠️ Erro ao ler estado no Firebase.")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro de conexão: {e}")

@bot.message_handler(commands=['analise'])
def enviar_analise(mensagem):
    if not eh_supervisor(mensagem): return
    bot.send_chat_action(mensagem.chat.id, 'upload_photo')
    try:
        imagem = gerar_analise_dados()
        bot.send_photo(mensagem.chat.id, imagem, caption="📊 Relatório Gerado")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro: {e}")

# ================= MONITORAMENTO INTELIGENTE =================
def monitorar_fraudes():
    print("📡 Monitoramento de fraudes iniciado...")
    ultimo_id_processado = None

    # Sessão persistente para evitar aquele erro de DNS/Connection
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('https://', adapter)

    while True:
        try:
            # 1. Busca apenas o ÚLTIMO evento do banco
            resp = session.get(URL_ULTIMO_EVENTO, timeout=10)
            
            if resp.status_code == 200 and resp.json():
                dados_dict = resp.json() 
                
                # O Firebase retorna: { "-ChaveDoEvento": { "fraudulento": true, ... } }
                # Precisamos pegar essa chave dinâmica
                id_evento = list(dados_dict.keys())[0]
                conteudo = dados_dict[id_evento]

                # 2. Verifica se é um evento NOVO (diferente do último que vimos)
                if id_evento != ultimo_id_processado:
                    
                    # 3. VERIFICAÇÃO DE FRAUDE
                    # Baseado no seu JSON, o campo é "fraudulento" (true/false)
                    eh_fraude = conteudo.get('fraudulento')

                    # DEBUG: Printa no terminal para você acompanhar
                    print(f"Novo evento: {id_evento} | Fraude: {eh_fraude}")

                    if eh_fraude == True:
                        cartao = conteudo.get('cartao', 'Desconhecido')
                        hora = conteudo.get('timestamp', 'Agora')
                        
                        alerta = f"""
🚨 **ALERTA DE FRAUDE DETECTADA** 🚨

⛔ **Cartão Bloqueado Tentou Acesso!**
🆔 ID: `{cartao}`
⏰ Hora: {hora}
                        """
                        try:
                            bot.send_message(ID_SUPERVISOR, alerta, parse_mode="Markdown")
                        except:
                            print("Erro ao enviar msg Telegram")
                    
                    # Atualiza o ID para não processar o mesmo evento de novo
                    ultimo_id_processado = id_evento
            
        except Exception as e:
            print(f"♻️ Reconectando monitoramento... ({e})")
            time.sleep(5)

        time.sleep(3) # Verifica a cada 3 segundos

# ================= EXECUÇÃO =================
if __name__ == "__main__":
    # Inicia Monitoramento
    t = threading.Thread(target=monitorar_fraudes)
    t.daemon = True
    t.start()

    # Inicia Bot com reconexão automática
    print("👮‍♂️ Bot Supervisor Rodando...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except:
            time.sleep(5)

