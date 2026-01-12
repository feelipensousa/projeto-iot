import telebot
import requests
import time
import threading
import io
import matplotlib.pyplot as plt
from analise_dados import analise_dados
from analise_dados_fraude import plotar_analise
import sys

# ================= CONFIGURAÇÕES =================
# 1. Token do Supervisor (Pode ser o mesmo ou outro bot)
TOKEN = "8465625783:AAEAQm0N9cZnbumMpO6-1HSkJT6CjlwKyiw"

# 2. Seu ID numérico do Telegram (SEGURANÇA CRÍTICA)
# O bot só responderá a você. Explico abaixo como pegar esse número.
ID_SUPERVISOR = 2056650757 

# 3. URL do Firebase (Base, sem o .json no final aqui)
URL_BASE = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com"

# URL Específica para ler o ESTADO (Ocupação)
# Isso acessa direto o nó: "estado": { ... }
URL_ESTADO = f"{URL_BASE}/estado.json"

# URL Específica para ler EVENTOS (Monitoramento)
# Isso acessa o nó "eventos", ordena pela chave e pega só o último
URL_ULTIMO_EVENTO = f"{URL_BASE}/eventos.json?orderBy=\"$key\"&limitToLast=1"

# Inicializa o Bot
bot = telebot.TeleBot(TOKEN)

# ================= 3. FUNÇÃO DE ANÁLISE DE DADOS =================
import sys # <--- Adicione esse import no topo do arquivo

def gerar_analise_dados():
    """
    Executa a análise, captura o texto printado e gera o gráfico.
    Retorna: (buffer_imagem, texto_metricas)
    """
    # 1. PREPARAÇÃO PARA CAPTURAR O PRINT
    old_stdout = sys.stdout  # Guarda a saída original (console)
    result_capture = io.StringIO()
    sys.stdout = result_capture  # Redireciona prints para nossa variável

    # 2. EXECUTA SUAS FUNÇÕES
    # Tudo que analise_dados() der de 'print', vai para result_capture
    try:
        analise_dados() 
    except Exception as e:
        print(f"Erro ao calcular métricas: {e}")
    
    # Restaura a saída padrão (para você voltar a ver erros no console)
    sys.stdout = old_stdout
    texto_metricas = result_capture.getvalue() # Pega o texto capturado

    # 3. GERA OS GRÁFICOS
    plotar_analise()
    
    # 4. SALVA A IMAGEM NA MEMÓRIA
    buf = io.BytesIO()
    # bbox_inches='tight' ajuda a não cortar legendas do gráfico
    plt.savefig(buf, format='png', bbox_inches='tight') 
    buf.seek(0)
    plt.close('all') # Fecha todas as figuras para limpar a memória
    
    # Retorna A IMAGEM e O TEXTO
    return buf, texto_metricas

# ================= 4. SEGURANÇA =================
def eh_supervisor(mensagem):
    """Verifica se quem mandou a mensagem é você"""
    if mensagem.from_user.id == ID_SUPERVISOR:
        return True
    bot.reply_to(mensagem, "⛔ Acesso Negado. Bot restrito ao supervisor.")
    return False

# ================= 5. COMANDOS DO CHAT =================

@bot.message_handler(commands=['start'])
def menu(mensagem):
    if not eh_supervisor(mensagem): return
    texto = """
👮‍♂️ **Painel do Supervisor**

✅ Monitoramento de Fraudes: ATIVO
📡 Conectado ao Firebase

**Comandos:**
/ocupacao - Ver lotação da sala
/analise - Ver gráficos de dados
    """
    bot.reply_to(mensagem, texto, parse_mode="Markdown")

@bot.message_handler(commands=['ocupacao'])
def ver_ocupacao(mensagem):
    if not eh_supervisor(mensagem): return
    
    try:
        # Usa a variável global URL_ESTADO definida lá em cima
        resp = requests.get(URL_ESTADO)
        
        if resp.status_code == 200:
            dados = resp.json()
            # O Firebase retorna: {"ocupacao_atual": 1, "limite_ocupacao": 10...}
            qtd = dados.get('ocupacao_atual', 0)
            limite = dados.get('limite_ocupacao', 10)
            
            msg = f"👥 **Ocupação Atual:** {qtd} / {limite}"
            bot.reply_to(mensagem, msg, parse_mode="Markdown")
        else:
            bot.reply_to(mensagem, "⚠️ Erro ao ler dados do Firebase.")
            
    except Exception as e:
        bot.reply_to(mensagem, f"Erro de conexão: {e}")

@bot.message_handler(commands=['analise'])
def enviar_analise(mensagem):
    if not eh_supervisor(mensagem): return
    
    # Avisa que está enviando foto
    bot.send_chat_action(mensagem.chat.id, 'upload_photo')
    
    try:
        imagem = gerar_analise_dados()
        bot.send_photo(mensagem.chat.id, imagem, caption="📊 **Análise de Dados**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro ao gerar gráfico: {e}")

# ================= 6. MONITORAMENTO EM SEGUNDO PLANO =================
def monitorar_fraudes():
    print("📡 Thread de Monitoramento Iniciada...")
    ultimo_id_processado = None

    # Configura sessão persistente (Evita erro de DNS/Connection)
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('https://', adapter)

    while True:
        try:
            # Usa a variável global URL_ULTIMO_EVENTO
            resp = session.get(URL_ULTIMO_EVENTO, timeout=10)
            
            if resp.status_code == 200 and resp.json():
                dados_dict = resp.json()
                
                # Pega a chave do evento (ex: "-OicTjn...")
                id_evento = list(dados_dict.keys())[0]
                conteudo = dados_dict[id_evento]

                # Se é um evento novo
                if id_evento != ultimo_id_processado:
                    
                    # Verifica se o campo 'fraudulento' é true
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
                    
                    # Atualiza o ID
                    ultimo_id_processado = id_evento
            
        except Exception as e:
            print(f"⚠️ Oscilação na rede (Monitoramento): {e}")
            time.sleep(5) # Espera um pouco se der erro

        time.sleep(3) # Intervalo entre verificações

# ================= 7. EXECUÇÃO PRINCIPAL =================
if __name__ == "__main__":
    # Inicia o monitoramento paralelo
    t = threading.Thread(target=monitorar_fraudes)
    t.daemon = True
    t.start()

    print("👮‍♂️ Bot Supervisor Rodando... (Ctrl+C para parar)")
    
    # Loop infinito com reconexão automática
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ Bot caiu. Reiniciando... Erro: {e}")
            time.sleep(5)