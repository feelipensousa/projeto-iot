#@title Média Móvel

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from math import sqrt

def analise_dados():
    path = "dadosreais.json"

    with open(path) as f:
        data = json.load(f)

    rows = []
    for k,v in data.items():
        ts = v.get("timestamp")
        if ts:
            rows.append({"timestamp": pd.to_datetime(ts)})

    df = pd.DataFrame(rows)
    df["date"] = df["timestamp"].dt.date

    daily = df.groupby("date").size().reset_index(name="acessos")
    daily = daily.sort_values("date").reset_index(drop=True)

    # janela da média móvel
    window = 4
    daily["ma"] = daily["acessos"].rolling(window).mean()

    target_day = pd.to_datetime("2025-12-29").date()

    idx = daily.index[daily["date"] == target_day][0]

    # previsão = média dos últimos k dias
    pred = daily.loc[idx-window:idx-1, "acessos"].mean()

    real = int(daily.loc[idx, "acessos"])

    mae = abs(real - pred)
    rmse = sqrt((real - pred)**2)
    accuracy = 1 - mae / real if real != 0 else 0
    precision = 1 - mae / (abs(pred) + abs(real))

    print("Predição:", pred)
    print("Real:", real)
    print("MAE:", mae)
    print("RMSE:", rmse)
    print("Acurácia:", accuracy)
    print("Precisão:", precision)

    plt.figure()
    plt.plot(daily["date"], daily["acessos"], marker="o", label="Real")
    plt.plot(daily["date"], daily["ma"], label=f"Média móvel ({window})")
    plt.scatter([pd.to_datetime(target_day)], [pred], label="Previsão 29/12")
    plt.title("Previsão com Média Móvel")
    plt.xlabel("Data")
    plt.ylabel("Acessos")
    plt.legend()
    plt.show()
