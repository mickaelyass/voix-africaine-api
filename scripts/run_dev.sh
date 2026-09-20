#!/usr/bin/env bash
#
# Lance l'API FastAPI en développement (MongoDB local).
#
#   ./scripts/run_dev.sh              # port 8000, rechargement auto
#   PORT=9000 ./scripts/run_dev.sh    # port personnalisé
#
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

if [ ! -f .env ]; then
  echo "❌ Fichier .env absent. Copiez .env.example :"
  echo "   cp .env.example .env"
  exit 1
fi

echo "▶  API       : http://${HOST}:${PORT}"
echo "▶  Swagger   : http://${HOST}:${PORT}/docs"
echo "▶  MongoDB   : mongodb://localhost:27017 (voir .env)"
echo

exec env/bin/uvicorn main:app --host "${HOST}" --port "${PORT}" --reload