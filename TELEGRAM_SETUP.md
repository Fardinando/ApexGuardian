# Configurar Telegram — Passo a Passo

---

## 📱 Passo 1 — Criar o Bot

1. Abra o Telegram
2. Pesquise por **@BotFather** (o oficial, com ✅ azul)
3. Envie:
   ```
   /newbot
   ```
4. Ele pergunta o **nome** (qualquer um):
   ```
   ApexGuardian
   ```
5. Ele pergunta o **username** (termina com `bot`):
   ```
   apexguardian_bot
   ```
6. O BotFather responde com:
   ```
   Use this token to access the HTTP API:
   1234567890:ABCdefGHIjklmNOPqrstUVwxyz
   ```
7. **Copie esse token** inteiro (tudo depois de "token:")

---

## 👤 Passo 2 — Descobrir SEU ID

1. No Telegram, pesquise por **@userinfobot**
2. Envie:
   ```
   /start
   ```
3. Ele responde:
   ```
   Id: 123456789
   ```
4. **Anote esse número** (são só números, sem espaços)

---

## 🌐 Passo 3 — Configurar no Render

1. Acesse o painel do **Render** → seu Web Service → **Environment**
2. Adicione (ou corrija) essas duas variáveis:

   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVwxyz
   ALLOWED_TELEGRAM_USER_ID=123456789
   ```

   > O primeiro é o token do @BotFather (letras + números)
   > O segundo é o número do @userinfobot (só números)

3. Salve. O Render vai fazer deploy automático.

---

## 🔗 Passo 4 — Conectar Telegram ao Render (Webhook)

Aguarde o deploy do Render terminar (verde no dashboard), DEPOIS execute:

```bash
curl "https://api.telegram.org/bot1234567890:ABCdefGHIjklmNOPqrstUVwxyz/setWebhook?url=https://apexguardian.onrender.com/webhook/telegram"
```

**Atenção:** Substitua:
- `1234567890:ABCdefGHIjklmNOPqrstUVwxyz` pelo SEU token do Passo 1
- `https://apexguardian.onrender.com` pela URL do SEU app no Render

Para verificar se o webhook está certo:

```bash
curl "https://api.telegram.org/bot1234567890:ABCdefGHIjklmNOPqrstUVwxyz/getWebhookInfo"
```

Resultado esperado:
```json
{"ok":true,"result":{"url":"https://apexguardian.onrender.com/webhook/telegram","pending_update_count":0}}
```

Se `url` estiver vazio, o webhook não foi configurado.

---

## ✅ Passo 5 — Testar

1. Abra o Telegram
2. Entre na conversa com **@apexguardian_bot** (o username que vc criou)
3. Envie:
   ```
   /start
   ```
4. O bot deve responder:
   ```
   🛡️ ApexGuardian ativo!
   ```

---

## ❗ Se não funcionar

| Problema | Causa | Solução |
|----------|-------|---------|
| Bot não responde nada | Webhook não configurado | Executar `setWebhook` |
| Bot responde "Not authenticated" | `ALLOWED_TELEGRAM_USER_ID` errado | Verificar no @userinfobot |
| Bot responde de outro usuário | ID errado | Pegar o SEU id no @userinfobot |
| "404 Not Found" no webhook | App não está rodando | Verificar deploy no Render |

---

## 🔄 Se precisar refazer o webhook

```bash
# Remove o webhook antigo
curl "https://api.telegram.org/botSEU_TOKEN/deleteWebhook"

# Configura de novo
curl "https://api.telegram.org/botSEU_TOKEN/setWebhook?url=https://SEU-APP.onrender.com/webhook/telegram"
```
