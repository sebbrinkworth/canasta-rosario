#!/usr/bin/env bash
# daily_collect.sh — recolección diaria canasta-rosario (corre LOCAL, 17:05 ART).
# SEPA bloquea IPs de GitHub Actions runners (403): por eso este job corre en la
# gateway local vía automations (job: canasta-daily-collect).
# Flujo: ETL del día → forecast-next → backtest → sitio → commit canasta-bot → push.
set -uo pipefail

REPO=/home/sebba/.openclaw/workspace/canasta-rosario
DATE=$(TZ=America/Argentina/Buenos_Aires date +%F)
cd "$REPO" || exit 1

echo "[daily] $(date -Is) repo=$REPO date=$DATE"

# 1) sincronizar (puede haber pushes de otros actores)
git pull --rebase --autostash origin main >>/tmp/canasta-daily.log 2>&1 \
  || { echo "[daily] WARN: pull falló, sigo con lo local"; }

# 2) ETL del día (descarga el ZIP SEPA del weekday actual vía CKAN)
PYTHONPATH=. uv run python -m etl.etl --date "$DATE" --gran-rosario
ETL_RC=$?
if [ $ETL_RC -ne 0 ]; then
  echo "[daily] ETL falló (rc=$ETL_RC) para $DATE — se preservan datos previos"
  exit 1
fi

# 3) pronóstico + backtest + sitio (todo real-only)
PYTHONPATH=. uv run python forecast/build_next.py || true
uv run python forecast/backtest.py || true
uv run python web/generate.py || true
cp web/index.html ./index.html || true
cp web/index.html docs/index.html || true

# 4) commit + push con identidad canasta-bot
git add data/rosario-*.json data/latest.json data/forecast-next.json \
        data/backtest.json web/index.html index.html docs/index.html || true
if git diff --cached --quiet; then
  echo "[daily] sin cambios que commitear (¿SEPA no publicó aún?)"
  exit 0
fi
git -c user.name="canasta-bot" -c user.email="bot@canasta-rosario" \
  commit -m "data: $DATE [skip ci]" || true

for i in 1 2 3; do
  if git push origin main 2>>/tmp/canasta-daily.log; then
    echo "[daily] push OK ($i)"
    exit 0
  fi
  echo "[daily] push intento $i falló; pull --rebase y reintento"
  git pull --rebase --autostash origin main >>/tmp/canasta-daily.log 2>&1 || true
  sleep 5
done
echo "[daily] ERROR: push falló tras 3 intentos — commits locales quedan en $(git rev-parse --short HEAD)"
exit 2
