#!/bin/bash
# Script para iniciar o cliente Claude Remote

set -e

echo "============================================"
echo "Claude Remote Client"
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
    echo "[WARN] Edite .env com as configurações do servidor!"
fi

# Instalar dependências
if [ -f requirements.txt ]; then
    echo "[INFO] Verificando dependências..."
    python3 -m pip install -q -r requirements.txt
fi

# Parse argumentos
INTERACTIVE=""
if [ "$1" = "-i" ] || [ "$1" = "--interactive" ]; then
    INTERACTIVE="--interactive"
fi

# Iniciar cliente
echo ""
echo "[INFO] Iniciando cliente..."
echo "============================================"
echo ""

python3 -m client.main $INTERACTIVE "$@"
