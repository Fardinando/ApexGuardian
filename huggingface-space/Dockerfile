FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    socat curl \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV OLLAMA_HOST=0.0.0.0:7860
ENV OLLAMA_KEEP_ALIVE=24h

EXPOSE 7860

ENTRYPOINT ["/entrypoint.sh"]
