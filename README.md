# PETR4.SA Stock Forecast

Projeto para o Tech Challenge Fase 4: coleta de dados, comparação entre RNN clássica e LSTM, e API FastAPI para prever o fechamento do próximo pregão de `PETR4.SA`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
```

Este projeto usa `tensorflow-cpu` por padrão. Em máquinas sem CUDA/cuDNN, isso evita os avisos do TensorFlow sobre bibliotecas de GPU ausentes.

## Modelos e Arquiteturas

Sim, o projeto treina **RNN clássica** e **LSTM**.

O script principal de comparação é `scripts/train_recurrent_models.py`. Ele usa os mesmos dados, o mesmo split temporal e as mesmas métricas para todas as arquiteturas, permitindo comparar a diferença prática entre uma RNN simples e uma LSTM.

Arquiteturas testadas por padrão:

| Nome | Tipo | Janela histórica | Camadas recorrentes | Dropout | Learning rate | Batch size |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| `rnn_simple_30` | RNN clássica (`SimpleRNN`) | 30 pregões | 32 unidades | 0.0 | 0.0010 | 32 |
| `rnn_stacked_45` | RNN clássica (`SimpleRNN`) | 45 pregões | 64 + 32 unidades | 0.2 | 0.0008 | 32 |
| `rnn_wide_60` | RNN clássica (`SimpleRNN`) | 60 pregões | 96 unidades | 0.2 | 0.0008 | 16 |
| `lstm_simple_30` | LSTM | 30 pregões | 32 unidades | 0.0 | 0.0010 | 32 |
| `lstm_stacked_45` | LSTM | 45 pregões | 64 + 32 unidades | 0.2 | 0.0008 | 32 |
| `lstm_wide_60` | LSTM | 60 pregões | 96 unidades | 0.2 | 0.0008 | 16 |

Todas preveem o `Close` do próximo pregão usando as colunas `Open`, `High`, `Low`, `Close` e `Volume`. A divisão dos dados é temporal, sem embaralhar: 70% treino, 15% validação e 15% teste. As métricas salvas são MAE, RMSE e MAPE.

Além disso, existe `scripts/train_lstm.py`, que treina somente uma LSTM com busca de hiperparâmetros via Optuna, e é opcional. 

## Pipeline

Coletar o CSV fixo do projeto:

```bash
python3 scripts/collect_data.py
```

Treinar e comparar todas as arquiteturas de RNN clássica e LSTM:

```bash
python3 scripts/train_recurrent_models.py --epochs 80
```

Esse comando:

- treina as 3 arquiteturas RNN e as 3 arquiteturas LSTM;
- escolhe a melhor RNN por RMSE no teste;
- escolhe a melhor LSTM por RMSE no teste;
- salva `models/rnn.keras` e `models/lstm.keras`;
- salva scalers/metadados em `models/rnn_bundle.joblib` e `models/lstm_bundle.joblib`;
- atualiza `reports/metrics.json`, `reports/best_model.json` e `reports/recurrent_architecture_comparison.json`.

Treinar somente algumas arquiteturas específicas:

```bash
python3 scripts/train_recurrent_models.py \
  --epochs 80 \
  --architectures rnn_simple_30 lstm_simple_30 lstm_stacked_45
```

Teste rápido do pipeline, útil antes de um treino completo:

```bash
python3 scripts/train_recurrent_models.py --epochs 3 --patience 1
```

Opcional: treinar apenas uma LSTM com busca de hiperparâmetros via Optuna:

```bash
python3 scripts/train_lstm.py --trials 40
```

Opcional: validar rapidamente o Optuna com poucos trials:

```bash
python3 scripts/train_lstm.py --trials 2
```

Gerar a previsão do próximo pregão usando o melhor modelo por RMSE:

```bash
python3 scripts/predict.py --model best
```

Gerar previsão escolhendo explicitamente a família do modelo:

```bash
python3 scripts/predict.py --model rnn
python3 scripts/predict.py --model lstm
```

## Orquestrador

O comando mais prático para gerenciar treino e validações é o orquestrador:

```bash
python3 scripts/orchestrate.py
```

Ele executa o fluxo principal de ponta a ponta:

- coleta os dados se `data/raw/PETR4.SA.csv` ainda não existir;
- valida o CSV;
- treina as arquiteturas RNN/LSTM com `scripts/train_recurrent_models.py`;
- valida modelos, bundles e relatórios gerados;
- roda `pytest`;
- salva um resumo em `reports/orchestration_summary.json`.

Teste rápido do orquestrador:

```bash
python3 scripts/orchestrate.py --quick
```

Rodar uma comparação com arquiteturas específicas:

```bash
python3 scripts/orchestrate.py \
  --epochs 80 \
  --architectures rnn_simple_30 rnn_stacked_45 lstm_simple_30 lstm_stacked_45
```

Validar artefatos existentes sem treinar novamente:

```bash
python3 scripts/orchestrate.py --skip-train
```

Forçar nova coleta antes do treinamento:

```bash
python3 scripts/orchestrate.py --collect
```

## API

Subir a API:

```bash
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health`: status e modelo vencedor.
- `POST /predict?model=best`: previsão do próximo fechamento.
- `GET /metrics`: métricas Prometheus.

Exemplo abreviado de payload para `/predict`:

```json
{
  "symbol": "PETR4.SA",
  "history": [
    {
      "date": "2024-06-20",
      "open": 36.5,
      "high": 37.2,
      "low": 36.1,
      "close": 36.9,
      "volume": 42000000
    }
  ]
}
```

O payload real precisa repetir esse formato para histórico suficiente: pelo menos a janela treinada para a RNN/LSTM escolhida.

### Exemplos reais de chamada

Antes dos exemplos, suba a API localmente:

```bash
uvicorn app.main:app --reload
```

Ou via Docker:

```bash
docker compose up --build
```

Exemplo real para o **modelo LSTM** usando os últimos 30 pregões do CSV do projeto:

```bash
python3 - <<'PY' | curl -s -X POST "http://localhost:8000/predict?model=lstm" \
  -H "Content-Type: application/json" \
  -d @-
import csv
import json

with open("data/raw/PETR4.SA.csv", newline="") as file:
    rows = list(csv.DictReader(file))[-30:]

history = [
    {
        "date": row["Date"],
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": float(row["Volume"]),
    }
    for row in rows
]

print(json.dumps({"symbol": "PETR4.SA", "history": history}))
PY
```

Exemplo real para o **modelo RNN** usando os últimos 60 pregões do CSV do projeto:

```bash
python3 - <<'PY' | curl -s -X POST "http://localhost:8000/predict?model=rnn" \
  -H "Content-Type: application/json" \
  -d @-
import csv
import json

with open("data/raw/PETR4.SA.csv", newline="") as file:
    rows = list(csv.DictReader(file))[-60:]

history = [
    {
        "date": row["Date"],
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": float(row["Volume"]),
    }
    for row in rows
]

print(json.dumps({"symbol": "PETR4.SA", "history": history}))
PY
```

Com os artefatos atuais, as previsões via CLI para o próximo fechamento foram:

```bash
python3 scripts/predict.py --model lstm
# {'model': 'lstm', ..., 'prediction_next_close': 38.3726}

python3 scripts/predict.py --model rnn
# {'model': 'rnn', ..., 'prediction_next_close': 38.0598}
```

## Docker

A API também pode ser executada com Docker. O container instala o pacote local e define `PYTHONPATH=/app/src`, então os imports `stock_forecast` funcionam dentro da imagem.

Build da imagem:

```bash
docker build -t stock-forecast-api .
```

Rodar a API:

```bash
docker run --rm -p 8000:8000 stock-forecast-api
```

Ou com Docker Compose:

```bash
docker compose up --build
```

Validar a API:

```bash
curl http://localhost:8000/health
```

Os arquivos `models/lstm.keras`, `models/lstm_bundle.joblib`, `models/rnn.keras`, `models/rnn_bundle.joblib`, `reports/best_model.json` e `reports/metrics.json` são copiados para a imagem. Por isso, treine os modelos antes de construir a imagem final, ou reconstrua a imagem depois de retreinar.

## Artefatos

- `data/raw/PETR4.SA.csv`: dados coletados.
- `models/rnn.keras`: melhor RNN clássica.
- `models/rnn_bundle.joblib`: scalers e metadados da RNN.
- `models/lstm.keras`: melhor LSTM.
- `models/lstm_bundle.joblib`: scalers e metadados da LSTM.
- `reports/metrics.json`: MAE, RMSE, MAPE, hiperparâmetros e caminhos dos artefatos.
- `reports/best_model.json`: modelo com menor RMSE no teste temporal.
- `reports/recurrent_architecture_comparison.json`: comparação de todas as arquiteturas RNN/LSTM treinadas.


## Análise dos Resultados

Nos testes atuais, o melhor modelo foi a **LSTM**.

| Modelo | Melhor arquitetura | Janela | MAE teste | RMSE teste | MAPE teste |
| --- | --- | ---: | ---: | ---: | ---: |
| LSTM | `lstm_simple_30` | 30 pregões | 0.5492 | 0.7322 | 1.4570% |
| RNN | `rnn_wide_60` | 60 pregões | 0.7777 | 0.9196 | 2.0312% |

A LSTM venceu nas três métricas principais: MAE, RMSE e MAPE. Isso indica que, no conjunto de teste temporal, ela errou menos em média, teve menor penalização para erros maiores e apresentou menor erro percentual.

Uma explicação provável é que a LSTM lida melhor com dependências temporais do que uma RNN clássica. Suas portas internas controlam o que deve ser esquecido, mantido e atualizado na memória, reduzindo o problema de desaparecimento do gradiente e ajudando a capturar padrões úteis sem carregar ruído demais.

Também é relevante que a melhor LSTM foi a arquitetura mais simples, com janela de 30 pregões e 32 unidades. Isso sugere que, para esta base, uma janela mais curta generalizou melhor do que arquiteturas maiores. A melhor RNN precisou de uma janela de 60 pregões e 96 unidades, mas ainda ficou atrás da LSTM, o que reforça a vantagem da arquitetura LSTM para essa série.

Como preços de ações são ruidosos e sujeitos a eventos externos, esses resultados devem ser interpretados como desempenho experimental no recorte histórico usado, não como garantia de acerto futuro. O ideal é reexecutar o treinamento periodicamente e comparar novamente as métricas em dados mais recentes.
