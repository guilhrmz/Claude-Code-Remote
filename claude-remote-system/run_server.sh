#!/bin/bash
# Script para iniciar o servidor Claude Remote

set -e

echo "============================================"
echo "Claude Remote Server"
echo "============================================"

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 não encontrado"
    exit 1
fi

# Verificar/criar .env
if [ ! -f .env ]; then
    echo "[INFO] Criando .env a partir de .env.example..."
    cp .env.example .env
    echo "[WARN] Edite .env com suas configurações!"
fi

# Instalar dependências
if [ -f requirements.txt ]; then
    echo "[INFO] Verificando dependências..."
    python3 -m pip install -q -r requirements.txt
fi

# Verificar Ollama
echo "[INFO] Verificando Ollama..."
if command -v curl &> /dev/null; then
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[OK] Ollama está rodando"
    else
        echo "[WARN] Ollama não está respondendo em http://localhost:11434"
        echo "[INFO] Inicie o Ollama com: ollama serve"
    fi
fi

# Criar work directory
WORK_DIR=$(grep WORK_DIR .env 2>/dev/null | cut -d'=' -f2)
WORK_DIR=${WORK_DIR:-/tmp/claude-remote-work}
echo "[INFO] Work directory: $WORK_DIR"
mkdir -p "$WORK_DIR"

# Iniciar servidor
echo ""
echo "[INFO] Iniciando servidor..."
echo "============================================"
echo ""

python3 -m server.main "$@"
