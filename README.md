# 🎬 Automação de Vídeos com Agnes AI / Pavo AI + OpenRouter + Telegram

Automação completa para geração autônoma de vídeos de **12 segundos, em 720p e proporção vertical 9:16** utilizando a API da **Agnes AI / Pavo AI** (`agnes-video-2.5-flash`), geração de prompts inteligentes via **OpenRouter** (com fallback entre modelos 100% gratuitos) e envio automático dos vídeos prontos para o **Telegram**.

O projeto funciona tanto **localmente** no computador quanto de forma 100% autônoma na nuvem através do **GitHub Actions**.

---

## 🚀 Arquitetura e Fluxo do Pipeline

```
[OpenRouter (Modelos Free)] 
         │
         ▼ (Gera Prompt Visual Rico em JSON)
[Agnes AI / Pavo AI (agnes-video-2.5-flash)]
         │
         ▼ (POST /v1/videos -> Polling /v1/agnesapi -> Download MP4 720p 9:16 de 12s)
[Telegram Bot API]
         │
         ▼ (Envia vídeo formatado com legenda rica para o chat/canal)
```

1. **Geração de Prompt (`scripts/generate_prompt.py`)**: Conecta ao OpenRouter e consulta uma lista ordenada de modelos gratuitos (Gemma 4, Nemotron Ultra, Liquid, Laguna, Inkling) até obter um prompt cinematográfico altamente descritivo para vídeo.
2. **Geração de Vídeo (`scripts/create_video.py`)**: Submete a requisição para `https://apihub.agnes-ai.com/v1/videos` com parâmetros otimizados para o modelo `agnes-video-2.5-flash`:
   - `seconds`: `"12"`
   - `size`: `"720P"`
   - `aspect_ratio`: `"9:16"`
   - `mode`: `"text"`
   - Polling automático e tolerância a fila cheia (503) e limites de requisição (429 - 1 requisição a cada 2 minutos).
3. **Envio Telegram (`scripts/send_telegram.py`)**: Envia o arquivo MP4 diretamente para o bot do Telegram com legenda contendo título, descrição, duração, resolução e tags.

---

## ⚙️ Estrutura do Projeto

```
CRIAÇÃO VIDEOS PAVO/
├── .github/
│   └── workflows/
│       └── video_pipeline.yml     # Workflow automático do GitHub Actions
├── config/
│   ├── master_prompt.txt          # Prompt mestre para guiar os temas dos vídeos
│   ├── models.json                # Lista de modelos gratuitos do OpenRouter com fallback
│   └── settings.json              # Configurações globais de vídeo, API e Telegram
├── scripts/
│   ├── generate_prompt.py         # Criação de prompt via IA de texto
│   ├── create_video.py            # Criação, polling e download do vídeo Agnes/Pavo
│   ├── send_telegram.py           # Envio do vídeo final para o Telegram
│   └── run_pipeline.py            # Orquestrador local para rodar tudo em 1 comando
├── output/                        # Diretório onde prompts e vídeos baixados são salvos
│   ├── prompts/
│   └── videos/
├── .env                           # Suas chaves de API locais (não versionado)
├── .env.example                   # Template de variáveis
├── requirements.txt               # Dependências Python
└── README.md                      # Documentação oficial
```

---

## 🔑 Configuração de Secrets no GitHub

Para que o GitHub Actions rode no seu repositório na nuvem, adicione os seguintes **Repository Secrets** no GitHub:

1. Acesse o seu repositório no GitHub: `Settings` → `Secrets and variables` → `Actions`.
2. Clique em **New repository secret** e adicione:

| Nome do Secret | Descrição |
| :--- | :--- |
| `OPENROUTER_API_KEY` | Chave de API do OpenRouter (`sk-or-v1-...`) |
| `AGNES_API_KEY` | Chave de API do Agnes AI / Pavo AI (`sk-I9rC...`) |
| `TELEGRAM_BOT_TOKEN` | Token do Bot do Telegram |
| `TELEGRAM_CHAT_ID` | Seu Chat ID ou ID do Canal no Telegram |

*(Opcional: `AGNES_BASE_URL` caso deseje alterar a URL base `https://apihub.agnes-ai.com/v1`).*

---

## 💻 Como Rodar Localmente

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar o `.env`
O arquivo `.env` já está pré-configurado na raiz do projeto com as suas chaves e tokens detectados.

### 3. Executar o pipeline completo
```bash
python scripts/run_pipeline.py
```

### 4. Executar com prompt personalizado (manual)
```bash
python scripts/run_pipeline.py --prompt "Drone em alta velocidade sobrevoando uma metrópole futurista com neon em estilo cyberpunk" --titulo "Metrópole Cyberpunk 2099"
```

---

## ☁️ Como Rodar no GitHub Actions

1. Abra a aba **Actions** no seu repositório no GitHub.
2. Selecione o workflow **🎬 Pipeline de Vídeos - Agnes AI / Pavo AI**.
3. Clique no botão **Run workflow**:
   - **Prompt visual personalizado**: (Opcional) Digite um prompt específico ou deixe em branco para a IA gerar aleatoriamente.
   - **Título do vídeo**: (Opcional) Título para a legenda do Telegram.
   - **Enviar vídeo para o Telegram?**: `true` ou `false`.
4. O GitHub Actions executará as 3 etapas sequencialmente e você receberá o vídeo pronto no seu Telegram!

---

## 🎨 Como Personalizar o Prompt Mestre

Quando quiser direcionar o estilo dos vídeos para um nicho específico (ex: temas bíblicos, curiosidades, memes, histórias épicas), basta abrir e editar o arquivo:

👉 `config/master_prompt.txt`

Tudo o que você definir nesse arquivo será utilizado pelos modelos gratuitos da OpenRouter para inventar cenas surpreendentes e inéditas a cada execução!
