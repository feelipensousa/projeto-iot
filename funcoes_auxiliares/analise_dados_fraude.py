import json
import requests
import os
from datetime import datetime
from collections import defaultdict, Counter
import matplotlib.pyplot as plt


LIMITE_SCORE_FRAUDE = 4
LIMITE_SCORE_SUSPEITO = 2
LIMITE_PERMANENCIA_MIN = 1  # minutos

# URL do Firebase
URL_FIREBASE = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com/eventos.json"

def parse_timestamp(ts):
    # Trata timestamps com ou sem milissegundos
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except:
        return datetime.now() # Fallback em caso de erro

def minutos_entre(t1, t2):
    return abs((t2 - t1).total_seconds()) / 60

# =====================================================
# FUNÇÃO PRINCIPAL
def plotar_analise():
    eventos = []
    ids_processados = set()

    # =====================================================
    # 1. ETL: CARREGAR DADOS LOCAIS
    if os.path.exists("dadosreais.json"):
        try:
            with open("dadosreais.json", "r", encoding="utf-8") as f:
                dados_local = json.load(f)
            
            for id_evento, evento in dados_local.items():
                # Normaliza para lista
                eventos.append({
                    "origem": "JSON",
                    "cartao": evento.get("cartao"),
                    "timestamp": parse_timestamp(evento.get("timestamp")),
                    "leitor": evento.get("leitor"),
                    "permitido": evento.get("acesso_permitido")
                })
                chave_unica = f"{evento.get('timestamp')}-{evento.get('cartao')}"
                ids_processados.add(chave_unica)
                
            print(f"Carregados {len(dados_local)} eventos locais.")
        except Exception as e:
            print(f"Erro ao ler JSON local: {e}")

    # =====================================================
    # 2. ETL: CARREGAR DADOS TEMPO REAL (FIREBASE)
    try:
        response = requests.get(URL_FIREBASE)
        if response.status_code == 200 and response.json():
            dados_cloud = response.json()
            count_cloud = 0
            
            for id_evento, evento in dados_cloud.items():
                ts_str = evento.get("timestamp")
                cartao = evento.get("cartao")
                
                # Verifica duplicidade
                chave_unica = f"{ts_str}-{cartao}"
                if chave_unica in ids_processados:
                    continue # Pula se já veio do JSON
                
                eventos.append({
                    "origem": "Firebase",
                    "cartao": cartao,
                    "timestamp": parse_timestamp(ts_str),
                    "leitor": evento.get("leitor"),
                    "permitido": evento.get("acesso_permitido")
                })
                count_cloud += 1
            print(f"Carregados {count_cloud} novos eventos do Firebase.")
    except Exception as e:
        print(f"Erro ao conectar no Firebase: {e}")

    # =====================================================
    # 3. ORDENAÇÃO E PREPARAÇÃO
    if not eventos:
        print("Nenhum evento para analisar.")
        return

    # Ordenação cronológica obrigatória para detectar sequência
    eventos.sort(key=lambda x: x["timestamp"])

    # =====================================================
    # 4. AGRUPAMENTO E PERFIL
    eventos_por_cartao = defaultdict(list)
    for e in eventos:
        eventos_por_cartao[e["cartao"]].append(e)
    perfil = {}
    for cartao, evs in eventos_por_cartao.items():
        entradas = [e["timestamp"].hour for e in evs if e["leitor"] == "entrada"]
        saidas = [e["timestamp"].hour for e in evs if e["leitor"] == "saida"]

        perfil[cartao] = {
            "media_entrada": sum(entradas) / len(entradas) if entradas else None,
            "media_saida": sum(saidas) / len(saidas) if saidas else None
        }
# =====================================================
    # 5. MOTOR DE REGRAS (DETECÇÃO DE FRAUDE)
    resultados = []

    for cartao, evs in eventos_por_cartao.items():
        ultimo_evento = None

        for e in evs:
            score = 0
            motivos = []

            # --- Regra 1: Sequência Inválida ---
            if ultimo_evento:
                if ultimo_evento["leitor"] == e["leitor"]:
                    score += 3
                    motivos.append(f"Sequência inválida ({e['leitor']} duplicada)")

            # --- Regra 2: Permanência muito curta  ---
            if ultimo_evento and ultimo_evento["leitor"] == "entrada" and e["leitor"] == "saida":
                tempo = minutos_entre(ultimo_evento["timestamp"], e["timestamp"])
                if tempo < LIMITE_PERMANENCIA_MIN:
                    score += 2
                    motivos.append(f"Permanência suspeita ({int(tempo)}min)")

            # --- Regra 3: Horário Atípico ---
            media = perfil[cartao]["media_entrada"]
            if e["leitor"] == "entrada" and media is not None:
                # Se desviar mais de 4 horas da média habitual
                if abs(e["timestamp"].hour - media) >= 4:
                    score += 3
                    motivos.append("Horário fora do perfil habitual")
            
            # --- Regra 4: Cartão Bloqueado ---
            if e["permitido"] == False:
                 score += 5
                 motivos.append("Acesso Negado pelo Hardware")

            if score >= LIMITE_SCORE_FRAUDE:
                classificacao = "FRAUDULENTO"
            elif score >= LIMITE_SCORE_SUSPEITO:
                classificacao = "SUSPEITO"
            else:
                classificacao = "NORMAL"

            resultados.append({
                "cartao": cartao,
                "timestamp": e["timestamp"],
                "leitor": e["leitor"],
                "score": score,
                "classificacao": classificacao,
                "motivos": motivos
            })

            ultimo_evento = e

    # =====================================================
    # 6. RELATÓRIO NO TERMINAL
    print("\n===== RELATÓRIO DE ANOMALIAS DETECTADAS =====")
    fraudes_detectadas = 0
    for r in resultados:
        if r["classificacao"] != "NORMAL":
            fraudes_detectadas += 1
            print(f"🔴 [{r['classificacao']}] Cartão: {r['cartao']}")
            print(f"   Hora: {r['timestamp'].strftime('%d/%m %H:%M')}")
            print(f"   Motivo: {', '.join(r['motivos'])}")
            print("-" * 40)
    
    if fraudes_detectadas == 0:
        print("Nenhuma anomalia grave detectada nos registros.")

    # =====================================================
    # 7. PLOTAGEM 
    classificacoes = [r["classificacao"] for r in resultados]
    contagem = Counter(classificacoes)
    cores = []
    for k in contagem.keys():
        if k == 'NORMAL': cores.append('green')
        elif k == 'SUSPEITO': cores.append('orange')
        elif k == 'FRAUDULENTO': cores.append('red')
        else: cores.append('blue')

    plt.bar(contagem.keys(), contagem.values(), color=cores)
    plt.title(f"Auditoria de Segurança ({len(eventos)} eventos analisados)")
    plt.xlabel("Categoria de Risco")
    plt.ylabel("Qtd de Eventos")
    plt.grid(axis='y', alpha=0.3)
    
    for i, v in enumerate(contagem.values()):
        plt.text(i, v, str(v), ha='center', va='bottom', fontweight='bold')