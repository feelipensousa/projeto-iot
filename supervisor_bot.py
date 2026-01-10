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
    """
    Aqui você coloca a lógica da sua função generate_analysis.
    O retorno deve ser um objeto Figure do Matplotlib ou a imagem salva.
    Vou simular um gráfico simples para o exemplo.
    """
    # --- SIMULAÇÃO (Substitua pelo seu código) ---
    plt.figure(figsize=(8, 4))
    plt.plot(['08h', '09h', '10h'], [2, 8, 5], color='red')
    plt.title("Análise de Tentativas de Fraude (Simulação)")
    plt.grid(True)
    # ---------------------------------------------
    
    # Salva na memória RAM (Buffer) para não criar arquivo no PC
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ================= SEGURANÇA =================
def eh_supervisor(mensagem):
    if mensagem.from_user.id == ID_SUPERVISOR:
        return True
    bot.reply_to(mensagem, "⛔ Acesso Negado. Este bot é restrito.")
    return False

# ================= COMANDOS DO BOT =================

@bot.message_handler(commands=['start'])
def menu(mensagem):
    if not eh_supervisor(mensagem): return
    texto = """
👮‍♂️ **Painel do Supervisor Ativo**

O sistema de alerta automático está ligado. 📡

/ocupacao - Ver lotação atual
/analise - 📊 Gerar gráfico de dados
    """
    bot.reply_to(mensagem, texto)

@bot.message_handler(commands=['ocupacao'])
def ver_ocupacao(mensagem):
    if not eh_supervisor(mensagem): return
    
    try:
        resp = requests.get(f"{URL_BASE}/estado.json")
        dados = resp.json()
        qtd = dados.get('ocupacao_atual', 0)
        limite = dados.get('limite_ocupacao', 10)
        bot.reply_to(mensagem, f"👥 **Ocupação:** {qtd}/{limite}")
    except:
        bot.reply_to(mensagem, "Erro ao conectar.")

@bot.message_handler(commands=['analise'])
def enviar_analise(mensagem):
    if not eh_supervisor(mensagem): return
    
    bot.send_chat_action(mensagem.chat.id, 'upload_photo')
    try:
        # Chama sua função
        imagem = gerar_analise_dados()
        bot.send_photo(mensagem.chat.id, imagem, caption="📊 **Relatório de Dados Gerado**")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro ao gerar análise: {e}")

# ================= MONITORAMENTO (THREAD) =================
def monitorar_fraudes():
    """
    Esta função roda em paralelo. Ela verifica o último evento
    a cada 5 segundos. Se for fraude e for NOVO, avisa.
    """
    print("📡 Monitoramento de fraudes iniciado...")
    ultimo_id_processado = None

    while True:
        try:
            # Pega apenas o ÚLTIMO evento registrado (limitToLast=1)
            url = f"{URL_BASE}/eventos.json?orderBy=\"$key\"&limitToLast=1"
            resp = requests.get(url)
            
            if resp.status_code == 200 and resp.json():
                dados = resp.json()
                # O Firebase retorna { "ID_UNICO": {dados...} }
                id_evento = list(dados.keys())[0]
                conteudo = dados[id_evento]

                # Se é um evento novo que ainda não vimos
                if id_evento != ultimo_id_processado:
                    # Verifica se é fraude
                    if conteudo.get('fraudulento') == True:
                        hora = conteudo.get('timestamp', 'Desconhecida')
                        cartao = conteudo.get('cartao', 'N/A')
                        
                        alerta = f"""
🚨 **ALERTA DE SEGURANÇA** 🚨

Foi detectada uma tentativa de acesso não autorizado!
💳 **Cartão:** {cartao}
⏰ **Horário:** {hora}
                        """
                        # Envia mensagem proativa (sem o usuário pedir)
                        bot.send_message(ID_SUPERVISOR, alerta)
                    
                    # Atualiza o ID para não repetir o alerta do mesmo evento
                    ultimo_id_processado = id_evento
            
        except Exception as e:
            print(f"Erro no monitoramento: {e}")

        time.sleep(3) # Verifica a cada 3 segundos

# ================= EXECUÇÃO =================
if __name__ == "__main__":
    # 1. Inicia o Monitoramento em outra Thread
    t = threading.Thread(target=monitorar_fraudes)
    t.daemon = True # Morre se o programa principal fechar
    t.start()

    # 2. Inicia o Bot
    print("👮‍♂️ Bot Supervisor rodando...")
    bot.polling()