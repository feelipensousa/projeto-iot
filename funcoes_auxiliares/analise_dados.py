import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from math import sqrt
import requests
import json
from datetime import timedelta
import os

def analise_dados():
    rows = []

    # ==========================================================
    # 1. CARREGAR HISTÓRICO LOCAL (dadosreais.json)
    arquivo_local = "dadosreais.json"
    
    if os.path.exists(arquivo_local):
        try:
            with open(arquivo_local, "r") as f:
                data_local = json.load(f)
            
            for k, v in data_local.items():
                ts = v.get("timestamp")
                if ts:
                    rows.append({"timestamp": pd.to_datetime(ts), "origem": "Histórico"})
            print(f"Carregados {len(data_local)} registros do histórico local.")
        except Exception as e:
            print(f"Erro ao ler JSON local: {e}")
    else:
        print("Arquivo 'dadosreais.json' não encontrado. Usando apenas Firebase.")

    # ==========================================================
    # 2. CARREGAR DADOS EM TEMPO REAL (Firebase)
    URL = "https://controle-de-acesso-iot-default-rtdb.firebaseio.com/eventos.json"
    
    try:
        response = requests.get(URL)
        if response.status_code == 200 and response.json():
            data_cloud = response.json()
            count_cloud = 0
            for k, v in data_cloud.items():
                ts = v.get("timestamp")
                if ts:
                    rows.append({"timestamp": pd.to_datetime(ts), "origem": "Tempo Real"})
                    count_cloud += 1
            print(f"Carregados {count_cloud} registros do Firebase.")
    except Exception as e:
        print(f"Erro ao baixar dados do Firebase: {e}")

    # ==========================================================
    # 3. LIMPEZA
    if not rows:
        print("Nenhum dado disponível (nem local, nem nuvem).")
        return

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["timestamp"])
    
    df["date"] = df["timestamp"].dt.date

    daily = df.groupby("date").size().reset_index(name="acessos")
    daily = daily.sort_values("date").reset_index(drop=True)

    # ==========================================================
    # 4. APLICAÇÃO DA MÉDIA MÓVEL E PREDIÇÃO
    window = 4
    daily["ma"] = daily["acessos"].rolling(window).mean().fillna(0)

    # --- LÓGICA DE VALIDAÇÃO (Performance no último dia real) ---
    if len(daily) > window:
        idx_validacao = daily.index[-1]
        real_validacao = int(daily.loc[idx_validacao, "acessos"])
        pred_validacao = daily.loc[idx_validacao-window:idx_validacao-1, "acessos"].mean()
        
        mae = abs(real_validacao - pred_validacao)
        rmse = sqrt((real_validacao - pred_validacao)**2)
        accuracy = (1 - mae / real_validacao) if real_validacao != 0 else 0
        if accuracy < 0: accuracy = 0

        print("\n--- PERFORMANCE (Validação Último Dia) ---")
        print(f"Data: {daily.iloc[-1]['date']}")
        print(f"Real: {real_validacao} | Estimado: {pred_validacao:.2f}")
        print(f"Acurácia: {accuracy:.2%}")

    # --- LÓGICA DE PREVISÃO FUTURA ---
    pred_futura = daily["acessos"].tail(window).mean()
    ultima_data = daily.iloc[-1]["date"]
    data_futura = ultima_data + timedelta(days=1)

    print(f"\nPREVISÃO PARA {data_futura}: {int(pred_futura)} acessos esperados.")

    # ==========================================================
    # 5. PLOTAGEM
    plt.plot(daily["date"], daily["acessos"], marker="o", label="Histórico Unificado", color='#1f77b4')
    plt.plot(daily["date"], daily["ma"], linestyle='--', label=f"Tendência ({window}d)", color='#ff7f0e')
    
    # Ponto da Previsão Futura
    plt.scatter([pd.to_datetime(data_futura)], [pred_futura], color='red', s=120, zorder=5, label=f"Prev: {data_futura}")
    
    plt.title(f"Análise de Demanda (Tempo Real)\nPrevisão {data_futura}: {int(pred_futura)} pessoas")
    plt.xlabel("Data")
    plt.ylabel("Acessos")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.xticks(rotation=45)