#!/bin/bash
set -e

echo "Iniciando Ollama server..."
ollama serve &

sleep 3

echo "Baixando modelo llama3.1..."
ollama pull llama3.1 2>&1 | tail -5
echo "Modelo pronto!"

wait
