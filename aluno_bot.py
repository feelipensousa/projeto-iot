import telebot
import requests

# ================= CONFIGURAÇÕES (PREENCHA AQUI) =================

# 1. Cole aqui o token que o @BotFather te deu
TOKEN = "8408999950:AAHKbp6_XLE0kgDFJUj-Ig-I25vItG6X5EM"

# 2. Sua URL do Firebase (Mantenha o .json no final)
URL_FIREBASE = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com/estado.json"

# Inicializa a conexão com o Telegram
bot = telebot.TeleBot(TOKEN)

# ================= FUNÇÃO ETL (Extração de Dados) =================
def buscar_dados_firebase():
    """Busca o JSON do Firebase e retorna um dicionário Python"""
    try:
        response = requests.get(URL_FIREBASE)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erro HTTP: {response.status_code}")
            return None
    except Exception as e:
        print(f"Erro de conexão: {e}")
        return None

# ================= COMANDOS DO BOT =================

# Comando /start (Boas vindas)
@bot.message_handler(commands=['start', 'help'])
def boas_vindas(mensagem):
    texto = """
👋 **Olá! Sou o Monitor da Biblioteca.**

Eu consulto os sensores IoT da sala em tempo real.
Use o comando abaixo para verificar se há vagas:

/ocupacao - Ver lotação atual
    """
    bot.reply_to(mensagem, texto)

# Comando /ocupacao (Onde a mágica acontece)
@bot.message_handler(commands=['ocupacao'])
def verificar_ocupacao(mensagem):
    # Mostra que o bot está "escrevendo..." (UX)
    bot.send_chat_action(mensagem.chat.id, 'typing')
    
    dados = buscar_dados_firebase()
    
    if dados:
        # Extrai os dados do JSON (Tratamento de Dados)
        qtd = dados.get('ocupacao_atual', 0)
        limite = dados.get('limite_ocupacao', 10)
        
        # Lógica de visualização
        if qtd >= limite:
            status = "🔴 **LOTADO**"
            msg_extra = "Aguarde alguém sair."
        elif qtd >= (limite * 0.8): # 80% cheio
            status = "🟠 **QUASE CHEIA**"
            msg_extra = "Restam poucas vagas!"
        else:
            status = "🟢 **DISPONÍVEL**"
            msg_extra = "Pode vir estudar!"

        # Monta a resposta final
        resposta = f"""
📊 **Status da Sala**
{status}

👥 Pessoas: {qtd} / {limite}
_{msg_extra}_
        """
        bot.reply_to(mensagem, resposta, parse_mode="Markdown")
    else:
        bot.reply_to(mensagem, "⚠️ Erro ao conectar com os sensores.")

# ================= LOOP DO SERVIDOR =================
print("🤖 Bot do Usuário rodando... (Não feche esta janela)")
bot.polling()