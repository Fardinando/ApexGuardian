# Tutorial Completo — ApexGuardian do Zero

## Índice

1. [Criar Conta no Hugging Face](#1-criar-conta-no-hugging-face)
2. [Criar o Space do Ollama](#2-criar-o-space-do-ollama)
3. [Configurar o Ping](#3-configurar-o-ping)
4. [Criar Bot no Telegram](#4-criar-bot-no-telegram)
5. [Conseguir Token da Vercel](#5-conseguir-token-da-vercel)
6. [Conseguir Token do GitHub](#6-conseguir-token-do-github)
7. [Conseguir Chave da Groq (fallback)](#7-conseguir-chave-da-groq-fallback)
8. [Deploy do ApexGuardian no Render](#8-deploy-do-apexguardian-no-render)
9. [Configurar Webhook do Telegram](#9-configurar-webhook-do-telegram)
10. [Verificar se Tudo Funcionou](#10-verificar-se-tudo-funcionou)
11. [Manutenção](#11-manutenção)

---

## 1. Criar Conta no Hugging Face

1. Acesse [huggingface.co/join](https://huggingface.co/join)
2. Preencha: **Email**, **Username**, **Senha**
3. Confirme o email
4. ✅ Pronto — você tem uma conta gratuita

---

## 2. Criar o Space do Ollama

### 2.1 Acessar o criador de Spaces

1. Vá em [huggingface.co/new-space](https://huggingface.co/new-space)
2. Preencha:

| Campo | Valor |
|-------|-------|
| **Space Name** | `apexguardian-ollama` |
| **License** | MIT |
| **SDK** | Docker |
| **Docker Template** | (deixe em branco — usaremos Dockerfile customizado) |
| **Space Hardware** | CPU free |
| **Space Type** | Public |

3. Clique em **Create Space**

### 2.2 Fazer upload dos arquivos

Você tem duas opções:

**Opção A — Via interface web (mais fácil):**

1. Dentro do Space, vá na aba **Files**
2. Clique em **Add file** > **Upload files**
3. Faça upload dos 3 arquivos da pasta `huggingface-space/` do ApexGuardian:

| Arquivo | Descrição |
|---------|-----------|
| `Dockerfile` | Define o container com Ollama + llama3.1 |
| `entrypoint.sh` | Script que inicia o Ollama e baixa o modelo |
| `README.md` | Metadados do Space (configura o `app_port: 7860`) |

4. Role até o final, escreva "Initial setup" no commit message
5. Clique em **Commit directly to main**

**Opção B — Via script (se tiver Git no PC):**

```bash
# No diretório do ApexGuardian
bash scripts/setup_hf_space.sh
```

### 2.3 Aguardar o build

1. Vá na aba **Builder** ou **Container** do Space
2. Você verá os logs em tempo real:
   ```
   Step 1/7 : FROM ollama/ollama:latest
   Step 2/7 : RUN apt-get install ...
   ...
   ```
3. A primeira vez leva de **3 a 5 minutos**
4. No final, o Ollama começa a baixar o modelo `llama3.1` (~4.7GB)
5. Espere mais **3 a 5 minutos** para o download terminar
6. ✅ Quando terminar, o log mostrará `Modelo pronto!`

### 2.4 Descobrir a URL do seu Space

A URL segue o padrão:

```
https://SEU-USERNAME-apexguardian-ollama.hf.space
```

Exemplo: se seu username é `joaosilva`, a URL é:
```
https://joaosilva-apexguardian-ollama.hf.space
```

### 2.5 Testar

```bash
curl https://SEU-USERNAME-apexguardian-ollama.hf.space/api/tags
```

Deve retornar algo como:
```json
{"models":[{"name":"llama3.1:latest",...}]}
```

---

## 3. Configurar o Ping

O Hugging Face Space grátis **dorme** após 48h sem atividade. Para manter o Ollama sempre pronto, você precisa pingar a URL a cada 30 minutos.

### Se você já tem um monitor de sites (ping):

Adicione no seu monitor:

| Campo | Valor |
|-------|-------|
| **URL** | `https://SEU-USERNAME-apexguardian-ollama.hf.space/api/tags` |
| **Intervalo** | 30 minutos |
| **Tipo** | GET |
| **Timeout** | 30 segundos |

### Se NÃO tem monitor:

Use o [UptimeRobot](https://uptimerobot.com) (grátis):

1. Crie conta em [uptimerobot.com](https://uptimerobot.com)
2. Clique em **Add New Monitor**
3. Preencha:

| Campo | Valor |
|-------|-------|
| **Monitor Type** | HTTP(s) |
| **Friendly Name** | Ollama ApexGuardian |
| **URL (or IP)** | `https://SEU-USERNAME-apexguardian-ollama.hf.space/api/tags` |
| **Monitoring Interval** | 30 minutes |

4. Clique **Create Monitor**

✅ Agora o Ollama nunca vai dormir.

---

## 4. Criar Bot no Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Envie o comando:
```
/newbot
```
3. Responda as perguntas:
   - **Nome do bot:** `ApexGuardian` (ou qualquer nome)
   - **Username do bot:** `apexguardian_bot` (precisa terminar com `bot`)

4. O BotFather vai responder com:

```
Use este token para acessar a API HTTP:
1234567890:ABCdefGHIjklmNOPqrstUVwxyz
```

5. **Copie o token** (salve em um bloco de notas)

### 4.1 Descobrir seu ID do Telegram

1. No Telegram, procure por **@userinfobot**
2. Envie `/start`
3. O bot responderá com seu ID:
```
Id: 123456789
```

4. **Anote este número** (salve junto com o token)

---

## 5. Conseguir Token da Vercel

1. Acesse [vercel.com/account/tokens](https://vercel.com/account/tokens)
2. Clique em **Create Token**
3. Preencha:

| Campo | Valor |
|-------|-------|
| **Name** | ApexGuardian |
| **Scope** | Full Account |

4. Clique **Create**
5. **Copie o token** (começa com algo como `QmX...`)

### 5.1 Descobrir o Project ID do ApexEnem

1. Acesse o [Dashboard da Vercel](https://vercel.com)
2. Clique no projeto **ApexEnem**
3. Vá em **Settings** > **General**
4. Role até **Project ID**
5. **Copie o ID** (começa com `prj_...`)

---

## 6. Conseguir Token do GitHub

1. Acesse [github.com/settings/tokens](https://github.com/settings/tokens)
2. Clique em **Generate new token (classic)**
3. Marque as permissões:

- [x] `repo` (Full control of private repositories)

4. Clique em **Generate token**
5. **Copie o token** (começa com `ghp_...`)

---

## 7. Conseguir Chave da Groq (fallback)

1. Acesse [console.groq.com/keys](https://console.groq.com/keys)
2. Crie uma conta (Google ou email)
3. Clique em **Create API Key**
4. **Copie a chave** (começa com `gsk_...`)

---

## 8. Deploy do ApexGuardian no Render

### 8.1 Criar conta no Render

1. Acesse [dashboard.render.com](https://dashboard.render.com)
2. Clique em **Sign Up** > **GitHub**
3. Autorize o acesso ao repositório `Fardinando/ApexGuardian`

### 8.2 Criar Web Service

1. No dashboard, clique em **New** > **Web Service**
2. Escolha o repositório `Fardinando/ApexGuardian`
3. Preencha:

| Campo | Valor |
|-------|-------|
| **Name** | `apexguardian` (ou outro nome) |
| **Region** | Escolha a mais próxima de você |
| **Branch** | `main` |
| **Runtime** | **Python 3** |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | **Free** |

### 8.3 Adicionar Variáveis de Ambiente

Role até **Environment Variables** e adicione cada uma:

| Variável | Valor | Exemplo |
|----------|-------|---------|
| `TELEGRAM_BOT_TOKEN` | Token do @BotFather | `1234567890:ABCdefGHIjklmNOPqrstUVwxyz` |
| `ALLOWED_TELEGRAM_USER_ID` | Seu ID do Telegram | `123456789` |
| `VERCEL_TOKEN` | Token da Vercel | `QmXabc123...` |
| `VERCEL_PROJECT_ID` | Project ID do ApexEnem | `prj_xxxxxx` |
| `GITHUB_TOKEN` | Token do GitHub | `ghp_xxxxxx` |
| `REPO_URL` | URL do repositório ApexEnem | `https://github.com/Fardinando/ApexEnem.git` |
| `OLLAMA_HOST` | URL do seu HF Space | `https://joaosilva-apexguardian-ollama.hf.space` |
| `OLLAMA_MODEL` | Modelo Ollama | `llama3.1` |
| `OLLAMA_TIMEOUT` | Timeout em segundos | `30` |
| `AI_API_KEY` | Chave da Groq (fallback) | `gsk_xxxxxx` |
| `AI_API_BASE_URL` | URL da API Groq | `https://api.groq.com/openai/v1` |
| `AI_MODEL` | Modelo de fallback | `llama3-8b-8192` |
| `ADMIN_USER` | Login do admin | `supreme` |
| `ADMIN_PASS` | **SENHA FORTE** (mínimo 12 caracteres) | `UmaSenhaBemForte123!` |
| `SESSION_SECRET` | 64 caracteres aleatórios | `a1b2c3d4e5f6...` (64 chars) |

> **Dica para SESSION_SECRET:** Gere uma string aleatória no terminal:
> ```bash
> # Linux/Mac:
> openssl rand -hex 32
> # Windows PowerShell:
> -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | % {[char]$_})
> ```

### 8.4 Finalizar

1. Clique em **Create Web Service**
2. O Render vai fazer o build automaticamente (leva 2-3 minutos)
3. Acompanhe os logs na aba **Logs**
4. ✅ Quando terminar, o Render mostra: `Your service is live 🎉`

### 8.5 Descobrir a URL do seu app

A URL será:
```
https://apexguardian.onrender.com
```

---

## 9. Configurar Webhook do Telegram

O Telegram precisa saber para onde enviar as mensagens dos usuários.

Abra o terminal e execute:

```bash
curl -F "url=https://apexguardian.onrender.com/webhook/telegram" \
  https://api.telegram.org/bot<SEU_TELEGRAM_TOKEN>/setWebhook
```

Substitua:
- `apexguardian.onrender.com` pela URL do SEU app no Render
- `<SEU_TELEGRAM_TOKEN>` pelo token que o BotFather deu

### Testar o webhook

Abra o Telegram, procure pelo seu bot, envie `/start`

Seu bot deve responder com:
```
🛡️ ApexGuardian ativo!
```

Se não responder, verifique:

```bash
curl https://api.telegram.org/bot<SEU_TELEGRAM_TOKEN>/getWebhookInfo
```

Deve mostrar:
```json
{"ok":true,"result":{"url":"https://apexguardian.onrender.com/webhook/telegram","pending_update_count":0}}
```

---

## 10. Verificar se Tudo Funcionou

### 10.1 Testar o Health Check

```bash
curl https://apexguardian.onrender.com/health
```

Resposta esperada:
```json
{"status":"ok","service":"apexguardian","version":"1.0.0"}
```

### 10.2 Acessar o Painel Admin

1. Abra no navegador: `https://apexguardian.onrender.com/admin`
2. Faça login com:
   - **Usuário:** `supreme`
   - **Senha:** a que você colocou em `ADMIN_PASS`
3. Clique em **Sistema** no menu
4. Verifique os status:
   - 🟢 **Ollama** — deve mostrar ✅ se o HF Space está respondendo
   - 🟡 **Fallback** — deve mostrar ✅ por causa da chave Groq

### 10.3 Testar uma denúncia manual

```bash
curl -X POST https://apexguardian.onrender.com/webhook/report \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Erro ao carregar dashboard: Cannot read properties of undefined",
    "user_id_anon": "test_user_123",
    "timestamp_frontend": 1800000000
  }'
```

Se tudo estiver funcionando, você receberá uma notificação no Telegram nos próximos segundos.

---

## 11. Manutenção

### Ver logs do Render

```
Dashboard Render > Seu Web Service > Logs
```

### Ver logs do Ollama (HF Space)

```
huggingface.co > Seu Space > Container > Logs
```

### Ver status do sistema

```
Telegram: /status
Painel Admin: /admin/system
```

### Atualizar o modelo Ollama

Se quiser mudar o modelo, edite o `entrypoint.sh` no HF Space:

```
ollama pull llama3.2  # modelo mais novo (3B)
```

E no .env do Render, atualize `OLLAMA_MODEL=llama3.2`

### Se o Ollama parar de responder

1. Verifique se o HF Space está **Running** (não dormindo)
2. Verifique o ping no UptimeRobot
3. Force um restart no HF Space: aba **Settings** > **Restart Space**
4. Se nada funcionar, o **fallback Groq** assume automaticamente enquanto você resolve

---

## Checklist Final

- [ ] Conta no Hugging Face criada
- [ ] Space `apexguardian-ollama` rodando
- [ ] Ping configurado (UptimeRobot ou outro)
- [ ] Bot Telegram criado + token salvo
- [ ] Token Vercel + Project ID salvos
- [ ] Token GitHub salvo
- [ ] Chave Groq salva
- [ ] Render Web Service criado
- [ ] Variáveis de ambiente configuradas
- [ ] Webhook do Telegram configurado
- [ ] `/admin` acessível
- [ ] Status do sistema mostra ✅ Ollama e ✅ Fallback
