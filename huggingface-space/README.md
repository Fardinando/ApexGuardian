---
title: Ollama for ApexGuardian
emoji: 🦙
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
---

# Ollama for ApexGuardian

Hospeda o Ollama (llama3.1) para o ApexGuardian usar como IA primária.

## Ping para manter acordado

O free tier do HF dorme após 48h. Configure um ping a cada 30 min na URL:

```
https://SEU-USER-SEU-SPACE.hf.space/api/tags
```

## Uso no ApexGuardian

```env
OLLAMA_HOST=https://SEU-USER-SEU-SPACE.hf.space
OLLAMA_MODEL=llama3.1
```
