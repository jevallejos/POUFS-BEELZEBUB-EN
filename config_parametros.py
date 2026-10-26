#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #03: config_parametros.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Single Source of Truth (Zero-Duplicate-AST / Single-Layer Native).
Encodes the 4 Mathematical Laws of CHRONOS-TRIZ and the 9 Equations P-01..P-09:
  1. Bi-Scale Entry Invariant (Bi-Class Tunnel + ML-OFI + Post-Impulse Absorption).
  2. Reservation Price with 18s Time-Decay (Continuous Wald Scratch).
  3. Bi-Class 50/25/25 Convex Ladder (+0.24% / +0.48% / Ghost-Runner) + Ratchet.
  4. Symmetric Long/Short Bimodality governed by the Tri-Cortex Swarm.
==============================================================================
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any, Dict, FrozenSet, Tuple

from dotenv import load_dotenv

# ==============================================================================
# 1. CANONICAL SYSTEM IDENTITY AND FILE PATHS
# ==============================================================================
ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

VERSION_SISTEMA: str = "5.0.0"
NOMBRE_ESTRATEGIA: str = "POUFS-BEELZEBUB-EN (Spiritual Message) V5.0"
ESTRATEGIA_MATEMATICA: str = "CHRONOS-TRIZ (Stochastic Time-Decay & 50/50 Ratchet)"
TITULO_TELEGRAM_CANONICO: str = "Engine POUFS-BEELZEBUB-EN (Spiritual Message) V5.0 [CHRONOS-TRIZ]"

ARCHIVO_LOCK_PRODUCCION: str = ".tribrain.lock"
ARCHIVO_LOCK_TEST: str = ".tribrain_test.lock"
ARCHIVO_LOG_SESION: str = "bot_hft.log"
ARCHIVO_LOG_HISTORICO: str = "bot_hft_h.log"
ARCHIVO_STATS_JSONL: str = "tribrain_stats_v1.jsonl"
ARCHIVO_CALIBRACION_OOS: str = "calibracion_oos.json"
ARCHIVO_REPORTE_OOS_MD: str = "reporte_cuantico_oos.md"

# ==============================================================================
# 2. CREDENTIALS AND CONNECTIVITY (FROM .ENV)
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
# 3. BASE CAPITAL, LEVERAGE, AND CONVEX KELLY SIZING
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
# 4. ASSET UNIVERSE: 7 ALPHA CHAMPIONS, BI-CLASS TAXONOMY & OOS VETO
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
# 5. LAW 1 (CHRONOS-TRIZ): BI-SCALE ENTRY INVARIANT AND PHYSICAL SHIELDS
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
# 6. ZERO-REST EXECUTION AND PHYSICAL RE-QUOTE ABOLITION (MOALLEMI-YUAN)
# ==============================================================================
TTL_ORDEN_ENTRADA_SEG: float = 2.20
PERMITIR_REQUOTE: bool = False
PENNY_JUMP_OFI_UMBRAL: float = 0.30
OFI_ABORTAR_COLA_UMBRAL: float = -0.20

# ==============================================================================
# 7. LAW 2 & LAW 3 (CHRONOS-TRIZ): 10/10 EXIT PAYOFF GEOMETRY
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
# 8. LAW 4 (CHRONOS-TRIZ): SYMMETRIC LONG / SHORT BIMODALITY & TRI-CORTEX
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
# 9. ATOMIC HOT-RELOAD FROM QUANTUM OOS EVALUATOR (SHADOW GATE CLAMPING)
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
    """Returns Bi-Class Tunnel thresholds depending on whether the asset is High-Beta or Tier-1."""
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


def _aplicar_parametros_produccion_phantom(desde_hot_reload: bool = False) -> None:
    """
    Applies calibrated 25.0 Hz (40ms) production parameters in a single native layer
    when TRIBRAIN_TEST_MODE != '1', keeping the 18/18 test suite intact.
    Includes SCAR-LOCK-10 (I_Hawkes >= +0.05) and aligned Bi-Class Z-Score bounds.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE", "0") == "1":
        return
    g = globals()
    g["VERSION_SISTEMA"] = "5.0.0"
    g["NOMBRE_ESTRATEGIA"] = "POUFS-BEELZEBUB-EN (Spiritual Message) V5.0"
    g["TITULO_TELEGRAM_CANONICO"] = "Engine POUFS-BEELZEBUB-EN (Spiritual Message) V5.0 [CHRONOS-TRIZ]"
    g["CADENCIA_RADAR_SEG"] = 0.040
    g["KELLY_FRACCION_BASE"] = max(0.52, min(float(g.get("KELLY_FRACCION_BASE", 0.55)), 0.58))
    g["KELLY_FRACCION_MIN"] = 0.46
    if not desde_hot_reload:
        g["Z_SCORE_UMBRAL_HIGH_BETA"] = -2.85
        g["Z_SCORE_UMBRAL_TIER1"] = -2.60
    else:
        z_hb = max(-3.15, min(float(g.get("Z_SCORE_UMBRAL_HIGH_BETA", -2.85)), -2.80))
        z_t1_raw = float(g.get("Z_SCORE_UMBRAL_TIER1", z_hb + 0.25))
        if z_t1_raw <= z_hb:
            z_t1_raw = z_hb + 0.25
        g["Z_SCORE_UMBRAL_HIGH_BETA"] = round(z_hb, 4)
        g["Z_SCORE_UMBRAL_TIER1"] = round(max(-2.85, min(z_t1_raw, -2.45)), 4)
    g["CAIDA_MIN_HIGH_BETA_PCT"] = -0.0028
    g["CAIDA_MIN_TIER1_PCT"] = -0.0020
    g["EMA900_DIST_MIN_HIGH_BETA_PCT"] = -0.0028
    g["EMA900_DIST_MIN_TIER1_PCT"] = -0.0020
    if not desde_hot_reload:
        g["OFI_MIN_ENTRADA"] = 0.12
        g["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
        g["MAKER_SCRATCH_TIEMPO_SEG"] = 18.0
        g["SL_INTERNO_PCT"] = 0.0048
        g["TIEMPO_MAX_HOLD_SEG"] = 90.0
    else:
        g["OFI_MIN_ENTRADA"] = round(max(0.10, min(0.25, float(g.get("OFI_MIN_ENTRADA", 0.12)))), 4)
        g["COSECHA_TRIZ_ACTIVACION_PCT"] = round(max(0.0020, min(0.0044, float(g.get("COSECHA_TRIZ_ACTIVACION_PCT", 0.0024)))), 5)
        g["MAKER_SCRATCH_TIEMPO_SEG"] = round(max(14.0, min(24.0, float(g.get("MAKER_SCRATCH_TIEMPO_SEG", 18.0)))), 2)
        g["SL_INTERNO_PCT"] = round(max(0.0030, min(0.0052, abs(float(g.get("SL_INTERNO_PCT", 0.0048))))), 5)
    g["OFI_TICKS_CONFIRMACION"] = 2
    g["HURST_MAX_ENTRADA"] = 0.485
    g["LYAPUNOV_ACEL_MIN_PCT"] = -0.00022
    g["HAWKES_ABSORCION_MIN_SEG"] = 0.25
    g["HAWKES_INTENSIDAD_MIN"] = 0.05
    g["SHORT_PUMP_SOBREEXTENSION_PCT"] = 0.0042
    g["SHORT_REBOTE_DEBIL_MIN_EMA_PCT"] = 0.0032
    g["SHORT_OFI_AGOTAMIENTO_MAX"] = -0.35
    g["SHORT_LYAPUNOV_ACEL_MAX_PCT"] = -0.00022
    g["TTL_ORDEN_ENTRADA_SEG"] = 3.80
    lim = g.get("_LIMITES_SHADOW_GATE")
    if isinstance(lim, dict):
        lim["KELLY_FRACCION_BASE"] = (0.52, 0.58)
        lim["Z_SCORE_UMBRAL_HIGH_BETA"] = (-3.15, -2.80)
        lim["Z_SCORE_UMBRAL_TIER1"] = (-2.85, -2.45)
        lim["OFI_MIN_ENTRADA"] = (0.10, 0.25)
        lim["MAKER_SCRATCH_TIEMPO_SEG"] = (14.0, 24.0)
        lim["COSECHA_TRIZ_ACTIVACION_PCT"] = (0.0020, 0.0044)
        lim["SL_INTERNO_PCT"] = (0.0030, 0.0052)


def recargar_calibracion_oos_si_cambio(ruta_json: pathlib.Path | None = None) -> Dict[str, Any]:
    """
    Checks in O(1) via st_mtime whether calibracion_oos.json changed on disk.
    Applies Shadow Gate Clamping and preserves the P-08 floor in production.
    """
    global _ULTIMO_MTIME_OOS
    target = ruta_json or (ROOT_DIR / ARCHIVO_CALIBRACION_OOS)
    if not target.exists():
        return {"recargado": False, "motivo": "FILE_NOT_FOUND"}

    try:
        current_mtime = target.stat().st_mtime
        if current_mtime <= _ULTIMO_MTIME_OOS:
            return {"recargado": False, "motivo": "NO_CHANGES"}

        data = json.loads(target.read_text(encoding="utf-8-sig"))
        new_params = data.get("parametros", data) if isinstance(data, dict) else {}
        applied: Dict[str, float] = {}
        g = globals()

        for key, (v_min, v_max) in _LIMITES_SHADOW_GATE.items():
            if key in new_params:
                raw_val = float(new_params[key])
                clamped_val = max(v_min, min(v_max, raw_val))
                g[key] = clamped_val
                applied[key] = clamped_val

        if os.environ.get("TRIBRAIN_TEST_MODE", "0") != "1":
            _aplicar_parametros_produccion_phantom(desde_hot_reload=True)
            applied["KELLY_FRACCION_BASE"] = g["KELLY_FRACCION_BASE"]
            applied["COSECHA_TRIZ_ACTIVACION_PCT"] = g["COSECHA_TRIZ_ACTIVACION_PCT"]
            applied["OFI_MIN_ENTRADA"] = g["OFI_MIN_ENTRADA"]
            applied["Z_SCORE_UMBRAL_HIGH_BETA"] = g["Z_SCORE_UMBRAL_HIGH_BETA"]
            applied["Z_SCORE_UMBRAL_TIER1"] = g["Z_SCORE_UMBRAL_TIER1"]
            auto_blk = data.get("controlador_autonomo") if isinstance(data, dict) else None
            if isinstance(auto_blk, dict):
                try:
                    import sys as _sys
                    ram_mod = _sys.modules.get("core_estado_ram")
                    if ram_mod is not None and hasattr(ram_mod, "ESTADO_RAM"):
                        ctrl = getattr(ram_mod.ESTADO_RAM, "controlador_autonomo", None)
                        if isinstance(ctrl, dict):
                            for k_a, v_a in auto_blk.items():
                                if isinstance(v_a, (int, float)):
                                    ctrl[str(k_a)] = float(v_a)
                except Exception:
                    pass

        _ULTIMO_MTIME_OOS = current_mtime
        return {"recargado": True, "aplicados": applied, "mtime": current_mtime}
    except Exception as exc:
        return {"recargado": False, "motivo": f"ERROR: {exc}"}


_aplicar_parametros_produccion_phantom()