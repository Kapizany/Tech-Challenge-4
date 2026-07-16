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
- salva `models/rnn.keras` e `models/lstm.keras` somente quando o novo RMSE de teste for melhor que o modelo já salvo;
- salva scalers/metadados em `models/rnn_bundle.joblib` e `models/lstm_bundle.joblib`;
- atualiza `reports/metrics.json`, `reports/best_model.json` e `reports/recurrent_architecture_comparison.json`.

Se já existir um modelo salvo, o treinamento novo é comparado contra o RMSE registrado em `reports/metrics.json`. O artefato anterior é preservado quando o novo treino não melhora a métrica de teste. Se algum artefato esperado estiver faltando, o script salva o novo modelo mesmo que a métrica não tenha melhorado, para recompor o pacote de inferência.

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
- `POST /collect`: coleta OHLCV por ticker/período, salva CSV local e opcionalmente envia ao S3.
- `GET /models`: lista modelos disponíveis e caminhos esperados dos artefatos.
- `GET /data/tickers`: lista tickers com dados locais ou no S3.
- `GET /data/{symbol}`: lista arquivos de dados disponíveis para um ticker.
- `POST /predict?model=best`: previsão do próximo fechamento.
- `GET /metrics`: métricas Prometheus.

A API registra tracing de requisições em JSON no stdout, que no ECS é enviado ao CloudWatch Logs. Por padrão, `/health` e `/metrics` são ignorados para reduzir ruído. Cada chamada inclui `request_id`, método, path, query params, status code, duração em milissegundos, IP do client e, quando habilitado, body de request/response truncado.

Variáveis de tracing:

| Variável | Padrão | Uso |
| --- | --- | --- |
| `TRACE_REQUESTS` | `true` | Liga/desliga o tracing HTTP. |
| `TRACE_LOG_BODIES` | `true` | Liga/desliga logging de bodies. |
| `TRACE_MAX_BODY_CHARS` | `4000` | Limite de caracteres para request/response body. |
| `TRACE_EXCLUDED_PATHS` | `/health,/metrics` | Paths ignorados pelo tracing, separados por vírgula. |

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

Exemplo de coleta:

```bash
curl -X POST "http://localhost:8000/collect" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "PETR4.SA",
    "start": "2024-01-01",
    "end": "2024-07-20",
    "upload_s3": true
  }'
```

Com `DATA_S3_BUCKET=capizani-techchallenge-4` e `DATA_S3_PREFIX=""`, a coleta salva dados agrupados por ticker em:

```text
s3://capizani-techchallenge-4/data/raw/PETR4.SA/PETR4.SA.csv
```

Os modelos existentes continuam no layout atual:

```text
s3://capizani-techchallenge-4/ml-data/models/lstm.keras
s3://capizani-techchallenge-4/ml-data/models/lstm_bundle.joblib
s3://capizani-techchallenge-4/ml-data/models/rnn.keras
s3://capizani-techchallenge-4/ml-data/models/rnn_bundle.joblib
s3://capizani-techchallenge-4/ml-data/reports/best_model.json
s3://capizani-techchallenge-4/ml-data/reports/metrics.json
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

## ECS Fargate

Existe uma task definition base em `infra/ecs-task-definition.json` para rodar a API no ECS Fargate.

Antes de registrar, ajuste:

- `image`: repositório/tag real no ECR;
- `DATA_S3_BUCKET`: bucket dos dados;
- `MODELS_S3_BUCKET`: bucket dos modelos e relatórios, podendo ser o mesmo de `DATA_S3_BUCKET`;
- `DATA_S3_PREFIX` e `MODELS_S3_PREFIX`, se os objetos estiverem dentro de prefixos;
- `taskRoleArn`, se a role atual não tiver permissão `s3:GetObject` e `s3:PutObject` no bucket configurado.

Registrar a task:

```bash
aws ecs register-task-definition \
  --cli-input-json file://infra/ecs-task-definition.json \
  --region us-east-1
```

A task expõe a API na porta `8000` e usa health check em `/health`.

### Terraform

Também existe uma stack Terraform em `infra/terraform/` para criar a infraestrutura AWS principal:

- bucket S3 único para dados, modelos e relatórios;
- repositório ECR;
- cluster ECS Fargate;
- task definition e service;
- Application Load Balancer;
- VPC, subnets públicas, Internet Gateway e security groups;
- CloudWatch Logs;
- roles IAM para ECS;
- role IAM para GitHub Actions publicar imagem no ECR;
- segredo no AWS Secrets Manager com a configuração de bucket/prefixos.

Como usar:

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

Edite `infra/terraform/terraform.tfvars` e depois rode:

- `artifact_bucket_name`: bucket único usado para dados, modelos e relatórios;
- `data_s3_prefix`: prefixo dos arquivos de dados, por exemplo `data`;
- `models_s3_prefix`: prefixo dos modelos e relatórios, por exemplo `ml-data`.

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

Depois do `apply`, copie o output `github_actions_role_arn` e cadastre no GitHub como secret:

```text
AWS_ROLE_TO_ASSUME=<github_actions_role_arn>
```

Scripts auxiliares:

```bash
./scripts/sync_artifacts_to_s3.sh
```

Sincroniza `data/`, `models/` e `reports/` para o bucket configurado em `infra/terraform/terraform.tfvars`. Use depois que o bucket existir. No primeiro setup, isso normalmente significa depois de `terraform apply`; em ambientes já criados, pode rodar após `terraform init`.

```bash
./scripts/cleanup_aws_before_destroy.sh
```

Esvazia o bucket S3 versionado e remove imagens do repositório ECR antes de `terraform destroy`:

```bash
./scripts/cleanup_aws_before_destroy.sh
cd infra/terraform
terraform destroy
cd ../..
./scripts/post_destroy_cleanup.sh
```

O `post_destroy_cleanup.sh` verifica se bucket, ECR, ECS, secret, log group e roles IAM principais não existem mais, e limpa arquivos locais gerados pelo Terraform como `.terraform/`, `.terraform.lock.hcl`, `terraform.tfstate` e backups.

## GitHub Actions

O workflow `.github/workflows/build-and-push-ecr.yml` publica a imagem da API no Amazon ECR sempre que houver push na branch `main`. Ele também pode ser executado manualmente pela aba **Actions** do GitHub.

Imagem publicada:

```text
447798043017.dkr.ecr.us-east-1.amazonaws.com/techchallenge/stock-forecast-api:latest
447798043017.dkr.ecr.us-east-1.amazonaws.com/techchallenge/stock-forecast-api:<commit-sha>
```

Antes de usar, crie no GitHub o secret:

```text
AWS_ROLE_TO_ASSUME
```

Esse secret deve apontar para uma IAM Role que o GitHub Actions possa assumir via OIDC. A role precisa permitir:

- `ecr:GetAuthorizationToken`;
- `ecr:BatchCheckLayerAvailability`;
- `ecr:BatchGetImage`;
- `ecr:CompleteLayerUpload`;
- `ecr:CreateRepository`;
- `ecr:DescribeRepositories`;
- `ecr:InitiateLayerUpload`;
- `ecr:PutImage`;
- `ecr:UploadLayerPart`;
- `ecs:DescribeServices`;
- `ecs:UpdateService`;
- `secretsmanager:GetSecretValue` no secret `stock-forecast-api-prod/runtime-config`.

O workflow lê o secret `stock-forecast-api-prod/runtime-config` no AWS Secrets Manager e exporta como variáveis de ambiente `DATA_S3_BUCKET`, `DATA_S3_PREFIX`, `MODELS_S3_BUCKET` e `MODELS_S3_PREFIX` para os passos seguintes. Depois cria o repositório `techchallenge/stock-forecast-api` caso ele ainda não exista, faz build com o `Dockerfile` do projeto, publica as tags `latest` e SHA do commit, força um novo deployment do serviço `stock-forecast-api-prod-service` no cluster `stock-forecast-api-prod-cluster` e espera o ECS estabilizar.

## Recuperação de Artefatos no S3

Antes de usar dados, modelos ou relatórios, o projeto verifica se os arquivos existem localmente. Se algum arquivo estiver ausente, ele tenta baixar do S3 usando variáveis de ambiente.

Variáveis suportadas:

| Variável | Uso |
| --- | --- |
| `DATA_S3_BUCKET` | Bucket para arquivos em `data/`, como `data/raw/PETR4.SA.csv`. |
| `MODELS_S3_BUCKET` | Bucket para arquivos em `models/` e `reports/`. Pode ser o mesmo de `DATA_S3_BUCKET`. |
| `DATA_S3_PREFIX` | Prefixo opcional para dados. |
| `MODELS_S3_PREFIX` | Prefixo opcional para modelos e relatórios. |
| `AWS_ACCESS_KEY_ID` | Credencial AWS, se necessário no ambiente. |
| `AWS_SECRET_ACCESS_KEY` | Credencial AWS, se necessário no ambiente. |
| `AWS_SESSION_TOKEN` | Token temporário AWS, se necessário. |
| `AWS_DEFAULT_REGION` | Região AWS usada pelo `boto3`. |

Por padrão, a chave no S3 segue o caminho relativo do projeto. Exemplos sem prefixo:

```text
data/raw/PETR4.SA.csv
models/lstm.keras
models/lstm_bundle.joblib
models/rnn.keras
models/rnn_bundle.joblib
reports/best_model.json
reports/metrics.json
reports/recurrent_architecture_comparison.json
```

Com `MODELS_S3_PREFIX=tech-challenge`, por exemplo, o modelo LSTM será buscado em:

```text
s3://$MODELS_S3_BUCKET/tech-challenge/models/lstm.keras
```

Exemplo local com bucket único:

```bash
export DATA_S3_BUCKET=meu-bucket-artifacts
export MODELS_S3_BUCKET=meu-bucket-artifacts
export DATA_S3_PREFIX=
export MODELS_S3_PREFIX=ml-data
export AWS_DEFAULT_REGION=us-east-1

python3 scripts/orchestrate.py --skip-train
```

Exemplo com Docker Compose:

```bash
DATA_S3_BUCKET=meu-bucket-artifacts \
MODELS_S3_BUCKET=meu-bucket-artifacts \
DATA_S3_PREFIX= \
MODELS_S3_PREFIX=ml-data \
AWS_DEFAULT_REGION=us-east-1 \
docker compose up --build
```

Se os modelos existirem, mas os relatórios em `reports/` não existirem, o projeto entra em modo degradado:

- chamadas explícitas como `POST /predict?model=lstm` e `POST /predict?model=rnn` continuam funcionando se os arquivos `.keras` e `_bundle.joblib` existirem;
- `POST /predict?model=best` usa o `reports/best_model.json` quando ele existe;
- se `best_model.json` estiver ausente, `model=best` usa um fallback determinístico: primeiro LSTM, depois RNN, desde que os artefatos estejam completos;
- o orquestrador avisa que os modelos existem, mas que métricas e melhor modelo não podem ser validados até restaurar os reports ou rodar o treinamento novamente.

Para recriar os relatórios com métricas reais, rode novamente:

```bash
python3 scripts/orchestrate.py
```

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

Estatísticas atuais salvas em `reports/metrics.json`:

| Modelo | Melhor arquitetura | Janela | MAE validação | RMSE validação | MAPE validação | MAE teste | RMSE teste | MAPE teste |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LSTM | `lstm_simple_30` | 30 pregões | 0.6155 | 0.8537 | 2.2899% | 0.5492 | 0.7322 | 1.4570% |
| RNN | `rnn_wide_60` | 60 pregões | 0.5953 | 0.7583 | 2.3083% | 0.7777 | 0.9196 | 2.0312% |

A LSTM venceu nas três métricas principais: MAE, RMSE e MAPE. Isso indica que, no conjunto de teste temporal, ela errou menos em média, teve menor penalização para erros maiores e apresentou menor erro percentual.

Uma explicação provável é que a LSTM lida melhor com dependências temporais do que uma RNN clássica. Suas portas internas controlam o que deve ser esquecido, mantido e atualizado na memória, reduzindo o problema de desaparecimento do gradiente e ajudando a capturar padrões úteis sem carregar ruído demais.

Também é relevante que a melhor LSTM foi a arquitetura mais simples, com janela de 30 pregões e 32 unidades. Isso sugere que, para esta base, uma janela mais curta generalizou melhor do que arquiteturas maiores. A melhor RNN precisou de uma janela de 60 pregões e 96 unidades, mas ainda ficou atrás da LSTM, o que reforça a vantagem da arquitetura LSTM para essa série.

Observação: os scripts de treinamento preservam o modelo anterior quando um novo treino não melhora o RMSE de teste salvo. Portanto, se `scripts/train_lstm.py` for executado novamente e o resultado novo for pior ou igual ao LSTM já salvo, `models/lstm.keras`, `models/lstm_bundle.joblib` e `reports/metrics.json` continuam apontando para o melhor LSTM conhecido.

Como preços de ações são ruidosos e sujeitos a eventos externos, esses resultados devem ser interpretados como desempenho experimental no recorte histórico usado, não como garantia de acerto futuro. O ideal é reexecutar o treinamento periodicamente e comparar novamente as métricas em dados mais recentes.
