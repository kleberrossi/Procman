# -*- coding: utf-8 -*-

# Densidades típicas (kg/m³). Valores médios para estimativa.
DENSIDADES = {
    # Polietilenos / Polipropilenos
    "PEBD": 920,   # Polietileno de baixa densidade (LDPE)
    "LDPE": 920,
    "PEAD": 950,   # Polietileno de alta densidade (HDPE)
    "HDPE": 950,
    "PE":   930,   # valor médio caso venha só "PE"
    "PP":   905,   # Polipropileno (cast)
    "BOPP": 905,   # PP biorientado

    # Extras úteis (opcionais; pode ajustar depois)
    "PET":  1380,  # Polietileno tereftalato
    "PVC":  1380,  # PVC (amplo intervalo; estimativa)
    "PA":   1140,  # Nylon (PA6 ~ 1.13-1.15 g/cm³)
    "EVOH": 1200,  # copolímero etileno-vinil álcool (médio)
}

# Sinônimos -> chave base do dicionário acima
_MATERIAL_ALIAS = {
    "LDPE": "PEBD",
    "HDPE": "PEAD",
    "POLIETILENO BAIXA": "PEBD",
    "POLIETILENO ALTA": "PEAD",
    "POLIPROPILENO": "PP",
    "NYLON": "PA",
}


def _normalize_material(material: str) -> str:
    m = (material or "").strip().upper()
    if m in DENSIDADES:
        return m
    return _MATERIAL_ALIAS.get(m, m)


def _as_float(x, default=0.0) -> float:
    """
    Converte string com vírgula/ponto para float.
    """
    if x is None:
        return float(default)
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return float(default)


def _nonneg(x: float) -> float:
    return x if x > 0 else 0.0


def massa_por_unidade(
    material: str,
    esp_um: int,
    largura_mm: int,
    altura_mm: int,
    sanfona_mm: int = 0,
    fator_extra: float = 0.0
) -> float:
    """
    Retorna massa aproximada (kg) por unidade de embalagem.

    Fórmula:
        massa = área * espessura * densidade
      - largura_efetiva considera a sanfona (2x).
      - espessura em µm convertida para metros (µm/1e6).
      - densidade em kg/m³ retirada de DENSIDADES (fallback PEBD=920).
      - fator_extra é percentual adicional opcional (ex.: reforços, perdas).

    Parâmetros podem vir como string com vírgula/ponto. Negativos viram 0.
    """
    # Normalizações/segurança
    material_key = _normalize_material(material)
    dens = float(DENSIDADES.get(material_key, DENSIDADES["PEBD"]))

    esp_um_f     = _nonneg(_as_float(esp_um))
    largura_mm_f = _nonneg(_as_float(largura_mm))
    altura_mm_f  = _nonneg(_as_float(altura_mm))
    sanfona_mm_f = _nonneg(_as_float(sanfona_mm))
    fator_extra_f = max(_as_float(fator_extra), 0.0)

    largura_efetiva_mm = largura_mm_f + 2.0 * sanfona_mm_f
    area_m2 = (largura_efetiva_mm * altura_mm_f) / 1_000_000.0  # mm² -> m²
    esp_m   = esp_um_f / 1_000_000.0                            # µm -> m

    massa = area_m2 * esp_m * dens  # kg
    return float(massa * (1.0 + fator_extra_f))


def unidades_estimadas_por_peso(peso_kg: float, massa_unid_kg: float) -> float:
    """
    Retorna a quantidade estimada de unidades em um lote a partir do peso líquido.
    Se massa_unid_kg <= 0, retorna 0.
    """
    peso = _nonneg(_as_float(peso_kg))
    mu   = _as_float(massa_unid_kg)
    if mu <= 0:
        return 0.0
    return float(peso / mu)


def unidades_minimas(qtd_solicitada_un: int, toler_percent: float) -> int:
    """
    Retorna o número mínimo de unidades aceitas, considerando a margem de tolerância (%).
    Exemplo: 1000 unidades solicitadas, tolerância 5% → mínimo = 950.
    """
    qtd = max(int(_as_float(qtd_solicitada_un)), 0)
    tol = _as_float(toler_percent)
    tol = 0.0 if tol < 0 else (100.0 if tol > 100 else tol)
    minimo = round(qtd * (1.0 - tol / 100.0))
    return int(minimo if minimo > 0 else 0)
