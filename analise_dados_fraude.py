#@title Detecção de fraude
import json
from datetime import datetime
from collections import defaultdict, Counter
import matplotlib.pyplot as plt

# =====================================================
# CONFIGURAÇÕES DO MODELO
# =====================================================
LIMITE_SCORE_FRAUDE = 4
LIMITE_SCORE_SUSPEITO = 2
LIMITE_PERMANENCIA_MIN = 1  # minutos

# =====================================================
# FUNÇÕES AUXILIARES
# =====================================================
def parse_timestamp(ts):
    return datetime.fromisoformat(ts)

def minutos_entre(t1, t2):
    return abs((t2 - t1).total_seconds()) / 60

# =====================================================
# 1. LEITURA DO JSON
# =====================================================
def plotar_analise():
    with open("dadosreais.json", "r", encoding="utf-8") as f:
        dados = json.load(f)

    # =====================================================
    # 2. NORMALIZAÇÃO DOS EVENTOS
    # =====================================================
    eventos = []

    for evento in dados.values():
        eventos.append({
            "cartao": evento["cartao"],
            "timestamp": parse_timestamp(evento["timestamp"]),
            "leitor": evento["leitor"],
            "permitido": evento["acesso_permitido"]
        })

    # Ordenação cronológica
    eventos.sort(key=lambda x: x["timestamp"])

    # =====================================================
    # 3. AGRUPAMENTO POR CARTÃO
    # =====================================================
    eventos_por_cartao = defaultdict(list)

    for e in eventos:
        eventos_por_cartao[e["cartao"]].append(e)

    # =====================================================
    # 4. PERFIL COMPORTAMENTAL
    # =====================================================
    perfil = {}

    for cartao, evs in eventos_por_cartao.items():
        entradas = [e["timestamp"].hour for e in evs if e["leitor"] == "entrada"]
        saidas = [e["timestamp"].hour for e in evs if e["leitor"] == "saida"]

        perfil[cartao] = {
            "media_entrada": sum(entradas) / len(entradas) if entradas else None,
            "media_saida": sum(saidas) / len(saidas) if saidas else None
        }

    # =====================================================
    # 5. DETECÇÃO DE FRAUDE (REGRAS + SCORE)
    # =====================================================
    resultados = []

    for cartao, evs in eventos_por_cartao.items():
        ultimo_evento = None

        for e in evs:
            score = 0
            motivos = []

            # Regra 1: sequência inválida
            if ultimo_evento:
                if ultimo_evento["leitor"] == e["leitor"]:
                    score += 3
                    motivos.append("Sequencia invalida (entrada/entrada ou saida/saida)")

            # Regra 2: permanência incompatível
            if ultimo_evento and ultimo_evento["leitor"] == "entrada" and e["leitor"] == "saida":
                tempo = minutos_entre(ultimo_evento["timestamp"], e["timestamp"])
                if tempo < LIMITE_PERMANENCIA_MIN:
                    score += 2
                    motivos.append("Permanência muito curta")

            # Regra 3: horário atípico
            media = perfil[cartao]["media_entrada"]
            if e["leitor"] == "entrada" and media is not None:
                if abs(e["timestamp"].hour - media) >= 3:
                    score += 3
                    motivos.append("Horário atípico")

            # Classificação final
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
    # 6. RELATÓRIO EM TEXTO
    # =====================================================
    print("\n===== EVENTOS SUSPEITOS E FRAUDULENTOS =====\n")

    for r in resultados:
        if r["classificacao"] != "NORMAL":
            print(f"Cartao: {r['cartao']}")
            print(f"Data/Hora: {r['timestamp']}")
            print(f"Leitor: {r['leitor']}")
            print(f"Classificacao: {r['classificacao']}")
            print(f"Score: {r['score']}")
            print(f"Motivos: {', '.join(r['motivos'])}")
            print("-" * 50)

    # =====================================================
    # 7. GRÁFICO – DISTRIBUIÇÃO DAS CLASSIFICAÇÕES
    # =====================================================

    classificacoes = [r["classificacao"] for r in resultados]
    contagem = Counter(classificacoes)

    plt.figure()
    plt.bar(contagem.keys(), contagem.values())
    plt.title("Distribuição de Eventos por Classificação")
    plt.xlabel("Classificação")
    plt.ylabel("Quantidade de Eventos")
    plt.tight_layout()
    plt.show()

