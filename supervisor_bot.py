import telebot
import requests
import time
import threading
import io
import sys
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os

from funcoes_auxiliares.analise_dados import analise_dados
from funcoes_auxiliares.analise_dados_fraude import plotar_analise

# ================= CONFIGURAÇÕES =================
load_dotenv()
TOKEN = os.getenv("bot_supervisor")
ID_SUPERVISOR = 2056650757 

URL_BASE = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com"
URL_ESTADO = f"{URL_BASE}/estado.json"
URL_ULTIMO_EVENTO = f"{URL_BASE}/eventos.json?orderBy=\"$key\"&limitToLast=1"


bot = telebot.TeleBot(TOKEN)

# ================= FUNÇÕES AUXILIARES DE GRÁFICOS =================

def gerar_grafico_ocupacao():
    """
    Chama analise_dados(), captura o print das métricas e gera o gráfico de predição.
    Retorna: (buffer_imagem, texto_metricas)
    """
    plt.close('all') 
    plt.figure(figsize=(10, 6)) # Cria o gráfico
    
    old_stdout = sys.stdout
    result_capture = io.StringIO()
    sys.stdout = result_capture
    
    try:
        analise_dados() 
    except Exception as e:
        print(f"Erro na analise_dados: {e}")

    sys.stdout = old_stdout
    texto_metricas = result_capture.getvalue()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close('all')
    
    return buf, texto_metricas

def gerar_grafico_fraude():
    """
    Chama plotar_analise() (do arquivo analise_dados_fraude) e gera o gráfico de barras.
    Retorna: buffer_imagem
    """
    plt.close('all')
    plt.figure(figsize=(10, 6)) # Cria o gráfico
    
    try:
        plotar_analise()
    except Exception as e:
        print(f"Erro na plotar_analise: {e}")

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close('all')
    
    return buf

# ================= SEGURANÇA =================
def eh_supervisor(mensagem):
    if mensagem.from_user.id == ID_SUPERVISOR:
        return True
    bot.reply_to(mensagem, "⛔ Acesso Negado. Bot restrito ao supervisor.")
    return False

# ================= COMANDOS DO CHAT =================
@bot.message_handler(commands=['start'])
def menu(mensagem):
    if not eh_supervisor(mensagem): return
    texto = """
👮‍♂️ **Painel do Supervisor**

✅ Monitoramento de Fraudes: ATIVO
📡 Conectado ao Firebase

**Comandos Disponíveis:**
/ocupacao - Ver lotação em tempo real
/analise_ocupacao - 📈 Ver predição e métricas de ML
/analise_fraude - 🚨 Ver gráfico de distribuição de fraudes
    """
    bot.reply_to(mensagem, texto, parse_mode="Markdown")

@bot.message_handler(commands=['ocupacao'])
def ver_ocupacao(mensagem):
    if not eh_supervisor(mensagem): return
    
    try:
        resp = requests.get(URL_ESTADO)
        if resp.status_code == 200:
            dados = resp.json()
            qtd = dados.get('ocupacao_atual', 0)
            limite = dados.get('limite_ocupacao', 10)
            msg = f"👥 **Ocupação Atual:** {qtd} / {limite}"
            bot.reply_to(mensagem, msg, parse_mode="Markdown")
        else:
            bot.reply_to(mensagem, "⚠️ Erro ao ler dados do Firebase.")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro de conexão: {e}")

# --- COMANDO 1: OCUPAÇÃO ---
@bot.message_handler(commands=['analise_ocupacao'])
def enviar_analise_ocupacao(mensagem):
    if not eh_supervisor(mensagem): return
    
    bot.send_chat_action(mensagem.chat.id, 'upload_photo')
    try:
        imagem, texto_metricas = gerar_grafico_ocupacao()
        
        legenda = f"📈 **Predição de Ocupação**\n\n```\n{texto_metricas}```"
        
        bot.send_photo(
            mensagem.chat.id, 
            photo=imagem, 
            caption=legenda, 
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(mensagem, f"Erro ao gerar análise de ocupação: {e}")

# --- COMANDO 2: FRAUDE ---
@bot.message_handler(commands=['analise_fraude'])
def enviar_analise_fraude(mensagem):
    if not eh_supervisor(mensagem): return
    
    bot.send_chat_action(mensagem.chat.id, 'upload_photo')
    try:
        imagem = gerar_grafico_fraude()
        
        bot.send_photo(
            mensagem.chat.id, 
            photo=imagem, 
            caption="🚨 **Distribuição de Eventos (Fraudes)**", 
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(mensagem, f"Erro ao gerar análise de fraude: {e}")

# ================= MONITORAMENTO DE FRAUDE =================
def monitorar_fraudes():
    print("📡 Thread de Monitoramento Iniciada...")
    ultimo_id_processado = None

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('https://', adapter)

    while True:
        try:
            resp = session.get(URL_ULTIMO_EVENTO, timeout=10)
            
            if resp.status_code == 200 and resp.json():
                dados_dict = resp.json()
                id_evento = list(dados_dict.keys())[0]
                conteudo = dados_dict[id_evento]

                if id_evento != ultimo_id_processado:
                    # Verifica fraude
                    if conteudo.get('fraudulento') == True:
                        cartao = conteudo.get('cartao', 'N/A')
                        hora = conteudo.get('timestamp', 'N/A')
                        
                        alerta = f"""
🚨 **ALERTA DE SEGURANÇA** 🚨

Foi detectada uma tentativa de acesso não autorizado!
💳 **Cartão:** `{cartao}`
⏰ **Horário:** {hora}
                        """
                        try:
                            bot.send_message(ID_SUPERVISOR, alerta, parse_mode="Markdown")
                            print(f"[ALERTA ENVIADO] Fraude no cartão {cartao}")
                        except Exception as e:
                            print(f"Erro ao enviar alerta Telegram: {e}")
                    
                    ultimo_id_processado = id_evento
            
        except Exception as e:
            print(f"⚠️ Oscilação na rede (Monitoramento): {e}")
            time.sleep(5)

        time.sleep(3)

if __name__ == "__main__":
    t = threading.Thread(target=monitorar_fraudes)
    t.daemon = True
    t.start()

    print("👮‍♂️ Bot Supervisor Rodando... (Ctrl+C para parar)")
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ Bot caiu. Reiniciando... Erro: {e}")
            time.sleep(5)