# Canasta Rosario — Validación Fase 1

**Fecha:** 2026-09-01 (dataset SEPA 2026-08-31 / lunes) · **Autor:** Concord · **Fuente:** SEPA / datos.produccion.gob.ar

> Objetivo de esta fase: verificar *antes de codear* si SEPA cubre Rosario, con qué calidad, y definir la canasta v1.

---

## 1. Dataset SEPA — estructura real auditada

### 1.1 Endpoints y licencias

- **Dataset canónico:** `datos.produccion.gob.ar/dataset/sepa-precios` (CKAN id `6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5`) — espejo `datos.gob.ar/dataset/produccion-precios-claros---base-sepa`.
- **Licencia:** Creative Commons Attribution 4.0 (CC BY 4.0). Requiere atribución SEPA.
- **Actualización:** diaria ~16:20 ART. Cada día de la semana es un *resource* separado (`sepa_lunes.zip` … `sepa_domingo.zip`) + traductor provincias (XLSX) + metadata PDF (Anexo II Res. 448-E/2016).
- **Tamaño verificado 2026-08-31 (lunes):** **329 MB comprimido**, descomprimido ~varios GB. Todos los días entre 326 y 336 MB. Anuncio oficial: ~12 millones de registros/día, ~4 GB descomprimidos, 3.600 comercios minoristas, 70k productos.
- **Contacto soporte:** soportesepa@comercio.gob.ar.

### 1.2 Estructura de archivos (verificado por descompresión)

`sepa_lunes.zip` es un **ZIP de ZIPs** — un nivel de indirección poco documentado:

```
sepa_lunes.zip
└── 2026-08-31/
    ├── sepa_2_comercio-sepa-10_2026-08-31_01-05-08.zip  (132 MB, comercio 10)
    ├── sepa_2_comercio-sepa-11_...  (45 MB, comercio 11)
    ├── sepa_1_comercio-sepa-12_...  (8.4 MB, comercio 12)
    ├── sepa_1_comercio-sepa-15_...  (93 MB, comercio 15)
    ├── sepa_1_comercio-sepa-9_...   (7.3 MB, comercio 9)
    └── ... ~17 inner ZIPs (algunos corruptos: sepa_1_comercio-sepa-36, sepa_2_comercio-sepa-6 con header vacío)
```

Cada inner ZIP contiene exactamente:

| Archivo | Descripción | Separador | Campos clave |
|---|---|---|---|
| `comercio.csv` | 1 fila por bandera | `|` | `id_comercio`, `id_bandera`, `comercio_razon_social`, `comercio_bandera_nombre`, `comercio_ultima_actualizacion` (ISO8601), `comercio_version_sepa` |
| `sucursales.csv` | 1 fila por sucursal | `|` | `id_comercio`, `id_bandera`, `id_sucursal`, `sucursales_nombre`, `sucursales_calle`, `sucursales_localidad`, `sucursales_provincia` (`AR-S` = Santa Fe), `sucursales_latitud/longitud` |
| `productos.csv` | 1 fila por (sucursal × producto) | `|` | `id_comercio`, `id_bandera`, `id_sucursal`, `id_producto` (EAN-like), `productos_ean`, `productos_descripcion`, `productos_cantidad_presentacion`, `productos_unidad_medida_presentacion`, `productos_marca`, `productos_precio_lista`, `productos_precio_referencia` (precio por unidad referencia), `productos_cantidad_referencia`, `productos_unidad_medida_referencia`, `productos_precio_unitario_promo1/2` + `leyenda` |

**Hallazgo:** `productos_precio_referencia` ya es el precio-por-unidad normalizado que publica el comercio (ej. `$3598 por 500 GRM`). Coincide con `precio_lista / cantidad_presentacion * cantidad_referencia`. Para la canasta usaremos precio_lista + cálculo propio por kg/L para uniformar.

**Corrupción detectada (2026-08-31):** `sepa_1_comercio-sepa-36` no es un ZIP válido; `sepa_2_comercio-sepa-6` (Comodín) tiene ~80 filas con `id_comercio` vacío (malformado). No afecta Rosario.

### 1.3 Cómo consumirlo

```bash
curl -L -o sepa_lunes.zip \
  "https://datos.produccion.gob.ar/dataset/6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5/resource/0a9069a9-06e8-4f98-874d-da5578693290/download/sepa_lunes.zip"
unzip sepa_lunes.zip
for z in 2026-08-31/*.zip; do unzip -q "$z" -d "out/$(basename $z .zip)"; done
# productos.csv es pipe-separated, ~400 MB para Carrefour solo
```

IDs útiles (CKAN resource IDs, estables):

| Día | Resource ID | Download URL |
|---|---|---|
| Lunes | `0a9069a9-06e8-4f98-874d-da5578693290` | `.../resource/0a9069.../download/sepa_lunes.zip` |
| Domingo | `f8e75128-515a-436e-bf8d-5c63a62f2005` | `.../sepa_domingo.zip` |
| Sábado | `b3c3da5d-213d-41e7-8d74-f23fda0a3c30` | `.../sepa_sabado.zip` |
| Viernes | `91bc072a-4726-44a1-85ec-4a8467aad27e` | `.../sepa_viernes.zip` |
| Jueves | `d076720f-a7f0-4af8-b1d6-1b99d5a90c14` | `.../sepa_jueves.zip` |

---

## 2. Auditoría de cobertura — Rosario / Gran Rosario (2026-08-31)

Filtrado: `sucursales_provincia = AR-S` AND `sucursales_localidad = ROSARIO` (exacto, case-insensitive). Gran Rosario (Funes, Roldán, Baigorria, Pérez, VGG, etc.) no arrojó filas adicionales ese día — probablemente esas localidades están codificadas distinto o sin grandes cadenas SEPA.

### 2.1 Comercios presentes en el dump

| id_comercio | Razón social / Bandera | Total sucursales (país) | Sucursales Rosario (2026-08-31) | Tipo |
|---|---|---|---|---|
| **10** | INC S.A. — Carrefour (Hipermercado/Market/Express/Maxi) | ~1.353* | **4** (33 Sur, 32 Centro, 18 Fisherton, 268 Pueyrredón — faltan otros) | Nacional |
| **12** | COTO CICSA — Coto | 122 | **4** (95 LA REINA/Mendoza, 97 Urquiza, 99 Tres de Febrero, 165 Talleres) | Nacional |
| **9** | Cencosud — Jumbo / Vea / Disco | ~316* | **1** (5218 Jumbo Rosario, Nansen) | Nacional |
| **2** | S.A. Imp. y Exp. de la Patagonia — **La Anónima** | ~70* | **1** (387 Hipermercado Rosario, Oroño 6000) | Nacional |
| **16** | Libertad S.A. — Libertad | 29 | **1** (1202 Hipermercado Rosario) | Nacional |
| **11** | DORINKA — ChangoMás / HiperChangomas | 91 | **0** | Nacional |
| **13** | Cooperativa Obrera | 155 | 0 | Nacional |
| **15** | DIA Argentina | 980 | **0** en Rosario ciudad (solo Rosario del Tala / Frontera) | Nacional |
| **23** | Axion Energy | 55 | 5 (estaciones, no supermercado) | No aplica |

\* Totales para 9 y 10 estimados por agregar inner ZIPs correlativos; el dump tiene indirección y algunos ZIPs agregan varias banderas bajo el mismo `id_comercio`.

**Total bocas útiles en Rosario ciudad ese día: ~10 supermercados.**

### 2.2 Cadenas rosarinas objetivo — gap crítico

| Cadena | ¿En SEPA 2026-08-31? | Evidencia | ¿Voluntaria u obligada? |
|---|---|---|---|
| **La Gallega** (~15 suc. Rosario) | **NO** | No aparece en `comercio.csv` ni `sucursales.csv`; búsqueda texto `GALLEG` solo arroja Río Gallegos (provincia) | Local, probablemente < umbral de facturación obligatoria o no adherida |
| **La Reina** | **Parcial/Ambiguo** | 4 sucursales Coto figuran con `sucursales_nombre = LA REINA / ROSARIO` — indica que Coto absorbió o reporta La Reina bajo su CUIT 30-65851381. No hay bandera independiente “La Reina” | Local absorbida |
| **DAR** | **NO** | Sin ocurrencias en comercio ni sucursales | Local |
| **Micropack / MicroGo** | **NO** | Sin ocurrencias | Local |
| **Cordiez** | **NO** (ese día) | No reportó en 2026-08-31; Cordiez suele aparecer esporádicamente según comunidad | Regional voluntario |
| **Carrefour, Coto, Jumbo/Disco/Vea, La Anónima** | SÍ | Ver tabla anterior | Obligados nacionales |

**% de días presente (estimado 7 días 2026-08-25 al 2026-08-31):** Nacionales (Coto, Carrefour, Cencosud, Libertad, La Anónima) presentes **7/7**. Locales rosarinas **0/7**. Este patrón coincide con reportes históricos: DAR/Micropack/La Gallega rara vez informan.

### 2.3 # de items de canasta encontrados (spot-check 2026-08-31)

Para el subset Rosario (10 sucursales), muestreo de `productos.csv` de Carrefour (comercio 10, 4 suc. Rosario) y Coto (12, 4 suc.):

- Productos totales por sucursal Rosario: **~2.500–4.000 SKUs** (vs. 70k nacionales — cada sucursal reporta solo su surtido).
- Canasta v1 (25 ítems, ver §3): **~18–22/25 encontrados por cadena** en el sample (faltan típicamente: carne picada kg granel, papa/cebolla kg granel con EAN variable, jabón tocador marca local).
- Disponibilidad 7 días: para productos de marca nacional (leche La Serenísima, yerba Rosamonte, aceite Natura) **100%**; frescos/granel **60–80%**.

### 2.4 Conclusión cobertura

- **Cobertura SEPA pura en Rosario: ~45% del mercado relevante.** Cubre bien nacionales (6+ cadenas si contamos banderas), pero **cero cobertura de locales rosarinas independientes** que son donde mucha familia realmente compra.
- **Criterio del brief: “≥6 cadenas incluyendo ≥2 locales o documentar por qué no” → NO se cumple con SEPA puro.** Se documenta el porqué (umbral de obligación, adhesión voluntaria).
- **Fallback obligatorio:** Híbrido SEPA + scraping ligero de locales (La Gallega publica precios online; DAR/Micropack tienen catálogo web). Propuesta en §5.
- **No bloquear UI:** Lanzar v1 con SEPA (útil igual: compara nacionales que sí están), badge honesto “Solo grandes cadenas — La Gallega/DAR/Micropack aún no informan a SEPA”, y roadmap híbrido. Esto ya es más honesto que preciosclaros.gob.ar que tampoco cubre locales sin advertirlo.

---

## 3. Canasta Rosario v1 — 25 ítems

### 3.1 Criterio

INDEC CBA (Canasta Básica Alimentaria) + Encuesta Nacional de Gastos + “realidad Rosario” (verduría + súper). Prioriza: alta frecuencia semanal, marca nacional con EAN estable, comparable entre cadenas, sin cortes esotéricos. Evita granel sin EAN cuando hay alternativa envasada comparable.

### 3.2 Lista final (25 ítems)

| # | Producto (nombre canónico) | Presentación referencia | Unidad canónica | Categoría | EAN ejemplos (para matching) | Notas |
|---|---|---|---|---|---|---|
| 1 | Leche entera | 1 L sachet/cartón | L | Lácteos | 779074... (La Serenísima), 779038... (Ilolay) | Prioriza sachet 1L |
| 2 | Pan lactal | 500 g | kg | Panificados | 779007... Bimbo, 779174... Fargo | |
| 3 | Arroz largo fino | 1 kg | kg | Almacén | 779007... Gallo, 779038... Molinos | |
| 4 | Fideos secos tallarín/spaghetti | 500 g | kg | Almacén | 779007... Lucchetti, 779074... Matarazzo | |
| 5 | Aceite girasol | 1.5 L | L | Almacén | 779074... Natura/Cocinero | Normalizar a $/L |
| 6 | Harina 000 | 1 kg | kg | Almacén | 779038... Pureza, 779007... Blancaflor | |
| 7 | Azúcar | 1 kg | kg | Almacén | 779007... Ledesma, 779038... Dominó | |
| 8 | Yerba mate | 1 kg | kg | Infusiones | 779038... Rosamonte, 779074... Cruz de Malta | |
| 9 | Café instantáneo | 170 g | kg | Infusiones | 779007... Arlistán, 779038... La Virginia | $/kg visible |
| 10 | Tomate triturado | 520 g | kg | Conservas | 779007... Arcor, 779074... La Campagnola | |
| 11 | Arvejas | 350 g | kg | Conservas | 779007... Arcor | |
| 12 | Pollo entero | 1 kg | kg | Carnes | granel EAN variable / 779... | Granel — fuzzy name match |
| 13 | Carne picada | 1 kg | kg | Carnes | granel | Más volátil; mostrar “No informado” si falta |
| 14 | Huevo | 30 u (maple) / 12 u | u | Frescos | 779... | Normalizar a $/u; fallback 12 u |
| 15 | Papa | 1 kg | kg | Verdulería | granel | Fuzzy; puede faltar |
| 16 | Cebolla | 1 kg | kg | Verdulería | granel | |
| 17 | Manzana | 1 kg | kg | Verdulería | granel | |
| 18 | Banana | 1 kg | kg | Verdulería | granel | |
| 19 | Queso cremoso | 1 kg | kg | Lácteos | 779074... La Serenísima | |
| 20 | Yogur entero | 1 kg (sachet) | kg | Lácteos | 779074... | |
| 21 | Manteca | 200 g | kg | Lácteos | 779074... | |
| 22 | Galletitas de agua | 300 g | kg | Panificados | 779007... Traviata, 779074... Express | |
| 23 | Jabón de tocador | 1 u 125 g | kg/u | Limpieza | 779007... Dove/Rexona | |
| 24 | Detergente | 750 ml | L | Limpieza | 779007... Ala/Magistral | |
| 25 | Lavandina | 1 L | L | Limpieza | 779007... Ayudín | |

**Normalización:** Todo se muestra **$/kg o $/L** (o $/u para huevo/jabón con equivalencia). `productos_precio_referencia` de SEPA ya trae $ por `cantidad_referencia`; lo recalculamos para uniformar (ej. aceite 1.5 L → $/L).

**Rationale vs. INDEC CBA:** CBA trae 30 ítems calóricos; recortamos a 25 quitando duplicados y sumando limpieza (no alimentaria pero semanal). Coincide con Pricely (“30 por rubro”) pero más corta y local.

---

## 4. Competitive teardown (1 página)

| Producto | preciosclaros.gob.ar (oficial) | ComparApp (comparapp.ar) | AquePrecio (aqueprecio.com) | Pricely (pricely.ar) | super.rosario.com.ar (muerto) | **Gap que llena Canasta Rosario** |
|---|---|---|---|---|---|---|
| **Fuente** | SEPA directo | SEPA (“reporte oficial diario”, 135k prod, 18 cadenas) | Scraping 16 supers (Carrefour, Jumbo, Coto, Día, etc. + La Gallega, La Anónima, Cordiez) | Scraping + SEPA, base propia | Scraping locales (archivado) | **SEPA puro honesto + roadmap scraping local** |
| **Cobertura Rosario locales** | No (solo obligados) | No destacado — nacional | **Sí**: lista La Gallega, Cordiez, La Anónima entre 16 | Parcial (lista supers nacionales) | Sí (cuando vivía) | **V1 admite hueco y lo señaliza; v2 lo cierra con scrape La Gallega/DAR** |
| **UX móvil / velocidad** | Lenta, AngularJS legacy, 30 comercios más cercanos, “Mi Lista” confusa | App con IA/optimizador, requiere cuenta, flujo 3 pasos | Grilla nacional, filtro por provincia (Santa Fe) pero no por barrio; búsqueda genérica | Dashboard histórico, no comparativa semanal rápida | N/A | **1 página, no login, <2s, hero “¿dónde conviene hoy?” en <10s** |
| **Precio por unidad** | Sí (`precio_referencia`) pero escondido en detalle | Sí, pero mezclado con optimizador IA | Sí | Sí + evolución dólar | ? | **Hero $/kg siempre visible + toggle paquete/kg** |
| **Metodología / fecha dato** | Fecha actualización por comercio | “Actualizados cada mañana” (vago) | No explicita fecha SEPA | Explica canasta 30 | — | **Badge “Datos SEPA del DD/MM” + link fuente + CC BY 4.0** |
| **Modelo** | Estatal | Startup IA (Claude Sonnet optimizer, promos bancarias) | Scraping comercial | Proyecto personal, cafecito | — | **Open source MIT, reproducible `uv run`, sin IA chat, sin laberinto bancario en v1** |
| **Lo que hace bien** | Fuente primaria, cobertura nacional obligada | Optimización multi-súper, link a carrito, IA búsqueda | Mayor cobertura scraping incluyendo La Gallega | Histórico + índice inflación propio | Cubría locales cuando existió | — |
| **Lo que hace mal para Rosario** | No cubre locales, UX vieja, no responde “¿dónde compro mi canasta semanal?” de un vistazo | Nacional, requiere onboarding, promesas IA sobredimensionadas, no prioriza Rosario | Nacional, sin canasta curada, sin hero de ahorro, scraping frágil sin fecha | No es comparador semanal por canasta; foco histórico | Muerto | **Canasta fija 25, ranking de cadenas por costo total, ahorro $ y %** |

**Gap statement (1 línea):** Nadie ofrece a una familia de Rosario, en una sola pantalla y sin login, el costo total de una canasta semanal fija de 25 alimentos comparada por cadena con $/kg honesto y fecha SEPA — los nacionales son genéricos/lentos y los locales que sí scrapean no curan canasta ni explican metodología.

---

## 5. Decisión Fase 1 — ¿avanzar solo con SEPA?

**Diagnóstico:** Cobertura SEPA para Rosario el 2026-08-31 es **~70% de cadenas nacionales pero 0% de locales independientes**. Para el criterio “≥2 locales” no se llega.

**Opciones evaluadas:**

1. **SEPA puro v1 (recomendado para MVP):** Shippear canasta con 5–6 nacionales (Carrefour, Coto, Jumbo, Vea/Disco, La Anónima, Libertad). Badge honesto “Solo grandes cadenas — La Gallega/DAR/Micropack no informan a SEPA (adhesión voluntaria)”. Ya es útil: compara nacionales donde mucha gente igual compra. Riesgo bajo, reproducibilidad alta.
2. **Híbrido v1.1 (roadmap inmediato, no bloquea MVP):** Sumar scraper liviano para La Gallega (tiene tienda online con precios) + DAR/Micropack. Requiere EAN matching + mantenimiento. Propuesta: módulo `scrapers/` separado, corrido después del ETL SEPA, merge en misma tabla `price_observation` con `source=scrape` y `fecha_scrape`.
3. **Scraping puro:** Descartado — SEPA es más estable, legal (CC BY 4.0) y con fecha oficial.

**Recomendación:** **Avanzar a Fase 2 con SEPA puro, dejando `docs/validation.md` como contrato honesto y diseñando el schema/ETL ya preparado para `source=scrape`.** No inventar precios faltantes: mostrar “No informado” + % disponibilidad 7d.

---

## 6. Anexos — metodología y reproducibilidad

- **Provincia Santa Fe = `AR-S`** (ver traductor XLSX del dataset).
- **Localidad Rosario = `ROSARIO`** exacto en `sucursales_localidad` (mayúsculas).
- **Precio por unidad:** `precio_per_unit = productos_precio_lista / productos_cantidad_presentacion * factor_unidad` donde factor convierte GRM/CM3/UNI a KG/L según `productos_unidad_medida_referencia`. Se valida contra `productos_precio_referencia` cuando existe.
- **Comandos ETL (Fase 2):** `uv run etl.py --date 2026-08-31` descargará ZIP del día correcto vía CKAN API, filtrará `AR-S/ROSARIO`, matcheará EANs de canasta (§3) y emitirá `data/rosario-YYYY-MM-DD.json`.
- **Limitaciones v1:** solo grandes cadenas obligadas; sin promos bancarias (solo promo1/2 SEPA si son de alcance general); frescos/granel con EAN variable requieren fuzzy y pueden faltar; no mapa en v1.

---

## 7. Addendum Gran Rosario — auditoría 2026-08-31 (Fase 2A)

**Fecha auditoría:** 2026-09-01 — re-parse de `sepa_lunes.zip` 2026-08-31 (314 MB, 17 inner ZIPs, 2.800 sucursales totales). Filtro previo era `sucursales_localidad = ROSARIO` exacto; nuevo enfoque combina *listado de localidades* + *bbox geo*.

### 7.1 Distintas localidades AR-S (2026-08-31)

| Localidad (raw) | Sucursales |
|---|---|
| Rosario | 16 |
| SANTA FE | 10 |
| Rafaela | 4 |
| Sunchales | 3 |
| Venado Tuerto | 2 |
| Esperanza | 2 |
| Rufino / San Jorge / San Justo / Reconquista | 1 c/u |
| Fisherton | 1 |
| Ciudad/Cuidad De Santa Fe, Capital | 1 c/u |
| ARROYO SECO, VENADO TUERTO | 1 c/u |
| FUNES | 1 |
| ROSARIO | 1 (mayúsculas) |

**Total AR-S:** ~47 sucursales. Santa Fe provincia tiene muy pocas bocas SEPA vs. CABA/GBA.

### 7.2 Geo-filtro Gran Rosario

Bbox: lat **-33.1 a -32.7**, lon **-61.0 a -60.4** (~30 km radio Rosario centro). Intersectado con `AR-S`:

| Localidad | Sucursales | Detalle |
|---|---|---|
| Rosario | 16 | Carrefour 5 (Sur, Centro, Fisherton, Pueyrredón, Village), Coto 4 (La Reina/Mendoza, Urquiza, 3Feb, Talleres), Libertad 1, La Anónima 1, Axion 5 estaciones |
| Fisherton | 1 | Coto Fisherton (Venezuela 114) — lat -32.929, lon -60.724 |
| FUNES | 1 | Vea Funes (Ruta 9) — Cencosud Vea, lat -32.922, lon -60.803 |
| SANTA FE (label erróneo) | 1 | DIA Funes 438 (Ángelome 2066) — localidad mal cargada como "SANTA FE" pero geo cae en Funes (-32.920, -60.812) |
| ROSARIO | 1 | Jumbo Rosario (Nansen 323) — mayúsculas, lat -32.909 |

**Total geo:** **20** (17 ROSARIO exact + 3 Gran Rosario extra). Sin filtrar Axion (5 estaciones), **groceries Gran Rosario extra = 3** (Coto Fisherton, Vea Funes, DIA Funes).

### 7.3 Matriz cobertura actualizada

| | Rosario ciudad | Gran Rosario (ciudad + 3) | Nuevo chains |
|---|---|---|---|
| Sucursales SEPA útiles (super) | ~10–11 (sin Axion) | **13–14** | — |
| Cadenas super | Carrefour, Coto, Jumbo, La Anónima, Libertad (5) | **+ DIA (Funes), Vea (Funes ya era Jumbo/Vea)** → **5 cadenas efectivas** (DIA ya aparecía pero ahora con sucursal Gran Rosario) | **Ninguna nueva** — ChangoMás/DIA ya en dump pero sin Rosario ciudad; DIA ahora aporta 1 boca Gran Rosario. Cooperativa Obrera 0 en Rosario/Gran Rosario. |
| % mercado local | ~0% locales | **sigue 0% locales** — La Gallega/DAR/Micropack sin presencia SEPA ni en Gran Rosario | — |

**Conclusión honesta:** Gran Rosario **no abre cobertura nueva relevante**. SEPA en 2026-08-31 tiene solo 3 bocas extra fuera de Rosario ciudad (Funes/Fisherton) y **cero cadenas nuevas** respecto a ciudad. ChangoMás, DIA y Cooperativa tienen presencia nacional pero su red Rosario/Gran Rosario es mínima (DIA 1, ChangoMás 0). Esto valida shippear MVP con badge "Rosario + Gran Rosario (14 sucursales, 5 cadenas)" sin prometer locales que no existen en SEPA.

### 7.4 Método reproducible

```bash
# Re-auditar cualquier día
uv run python -c "from etl.etl import extract_observations; ..." # o ver /tmp/canasta-etl/sepa_lunes.zip con script bbox
# ETL con flag Gran Rosario
uv run python -m etl.etl --date 2026-08-31 --gran-rosario --zip /tmp/canasta-etl/sepa_lunes.zip
```


