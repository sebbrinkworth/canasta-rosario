from etl.etl import price_per_unit, price_per_unit_calc, match_product

def test_price_per_unit_kg():
    val, unit = price_per_unit(1000, 500, "GRM")
    assert unit=="kg"
    assert val==2000

def test_price_per_unit_litro():
    val, unit = price_per_unit(1500, 1500, "MLT")
    assert unit=="L"
    assert val==1000

def test_price_per_unit_calc_wrapper():
    val, unit = price_per_unit_calc("1500", "1.5", "LTR")
    assert unit=="L"
    assert val==1000

def test_ean_matching_keyword():
    assert match_product("Leche entera La Serenisima 1L")=="leche_entera"
    assert match_product("Yerba Mate Rosamonte 1kg")=="yerba"
    assert match_product("Aceite Girasol Natura 1.5L")=="aceite_girasol"
    assert match_product("Detergente Magistral 750ml")=="detergente"
    assert match_product("Producto inexistente xyz") is None

def test_normalize():
    assert match_product("AZÚCAR Ledesma 1kg")=="azucar"

def test_rejects_false_positive_leche():
    assert match_product("PREF.PAN D LECHE CJ.X 100 UDS") is None
    assert match_product("ALIMENTO GATOS KINGFOOD POLLO Y LECHE 85GR") is None
    assert match_product("LECHE ENTERA COTO SCH 1 LTR") == "leche_entera"

def test_rejects_false_positive_arroz_etc():
    assert match_product("Barrita de Arroz CROWIE Limon 3u") is None
    assert match_product("Barra de Cereal Muecas SIN AZUCAR 45g") is None
    assert match_product("HARINA INTEGRAL MORIXE 1kg") is None
    assert match_product("CAPELLETIS DE POLLO Y VERDURA") is None
    assert match_product("PAPA BASTON SIMPLOT 700g") is None

def test_outlier_rejection():
    from etl.etl import filter_outliers
    obs = [
        {"canonical_id":"papa","price_per_unit":2000,"chain_label":"A","descripcion":"a","chain_id":"2"},
        {"canonical_id":"papa","price_per_unit":2200,"chain_label":"B","descripcion":"b","chain_id":"10"},
        {"canonical_id":"papa","price_per_unit":1800,"chain_label":"C","descripcion":"c","chain_id":"12"},
        {"canonical_id":"papa","price_per_unit":95,"chain_label":"D","descripcion":"d","chain_id":"15"},  # low outlier
        {"canonical_id":"papa","price_per_unit":35000,"chain_label":"E","descripcion":"e","chain_id":"9"},  # high outlier >6.5x median ~2000
    ]
    kept, rej, med = filter_outliers(obs)
    assert any(r[0]["descripcion"]=="d" for r in rej)
    assert any(r[0]["descripcion"]=="e" for r in rej)
    assert len(kept)==3

def test_ean_priority():
    # EAN prefix should win even if description ambiguous
    assert match_product("ALIMENTO CUALQUIERA", ean="7790741234567") == "leche_entera"
    assert match_product("PAN RALLADO", ean="7790740000000") == "leche_entera"  # EAN trumps keyword negative

def test_strict_pan_lactal():
    assert match_product("PAN RALLADO") is None
    assert match_product("PAN LACTAL X 600GRS") == "pan_lactal"
