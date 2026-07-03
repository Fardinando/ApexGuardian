# ApexGuardian 🛡️

Assistente automatizado de gerenciamento de bugs para o [ApexEnem](https://github.com/Fardinando/ApexEnem).

Recebe denúncias de usuários, monitora logs da Vercel, pesquisa soluções com IA local (Ollama), e gerencia todo o ciclo de correção — da detecção ao deploy — sempre com aprovação humana via Telegram.

**Custo:** Zero (exceto sua máquina local para o Ollama)

---

## 📋 Funcionalidades

- **Pipeline de Denúncia**: Usuários reportam erros com screenshot → ApexGuardian correlaciona com logs da Vercel
- **Monitoramento de Logs**: Polling automático a cada 3 minutos na API da Vercel
- **Gatilho por Volume**: Erros arquivados com >10 usuários (14d) ou >30 usuários (60d) são reinvestigados
- **Pesquisa Web**: Busca soluções no DuckDuckGo automaticamente
- **Análise com IA Local**: Ollama (llama3.1) gera diagnóstico, plano de correção e código corrigido
- **Loop de Feedback no Telegram**: Você aprova, rejeita ou pede refação dos planos
- **Deploy Automático**: Correção → branch → preview → aprovação → produção
- **Design Guard**: Proteção absoluta contra alterações de design/CSS
- **Painel Admin**: Dashboard completo com gráficos, listas, RBAC (supreme, operator, analyst, basic)

---

## 🏗️ Arquitetura

```
┌──────────────┐     POST /webhook/report     ┌──────────────────┐
│  ApexEnem     │ ──────────────────────────►  │  ApexGuardian    │
│  (Vercel)     │                              │  (Render/Local)  │
└──────────────┘                              └────────┬─────────┘
                                                       │
              ┌────────────────────────────────────────┤
              │            │              │            │
              ▼            ▼              ▼            ▼
         SQLite        Ollama         DuckDuckGo    Vercel API
         (dados)     (IA local)      (pesquisa)    (logs)
              │            │                          
              └────────────┼─────────────────────────┘
                           │
                           ▼
                    Telegram Bot ↔ Você (dev)
```

---

## 🚀 Setup Rápido

### Pré-requisitos

- Python 3.11+
- [Ollama](https://ollama.com) (para IA local)
- Conta no Telegram + [@BotFather](https://t.me/BotFather)
- Token da Vercel ([vercel.com/account/tokens](https://vercel.com/account/tokens))
- Token do GitHub com permissão de push

### 1. Clone e configure

```bash
git clone https://github.com/Fardinando/ApexGuardian.git
cd ApexGuardian
cp .env.example .env
# Edite .env com suas credenciais
```

### 2. Instale dependências

```bash
pip install -r requirements.txt
```

### 3. Setup do Ollama

```bash
chmod +x setup_ollama.sh
./setup_ollama.sh
```

O script instala:
- Ollama + modelo llama3.1
- Cloudflare Tunnel (para expor o Ollama)

### 4. Execute

```bash
uvicorn main:app --reload --port 8000
```

### 5. Configure o Webhook do Telegram

```bash
curl -F "url=https://SEU-URL/webhook/telegram" \
  https://api.telegram.org/bot<SEU_TOKEN>/setWebhook
```

---

## 🌐 Deploy no Render

1. Crie um Web Service no [Render](https://render.com)
2. Conecte ao repositório `Fardinando/ApexGuardian`
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Health Check Path:** `/health`
6. Adicione todas as variáveis do `.env` no painel do Render

---

## 🎯 Integração com o Frontend ApexEnem

No seu frontend React, adicione um botão "Reportar Erro" que envia:

```typescript
await fetch("https://SEU-APEXGUARDIAN.onrender.com/webhook/report", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    screenshot_base64: "data:image/png;base64,...",
    description: "Descrição do erro pelo usuário",
    timestamp_frontend: Date.now(),
    user_id_anon: hash_anonimo_do_usuario  // SHA256 do user.id
  })
});
```

---

## 🔧 Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas |
| `/status` | Status atual do sistema |
| `/help` | Lista de comandos |

Responda a notificações com:

| Resposta | Ação |
|----------|------|
| ✅ "Ok" / "Aprovado" | Publica em produção |
| ❌ "Não gostei" / "Refaça" | Gera novo plano (max 3x) |
| 🔄 "Reverte" / "Deu problema" | Rollback + deleta branch |

---

## 👥 Roles do Painel Admin

| Role | Acesso |
|------|--------|
| **Supreme** | Tudo: gerenciar admins, deletar erros, forçar workers, modo manutenção |
| **Operator** | Corrigir erros, deploy preview, aprovar produção, reverter |
| **Analyst** | Investigar erros, adicionar manualmente, ver activity logs |
| **Basic** | Visualizar dashboard e erros (leitura) |

Acesse: `https://SEU-DOMINIO/admin`

---

## 🛡️ Design Guard

O ApexGuardian **NUNCA** altera design, CSS, layout ou estilo visual. A proteção opera em 3 camadas:

1. **Prompt**: Ollama recebe instrução explícita para não modificar design
2. **File Blocklist**: Arquivos `.css`, `tailwind.config.*`, `public/*.svg` etc. são protegidos
3. **Diff Validation**: Antes do commit, o diff é verificado contra padrões de design

Se uma correção tentar alterar design, ela é **bloqueada** e o erro é registrado.

---

## 📁 Estrutura do Projeto

```
apexguardian/
├── main.py                    # FastAPI app + workers
├── requirements.txt           # Dependências Python
├── Dockerfile                 # Deploy containerizado
├── .env.example               # Template de variáveis
├── setup_ollama.sh            # Script de setup do Ollama
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
│   │   ├── ollama.py          # Ollama client
│   │   ├── search.py          # DuckDuckGo search
│   │   ├── pipeline.py        # Orquestrador
│   │   └── git_ops.py         # Git + deploy
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
| GET | `/admin/activity` | Activity log (supreme/analyst) |
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
