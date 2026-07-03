#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  setup_hf_space.sh
#  Hugging Face Space — Setup Ollama para ApexGuardian
# ═══════════════════════════════════════════════════════════════
# Esse script CRIA o repositório no Hugging Face e faz push
# dos arquivos necessários para rodar o Ollama.
#
# Pré-requisitos:
#   1. Conta no Hugging Face (gratuita)
#   2. Token de acesso em https://huggingface.co/settings/tokens
#   3. Git instalado
# ═══════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════"
echo "  ApexGuardian — Ollama no HF Space"
echo "═══════════════════════════════════════════"
echo ""

# ─── Pedir token ─────────────────────────────────────────────
read -rp "Token do Hugging Face (crie em https://huggingface.co/settings/tokens): " HF_TOKEN
if [ -z "$HF_TOKEN" ]; then
  echo "❌ Token necessário."
  exit 1
fi

# ─── Pedir nome do Space ─────────────────────────────────────
read -rp "Nome do Space (ex: apexguardian-ollama): " SPACE_NAME
SPACE_NAME="${SPACE_NAME:-apexguardian-ollama}"
read -rp "Seu username no HF: " HF_USER
if [ -z "$HF_USER" ]; then
  echo "❌ Username necessário."
  exit 1
fi

SPACE_REPO="https://$HF_USER:$HF_TOKEN@huggingface.co/spaces/$HF_USER/$SPACE_NAME"

echo ""
echo "[1/4] Criando Space no Hugging Face..."
git clone "$SPACE_REPO" /tmp/hf-ollama-space 2>/dev/null || {
  echo "Space ainda não existe. Crie manualmente em:"
  echo "  https://huggingface.co/new-space"
  echo ""
  echo "Configurações:"
  echo "  - Space Name: $SPACE_NAME"
  echo "  - License: MIT"
  echo "  - SDK: Docker"
  echo "  - Hardware: CPU (free)"
  echo ""
  echo "Depois de criar, execute este script novamente."
  exit 1
}

echo "[2/4] Copiando arquivos do Ollama..."
cp "$(dirname "$0")/../huggingface-space/Dockerfile" /tmp/hf-ollama-space/
cp "$(dirname "$0")/../huggingface-space/entrypoint.sh" /tmp/hf-ollama-space/
cp "$(dirname "$0")/../huggingface-space/README.md" /tmp/hf-ollama-space/
chmod +x /tmp/hf-ollama-space/entrypoint.sh

echo "[3/4] Fazendo push para o Hugging Face..."
cd /tmp/hf-ollama-space
git add .
git commit -m "Initial setup: Ollama llama3.1 for ApexGuardian"
git push origin main
cd /tmp
rm -rf /tmp/hf-ollama-space

echo "[4/4] ✅ Space criado com sucesso!"
echo ""
echo "═══════════════════════════════════════════"
echo "  PRÓXIMOS PASSOS"
echo "═══════════════════════════════════════════"
echo ""
echo "1. Acesse: https://huggingface.co/spaces/$HF_USER/$SPACE_NAME"
echo "   O Ollama vai iniciar e baixar o modelo (leva ~5 min na 1ª vez)"
echo ""
echo "2. Teste se está funcionando:"
echo "   curl https://$HF_USER-$SPACE_NAME.hf.space/api/tags"
echo ""
echo "3. Configure o PING (HF free dorme após 48h):"
echo "   Adicione no seu monitor de uptime:"
echo "   URL: https://$HF_USER-$SPACE_NAME.hf.space/api/tags"
echo "   Intervalo: a cada 30 minutos"
echo ""
echo "4. No .env do ApexGuardian, use:"
echo "   OLLAMA_HOST=https://$HF_USER-$SPACE_NAME.hf.space"
echo "   OLLAMA_MODEL=llama3.1"
echo "   OLLAMA_TIMEOUT=30"
echo ""
echo "═══════════════════════════════════════════"
