# ApexGuardian 🛡️

Assistente automatizado de gerenciamento de bugs para o [ApexEnem](https://github.com/Fardinando/ApexEnem).

Recebe denúncias de usuários, monitora logs da Vercel, pesquisa soluções com IA (Ollama + fallback Groq), e gerencia todo o ciclo de correção — da detecção ao deploy — sempre com aprovação humana via Telegram.

**Custo:** Zero (Hugging Face Space + Groq API free tier + Render free tier)

---

## 📋 Funcionalidades

- **Pipeline de Denúncia**: Usuários reportam erros → ApexGuardian correlaciona com logs da Vercel
- **Monitoramento de Logs**: Polling automático a cada 3 minutos na API da Vercel
- **Gatilho por Volume**: Erros arquivados com >10 usuários (14d) ou >30 usuários (60d) são reinvestigados
- **Pesquisa Web**: Busca soluções no DuckDuckGo automaticamente
- **Análise com IA**: Ollama (primário) + fallback automático para Groq API se Ollama estiver offline
- **Loop de Feedback no Telegram**: Você aprova, rejeita ou pede refação dos planos
- **Deploy Automático**: Correção → branch → preview → aprovação → produção
- **Design Guard**: Proteção absoluta contra alterações de design/CSS
- **Painel Admin**: Dashboard completo com gráficos, RBAC (supreme, operator, analyst, basic)
- **Deploy 100% gratuito**: Oracle Cloud (Ollama) + Render (app) + Groq (fallback)

---

## 🏗️ Arquitetura

```
┌──────────────┐     POST /webhook/report     ┌──────────────────┐
│  ApexEnem     │ ──────────────────────────►  │  ApexGuardian    │
│  (Vercel)     │                              │  (Render/Local)  │
└──────────────┘                              └────────┬─────────┘
                                                       │
              ┌─────────────────────────────────────────┤
              │            │              │            │
              ▼            ▼              ▼            ▼
          SQLite      Ollama ──fallback── DuckDuckGo  Vercel API
          (dados)  (HF Space)   ▶   (pesquisa)    (logs)
                         │       Groq API
                         │           (grátis)
              └──────────┴─────────────────────────────────┘
                                 │
                                 ▼
                          Telegram Bot ↔ Você (dev)
```

---

## 🚀 Setup Passo a Passo

### Pré-requisitos

- [x] Conta no [Oracle Cloud](https://cloud.oracle.com) (cartão de crédito p/ verificação, não cobra)
- [x] Conta no [Render](https://render.com) (GitHub login)
- [x] Conta no [Groq](https://console.groq.com/keys) (fallback grátis)
- [x] Bot no Telegram [@BotFather](https://t.me/BotFather)
- [x] Token da Vercel [vercel.com/account/tokens](https://vercel.com/account/tokens)
- [x] Token do GitHub com permissão de push

---

### Passo 1: Provisionar Ollama no Hugging Face Space

1. Acesse [huggingface.co/new-space](https://huggingface.co/new-space)
2. Configure:

| Campo | Valor |
|-------|-------|
| **Space Name** | `apexguardian-ollama` |
| **License** | MIT |
| **SDK** | Docker |
| **Hardware** | CPU (free — 2 vCPU, 16GB RAM) |
| **Space Type** | Public |

3. Faça upload dos arquivos da pasta `huggingface-space/`:
   - `Dockerfile`
   - `entrypoint.sh`
   - `README.md`

   Ou use o script automático:

```bash
bash scripts/setup_hf_space.sh
```

4. O Ollama inicia automaticamente e baixa o modelo `llama3.1` (~5 min na primeira vez)

5. Verifique se está pronto:

```bash
curl https://SEU-USER-apexguardian-ollama.hf.space/api/tags
```

6. **Configure o ping** (HF Space dorme após 48h sem uso):
   - Adicione no seu monitor de uptime a URL:
   ```
   https://SEU-USER-apexguardian-ollama.hf.space/api/tags
   ```
   - Intervalo: a cada **30 minutos**

---

### Passo 2: Deploy do ApexGuardian no Render

1. Faça fork/clone deste repositório
2. Conecte no [Render Dashboard](https://dashboard.render.com) > New Web Service
3. Escolha o repositório `Fardinando/ApexGuardian`
4. Configurações:

| Campo | Valor |
|-------|-------|
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Health Check** | `/health` |
| **Plan** | **Free** |

5. Adicione as variáveis de ambiente (aba Environment):

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `TELEGRAM_BOT_TOKEN` | Token do @BotFather | `123456:ABC-DEF1234` |
| `ALLOWED_TELEGRAM_USER_ID` | Seu ID no Telegram | `123456789` |
| `VERCEL_TOKEN` | Token da Vercel | `abc123...` |
| `VERCEL_PROJECT_ID` | ID do projeto ApexEnem na Vercel | `prj_xxxxxx` |
| `GITHUB_TOKEN` | Token do GitHub com permissão de push | `ghp_xxxxxx` |
| `REPO_URL` | URL do repositório ApexEnem | `https://github.com/Fardinando/ApexEnem.git` |
| `OLLAMA_HOST` | URL do Ollama no Oracle Cloud | `https://ollama.seusite.com` |
| `OLLAMA_MODEL` | Modelo Ollama | `llama3.1` |
| `AI_API_KEY` | Chave Groq (fallback) | `gsk_xxxxxx` |
| `ADMIN_USER` | Login do admin supreme | `supreme` |
| `ADMIN_PASS` | Senha do admin supreme | `escolha_uma_senha_forte` |
| `SESSION_SECRET` | String aleatória para sessões | `64-caracteres-aleatorios` |

---

### Passo 3: Configurar Webhook do Telegram

```bash
curl -F "url=https://SEU-APP.onrender.com/webhook/telegram" \
  https://api.telegram.org/bot<SEU_TOKEN>/setWebhook
```

---

## 🔧 Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas |
| `/status` | Status atual do sistema |
| `/help` | Lista de comandos |

**Responda a notificações com:**

| Resposta | Ação |
|----------|------|
| ✅ "Ok" / "Aprovado" | Publica em produção |
| ❌ "Não gostei" / "Refaça" | Gera novo plano (max 3x) |
| 🔄 "Reverte" / "Deu problema" | Rollback + deleta branch |

---

## 👥 Roles do Painel Admin

Acesse: `https://SEU-APP.onrender.com/admin`

| Role | Acesso |
|------|--------|
| **Supreme** | Tudo: gerenciar admins, deletar erros, forçar workers |
| **Operator** | Corrigir erros, deploy preview, aprovar produção, reverter |
| **Analyst** | Investigar erros, adicionar manualmente, ver activity logs |
| **Basic** | Visualizar dashboard e erros (leitura) |

---

## 🛡️ Design Guard

O ApexGuardian **NUNCA** altera design, CSS, layout ou estilo visual. A proteção opera em 3 camadas:

1. **Prompt**: A IA recebe instrução explícita para não modificar design
2. **File Blocklist**: Arquivos `.css`, `tailwind.config.*`, `public/*.svg` etc. são protegidos
3. **Diff Validation**: Antes do commit, o diff é verificado contra padrões de design

Se uma correção tentar alterar design, ela é **bloqueada** e o erro é registrado.

---

## 🔄 Fallback Automático

```
Ollama online? ──Sim──► Usa Ollama (Oracle Cloud)
     │
     ▼ Não
Groq online? ────Sim──► Usa Groq API (grátis, 30 req/min)
     │
     ▼ Não
Retorna erro amigável
```

- `OLLAMA_HOST` vazio → usa só fallback
- `AI_API_KEY` vazio → usa só Ollama
- Ambos configurados → Ollama primeiro, fallback automático

---

## 📁 Estrutura do Projeto

```
apexguardian/
├── main.py                    # FastAPI app + workers
├── requirements.txt           # Dependências Python
├── Dockerfile                 # Deploy containerizado
├── .env.example               # Template de variáveis
├── huggingface-space/        # Arquivos do HF Space (Ollama)
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── README.md
├── scripts/
│   └── setup_hf_space.sh     # Setup automático do HF Space
├── app/
│   ├── config.py              # Configurações (pydantic-settings)
│   ├── database.py            # SQLite (6 tabelas + CRUD)
│   ├── schemas.py             # Pydantic models
│   ├── auth.py                # RBAC + autenticação
│   ├── routers/
│   │   ├── health.py          # GET /health
│   │   ├── reports.py         # POST /webhook/report
│   │   ├── telegram_webhook.py# POST /webhook/telegram
│   │   └── admin.py           # 25+ rotas admin
│   ├── services/
│   │   ├── telegram.py        # Bot Telegram
│   │   ├── vercel_logs.py     # Vercel API
│   │   ├── ai_client.py       # IA client (Ollama + fallback Groq)
│   │   ├── search.py          # DuckDuckGo search
│   │   ├── pipeline.py        # Orquestrador
│   │   └── git_ops.py         # Git + deploy + Design Guard
│   ├── workers/
│   │   ├── log_poller.py      # Polling 3min
│   │   └── volume_checker.py  # Thresholds 1h
│   └── templates/admin/       # Jinja2 templates
├── data/                      # SQLite DB
└── README.md
```

---

## 📊 Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Status do serviço |
| POST | `/webhook/report` | Recebe denúncia do frontend |
| POST | `/webhook/telegram` | Webhook do Telegram |
| GET | `/admin` | Dashboard |
| GET | `/admin/errors` | Lista de erros |
| GET | `/admin/errors/{id}` | Detalhe do erro |
| GET | `/admin/admins` | Gerenciar admins (supreme) |
| GET | `/admin/activity` | Activity log |
| GET | `/admin/system` | Status do sistema |

---

## 🔒 Segurança

- Senhas armazenadas com **bcrypt**
- Sessões com **token aleatório** (24h de expiração)
- RBAC com **4 níveis de acesso**
- Toda ação admin é **logada**
- Ações críticas notificam o **supreme**
- **Design Guard** impede alterações de layout
- Modo **manutenção** pausa workers

---

## 📝 Licença

MIT
