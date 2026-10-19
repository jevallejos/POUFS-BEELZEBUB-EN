#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #03: config_parametros.py
SISTEMA: TRI-BRAIN-SNIPER (EMPEROR TIME) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Fuente Unica de Verdad (Zero-Duplicate-AST).
Codifica las 4 Leyes Matematicas de CHRONOS-TRIZ:
  1. Invariante Biescala de Entrada (Tunel Biclase + 3 Ticks ML-OFI + Hurst).
  2. Precio de Reserva con Decaimiento Temporal a los 18s (Maker-Scratch).
  3. Cosecha Fraccionada 50/50 TRIZ (+0.26%) + Trinquete Continuo Maker.
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
NOMBRE_ESTRATEGIA: str = "Tri-Brain-Sniper (Emperor Time) v1.0"
ESTRATEGIA_MATEMATICA: str = "CHRONOS-TRIZ (Stochastic Time-Decay & 50/50 Ratchet)"
TITULO_TELEGRAM_CANONICO: str = "Motor Tri-Brain-Sniper (Emperor Time) v1.0 [CHRONOS-TRIZ]"

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
NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY", "").strip()

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
CAPITAL_BASE_USDT: float = 9.8662          # Patrimonio certificado en Estado Cero (Paso 0.2)
APALANCAMIENTO_BASE: int = 3               # Apalancamiento cruzado UTA (3x)
MAX_POSICIONES_SIMULTANEAS: int = 1        # Single-Slot Mutex (100% foco y cero colision de margen)

KELLY_FRACCION_BASE: float = 0.55          # Fraccion base de Kelly Convexo (55%)
KELLY_FRACCION_MIN: float = 0.42           # Piso defensivo ante alta volatilidad
KELLY_FRACCION_MAX: float = 0.62           # Techo maximo con sennal extrema (|Z| >= 4.5)
MARGEN_MINIMO_OPERACION_USDT: float = 2.00 # Margen minimo requerido por disparo
NOCIONAL_MAX_HIGH_BETA_USDT: float = 16.50 # Tope nocional anti-seleccion adversa en High-Beta

# Estructura de Comisiones Bybit UTA VIP 0
FEE_MAKER_PCT: float = 0.00020             # 0.020% por lado (0.040% ida y vuelta)
FEE_TAKER_PCT: float = 0.00055             # 0.055% por lado (0.110% ida y vuelta)

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
CADENCIA_RADAR_SEG: float = 0.150          # 150 ms (6.6 Hz de muestreo continuo L1/L2)
VENTANA_Z_TICKS: int = 60                  # Ventana rodante para Z-Score Bipower
VENTANA_EMA_MACRO_TICKS: int = 900         # EMA900 de referencia estructural

# 5.1 Tunel Biclase para Clase High-Beta (ZEREBRO, WAL) -> Evita entradas superficiales
Z_SCORE_UMBRAL_HIGH_BETA: float = -3.20
CAIDA_MIN_HIGH_BETA_PCT: float = -0.0085   # Exige al menos -0.85% de dislocacion local
EMA900_DIST_MIN_HIGH_BETA_PCT: float = -0.0115  # Exige -1.15% bajo EMA900 (salvo Z <= -4.50)

# 5.2 Tunel Biclase para Clase Tier-1 (INJ, XRP, AVAX, TAO, ARB)
Z_SCORE_UMBRAL_TIER1: float = -2.85
CAIDA_MIN_TIER1_PCT: float = -0.0045       # Exige al menos -0.45% de dislocacion local
EMA900_DIST_MIN_TIER1_PCT: float = -0.0055 # Exige -0.55% bajo EMA900

# 5.3 Escudos Fisicos Secuenciales (Spread, Hurst, Lyapunov, Hawkes y 3 Ticks ML-OFI)
SPREAD_MAX_PCT: float = 0.00180            # 0.180% spread relativo maximo permitido
HURST_MAX_ENTRADA: float = 0.490           # H <= 0.49 garantiza regimen de reversion a la media
LYAPUNOV_ACEL_MIN_PCT: float = -0.00020    # a >= -0.020% certifica frenado fisico del cuchillo
HAWKES_DECAY_BETA: float = 1.80            # Decaimiento exponencial del nucleo de Hawkes
HAWKES_ABSORCION_MIN_SEG: float = 0.55     # Tiempo minimo de absorcion tras pulso toxico
HAWKES_INTENSIDAD_MIN: float = 0.15        # Intensidad neta compradora minima I_Hawkes
OFI_MIN_ENTRADA: float = 0.12              # ML-OFI L1-L5 minimo requerido
OFI_TICKS_CONFIRMACION: int = 3            # 3 ticks consecutivos (450 ms) sin caer (Cero falsos picos)
VPIN_TOXICO_MAX: float = 0.58              # Bloqueo por toxicidad de flujo informacional

# 5.4 Cortafuegos de Contagio Sistemico Cross-Asset y Anti-LUNA
BTC_Z_CRASH_UMBRAL: float = -4.00          # Veto macro si BTC colapsa Z <= -4.0
CONTAGIO_PARES_SIMULTANEOS: int = 3        # >= 3 pares cayendo simultaneamente
CONTAGIO_VENTANA_SEG: float = 10.0         # dentro de una ventana de 10 segundos
CONTAGIO_PAUSA_MACRO_SEG: float = 90.0     # Pausa global del motor y evacuacion
CAIDA_COLAPSO_ESTRUCTURAL_PCT: float = -0.065 # Filtro Anti-LUNA (-6.5% con OFI <= -0.80)

# ==============================================================================
# 6. EJECUCION ZERO-REST Y ABOLICION FISICA DEL RE-QUOTE (MOALLEMI-YUAN)
# ==============================================================================
TTL_ORDEN_ENTRADA_SEG: float = 2.20        # Si no llena en 2.2s, cancela y libera margen
PERMITIR_REQUOTE: bool = False             # PROHIBIDO perseguir el precio con Re-Quote
PENNY_JUMP_OFI_UMBRAL: float = 0.30        # Cotiza best_bid + 1 tick si el spread >= 2 ticks
OFI_ABORTAR_COLA_UMBRAL: float = -0.20     # Cancela antes de 2.2s si el OFI se desploma

# ==============================================================================
# 7. LEY 2 Y LEY 3 (CHRONOS-TRIZ): GEOMETRIA DE SALIDA 10/10
# ==============================================================================
# 7.1 Ley 2: Desplazamiento de Precio de Reserva a los 18s (Avellaneda-Stoikov Maker-Scratch)
MAKER_SCRATCH_TIEMPO_SEG: float = 18.0     # Evaluacion de tesis en t = 18.0 segundos
MAKER_SCRATCH_PNL_MAX_PCT: float = 0.0005  # Si en 18s nunca supero +0.05% bruto
MAKER_SCRATCH_OFI_UMBRAL: float = -0.15    # y el flujo acumulado de 5s es adverso (< -0.15)
MAKER_SCRATCH_MAX_LOSS_PCT: float = -0.0014 # Evacua en Limit PostOnly hasta -0.14% max

# 7.2 Ley 3: Cosecha Fraccionada 50/50 TRIZ + Trinquete Continuo Maker (First-Passage Ratchet)
COSECHA_TRIZ_ACTIVACION_PCT: float = 0.0026 # En +0.26% bruto vende el 50% en Limit PostOnly
COSECHA_TRIZ_FRACCION: float = 0.50         # 50% de la posicion asegura costos y flujo de caja
TRINQUETE_BE_NETO_PCT: float = 0.0012       # Sube el SL del 50% restante a +0.12% neto
TRINQUETE_RATCHET_ACTIVACION_PCT: float = 0.0038 # Desde +0.38% persigue el pico con Limit PostOnly
TRINQUETE_DISTANCIA_TICKS: int = 2          # 2 ticks detras del maximo alcanzado
TRAILING_ACTIVACION_PCT: float = 0.0065     # +0.65% activa Trailing Stop de expansion libre
TRAILING_DISTANCIA_PCT: float = 0.0022      # 0.22% de holgura dinamica en corridas fuertes

# 7.3 Escudo de Evacuacion Ganadora (Fase 2 para posiciones con flujo sano > 32s)
ESCUDO_MAKER_FASE2_SEG: float = 32.0       # Desde los 32s busca salida pasiva ganadora
PISO_MAKER_BRUTO_MIN_PCT: float = 0.0020   # Minimo +0.20% bruto (>= 2x fee Maker + +0.16% neto)
PISO_MAKER_NETO_MIN_PCT: float = 0.0016    # Jamas cotizar salida Maker debajo de +0.16% neto
PERSISTENCIA_ORDEN_MAKER_SEG: float = 12.0 # Persistencia PFQI de ordenes Limit PostOnly

# 7.4 Stop-Loss Quirurgico Acotado y Reloj Impostergable (Cero prorrogas ocultas)
SL_INTERNO_PCT: float = 0.0048             # -0.48% Stop-Loss interno (erradica perdidas de -1.41%)
SL_BYBIT_SERVIDOR_PCT: float = 0.0070      # -0.70% Stop-Loss fisico en servidor Bybit UTA
TIEMPO_MAX_HOLD_SEG: float = 90.0          # 90s tiempo maximo absoluto sin trinquete activo
TIEMPO_MAX_HOLD_TRINQUETE_SEG: float = 180.0 # Hasta 180s solo si ya cobro Cosecha 50% y esta en BE+
COOLDOWN_POST_CIERRE_WIN_SEG: float = 90.0  # 90s de enfriamiento tras victoria
COOLDOWN_POST_CIERRE_LOSS_SEG: float = 300.0 # 300s de cuarentena tras cierre negativo

# ==============================================================================
# 8. LEY 4 (CHRONOS-TRIZ): BIMODALIDAD SIMETRICA LONG / SHORT Y TRI-CORTEX
# ==============================================================================
MODO_BIDIRECCIONAL: bool = True
SHORT_PUMP_SOBREEXTENSION_PCT: float = 0.0080   # +0.80% sobre EMA900 activa vigilancia Short
SHORT_REBOTE_DEBIL_MIN_EMA_PCT: float = -0.0015 # En regimen SHORT_ONLY permite Short cerca de EMA900
SHORT_OFI_AGOTAMIENTO_MAX: float = -0.35        # Exige colapso de flujo comprador (OFI <= -0.35)
SHORT_LYAPUNOV_ACEL_MAX_PCT: float = -0.00030   # Aceleracion negativa confirmada hacia abajo

# 8.1 Cortex 1: Groq LPU (Matriz Direccional de Regimen cada 45s — Ordenado por RTT Tokio)
CICLO_GROQ_REGIMEN_SEG: float = 45.0
TIMEOUT_GROQ_SEG: float = 3.5
GROQ_MODEL: str = "qwen/qwen3.8-27b"
GROQ_MODEL_POOL: Tuple[str, ...] = (
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
)

# 8.2 Cortex 2: Google Gemini (Dimensionamiento Anti-Fragil por Magnitud de Dislocacion)
CICLO_GEMINI_SIZING_SEG: float = 120.0
TIMEOUT_GEMINI_SEG: float = 4.5
GEMINI_MODEL_POOL: Tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)

# 8.3 Cortex 3: NVIDIA NIM / DeepSeek (Calibracion Pre-Vuelo cada 15m + Auditoria Post-Loss)
CICLO_NVIDIA_PREFLIGHT_SEG: float = 900.0
TIMEOUT_NVIDIA_SEG: float = 6.0
NVIDIA_MODEL_POOL: Tuple[str, ...] = (
    "deepseek-ai/deepseek-v3.2",
    "qwen/qwen3-next-80b-a3b-instruct",
)

# ==============================================================================
# 9. HOT-RELOAD ATOMICO DESDE EVALUADOR CUANTICO OOS (SHADOW GATE CLAMPING)
# ==============================================================================
_ULTIMO_MTIME_OOS: float = 0.0

# Limites fisicos inquebrantables (Shadow Gate): ninguna calibracion OOS puede salir de estos rangos
_LIMITES_SHADOW_GATE: Dict[str, Tuple[float, float]] = {
    "KELLY_FRACCION_BASE": (0.35, 0.62),
    "Z_SCORE_UMBRAL_HIGH_BETA": (-4.50, -2.90),
    "Z_SCORE_UMBRAL_TIER1": (-4.00, -2.60),
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


def recargar_calibracion_oos_si_cambio(ruta_json: pathlib.Path | None = None) -> Dict[str, Any]:
    """
    Verifica en O(1) mediante st_mtime si calibracion_oos.json cambio en disco.
    Si cambio, aplica Shadow Gate Clamping y actualiza las variables en RAM sin reiniciar el bot.
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

        _ULTIMO_MTIME_OOS = mtime_actual
        return {"recargado": True, "aplicados": aplicados, "mtime": mtime_actual}
    except Exception as exc:
        return {"recargado": False, "motivo": f"ERROR: {exc}"}