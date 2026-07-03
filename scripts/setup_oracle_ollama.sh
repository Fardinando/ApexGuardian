#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
#  setup_oracle_ollama.sh
#  Oracle Cloud Always Free — Setup Docker + Ollama + Cloudflare
# ═══════════════════════════════════════════════════════════════
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/Fardinando/ApexGuardian/main/scripts/setup_oracle_ollama.sh | bash
#
# Pré-requisitos (faça antes no console Oracle):
#   1. Crie VM.Standard.A1.Flex (4 OCPU, 24GB RAM, 200GB)
#      - OS: Ubuntu 22.04 LTS (arm64)
#      - VCN com porta 22 liberada
#      - Adicione sua chave SSH pública
#   2. Conecte via SSH: ssh ubuntu@<IP-DA-VM>
#   3. Cole e execute este script
#
# ═══════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════"
echo "  ApexGuardian — Ollama no Oracle Cloud"
echo "═══════════════════════════════════════════"
echo ""

# ─── 1. Atualizar sistema ────────────────────────────────────
echo "[1/7] Atualizando sistema..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

# ─── 2. Instalar Docker ──────────────────────────────────────
echo "[2/7] Instalando Docker..."
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker "$USER"

# ─── 3. Instalar Ollama via Docker ───────────────────────────
echo "[3/7] Instalando Ollama..."
sudo docker rm -f ollama 2>/dev/null || true
sudo docker run -d \
  --name ollama \
  --restart unless-stopped \
  -p 127.0.0.1:11434:11434 \
  -v ollama_data:/root/.ollama \
  ollama/ollama

# Aguardar Ollama iniciar
echo "Aguardando Ollama iniciar..."
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama pronto!"
    break
  fi
  sleep 2
done

# ─── 4. Baixar modelo ────────────────────────────────────────
echo "[4/7] Baixando modelo llama3.1 (~4.7GB)..."
sudo docker exec ollama ollama pull llama3.1
echo "Modelo baixado!"

# ─── 5. Configurar Cloudflare Tunnel ─────────────────────────
echo "[5/7] Configurando Cloudflare Tunnel..."
echo ""
echo "═══════════════════════════════════════════"
echo "  Agora você precisa de um token do"
echo "  Cloudflare Tunnel."
echo ""
echo "  Passos:"
echo "   1. Acesse https://dash.cloudflare.com/"
echo "   2. Vá em Zero Trust > Networks > Tunnels"
echo "   3. Crie um tunnel, escolha 'docker'"
echo "   4. Copie o token (começa com 'eyJ...')"
echo "═══════════════════════════════════════════"
echo ""

read -rp "Cole o token do Cloudflare Tunnel: " CF_TOKEN
if [ -z "$CF_TOKEN" ]; then
  echo "Token vazio. O tunnel NÃO será configurado."
  echo "Configure manualmente depois com:"
  echo "  docker run -d --name tunnel --restart unless-stopped cloudflare/cloudflared tunnel --no-autoupdate run --token SEU_TOKEN"
else
  sudo docker rm -f cloudflare-tunnel 2>/dev/null || true
  sudo docker run -d \
    --name cloudflare-tunnel \
    --restart unless-stopped \
    cloudflare/cloudflared:latest \
    tunnel --no-autoupdate run --token "$CF_TOKEN"

  echo ""
  echo "Tunnel configurado! No Cloudflare Zero Trust:"
  echo "  - Adicione um Public Hostname apontando para:"
  echo "    Serviço: HTTP://localhost:11434"
}

# ─── 6. Verificar ────────────────────────────────────────────
echo "[6/7] Verificando instalação..."
echo ""
echo "Ollama:"
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool 2>/dev/null || echo "  (verifique manualmente)"
echo ""

if sudo docker ps --format '{{.Names}}' | grep -q cloudflare-tunnel; then
  TUNNEL_STATUS="rodando"
else
  TUNNEL_STATUS="não configurado"
fi

echo "Docker containers:"
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'

# ─── 7. Mostrar resumo ───────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Setup concluído!"
echo "═══════════════════════════════════════════"
echo ""
echo "Informações para o .env do ApexGuardian:"
echo ""
echo "OLLAMA_HOST=http://127.0.0.1:11434"
echo "OLLAMA_MODEL=llama3.1"
echo "OLLAMA_TIMEOUT=10"
echo ""

if [ -n "${CF_TOKEN:-}" ]; then
  echo "Se você configurou o Public Hostname no Cloudflare"
  echo "com o domínio 'ollama.seusite.com', use:"
  echo ""
  echo "OLLAMA_HOST=https://ollama.seusite.com"
fi
echo ""
echo "Comandos úteis:"
echo "  Ver logs:          docker logs -f ollama"
echo "  Testar API:        curl http://127.0.0.1:11434/api/generate -d '{\"model\":\"llama3.1\",\"prompt\":\"diga oi\"}'"
echo "  Tunnel status:     docker logs cloudflare-tunnel"
echo "  Parar tudo:        docker stop ollama cloudflare-tunnel"
echo "  Atualizar imagem:  docker pull ollama/ollama && docker restart ollama"
echo ""

# ─── Aviso ───────────────────────────────────────────────────
echo "⚠️  AVISO IMPORTANTE:"
echo "   Após o setup, RECONECTE o SSH em outro terminal"
echo "   para usar o Docker sem sudo (grupo docker)"
echo "   OU execute: newgrp docker"
echo "═══════════════════════════════════════════"
echo ""
