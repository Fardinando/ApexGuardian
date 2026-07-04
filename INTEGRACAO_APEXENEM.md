# Integração ApexEnem → ApexGuardian

Como conectar o frontend do ApexEnem para enviar denúncias de erro ao ApexGuardian.

---

## 📡 Endpoint de Denúncia

O ApexGuardian expõe um endpoint que o frontend do ApexEnem chama quando o usuário reporta um erro:

```
POST https://SEU-APP.onrender.com/webhook/report
Content-Type: application/json
```

---

## 📦 Payload esperado

```json
{
  "screenshot_base64": "data:image/png;base64,iVBOR...",
  "description": "Descrição do erro pelo usuário",
  "timestamp_frontend": 1800000000,
  "user_id_anon": "a1b2c3d4..."
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `description` | string | ✅ | Descrição do erro escrita pelo usuário |
| `user_id_anon` | string | ✅ | Hash anônimo do ID do usuário (SHA256 do user.id) |
| `timestamp_frontend` | number | ✅ | Unix timestamp em segundos do momento do erro |
| `screenshot_base64` | string | ❌ | Screenshot em base64 (data URI) |

---

## 🔌 Implementação no React

### Botão "Reportar Erro"

Adicione um botão/flutuante no site do ApexEnem:

```tsx
import { sha256 } from 'crypto-js';

function ReportButton() {
  const reportError = async (description: string, screenshotBase64?: string) => {
    const userHash = sha256(user.id.toString()).toString();

    await fetch("https://SEU-APP.onrender.com/webhook/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        screenshot_base64: screenshotBase64 || "",
        description,
        timestamp_frontend: Math.floor(Date.now() / 1000),
        user_id_anon: userHash,
      }),
    });
  };

  // ...
}
```

### Captura de tela (opcional)

```tsx
import html2canvas from 'html2canvas';

async function captureScreenshot(): Promise<string> {
  const canvas = await html2canvas(document.body);
  return canvas.toDataURL("image/png");
}
```

---

## 📥 Resposta da API

```json
{
  "status": "received",
  "message": "Denúncia recebida com sucesso.",
  "error_id": 42,
  "log_matched": true
}
```

| Campo | Significado |
|-------|-------------|
| `status` | `received` (com log correspondente) ou `archived` (sem log) |
| `error_id` | ID interno do erro no banco |
| `log_matched` | Se o erro foi encontrado nos logs da Vercel |

---

## 🔄 Fluxo Completo

```
Usuário clica "Reportar Erro"
       │
       ▼
Frontend envia POST /webhook/report
       │
       ▼
ApexGuardian recebe a denúncia
       │
       ├── Busca logs da Vercel (últimos 10 min)
       │
       ├── Se achou log → Inicia investigação com IA
       │   └── Você recebe notificação no Telegram
       │
       └── Se NÃO achou log → Arquivado
           └── Se >10 usuários reportarem, reabre automático
```

---

## 📊 Consultar Status do Erro

Dashboard admin: `https://SEU-APP.onrender.com/admin`

---

## ⚙️ Variáveis de Ambiente no ApexEnem

Recomendado usar variável de ambiente para a URL do ApexGuardian:

```env
NEXT_PUBLIC_APEXGUARDIAN_URL=https://apexguardian.onrender.com
```

E no código:

```tsx
const APEXGUARDIAN_URL = process.env.NEXT_PUBLIC_APEXGUARDIAN_URL;

await fetch(`${APEXGUARDIAN_URL}/webhook/report`, { ... });
```
