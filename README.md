# Canasta Rosario — 25 alimentos, ¿dónde conviene hoy?

> Datos SEPA (CC BY 4.0) · Rosario + Gran Rosario · 1 página, sin login, <2s.

[![daily-etl](https://github.com/sebbrinkworth/canasta-rosario/actions/workflows/daily.yml/badge.svg)](https://github.com/sebbrinkworth/canasta-rosario/actions) · [Demo (GitHub Pages)](https://sebbrinkworth.github.io/canasta-rosario/)

![Canasta](web/index.html)

**Problema:** Nadie muestra en una sola pantalla el costo de una canasta fija de 25 alimentos comparada por cadena en Rosario. Los comparadores nacionales son genéricos/lentos y no cubren locales; preciosclaros.gob.ar no advierte que La Gallega/DAR no informan SEPA.

**Solución:** ETL reproducible SEPA + sitio estático 1-página con hero “costo total por cadena, más barato primero”, tabla 25×5 con $/paquete y $/kg-L, badge honesto de cobertura.

## Demo local

```bash
# ETL (requiere uv)
uv sync
uv run pytest -q
# Generar datos para un día (Gran Rosario = Rosario + Funes/Fisherton via bbox)
uv run python -m etl.etl --date 2026-08-31 --gran-rosario --zip /tmp/canasta-etl/sepa_lunes.zip
# o descarga automática por CKAN si no pasás --zip
PYTHONPATH=. uv run python -m etl.etl --date 2026-08-31 --gran-rosario

# Sitio estático (HTML puro, sin build)
PYTHONPATH=. uv run python web/generate.py
# Servir
python -m http.server 8000 --directory web
# Abrir http://localhost:8000
```

Datos emitidos:
- `data/raw/rosario-YYYY-MM-DD.json` — observaciones crudas
- `data/rosario-YYYY-MM-DD.json` — agregado (hero + tabla) consumido por `web/generate.py`

## Actualización diaria (cron)

El ETL descarga `sepa_lunes.zip` … `sepa_domingo.zip` vía CKAN (dataset `6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5`). Un GitHub Action corre diario 17:00 ART y commitea `data/`.

## Validación

Ver [`docs/validation.md`](docs/validation.md) — auditoría real SEPA 2026-08-31 (2.800 sucursales, 47 en AR-S, 20 en Gran Rosario, 5 cadenas super). §7 Addendum Gran Rosario documenta bbox y por qué no hay nuevas cadenas.

## Roadmap

- v1 (hoy): SEPA puro, 5 cadenas (Carrefour, Coto, Jumbo/Vea, La Anónima, DIA), badge honesto.
- v1.1: scraper La Gallega (tienda online) + merge `source=scrape`.

## Licencia

MIT · Datos SEPA CC BY 4.0 (atribución: SEPA / datos.produccion.gob.ar).

## Repo

https://github.com/sebbrinkworth/canasta-rosario
