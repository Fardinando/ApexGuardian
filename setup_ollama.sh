#!/bin/bash
# ============================================================
# setup_ollama.sh - Instala Ollama + llama3.1 + Cloudflare Tunnel
# Uso: chmod +x setup_ollama.sh && ./setup_ollama.sh
# ============================================================

set -e

echo "========================================"
echo "  ApexGuardian - Setup do Ollama"
echo "========================================"
echo ""

# 1. Instalar Ollama
echo "[1/5] Instalando Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "  ✅ Ollama instalado"
else
    echo "  ✅ Ollama já está instalado"
fi

# 2. Iniciar servidor Ollama em background
echo "[2/5] Iniciando servidor Ollama..."
ollama serve &
OLLAMA_PID=$!
echo "  ✅ Servidor iniciado (PID: $OLLAMA_PID)"

# 3. Aguardar servidor ficar pronto
echo "[3/5] Aguardando servidor ficar pronto..."
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "  ✅ Servidor pronto!"
        break
    fi
    sleep 2
done

# 4. Baixar modelo llama3.1
echo "[4/5] Baixando modelo llama3.1..."
ollama pull llama3.1
echo "  ✅ Modelo llama3.1 baixado"

# 5. Instalar e configurar Cloudflare Tunnel
echo "[5/5] Instalando Cloudflare Tunnel..."
if ! command -v cloudflared &>/dev/null; then
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
        chmod +x cloudflared
        sudo mv cloudflared /usr/local/bin/
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install cloudflare/cloudflare/cloudflared
    fi
    echo "  ✅ Cloudflare Tunnel instalado"
else
    echo "  ✅ Cloudflare Tunnel já está instalado"
fi

echo ""
echo "========================================"
echo "  Setup concluído!"
echo "========================================"
echo ""
echo "Para expor o Ollama via Cloudflare Tunnel:"
echo "  cloudflared tunnel --url http://localhost:11434"
echo ""
echo "Copie a URL gerada (ex: https://random.trycloudflare.com)"
echo "e use como OLLAMA_HOST no .env do ApexGuardian"
echo ""
echo "Para testar se o Ollama está funcionando:"
echo "  curl http://localhost:11434/api/generate -d '{"
echo '    "model": "llama3.1",'
echo '    "prompt": "Hello",'
echo '    "stream": false'
echo "  }'"
echo ""
