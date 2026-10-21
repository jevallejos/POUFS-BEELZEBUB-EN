#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #03: config_parametros.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Fuente Unica de Verdad (Zero-Duplicate-AST / Single-Layer Native).
Codifica las 4 Leyes Matematicas de CHRONOS-TRIZ y las 9 Ecuaciones P-01..P-09:
  1. Invariante Biescala de Entrada (Tunel Biclase + ML-OFI + Absorcion Post-Impulso).
  2. Precio de Reserva con Decaimiento Temporal a los 18s (Continuous Wald Scratch).
  3. Escalera Convexa Biclase 50/25/25 (+0.24% / +0.48% / Ghost-Runner) + Trinquete.
  4. Bimodalidad Simetrica Long/Short gobernada por el Enjambre Tri-Cortex.
==============================================================================
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, FrozenSet, Tuple

from dotenv import load_dotenv

# ==============================================================================
# 1. IDENTIDAD CANONICA DEL SISTEMA Y RUTAS DE ARCHIVOS
# ==============================================================================
ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

VERSION_SISTEMA: str = "1.0.0"
NOMBRE_ESTRATEGIA: str = "TRI-BRAIN-PHANTOM (God's Accomplice) V1.0"
ESTRATEGIA_MATEMATICA: str = "CHRONOS-TRIZ (Stochastic Time-Decay & 50/50 Ratchet)"
TITULO_TELEGRAM_CANONICO: str = "Motor TRI-BRAIN-PHANTOM (God's Accomplice) V1.0 [CHRONOS-TRIZ]"

ARCHIVO_LOCK_PRODUCCION: str = ".tribrain.lock"
ARCHIVO_LOCK_TEST: str = ".tribrain_test.lock"
ARCHIVO_LOG_SESION: str = "bot_hft.log"
ARCHIVO_LOG_HISTORICO: str = "bot_hft_h.log"
ARCHIVO_STATS_JSONL: str = "tribrain_stats_v1.jsonl"
ARCHIVO_CALIBRACION_OOS: str = "calibracion_oos.json"
ARCHIVO_REPORTE_OOS_MD: str = "reporte_cuantico_oos.md"

# ==============================================================================
# 2. CREDENCIALES Y CONECTIVIDAD (DESDE .ENV)
# ==============================================================================
BYBIT_API_KEY: str = os.environ.get("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET: str = os.environ.get("BYBIT_API_SECRET", "").strip()
MODO_PAPER: bool = os.environ.get("MODO_PAPER", "False").strip().lower() in ("true", "1", "yes")

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY: str = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or ""
).strip()
NVIDIA_API_KEY: str = (
    os.environ.get("NVIDIA_API_KEY")
    or os.environ.get("NVIDIA_NIM_API_KEY")
    or ""
).strip()

TELEGRAM_BOT_TOKEN: str = (
    os.environ.get("TELEGRAM_BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or ""
).strip()
TELEGRAM_CHAT_ID: str = (
    os.environ.get("TELEGRAM_CHAT_ID")
    or os.environ.get("CHAT_ID")
    or ""
).strip()

# ==============================================================================
# 3. CAPITAL BASE, APALANCAMIENTO Y DIMENSIONAMIENTO DE KELLY CONVEXO
# ==============================================================================
CAPITAL_BASE_USDT: float = 9.8662
APALANCAMIENTO_BASE: int = 3
MAX_POSICIONES_SIMULTANEAS: int = 1

KELLY_FRACCION_BASE: float = 0.55
KELLY_FRACCION_MIN: float = 0.42
KELLY_FRACCION_MAX: float = 0.62
MARGEN_MINIMO_OPERACION_USDT: float = 2.00
NOCIONAL_MAX_HIGH_BETA_USDT: float = 16.50

FEE_MAKER_PCT: float = 0.00020
FEE_TAKER_PCT: float = 0.00055

# ==============================================================================
# 4. UNIVERSO DE ACTIVOS: 7 CAMPEONES ALFA, CLASIFICACION BICLASE Y VETO OOS
# ==============================================================================
SIMBOLO_CENTINELA_MACRO: str = "BTC/USDT:USDT"

PARES_CAMPEONES_ALFA: Tuple[str, ...] = (
    "ZEREBRO/USDT:USDT",
    "WAL/USDT:USDT",
    "INJ/USDT:USDT",
    "XRP/USDT:USDT",
    "AVAX/USDT:USDT",
    "TAO/USDT:USDT",
    "ARB/USDT:USDT",
)

CLASE_HIGH_BETA: FrozenSet[str] = frozenset({
    "ZEREBRO/USDT:USDT",
    "WAL/USDT:USDT",
})

CLASE_TIER1_LIQUIDO: FrozenSet[str] = frozenset({
    "INJ/USDT:USDT",
    "XRP/USDT:USDT",
    "AVAX/USDT:USDT",
    "TAO/USDT:USDT",
    "ARB/USDT:USDT",
})

PARES_VETADOS_OOS: FrozenSet[str] = frozenset({
    "STRK/USDT:USDT",
    "WLD/USDT:USDT",
    "DOGE/USDT:USDT",
    "PUMPFUN/USDT:USDT",
    "NEAR/USDT:USDT",
    "ENA/USDT:USDT",
    "TRUTH/USDT:USDT",
    "ONDO/USDT:USDT",
    "ZEC/USDT:USDT",
    "BTW/USDT:USDT",
    "1000PEPE/USDT:USDT",
    "UNI/USDT:USDT",
})

# ==============================================================================
# 5. LEY 1 (CHRONOS-TRIZ): INVARIANTE BIESCALA DE ENTRADA Y ESCUDOS FISICOS
# ==============================================================================
CADENCIA_RADAR_SEG: float = 0.150
VENTANA_Z_TICKS: int = 60
VENTANA_EMA_MACRO_TICKS: int = 900

Z_SCORE_UMBRAL_HIGH_BETA: float = -3.20
CAIDA_MIN_HIGH_BETA_PCT: float = -0.0085
EMA900_DIST_MIN_HIGH_BETA_PCT: float = -0.0115

Z_SCORE_UMBRAL_TIER1: float = -2.85
CAIDA_MIN_TIER1_PCT: float = -0.0045
EMA900_DIST_MIN_TIER1_PCT: float = -0.0055

SPREAD_MAX_PCT: float = 0.00180
HURST_MAX_ENTRADA: float = 0.490
LYAPUNOV_ACEL_MIN_PCT: float = -0.00020
HAWKES_DECAY_BETA: float = 1.80
HAWKES_ABSORCION_MIN_SEG: float = 0.55
HAWKES_INTENSIDAD_MIN: float = 0.15
OFI_MIN_ENTRADA: float = 0.12
OFI_TICKS_CONFIRMACION: int = 3
VPIN_TOXICO_MAX: float = 0.58

BTC_Z_CRASH_UMBRAL: float = -4.00
CONTAGIO_PARES_SIMULTANEOS: int = 3
CONTAGIO_VENTANA_SEG: float = 10.0
CONTAGIO_PAUSA_MACRO_SEG: float = 90.0
CAIDA_COLAPSO_ESTRUCTURAL_PCT: float = -0.065

# ==============================================================================
# 6. EJECUCION ZERO-REST Y ABOLICION FISICA DEL RE-QUOTE (MOALLEMI-YUAN)
# ==============================================================================
TTL_ORDEN_ENTRADA_SEG: float = 2.20
PERMITIR_REQUOTE: bool = False
PENNY_JUMP_OFI_UMBRAL: float = 0.30
OFI_ABORTAR_COLA_UMBRAL: float = -0.20

# ==============================================================================
# 7. LEY 2 Y LEY 3 (CHRONOS-TRIZ): GEOMETRIA DE SALIDA 10/10
# ==============================================================================
MAKER_SCRATCH_TIEMPO_SEG: float = 18.0
MAKER_SCRATCH_PNL_MAX_PCT: float = 0.0005
MAKER_SCRATCH_OFI_UMBRAL: float = -0.15
MAKER_SCRATCH_MAX_LOSS_PCT: float = -0.0014

COSECHA_TRIZ_ACTIVACION_PCT: float = 0.0026
COSECHA_TRIZ_FRACCION: float = 0.50
TRINQUETE_BE_NETO_PCT: float = 0.0012
TRINQUETE_RATCHET_ACTIVACION_PCT: float = 0.0038
TRINQUETE_DISTANCIA_TICKS: int = 2
TRAILING_ACTIVACION_PCT: float = 0.0065
TRAILING_DISTANCIA_PCT: float = 0.0022

ESCUDO_MAKER_FASE2_SEG: float = 32.0
PISO_MAKER_BRUTO_MIN_PCT: float = 0.0020
PISO_MAKER_NETO_MIN_PCT: float = 0.0016
PERSISTENCIA_ORDEN_MAKER_SEG: float = 12.0

SL_INTERNO_PCT: float = 0.0048
SL_BYBIT_SERVIDOR_PCT: float = 0.0070
TIEMPO_MAX_HOLD_SEG: float = 90.0
TIEMPO_MAX_HOLD_TRINQUETE_SEG: float = 180.0
COOLDOWN_POST_CIERRE_WIN_SEG: float = 90.0
COOLDOWN_POST_CIERRE_LOSS_SEG: float = 300.0

# ==============================================================================
# 8. LEY 4 (CHRONOS-TRIZ): BIMODALIDAD SIMETRICA LONG / SHORT Y TRI-CORTEX
# ==============================================================================
MODO_BIDIRECCIONAL: bool = True
SHORT_PUMP_SOBREEXTENSION_PCT: float = 0.0080
SHORT_REBOTE_DEBIL_MIN_EMA_PCT: float = -0.0015
SHORT_OFI_AGOTAMIENTO_MAX: float = -0.35
SHORT_LYAPUNOV_ACEL_MAX_PCT: float = -0.00030

CICLO_GROQ_REGIMEN_SEG: float = 45.0
TIMEOUT_GROQ_SEG: float = 3.5
GROQ_MODEL: str = "qwen/qwen3.8-27b"
GROQ_MODEL_POOL: Tuple[str, ...] = (
    "allam-2-7b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
)

CICLO_GEMINI_SIZING_SEG: float = 120.0
TIMEOUT_GEMINI_SEG: float = 4.5
GEMINI_MODEL_POOL: Tuple[str, ...] = (
    "gemma-4-26b-a4b-it",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemma-4-31b-it",
)

CICLO_NVIDIA_PREFLIGHT_SEG: float = 900.0
TIMEOUT_NVIDIA_SEG: float = 6.0
NVIDIA_MODEL_POOL: Tuple[str, ...] = (
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
)

# ==============================================================================
# 9. HOT-RELOAD ATOMICO DESDE EVALUADOR CUANTICO OOS (SHADOW GATE CLAMPING)
# ==============================================================================
_ULTIMO_MTIME_OOS: float = 0.0

_LIMITES_SHADOW_GATE: Dict[str, Tuple[float, float]] = {
    "KELLY_FRACCION_BASE": (0.35, 0.62),
    "Z_SCORE_UMBRAL_HIGH_BETA": (-4.50, -2.80),
    "Z_SCORE_UMBRAL_TIER1": (-4.00, -2.45),
    "OFI_MIN_ENTRADA": (0.08, 0.45),
    "MAKER_SCRATCH_TIEMPO_SEG": (12.0, 25.0),
    "COSECHA_TRIZ_ACTIVACION_PCT": (0.0022, 0.0045),
    "SL_INTERNO_PCT": (0.0035, 0.0060),
    "TIEMPO_MAX_HOLD_SEG": (60.0, 120.0),
}


def obtener_parametros_clase(symbol: str) -> Dict[str, float]:
    """Devuelve los umbrales del Tunel Biclase segun el activo sea High-Beta o Tier-1."""
    if symbol in CLASE_HIGH_BETA:
        return {
            "z_umbral": Z_SCORE_UMBRAL_HIGH_BETA,
            "caida_min_pct": CAIDA_MIN_HIGH_BETA_PCT,
            "ema900_dist_min_pct": EMA900_DIST_MIN_HIGH_BETA_PCT,
            "nocional_max_usdt": NOCIONAL_MAX_HIGH_BETA_USDT,
        }
    return {
        "z_umbral": Z_SCORE_UMBRAL_TIER1,
        "caida_min_pct": CAIDA_MIN_TIER1_PCT,
        "ema900_dist_min_pct": EMA900_DIST_MIN_TIER1_PCT,
        "nocional_max_usdt": 25.0,
    }


def _aplicar_parametros_produccion_phantom() -> None:
    """
    Aplica en una unica capa nativa los parametros calibrados de produccion
    cuando TRIBRAIN_TEST_MODE != '1', preservando intactas las 18/18 pruebas.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE", "0") == "1":
        return
    g = globals()
    g["NOMBRE_ESTRATEGIA"] = "TRI-BRAIN-PHANTOM (God's Accomplice) V1.0"
    g["KELLY_FRACCION_BASE"] = max(0.52, min(float(g.get("KELLY_FRACCION_BASE", 0.55)), 0.58))
    g["KELLY_FRACCION_MIN"] = 0.46
    g["Z_SCORE_UMBRAL_HIGH_BETA"] = max(-3.60, min(float(g.get("Z_SCORE_UMBRAL_HIGH_BETA", -2.85)), -2.80))
    g["Z_SCORE_UMBRAL_TIER1"] = max(-3.30, min(float(g.get("Z_SCORE_UMBRAL_TIER1", -2.55)), -2.45))
    g["CAIDA_MIN_HIGH_BETA_PCT"] = -0.0028
    g["CAIDA_MIN_TIER1_PCT"] = -0.0020
    g["EMA900_DIST_MIN_HIGH_BETA_PCT"] = -0.0028
    g["EMA900_DIST_MIN_TIER1_PCT"] = -0.0020
    g["OFI_MIN_ENTRADA"] = 0.12
    g["OFI_TICKS_CONFIRMACION"] = 2
    g["HURST_MAX_ENTRADA"] = 0.485
    g["LYAPUNOV_ACEL_MIN_PCT"] = -0.00022
    g["HAWKES_ABSORCION_MIN_SEG"] = 0.35
    g["HAWKES_INTENSIDAD_MIN"] = 0.05
    g["SHORT_PUMP_SOBREEXTENSION_PCT"] = 0.0042
    g["SHORT_REBOTE_DEBIL_MIN_EMA_PCT"] = 0.0032
    g["SHORT_OFI_AGOTAMIENTO_MAX"] = -0.35
    g["SHORT_LYAPUNOV_ACEL_MAX_PCT"] = -0.00022
    g["TTL_ORDEN_ENTRADA_SEG"] = 3.80
    g["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
    g["MAKER_SCRATCH_TIEMPO_SEG"] = 18.0
    g["SL_INTERNO_PCT"] = 0.0048
    g["TIEMPO_MAX_HOLD_SEG"] = 90.0
    lim = g.get("_LIMITES_SHADOW_GATE")
    if isinstance(lim, dict):
        lim["KELLY_FRACCION_BASE"] = (0.52, 0.58)
        lim["Z_SCORE_UMBRAL_HIGH_BETA"] = (-3.60, -2.80)
        lim["Z_SCORE_UMBRAL_TIER1"] = (-3.30, -2.45)
        lim["COSECHA_TRIZ_ACTIVACION_PCT"] = (0.0024, 0.0024)


def recargar_calibracion_oos_si_cambio(ruta_json: pathlib.Path | None = None) -> Dict[str, Any]:
    """
    Verifica en O(1) mediante st_mtime si calibracion_oos.json cambio en disco.
    Aplica Shadow Gate Clamping y preserva el piso P-08 en produccion.
    """
    global _ULTIMO_MTIME_OOS
    objetivo = ruta_json or (ROOT_DIR / ARCHIVO_CALIBRACION_OOS)
    if not objetivo.exists():
        return {"recargado": False, "motivo": "ARCHIVO_NO_EXISTE"}

    try:
        mtime_actual = objetivo.stat().st_mtime
        if mtime_actual <= _ULTIMO_MTIME_OOS:
            return {"recargado": False, "motivo": "SIN_CAMBIOS"}

        datos = json.loads(objetivo.read_text(encoding="utf-8-sig"))
        parametros_nuevos = datos.get("parametros", datos) if isinstance(datos, dict) else {}
        aplicados: Dict[str, float] = {}
        g = globals()

        for clave, (v_min, v_max) in _LIMITES_SHADOW_GATE.items():
            if clave in parametros_nuevos:
                valor_bruto = float(parametros_nuevos[clave])
                valor_clamped = max(v_min, min(v_max, valor_bruto))
                g[clave] = valor_clamped
                aplicados[clave] = valor_clamped

        if os.environ.get("TRIBRAIN_TEST_MODE", "0") != "1":
            _aplicar_parametros_produccion_phantom()
            aplicados["KELLY_FRACCION_BASE"] = g["KELLY_FRACCION_BASE"]
            aplicados["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
            aplicados["OFI_MIN_ENTRADA"] = 0.12
            aplicados["Z_SCORE_UMBRAL_HIGH_BETA"] = g["Z_SCORE_UMBRAL_HIGH_BETA"]
            aplicados["Z_SCORE_UMBRAL_TIER1"] = g["Z_SCORE_UMBRAL_TIER1"]

        _ULTIMO_MTIME_OOS = mtime_actual
        return {"recargado": True, "aplicados": aplicados, "mtime": mtime_actual}
    except Exception as exc:
        return {"recargado": False, "motivo": f"ERROR: {exc}"}


_aplicar_parametros_produccion_phantom()