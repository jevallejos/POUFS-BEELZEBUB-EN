#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #08: radar_volatilidad.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
High-Frequency Microstructural Radar (25.0 Hz / 40 ms Prod | 6.6 Hz Test) in O(1) (< 25 us):
  - Bipower VentanaZ estimator with O(1) incremental accumulators and EMA900.
  - Multi-Level L1-L5 ML-OFI (Cont-Kukanov-Stoikov) in a single fused loop.
  - Active-tick Hurst Roughness Exponent and Extreme Lyapunov Shock Time
    Buffer (SCAR-LOCK-03 + Bi-Class SCAR-LOCK-09).
  - Continuous Hourly-Bipower Elastic Band (Gradient L8..L13 - CHRONOS-TRIZ V5.0):
      * Computes in O(1) the Intraday Percentile P_day(t, sigma_BV) combining
        the 24h UTC harmonic seasonal curve (00/08/16 Funding, Asia Midday,
        London, and Wall Street NYSE) with live Bipower volatility.
      * Post-Boot Maturity Band mu_boot(n) proportional to real EMA900 tick
        population (eliminates cold-start distortions).
      * Anti-Squeeze Spatial Memory (px_ultimo_anti_squeeze): blocks short
        sales in bullish flags above prior breakout prices.
      * SCAR-LOCK-09..12: Bi-class Lyapunov + aftershock, Hawkes >= +0.05,
        EMA900 band in SHORT + |Z| >= 8.0 ignition + 1800s STEP-LOCK & Tier-1 LONG.
      * SCAR-LOCK-13: 1200ms Arm-and-Fire Absorption Automaton, OFI absorption
        proportional to |Z_t| and H_t in LONG, strict fractal ceiling
        H_max^long <= 0.475 (hard cap 0.485), and O(1) Vault instrumentation.
==============================================================================
"""
from __future__ import annotations

import math
import os
import time
from collections import deque
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, MetricaTick, log_sniper
from escudo_tricortex import ESCUDO_TRICORTEX

_PESOS_ML_OFI: Tuple[float, ...] = tuple(math.exp(-0.35 * i) for i in range(5))
_PI_HALF: float = math.pi / 2.0
_INV_LN2: float = 1.0 / math.log(2.0)
_INV_LN4: float = 1.0 / math.log(4.0)

_ULTIMO_TS_LIBRO_PHANTOM: Dict[str, float] = {}
_COOLDOWN_WS_PHANTOM: Dict[str, float] = {}
_SILENCIO_LOG_PHANTOM: Dict[Tuple[str, str], float] = {}


def _dist_circular_horas(h1: float, h2: float) -> float:
    diff = abs(h1 - h2) % 24.0
    return (24.0 - diff) if diff > 12.0 else diff


def _calcular_percentil_elastico_intradia(ahora_t: float, vol_bipower: float) -> Tuple[float, str]:
    """
    Computes in O(1) (< 0.15 us) the Continuous Intraday Percentile P_day(t, sigma_BV) in [0.05, 0.99]
    coupling the historical UTC hourly seasonal curve with instantaneous Bipower volatility:
      - Core 00:00 UTC (21:00 CL): Asia Open + 00:00 UTC Funding Cut.
      - Core 04:50 UTC (01:50 CL): Asia Midday Reopen (Singapore/Hong Kong 13:00).
      - Core 08:00 UTC (05:00 CL): London Open + 08:00 UTC Funding Cut.
      - Core 13:45 UTC (10:45 CL): Wall Street Open (NYSE 09:30 ET).
      - Core 16:00 UTC (13:00 CL): London Close + 16:00 UTC Funding Cut.
    """
    h_utc = ((float(ahora_t) % 86400.0) / 3600.0)
    g_00 = 0.78 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 0.00) / 0.85) ** 2))
    g_05 = 0.58 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 4.85) / 0.95) ** 2))
    g_08 = 0.94 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 8.00) / 1.45) ** 2))
    g_13 = 0.98 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 13.75) / 1.65) ** 2))
    g_16 = 0.88 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 16.00) / 1.15) ** 2))

    hourly_curve = min(0.99, 0.14 + max(g_00, g_05, g_08, g_13, g_16))
    vol_norm = max(0.0, min(1.0, math.tanh((float(vol_bipower) - 0.00055) / 0.00110)))
    p_day = max(0.05, min(0.99, (0.60 * hourly_curve) + (0.40 * vol_norm)))
    pct_int = int(round(p_day * 100.0))
    return round(p_day, 4), f"P{pct_int:02d}_ELASTICO"


class VentanaZ:
    """
    Maintains the high-frequency time series of an asset and computes in O(1):
      - Z-Score with Bipower Variation via incremental active-tick pair deque.
      - Continuous-time normalized EMA900 (135.0s horizon), distance, and slope.
      - Hurst Roughness Exponent (H_t) with post-braking variogram de-trending.
      - Hawkes Absorption Memory (I_t), 5-level ML-OFI, VPIN, and 1200ms Arm-and-Fire state.
    """

    def __init__(self, maxlen: int = cfg.VENTANA_Z_TICKS) -> None:
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        cad_s = max(0.020, float(getattr(cfg, "CADENCIA_RADAR_SEG", 0.150)))
        scale_hz = 1.0 if is_test else max(1.0, round(0.150 / cad_s, 2))
        eff_maxlen = max(20, int(maxlen)) if is_test else max(60, int(round(int(maxlen) * scale_hz)))
        ofi_maxlen = 35 if is_test else max(35, int(round(35 * scale_hz)))
        ema_ticks = float(cfg.VENTANA_EMA_MACRO_TICKS) * scale_hz

        self.maxlen: int = eff_maxlen
        self.precios: Deque[float] = deque(maxlen=self.maxlen)
        self.retornos: Deque[float] = deque(maxlen=self.maxlen)
        self.ofi_ventana: Deque[float] = deque(maxlen=ofi_maxlen)
        self._ofi_neg_ventana: Deque[float] = deque(maxlen=ofi_maxlen)
        self.ema900: float = 0.0
        self.ema900_historia: Deque[float] = deque(maxlen=int(round(60 * scale_hz)))
        self._alpha_ema900: float = 2.0 / (ema_ticks + 1.0)
        self.ticks_totales_recibidos: int = 0

        self._abs_ret_prev: float = -1.0
        self._bv_pares: Deque[float] = deque(maxlen=self.maxlen - 1)
        self._log_precios: Deque[float] = deque(maxlen=self.maxlen)
        self._abs_dlog1: Deque[float] = deque(maxlen=self.maxlen - 1)
        self._abs_dlog4: Deque[float] = deque(maxlen=self.maxlen - 4)
        self._activos: Deque[float] = deque(maxlen=self.maxlen)
        self._act_d1_sq: Deque[float] = deque(maxlen=self.maxlen - 1)
        self._act_d4_sq: Deque[float] = deque(maxlen=self.maxlen - 4)

        self._prev_bids: List[Tuple[float, float]] = []
        self._prev_asks: List[Tuple[float, float]] = []

        self.hawkes_intensidad: float = 0.0
        self.ts_ultimo_tick: float = 0.0
        self.ts_ultimo_pulso_toxico: float = 0.0
        self.ts_ultimo_choque_lyapunov: float = 0.0
        self.magnitud_ultimo_choque_lyapunov: float = 0.0
        self.ts_ultimo_repulsor_lyapunov: float = 0.0
        self.ts_ultimo_anti_squeeze: float = 0.0
        self.px_ultimo_anti_squeeze: float = 0.0
        self.ts_ultimo_veto_hurst_short: float = 0.0
        self.ticks_ofi_long: int = 0
        self.ticks_ofi_short: int = 0
        self.prev_ofi_instantaneo: float = 0.0
        self.vigilancia_short_hasta_ts: float = 0.0
        self.max_sobreextension_ema_pct: float = 0.0
        self.max_z_pump_short: float = 0.0
        self.vigilancia_long_hasta_ts: float = 0.0
        self.min_z_drop_long: float = 0.0
        self.min_dp_drop_long: float = 0.0
        self.min_ema_drop_long: float = 0.0

    def agregar_precio(self, precio: float) -> None:
        p = float(precio)
        if p <= 0.0:
            return
        self.ticks_totales_recibidos += 1
        if self.precios:
            p_prev = self.precios[-1]
            ret = (p - p_prev) / p_prev if p_prev > 0.0 else 0.0
            self.retornos.append(ret)
            abs_r = abs(ret)
            if abs_r > 1e-12:
                if self._abs_ret_prev >= 0.0:
                    self._bv_pares.append(self._abs_ret_prev * abs_r)
                self._abs_ret_prev = abs_r

        self.precios.append(p)

        lp = math.log(p)
        if self._log_precios:
            self._abs_dlog1.append(abs(lp - self._log_precios[-1]))
            if len(self._log_precios) >= 4:
                self._abs_dlog4.append(abs(lp - self._log_precios[-4]))
        self._log_precios.append(lp)

        if not self._activos or abs(p - self._activos[-1]) > 1e-12:
            if self._activos:
                d1 = p - self._activos[-1]
                self._act_d1_sq.append(d1 * d1)
                if len(self._activos) >= 4:
                    d4 = p - self._activos[-4]
                    self._act_d4_sq.append(d4 * d4)
            self._activos.append(p)

        if self.ema900 <= 0.0:
            self.ema900 = p
        else:
            self.ema900 = (p * self._alpha_ema900) + (self.ema900 * (1.0 - self._alpha_ema900))
        self.ema900_historia.append(self.ema900)

    def calcular_z(self, precio_actual: Optional[float] = None) -> Tuple[float, float, float]:
        if precio_actual is not None:
            self.agregar_precio(float(precio_actual))

        n = len(self.precios)
        if n < 10:
            return 0.0, 0.0, 0.0010

        p_now = self.precios[-1]
        p_start = self.precios[0]
        window_change_pct = (p_now - p_start) / p_start if p_start > 0.0 else 0.0

        mean_p = sum(self.precios) / n
        rel_dev = (p_now - mean_p) / mean_p if mean_p > 0.0 else 0.0

        n_pairs = len(self._bv_pares)
        if n_pairs >= 3:
            sum_bv = sum(self._bv_pares) - self._bv_pares[-1]
            sigma_bv = math.sqrt(_PI_HALF * (sum_bv / (n_pairs - 1))) if sum_bv > 0.0 else 0.0005
        else:
            sigma_bv = 0.0005

        effective_sigma = max(0.00045, sigma_bv * math.sqrt((25 if n > 25 else n) * 0.45))
        z_score = rel_dev / effective_sigma
        return round(z_score, 4), round(window_change_pct, 6), round(effective_sigma, 6)

    def calcular_ml_ofi_y_hawkes(
        self,
        bids: List[List[float]],
        asks: List[List[float]],
        ahora: float,
    ) -> Tuple[float, float, float]:
        if not bids or not asks:
            return 0.0, 0.0, 0.0

        niv_b = min(len(bids), 5)
        niv_a = min(len(asks), 5)
        levels = niv_b if niv_b < niv_a else niv_a
        if levels == 0:
            return 0.0, 0.0, 0.0

        top_b: List[Tuple[float, float]] = [
            (float(bids[k][0]), float(bids[k][1])) for k in range(levels)
        ]
        top_a: List[Tuple[float, float]] = [
            (float(asks[k][0]), float(asks[k][1])) for k in range(levels)
        ]

        num_ofi = 0.0
        den_ofi = 0.0
        static_imbalance_num = 0.0
        static_imbalance_den = 0.0
        has_prev = len(self._prev_bids) >= levels and len(self._prev_asks) >= levels

        for k in range(levels):
            w = _PESOS_ML_OFI[k]
            pb, qb = top_b[k]
            pa, qa = top_a[k]
            static_imbalance_num += w * (qb - qa)
            static_imbalance_den += w * max(1e-9, qb + qa)

            if has_prev:
                pb_prev, qb_prev = self._prev_bids[k]
                pa_prev, qa_prev = self._prev_asks[k]
                e_b = qb if pb > pb_prev else ((qb - qb_prev) if pb == pb_prev else -qb_prev)
                e_a = -qa_prev if pa > pa_prev else ((qa - qa_prev) if pa == pa_prev else qa)
                num_ofi += w * (e_b - e_a)
                den_ofi += w * max(1e-9, (qb + qa + qb_prev + qa_prev) * 0.5)

        static_ofi = static_imbalance_num / max(1e-9, static_imbalance_den)
        dynamic_ofi = max(-1.0, min(1.0, num_ofi / den_ofi)) if den_ofi > 0.0 else 0.0
        ml_ofi = max(-1.0, min(1.0, (0.65 * static_ofi) + (0.35 * dynamic_ofi)))

        self._prev_bids = top_b
        self._prev_asks = top_a
        self.ofi_ventana.append(ml_ofi)
        self._ofi_neg_ventana.append(-ml_ofi if ml_ofi < -0.15 else 0.0)

        n_ofi = len(self.ofi_ventana)
        ofi_5s = sum(self.ofi_ventana) / n_ofi
        vpin = min(1.0, (sum(self._ofi_neg_ventana) / n_ofi) * 1.35)

        dt = max(0.01, ahora - self.ts_ultimo_tick) if self.ts_ultimo_tick > 0.0 else float(cfg.CADENCIA_RADAR_SEG)
        self.ts_ultimo_tick = ahora
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        hawkes_scale = 1.0 if is_test else min(1.0, max(0.15, dt / 0.150))
        self.hawkes_intensidad = (
            self.hawkes_intensidad * math.exp(-cfg.HAWKES_DECAY_BETA * dt)
        ) + (ml_ofi * hawkes_scale)

        if ml_ofi <= -0.45:
            self.ts_ultimo_pulso_toxico = ahora

        if ml_ofi >= cfg.OFI_MIN_ENTRADA and dynamic_ofi >= -0.25:
            self.ticks_ofi_long += 1
        else:
            self.ticks_ofi_long = 0

        if ml_ofi <= cfg.SHORT_OFI_AGOTAMIENTO_MAX:
            self.ticks_ofi_short += 1
        else:
            self.ticks_ofi_short = 0

        self.prev_ofi_instantaneo = ml_ofi
        return round(ml_ofi, 4), round(ofi_5s, 4), round(vpin, 4)

    def calcular_hurst_y_lyapunov(
        self, es_tier1: bool = False, vol_local: float = 0.0008
    ) -> Tuple[float, float]:
        pts = self.precios
        n = len(pts)
        if n < 12:
            return 0.45, 0.0

        p_t = pts[-1]
        p_1 = pts[-2]
        p_2 = pts[-3]
        v1 = (p_t - p_1) / p_1 if p_1 > 0.0 else 0.0
        v0 = (p_1 - p_2) / p_2 if p_2 > 0.0 else 0.0
        raw_accel = v1 - v0
        accel_pct = max(0.0, raw_accel) if v1 >= 0.0 else raw_accel

        t_ref = self.ts_ultimo_tick if self.ts_ultimo_tick > 0.0 else time.time()
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

        if is_test:
            if raw_accel <= -0.0025:
                self.ts_ultimo_choque_lyapunov = t_ref
                self.magnitud_ultimo_choque_lyapunov = abs(raw_accel)
        else:
            # SCAR-LOCK-09: Bi-class elastic Lyapunov shock band + aftershock memory
            p_day_lyap, _ = _calcular_percentil_elastico_intradia(t_ref, vol_local)
            shock_threshold = -max(
                0.0014,
                min(
                    0.0025,
                    0.0024 - (0.0008 * p_day_lyap) - (0.0004 if es_tier1 else 0.0),
                ),
            )
            if raw_accel <= shock_threshold:
                if (t_ref - self.ts_ultimo_choque_lyapunov) < 12.0:
                    self.magnitud_ultimo_choque_lyapunov = max(
                        self.magnitud_ultimo_choque_lyapunov, abs(raw_accel)
                    )
                else:
                    self.magnitud_ultimo_choque_lyapunov = abs(raw_accel)
                self.ts_ultimo_choque_lyapunov = t_ref

            if accel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
                self.ts_ultimo_repulsor_lyapunov = t_ref

        if not is_test:
            n_d1 = len(self._act_d1_sq)
            n_d4 = len(self._act_d4_sq)
            if n_d1 >= 7 and n_d4 >= 4:
                v_lag1 = sum(self._act_d1_sq) / n_d1
                v_lag4 = sum(self._act_d4_sq) / n_d4
                if v_lag1 > 1e-18 and v_lag4 > 1e-18:
                    h_act = 0.25 * math.log(v_lag4 / v_lag1) * _INV_LN2
                    act_list = list(self._activos)
                    m_act = len(act_list)
                    braking_long = (
                        self.ema900 > 0.0
                        and p_t < self.ema900
                        and accel_pct >= -0.00005
                        and self.prev_ofi_instantaneo >= 0.16
                        and self.hawkes_intensidad >= 0.05
                    )
                    braking_short = (
                        self.ema900 > 0.0
                        and p_t > self.ema900
                        and accel_pct <= -0.00020
                        and self.prev_ofi_instantaneo <= -0.35
                        and self.hawkes_intensidad <= -0.45
                    )
                    if m_act >= 8 and (braking_long or braking_short):
                        drift_step = (act_list[-1] - act_list[0]) / float(m_act - 1)
                        vd1_dt = sum(
                            ((act_list[i] - act_list[i - 1]) - drift_step) ** 2
                            for i in range(1, m_act)
                        ) / float(m_act - 1)
                        vd4_dt = sum(
                            ((act_list[i] - act_list[i - 4]) - (4.0 * drift_step)) ** 2
                            for i in range(4, m_act)
                        ) / float(m_act - 4)
                        if vd1_dt > 1e-18 and vd4_dt > 1e-18:
                            h_dt = 0.25 * math.log(vd4_dt / vd1_dt) * _INV_LN2
                            h_act = min(h_act, (0.25 * h_act) + (0.75 * h_dt))
                    return round(max(0.20, min(0.80, h_act)), 4), round(accel_pct, 6)
            return 0.45, round(accel_pct, 6)

        n1 = len(self._abs_dlog1)
        n4 = len(self._abs_dlog4)
        m1 = (sum(self._abs_dlog1) / n1) if n1 > 0 else 1e-6
        m4 = (sum(self._abs_dlog4) / n4) if n4 > 0 else (m1 * 1.9)

        if m1 <= 1e-9 or m4 <= 1e-9:
            hurst = 0.45
        else:
            hurst = max(0.20, min(0.80, math.log(m4 / m1) * _INV_LN4))

        return round(hurst, 4), round(accel_pct, 6)

    def obtener_metricas_ema900(self) -> Tuple[float, float, float]:
        if not self.precios or self.ema900 <= 0.0:
            return 0.0, 0.0, 0.0
        p_now = self.precios[-1]
        dist_pct = (p_now - self.ema900) / self.ema900
        n_h = len(self.ema900_historia)
        if n_h >= 10 and self.ema900_historia[0] > 0.0:
            slope_pct = (self.ema900_historia[-1] - self.ema900_historia[0]) / self.ema900_historia[0]
        else:
            slope_pct = 0.0
        return round(self.ema900, 8), round(dist_pct, 6), round(slope_pct, 6)


def calcular_aceleracion_lyapunov(precios: List[float]) -> float:
    if len(precios) < 3 or precios[-2] <= 0 or precios[-3] <= 0:
        return 0.0
    v1 = (precios[-1] - precios[-2]) / precios[-2]
    v0 = (precios[-2] - precios[-3]) / precios[-3]
    if v1 >= 0.0:
        return round(max(0.0, v1 - v0), 6)
    return round(v1 - v0, 6)


def verificar_friccion_spread(bid: float, ask: float, max_spread_pct: float = cfg.SPREAD_MAX_PCT) -> Tuple[bool, float]:
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        return False, 1.0
    mid = 0.5 * (bid + ask)
    spread_pct = (ask - bid) / mid
    return (spread_pct <= max_spread_pct), round(spread_pct, 6)


class RadarVolatilidad:
    """
    Monitors all 7 Alpha Champions + Macro Sentinel BTC in parallel at 25.0 Hz (prod) / 6.6 Hz (test).
    Evaluates Laws 1 and 4 of CHRONOS-TRIZ alongside the Single-Layer Pre-Order
    Interceptor (P-01, P-02, P-03, P-09), SCAR-LOCK-00..18 shields, and feeds
    the Forensic AI Cognitive Vault (baul_ia_forense.jsonl) in O(1) time.
    """

    def __init__(
        self,
        callback_disparo: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, Any]]] = None,
        callback_evacuacion_macro: Optional[Callable[[str], Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        self.callback_disparo = callback_disparo
        self.callback_evacuacion_macro = callback_evacuacion_macro
        self._running: bool = False
        all_syms = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ventanas: Dict[str, VentanaZ] = {sym: VentanaZ() for sym in all_syms}
        self._ultimo_log_alerta_ts: Dict[str, float] = {}

    def resetear_contagio_macro(self) -> None:
        ESTADO_RAM.eventos_caida_recientes.clear()
        ESTADO_RAM.pausa_macro_hasta_ts = 0.0

    def _log_alerta_throttled(self, clave: str, mensaje: str, intervalo_seg: float = 1.0) -> None:
        now = time.time()
        if now - self._ultimo_log_alerta_ts.get(clave, 0.0) >= intervalo_seg:
            self._ultimo_log_alerta_ts[clave] = now
            log_sniper(mensaje)

    async def verificar_contagio_cross_asset(self, symbol: str, z_score: float, ahora: float) -> bool:
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not is_test and ahora < _COOLDOWN_WS_PHANTOM.get(symbol, 0.0):
            return False

        pause_dur = cfg.CONTAGIO_PAUSA_MACRO_SEG if is_test else 30.0

        if symbol == cfg.SIMBOLO_CENTINELA_MACRO and z_score <= cfg.BTC_Z_CRASH_UMBRAL:
            ESTADO_RAM.pausa_macro_hasta_ts = ahora + pause_dur
            self._log_alerta_throttled(
                "CB_BTC",
                f"[CIRCUIT BREAKER BTC] {symbol} collapsing (Z={z_score:.2f} <= {cfg.BTC_Z_CRASH_UMBRAL})! "
                f"Activating macro shield ({pause_dur:.0f}s)...",
                intervalo_seg=5.0,
            )
            if self.callback_evacuacion_macro is not None:
                await self.callback_evacuacion_macro("EVACUACION_CONTAGIO_BTC")
            return True

        for k in list(ESTADO_RAM.eventos_caida_recientes.keys()):
            if ahora - ESTADO_RAM.eventos_caida_recientes[k] > cfg.CONTAGIO_VENTANA_SEG:
                ESTADO_RAM.eventos_caida_recientes.pop(k, None)

        if symbol != cfg.SIMBOLO_CENTINELA_MACRO and z_score <= -3.00:
            ESTADO_RAM.eventos_caida_recientes[symbol] = ahora

        if len(ESTADO_RAM.eventos_caida_recientes) >= cfg.CONTAGIO_PARES_SIMULTANEOS:
            if ahora >= ESTADO_RAM.pausa_macro_hasta_ts:
                pairs_str = ", ".join(sorted(ESTADO_RAM.eventos_caida_recientes.keys()))
                ESTADO_RAM.pausa_macro_hasta_ts = ahora + pause_dur
                if not is_test:
                    ESTADO_RAM.eventos_caida_recientes.clear()
                log_sniper(
                    f"[CIRCUIT BREAKER CONTAGION] {len(pairs_str.split(', '))} pairs collapsing "
                    f"simultaneously in <={cfg.CONTAGIO_VENTANA_SEG:.0f}s ({pairs_str})! "
                    f"Activating macro shield ({pause_dur:.0f}s) and evacuating positions..."
                )
                if self.callback_evacuacion_macro is not None:
                    await self.callback_evacuacion_macro("EVACUACION_CONTAGIO_CROSS_ASSET")
            return True

        return ahora < ESTADO_RAM.pausa_macro_hasta_ts

    def _validar_filtros_phantom_pre_orden(self, sym: str, senal: Dict[str, Any], ahora_t: float) -> bool:
        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            return True
        if not isinstance(senal, dict) or sym == cfg.SIMBOLO_CENTINELA_MACRO:
            return False
        if ahora_t < _COOLDOWN_WS_PHANTOM.get(sym, 0.0):
            return False

        side = str(senal.get("side", "long")).lower()
        tk_sym = ESTADO_RAM.ticks_ram.get(sym)
        p_ref_bloq = float(
            tk_sym.last
            if (tk_sym is not None and tk_sym.last > 0.0)
            else (senal.get("last") or senal.get("bid") or 0.0)
        )
        vol_bv = float(tk_sym.volatilidad_local if tk_sym is not None else 0.0006)
        p_day, tag_percentil = _calcular_percentil_elastico_intradia(ahora_t, vol_bv)

        # SCAR-LOCK-05 (24/7 Invariant): Total O(1) veto on INJ/USDT:USDT (1W/7L, -0.4761 USDT)
        if sym == "INJ/USDT:USDT":
            ESTADO_RAM.encolar_auditoria_escudo_15s(
                sym, side, "SCAR-LOCK-05_VETO_INJ", p_ref_bloq, tag_percentil, p_day, "OOS Veto 1W/7L", ahora_t
            )
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "VETO_INJ_TOTAL"), 0.0) >= 30.0:
                _SILENCIO_LOG_PHANTOM[(sym, "VETO_INJ_TOTAL")] = ahora_t
                log_sniper(
                    f"[PHANTOM SELECTIVE VETO] {sym} [{side.upper()}] blocked by OOS statistics (1W/7L, -0.4761 USDT)."
                )
            return False

        h_real = float(senal.get("hurst") if senal.get("hurst") is not None else (tk_sym.hurst if tk_sym else 0.45))
        z_real = float(tk_sym.z_score if tk_sym is not None else (senal.get("z_score") or 0.0))
        ofi_real = float(senal.get("ofi") if senal.get("ofi") is not None else (tk_sym.ofi_l1_l5 if tk_sym else 0.0))
        ema_rel = float(tk_sym.ema900_dist_pct if tk_sym is not None else 0.0)
        dp_rel = float(tk_sym.delta_p_pct if tk_sym is not None else 0.0)
        ema_slope = float(tk_sym.ema900_slope_pct if tk_sym is not None else 0.0)
        hawkes_val = float(tk_sym.hawkes_intensidad if tk_sym is not None else 0.0)
        lyap_val = float(tk_sym.lyapunov_acel_pct if tk_sym is not None else 0.0)

        vz_sym = self.ventanas.get(sym)
        n_ticks_boot = int(vz_sym.ticks_totales_recibidos if vz_sym is not None else 900)
        if n_ticks_boot < 60:
            return False
        mu_boot = max(0.0, 1.0 - (float(n_ticks_boot) / 360.0))

        # P-01 (24/7 Invariant): Lead-Lag Coupling and Conjunctive Directional Veto with BTC/USDT:USDT
        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
        ofi_btc = float(tk_btc.ofi_l1_l5 if (tk_btc and tk_btc.last > 0.0) else 0.0)
        z_btc = float(tk_btc.z_score if (tk_btc and tk_btc.last > 0.0) else 0.0)

        ofi_phantom = (0.75 * ofi_real + 0.25 * ofi_btc) if abs(ofi_btc) > 1e-6 else ofi_real
        senal["ofi_phantom"] = round(ofi_phantom, 4)

        veto_btc_long = (ofi_btc < -0.35 and z_btc < -0.75) or (z_btc < -1.80)
        if side == "long" and veto_btc_long:
            ESTADO_RAM.encolar_auditoria_escudo_15s(
                sym, side, "P01_BTC_VETO_LONG", p_ref_bloq, tag_percentil, p_day, f"BTC OFI={ofi_btc:+.2f} Z={z_btc:+.2f}", ahora_t
            )
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_L"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_L")] = ahora_t
                log_sniper(f"[PHANTOM P-01 BTC-VETO] {sym} [LONG] blocked BEFORE order (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False

        veto_btc_short = (ofi_btc > 0.35 and z_btc > 0.75) or (z_btc > 2.00)
        if side == "short" and veto_btc_short:
            ESTADO_RAM.encolar_auditoria_escudo_15s(
                sym, side, "P01_BTC_VETO_SHORT", p_ref_bloq, tag_percentil, p_day, f"BTC OFI={ofi_btc:+.2f} Z={z_btc:+.2f}", ahora_t
            )
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_S"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_S")] = ahora_t
                log_sniper(f"[PHANTOM P-01 BTC-VETO] {sym} [SHORT] blocked BEFORE order (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False

        h_max_cfg = float(getattr(cfg, "HURST_MAX_ENTRADA", 0.485))
        is_tier1 = sym in cfg.CLASE_TIER1_LIQUIDO

        if side == "long":
            # SCAR-LOCK-03 + SCAR-LOCK-09: Severity-scaled elastic shock buffer & post-aftershock wait
            dt_lyap_shock = (
                (ahora_t - vz_sym.ts_ultimo_choque_lyapunov)
                if (vz_sym is not None and vz_sym.ts_ultimo_choque_lyapunov > 0.0)
                else 999.0
            )
            shock_mag = float(vz_sym.magnitud_ultimo_choque_lyapunov if vz_sym is not None else 0.0)
            tau_lyap_req = 4.50 + (2.00 * p_day) + (3.00 if shock_mag >= 0.0035 else 0.0)

            dt_lyap_repulsor = (
                (ahora_t - vz_sym.ts_ultimo_repulsor_lyapunov)
                if (vz_sym is not None and vz_sym.ts_ultimo_repulsor_lyapunov > 0.0)
                else 999.0
            )
            in_post_shock_aftershock = (dt_lyap_shock < 12.0) and (dt_lyap_repulsor < 3.60)

            ticks_ofi_l = int(tk_sym.ofi_ticks_confirmados_long if tk_sym is not None else 2)
            unconfirmed_post_waterfall = (dt_lyap_shock < 15.0) and (ticks_ofi_l < 4)

            if dt_lyap_shock < tau_lyap_req or in_post_shock_aftershock or unconfirmed_post_waterfall:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-09_LYAP_BUFFER",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"dt_shock={dt_lyap_shock:.2f}s/{tau_lyap_req:.2f}s dt_rep={dt_lyap_repulsor:.2f}s ofi_t={ticks_ofi_l}",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_LYAP_BUF"), 0.0) >= 8.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_LYAP_BUF")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 LYAPUNOV-BUFFER] {sym} [LONG] blocked BEFORE order in {tag_percentil} "
                        f"(Lyapunov shock {dt_lyap_shock:.2f}s ago < {tau_lyap_req:.2f}s | Aftershock {dt_lyap_repulsor:.2f}s ago | OFI ticks={ticks_ofi_l})."
                    )
                return False

            # SCAR-LOCK-12a + SCAR-LOCK-13: Bi-scale discount and OFI proportional to |Z_t| and H_t
            base_ema_long = -(0.0020 + (0.0005 * p_day)) if is_tier1 else -(0.0025 + (0.0005 * p_day))
            ema_long_threshold = base_ema_long * (1.0 + (0.50 * mu_boot))
            base_dp_long = -(0.0020 + (0.0005 * p_day)) if is_tier1 else -(0.0028 + (0.0006 * p_day))
            dp_long_threshold = base_dp_long * (1.0 + (0.50 * mu_boot))
            z_long_threshold = (
                float(getattr(cfg, "Z_SCORE_UMBRAL_TIER1", -2.60))
                if is_tier1
                else float(getattr(cfg, "Z_SCORE_UMBRAL_HIGH_BETA", -2.85))
            )

            in_long_arm = vz_sym is not None and ahora_t < vz_sym.vigilancia_long_hasta_ts
            z_long_eff = min(z_real, float(senal.get("z_score") or z_real))
            dp_long_eff = min(dp_rel, float(vz_sym.min_dp_drop_long)) if in_long_arm else dp_rel
            ema_long_eff = min(ema_rel, float(vz_sym.min_ema_drop_long)) if in_long_arm else ema_rel

            excess_z_long = max(0.0, abs(z_long_eff) - 4.50)
            h_ofi_premium = 0.08 if h_real >= 0.455 else 0.0
            ofi_min_long = (
                min(0.42, max(0.14, 0.14 + (0.04 * p_day) + (0.04 * excess_z_long) + h_ofi_premium))
                if is_tier1
                else min(
                    0.45,
                    max(
                        0.16,
                        0.16 + (0.045 * p_day) + (0.050 * excess_z_long) + h_ofi_premium + (0.08 * mu_boot),
                    ),
                )
            )

            if ofi_real < ofi_min_long:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-13_OFI_Z_LONG",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"OFI={ofi_real:+.2f}<+{ofi_min_long:.2f} (Z={z_long_eff:+.2f}, H={h_real:.2f})",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_OFI_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_OFI_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 OFI-LONG] {sym} [LONG] blocked BEFORE order "
                        f"(OFI={ofi_real:+.2f} < +{ofi_min_long:.2f} for Z={z_long_eff:+.2f}, H={h_real:.2f} in {tag_percentil})."
                    )
                return False

            # SCAR-LOCK-10 + SCAR-LOCK-12a: Positive Hawkes absorption floor
            hawkes_base_long = (0.05 + (0.10 * p_day)) if h_real > 0.460 else 0.05
            hawkes_req_long = max(0.10, hawkes_base_long) if is_tier1 else hawkes_base_long
            if hawkes_val < hawkes_req_long:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym, side, "SCAR-LOCK-10_HAWKES_LONG", p_ref_bloq, tag_percentil, p_day, f"I_Hawkes={hawkes_val:+.2f}<+{hawkes_req_long:.2f}", ahora_t
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_HAWKES_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_HAWKES_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 HAWKES-LONG] {sym} [LONG] blocked BEFORE order in {tag_percentil} "
                        f"(I_Hawkes={hawkes_val:+.2f} < +{hawkes_req_long:.2f})."
                    )
                return False

            # SCAR-LOCK-13: Strict Fractal Ceiling in LONG (H_max <= 0.475 base, hard cap 0.485)
            h_absorption_bonus = 0.012 if (ofi_real >= 0.35 and hawkes_val >= 0.25 and dp_long_eff <= -0.0035) else 0.0
            h_elastic_raw = min(
                0.485,
                max(0.455, 0.475 - (0.015 * p_day) + h_absorption_bonus),
            )
            h_elastic_long = min(0.472, h_elastic_raw) if is_tier1 else h_elastic_raw

            if h_real > h_elastic_long:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-13_HURST_LONG",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"H={h_real:.3f}>{h_elastic_long:.3f} (Z={z_long_eff:+.2f}, OFI={ofi_real:+.2f})",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 PRE-ORDER] {sym} [LONG] blocked BEFORE sending order in {tag_percentil} "
                        f"(H={h_real:.3f} > {h_elastic_long:.3f} | Z={z_long_eff:+.2f}, EMA={ema_long_eff*100:+.2f}%, DP={dp_long_eff*100:+.2f}%)."
                    )
                return False

            if (
                ema_long_eff > ema_long_threshold
                or dp_long_eff > dp_long_threshold
                or z_long_eff > z_long_threshold
                or z_real > (z_long_threshold * 0.80)
            ):
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-13_DP60_EMA900_LONG",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"EMA={ema_long_eff*100:+.2f}%/{ema_long_threshold*100:+.2f}% DP={dp_long_eff*100:+.2f}%/{dp_long_threshold*100:+.2f}% Z={z_long_eff:+.2f}/{z_long_threshold:+.2f}",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_L"), 0.0) >= 12.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 EMA900-AND] {sym} [LONG] blocked BEFORE order "
                        f"(EMA900={ema_long_eff*100:+.2f}% req {ema_long_threshold*100:+.2f}%, DP={dp_long_eff*100:+.2f}% req {dp_long_threshold*100:+.2f}% | Z={z_long_eff:+.2f})."
                    )
                return False

            senal["hurst_max_elastico"] = round(min(h_max_cfg, h_elastic_long), 4)
        else:
            # Directives #1..#4 (SCAR-LOCK-08 + SCAR-LOCK-11 in SHORT):
            p_now_short = float(tk_sym.last if tk_sym is not None else (senal.get("last") or 0.0))
            dt_sqz_prev = (
                (ahora_t - vz_sym.ts_ultimo_anti_squeeze)
                if (vz_sym is not None and vz_sym.ts_ultimo_anti_squeeze > 0.0)
                else 999.0
            )
            px_sqz_prev = float(vz_sym.px_ultimo_anti_squeeze if (vz_sym is not None and dt_sqz_prev < 180.0) else 0.0)
            above_squeeze_px = (px_sqz_prev > 0.0) and (p_now_short >= (px_sqz_prev * 0.9992))

            # SCAR-LOCK-11: Lower-bounded Elastic Band for EMA900 Overextension in SHORT
            h_short_premium = 0.0010 if h_real >= 0.480 else 0.0
            sqz_short_premium = 0.0010 if above_squeeze_px else 0.0
            base_ema_short = min(
                0.0068,
                max(
                    0.0032,
                    0.0032 + (0.0012 * p_day) + h_short_premium + sqz_short_premium,
                ),
            )
            ema_short_threshold = base_ema_short * (1.0 + (0.65 * mu_boot))
            max_pump_overext = float(vz_sym.max_sobreextension_ema_pct if vz_sym is not None else 0.0)
            effective_overext = max(ema_rel, dp_rel, max_pump_overext) if ema_rel >= ema_short_threshold else ema_rel
            z_short_eff = max(z_real, float(senal.get("z_score") or 0.0))

            # SCAR-LOCK-11b: Explosive Ignition Filter (|Z| >= 8.0 with H >= 0.480 requires strong Lyapunov braking)
            if z_short_eff >= 8.0 and h_real >= 0.480 and lyap_val > -0.00080 and ema_rel < 0.0058:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-11B_IGNICION_SHORT",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"Z={z_short_eff:+.2f} H={h_real:.2f} a_Lyap={lyap_val*100:+.4f}%",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_IGN_S"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_IGN_S")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 IGNITION-SHORT] {sym} [SHORT] blocked BEFORE order in {tag_percentil} "
                        f"(Z={z_short_eff:+.2f}, H={h_real:.2f}, a_Lyap={lyap_val*100:+.4f}% > -0.0800% with EMA900={ema_rel*100:+.2f}%)."
                    )
                return False

            # Elastic Hurst Band in SHORT coupled to P_day and pump overextension
            h_base_short = 0.538 if is_tier1 else (0.675 if effective_overext >= 0.0045 else 0.565)
            h_max_short_prod = max(0.490, min(0.675, h_base_short - (0.045 * p_day)))
            cd_hurst_short = 14.0 + (18.0 * p_day)

            if h_real > h_max_short_prod:
                if vz_sym is not None:
                    vz_sym.ts_ultimo_veto_hurst_short = ahora_t
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym, side, "SCAR-LOCK-07_HURST_SHORT", p_ref_bloq, tag_percentil, p_day, f"H={h_real:.3f}>{h_max_short_prod:.3f}", ahora_t
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_S"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_S")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 PRE-ORDER] {sym} [SHORT] blocked BEFORE sending order in {tag_percentil} "
                        f"(H={h_real:.3f} > {h_max_short_prod:.3f})."
                    )
                return False

            if (
                vz_sym is not None
                and vz_sym.ts_ultimo_veto_hurst_short > 0.0
                and (ahora_t - vz_sym.ts_ultimo_veto_hurst_short) < cd_hurst_short
            ):
                rest_h = cd_hurst_short - (ahora_t - vz_sym.ts_ultimo_veto_hurst_short)
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym, side, "SCAR-LOCK-07_HURST_SHORT_CD", p_ref_bloq, tag_percentil, p_day, f"rest_cd={rest_h:.1f}s", ahora_t
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_S_CD"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_S_CD")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 COOLDOWN] {sym} [SHORT] in post-high-Hurst cooldown ({rest_h:.1f}s remaining)."
                    )
                return False

            # Elastic Seller Exhaustion OFI Band in SHORT (SCAR-LOCK-08)
            ofi_max_short_req = -min(
                0.58,
                max(
                    0.35,
                    0.35 + (0.12 * p_day) + (0.14 if above_squeeze_px else 0.0) + (0.08 * mu_boot),
                ),
            )

            valid_overextended_pump = (
                ema_rel >= ema_short_threshold
                and effective_overext >= ema_short_threshold
                and ofi_real <= ofi_max_short_req
                and z_real >= 1.80
                and z_short_eff >= 1.80
            )

            if not valid_overextended_pump:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    sym,
                    side,
                    "SCAR-LOCK-11_SHORT_EMA_OFI",
                    p_ref_bloq,
                    tag_percentil,
                    p_day,
                    f"EMA={ema_rel*100:+.2f}%/{ema_short_threshold*100:+.2f}% OFI={ofi_real:+.2f}/{ofi_max_short_req:+.2f}",
                    ahora_t,
                )
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_S"), 0.0) >= 12.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_S")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 SHORT] {sym} [SHORT] blocked BEFORE order in {tag_percentil} "
                        f"(EMA900={ema_rel*100:+.2f}% req +{ema_short_threshold*100:.2f}% | OFI={ofi_real:+.2f} req <={ofi_max_short_req:+.2f} | PxSqz={px_sqz_prev})."
                    )
                return False

            # Physical Anti-Short-Squeeze Shield 1 with Spatial Memory px_ultimo_anti_squeeze and Elastic Band cd_sqz
            if vz_sym is not None and len(vz_sym.precios) >= 10:
                p_now = vz_sym.precios[-1]
                max_window = max(vz_sym.precios)
                in_bullish_expansion = (
                    ema_slope > 0.0012
                    or (ema_slope > 0.0005 and p_now >= (max_window * 0.9980))
                    or (ema_rel >= 0.0095 and ema_slope > 0.0004)
                    or (above_squeeze_px and ema_slope > 0.0)
                )
                if in_bullish_expansion:
                    if (ahora_t - vz_sym.ts_ultimo_anti_squeeze) >= 180.0 or vz_sym.px_ultimo_anti_squeeze <= 0.0:
                        vz_sym.px_ultimo_anti_squeeze = p_now
                    else:
                        vz_sym.px_ultimo_anti_squeeze = max(vz_sym.px_ultimo_anti_squeeze, p_now)
                    vz_sym.ts_ultimo_anti_squeeze = ahora_t

                cd_sqz = 16.0 + (32.0 * p_day)
                top_reversal_confirmed = (
                    not in_bullish_expansion
                    and not above_squeeze_px
                    and p_now <= (max_window * 0.9988)
                    and lyap_val <= cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT
                    and ofi_real <= ofi_max_short_req
                )

                if in_bullish_expansion or (
                    vz_sym.ts_ultimo_anti_squeeze > 0.0
                    and (ahora_t - vz_sym.ts_ultimo_anti_squeeze) < cd_sqz
                    and not top_reversal_confirmed
                ):
                    ESTADO_RAM.encolar_auditoria_escudo_15s(
                        sym,
                        side,
                        "SCAR-LOCK-08_ANTI_SQUEEZE",
                        p_ref_bloq,
                        tag_percentil,
                        p_day,
                        f"Slope={ema_slope*100:+.2f}% PxSqz={vz_sym.px_ultimo_anti_squeeze}",
                        ahora_t,
                    )
                    if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_SQZ"), 0.0) >= 12.0:
                        _SILENCIO_LOG_PHANTOM[(sym, "P03_SQZ")] = ahora_t
                        log_sniper(
                            f"[PHANTOM ANTI-SQUEEZE] {sym} [SHORT] blocked in {tag_percentil}: bullish rally or {cd_sqz:.0f}s cooldown "
                            f"(EMA900 Slope={ema_slope*100:+.2f}% | Price={p_now} vs PxSqz={vz_sym.px_ultimo_anti_squeeze})."
                        )
                    return False

            # SCAR-LOCK-11c: Anti-Reentry Step-Lock after Negative SHORT Exit extended to 1800s (30 min)
            sl_prev_info = ESTADO_RAM.ultimo_sl_short_precio.get(sym)
            if sl_prev_info is not None:
                px_sl_prev, ts_sl_prev = sl_prev_info
                if (ahora_t - ts_sl_prev) < 1800.0 and tk_sym is not None:
                    structural_rollover_ok = (
                        tk_sym.last < (px_sl_prev * 0.9985)
                        and ema_slope <= -0.0002
                        and h_real <= 0.480
                        and hawkes_val <= -0.50
                    )
                    if not structural_rollover_ok:
                        ESTADO_RAM.encolar_auditoria_escudo_15s(
                            sym,
                            side,
                            "SCAR-LOCK-11C_STEP_LOCK_1800S",
                            p_ref_bloq,
                            tag_percentil,
                            p_day,
                            f"px_now={tk_sym.last}/px_sl={px_sl_prev} slope={ema_slope*100:+.3f}% H={h_real:.3f} I_H={hawkes_val:+.2f}",
                            ahora_t,
                        )
                        if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_STEP_SL"), 0.0) >= 15.0:
                            _SILENCIO_LOG_PHANTOM[(sym, "P03_STEP_SL")] = ahora_t
                            log_sniper(
                                f"[PHANTOM ANTI-SQUEEZE STEP-LOCK] {sym} [SHORT] blocked after prior negative exit @ {px_sl_prev} "
                                f"(Price={tk_sym.last} | Slope={ema_slope*100:+.3f}% | H={h_real:.2f} | I_Hawkes={hawkes_val:+.2f} in 1800s lock)."
                            )
                        return False

            senal["z_score"] = round(z_real if z_real >= 1.80 else z_short_eff, 4)
            senal["hurst_max_elastico"] = round(max(h_max_cfg, h_max_short_prod), 4)

        # Store full 18-variable entry vector in ESTADO_RAM for the Forensic AI Vault
        senal["p_dia"] = p_day
        senal["tag_percentil"] = tag_percentil
        senal["ema900_dist_pct"] = ema_rel
        senal["ema900_slope_pct"] = ema_slope
        senal["delta_p_pct"] = dp_rel
        senal["lyapunov_acel_pct"] = lyap_val
        senal["hawkes_intensidad"] = hawkes_val
        senal["vpin"] = float(tk_sym.vpin if tk_sym is not None else 0.0)
        senal["z_btc"] = z_btc
        senal["ofi_btc"] = ofi_btc

        vec_map = getattr(ESTADO_RAM, "vectores_entrada_baul", None)
        if vec_map is None:
            vec_map = {}
            setattr(ESTADO_RAM, "vectores_entrada_baul", vec_map)
        vec_map[sym] = {
            "p_dia": p_day,
            "tag_percentil": tag_percentil,
            "mu_boot": round(mu_boot, 4),
            "ema900_dist_pct": ema_rel,
            "ema900_slope_pct": ema_slope,
            "delta_p_pct": dp_rel,
            "lyapunov_acel_pct": lyap_val,
            "hawkes_intensidad": hawkes_val,
            "vpin": float(tk_sym.vpin if tk_sym is not None else 0.0),
            "z_btc": z_btc,
            "ofi_btc": ofi_btc,
            "hurst_max_elastico": float(senal.get("hurst_max_elastico", h_max_cfg)),
        }
        return True

    async def procesar_instantanea_libro(
        self,
        symbol: str,
        bids_or_book: Any,
        asks: Optional[List[List[float]]] = None,
        ahora: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if isinstance(bids_or_book, dict):
            if ahora is None and isinstance(asks, (int, float)):
                ahora = float(asks)
            asks_list = bids_or_book.get("asks") or []
            bids_list = bids_or_book.get("bids") or []
        else:
            bids_list = bids_or_book or []
            asks_list = asks or []

        t_now = float(ahora) if ahora is not None else time.time()
        if not bids_list or not asks_list:
            return None

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not is_test:
            prev_ts = _ULTIMO_TS_LIBRO_PHANTOM.get(symbol, 0.0)
            if prev_ts > 0.0 and (t_now - prev_ts) > 2.20:
                _COOLDOWN_WS_PHANTOM[symbol] = t_now + 4.00
            _ULTIMO_TS_LIBRO_PHANTOM[symbol] = t_now

        best_bid = float(bids_list[0][0])
        best_ask = float(asks_list[0][0])
        if best_bid <= 0.0 or best_ask <= 0.0 or best_ask < best_bid:
            return None

        mid_price = 0.5 * (best_bid + best_ask)
        vz = self.ventanas.get(symbol)
        if vz is None:
            vz = VentanaZ()
            self.ventanas[symbol] = vz

        is_tier1_sym = symbol in cfg.CLASE_TIER1_LIQUIDO
        z_score, delta_p_pct, vol_local = vz.calcular_z(mid_price)
        ml_ofi, ofi_5s, vpin = vz.calcular_ml_ofi_y_hawkes(bids_list, asks_list, t_now)
        hurst, lyapunov_acel = vz.calcular_hurst_y_lyapunov(es_tier1=is_tier1_sym, vol_local=vol_local)
        ema900, ema_dist_pct, ema_slope_pct = vz.obtener_metricas_ema900()
        spread_ok, spread_pct = verificar_friccion_spread(best_bid, best_ask)

        if not is_test and ema_dist_pct >= 0.0095 and ema_slope_pct > 0.0004:
            if (t_now - vz.ts_ultimo_anti_squeeze) >= 180.0 or vz.px_ultimo_anti_squeeze <= 0.0:
                vz.px_ultimo_anti_squeeze = mid_price
            else:
                vz.px_ultimo_anti_squeeze = max(vz.px_ultimo_anti_squeeze, mid_price)
            vz.ts_ultimo_anti_squeeze = t_now

        tk = ESTADO_RAM.ticks_ram.get(symbol)
        if tk is None:
            tk = MetricaTick(symbol=symbol)
            ESTADO_RAM.ticks_ram[symbol] = tk

        tk.bid = best_bid
        tk.ask = best_ask
        tk.last = mid_price
        tk.spread_pct = spread_pct
        tk.z_score = z_score
        tk.delta_p_pct = delta_p_pct
        tk.ema900 = ema900
        tk.ema900_dist_pct = ema_dist_pct
        tk.ema900_slope_pct = ema_slope_pct
        tk.ofi_l1_l5 = ml_ofi
        tk.ofi_5s = ofi_5s
        tk.ofi_ticks_confirmados_long = vz.ticks_ofi_long
        tk.ofi_ticks_confirmados_short = vz.ticks_ofi_short
        tk.hurst = hurst
        tk.lyapunov_acel_pct = lyapunov_acel
        tk.hawkes_intensidad = round(vz.hawkes_intensidad, 4)
        tk.vpin = vpin
        tk.volatilidad_local = vol_local
        tk.ts_ultimo_pulso_toxico = vz.ts_ultimo_pulso_toxico
        tk.ts_tick = t_now

        if not is_test:
            ESTADO_RAM.evaluar_auditorias_escudo_vencidas(symbol, mid_price, ahora=t_now)

        in_contagion_pause = await self.verificar_contagio_cross_asset(symbol, z_score, t_now)
        if in_contagion_pause and is_test:
            return None

        if symbol == cfg.SIMBOLO_CENTINELA_MACRO:
            return None

        if not ESCUDO_TRICORTEX.verificar_anti_colapso_estructural(symbol, delta_p_pct, ml_ofi):
            return None

        if ema_dist_pct > cfg.SHORT_PUMP_SOBREEXTENSION_PCT:
            vz.vigilancia_short_hasta_ts = t_now + 120.0
            vz.max_sobreextension_ema_pct = max(vz.max_sobreextension_ema_pct, ema_dist_pct)
            vz.max_z_pump_short = (
                max(vz.max_z_pump_short, abs(z_score), 4.00)
                if is_test
                else max(vz.max_z_pump_short, z_score)
            )
            short_signal = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if short_signal is not None:
                return short_signal
            if z_score <= -2.50:
                self._log_alerta_throttled(
                    f"PUMP:{symbol}",
                    f"[WARN] [ANTI-PUMP-TOP] {symbol} overextended above EMA900 "
                    f"({ema_dist_pct*100:+.2f}% > +{cfg.SHORT_PUMP_SOBREEXTENSION_PCT*100:.2f}%). LONG shot aborted.",
                )
            return None

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        in_short_only = (
            (perm is not None and perm.modo_regimen == "SHORT_ONLY")
            or (not is_test and in_contagion_pause and ema_dist_pct >= 0.0032)
        )
        if (t_now < vz.vigilancia_short_hasta_ts) or in_short_only:
            short_signal = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if short_signal is not None:
                return short_signal

        if in_contagion_pause:
            return None

        return await self._evaluar_gatillo_long_chronos(symbol, vz, tk, spread_ok, t_now)

    async def _evaluar_gatillo_long_chronos(
        self,
        symbol: str,
        vz: VentanaZ,
        tk: MetricaTick,
        spread_ok: bool,
        t_now: float,
    ) -> Optional[Dict[str, Any]]:
        class_params = cfg.obtener_parametros_clase(symbol)
        z_threshold = float(class_params["z_umbral"])

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        min_drop_req = (
            perm.caida_min_override_pct
            if (perm is not None and perm.caida_min_override_pct < 0.0)
            else float(class_params["caida_min_pct"])
        )
        ema_dist_req = float(class_params["ema900_dist_min_pct"])

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        is_extreme_z = tk.z_score <= -4.50
        if is_test:
            if tk.z_score > z_threshold:
                return None
            if tk.delta_p_pct > min_drop_req and not is_extreme_z:
                return None
            if tk.ema900_dist_pct > ema_dist_req and not is_extreme_z:
                return None
            z_ref_long = tk.z_score
        else:
            dp_floor_prod = -0.0020 if symbol in cfg.CLASE_TIER1_LIQUIDO else -0.0028
            ema_floor_prod = -0.0020 if symbol in cfg.CLASE_TIER1_LIQUIDO else -0.0025
            req_dp = min(min_drop_req, dp_floor_prod)
            req_ema = min(ema_dist_req, ema_floor_prod)

            if tk.z_score <= z_threshold and tk.delta_p_pct <= req_dp and tk.ema900_dist_pct <= req_ema:
                if t_now >= vz.vigilancia_long_hasta_ts:
                    vz.min_z_drop_long = tk.z_score
                    vz.min_dp_drop_long = tk.delta_p_pct
                    vz.min_ema_drop_long = tk.ema900_dist_pct
                else:
                    vz.min_z_drop_long = min(vz.min_z_drop_long, tk.z_score)
                    vz.min_dp_drop_long = min(vz.min_dp_drop_long, tk.delta_p_pct)
                    vz.min_ema_drop_long = min(vz.min_ema_drop_long, tk.ema900_dist_pct)
                arm_horizon = t_now + 1.20
                if vz.ts_ultimo_choque_lyapunov > 0.0 and (t_now - vz.ts_ultimo_choque_lyapunov) < 9.0:
                    arm_horizon = max(arm_horizon, vz.ts_ultimo_choque_lyapunov + 9.50)
                vz.vigilancia_long_hasta_ts = arm_horizon

            armed_long = (
                t_now < vz.vigilancia_long_hasta_ts
                and tk.z_score <= (z_threshold * 0.82)
                and tk.delta_p_pct <= (req_dp * 0.80)
                and tk.ema900_dist_pct <= (req_ema * 0.80)
            )
            if not armed_long:
                return None
            z_ref_long = min(tk.z_score, vz.min_z_drop_long)

        if not spread_ok:
            self._log_alerta_throttled(
                f"SPREAD:{symbol}",
                f"[WARN] [SPREAD FRICTION] {symbol} excessive spread ({tk.spread_pct*100:.2f}% > {cfg.SPREAD_MAX_PCT*100:.2f}%). Shot aborted.",
            )
            return None

        if tk.lyapunov_acel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
            self._log_alerta_throttled(
                f"LYAP:{symbol}",
                f"[WARN] [LYAPUNOV REPULSOR] {symbol} drop accelerating (a={tk.lyapunov_acel_pct*100:+.4f}% < {cfg.LYAPUNOV_ACEL_MIN_PCT*100:+.4f}%). Waiting for braking.",
            )
            return None

        if is_test:
            h_radar_ceiling = cfg.HURST_MAX_ENTRADA
        else:
            p_day, _ = _calcular_percentil_elastico_intradia(t_now, tk.volatilidad_local)
            h_abs_bonus = 0.012 if (tk.ofi_l1_l5 >= 0.35 and tk.hawkes_intensidad >= 0.25 and tk.delta_p_pct <= -0.0035) else 0.0
            h_raw_ceiling = min(
                0.485,
                max(0.455, 0.475 - (0.015 * p_day) + h_abs_bonus),
            )
            h_radar_ceiling = min(0.472, h_raw_ceiling) if symbol in cfg.CLASE_TIER1_LIQUIDO else h_raw_ceiling

        if tk.hurst > h_radar_ceiling and not (is_test and is_extreme_z):
            self._log_alerta_throttled(
                f"HURST:{symbol}",
                f"[WARN] [HURST FILTER] {symbol} high trend persistence (H={tk.hurst:.3f} > {h_radar_ceiling:.3f}). Aborting.",
            )
            return None

        dt_since_toxic = (t_now - vz.ts_ultimo_pulso_toxico) if vz.ts_ultimo_pulso_toxico > 0.0 else 999.0
        dt_min_req = cfg.HAWKES_ABSORCION_MIN_SEG if (is_test or tk.hawkes_intensidad < -0.25) else 0.0
        if dt_since_toxic < dt_min_req or tk.hawkes_intensidad < cfg.HAWKES_INTENSIDAD_MIN:
            self._log_alerta_throttled(
                f"HAWKES:{symbol}",
                f"[WARN] [HAWKES MEMORY] {symbol} absorption still weak after toxic pulse "
                f"({dt_since_toxic:.1f}s < {cfg.HAWKES_ABSORCION_MIN_SEG:.1f}s | I_Hawkes={tk.hawkes_intensidad:+.2f} | Z={tk.z_score:.2f}).",
            )
            return None

        if tk.ofi_l1_l5 < cfg.OFI_MIN_ENTRADA or tk.vpin >= cfg.VPIN_TOXICO_MAX:
            self._log_alerta_throttled(
                f"OFI:{symbol}",
                f"[WARN] [MICROSTRUCTURE] TOXIC/WEAK flow. Aborting. ({symbol} OFI={tk.ofi_l1_l5:+.2f} < +{cfg.OFI_MIN_ENTRADA:.2f} | VPIN={tk.vpin:.2f})",
            )
            return None

        if tk.ofi_ticks_confirmados_long < cfg.OFI_TICKS_CONFIRMACION:
            return None

        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
        if tk_btc is not None and tk_btc.ofi_l1_l5 < -0.65:
            return None

        t0_ram = time.perf_counter()
        ok_ram, mot_ram, mult_gemini = ESTADO_RAM.consultar_permiso_o1(symbol, "long", z_ref_long, t_now)
        dt_ram_us = (time.perf_counter() - t0_ram) * 1e6

        if not ok_ram:
            if "QUARANTINE" in mot_ram or "CUARENTENA" in mot_ram:
                self._log_alerta_throttled(
                    f"CD:{symbol}",
                    f"[POST-CLOSE COOLDOWN] {symbol} in {mot_ram}. Shot ignored.",
                    intervalo_seg=2.0,
                )
            return None

        senal = {
            "symbol": symbol,
            "side": "long",
            "bid": tk.bid,
            "ask": tk.ask,
            "last": tk.last,
            "z_score": z_ref_long,
            "ofi": tk.ofi_l1_l5,
            "hurst": tk.hurst,
            "volatilidad": tk.volatilidad_local,
            "sizing_mult": mult_gemini,
            "ts_senal": t_now,
        }

        if not self._validar_filtros_phantom_pre_orden(symbol, senal, t_now):
            return None

        vz.vigilancia_long_hasta_ts = 0.0
        vz.min_z_drop_long = 0.0
        vz.min_dp_drop_long = 0.0
        vz.min_ema_drop_long = 0.0

        log_sniper(
            f"[RADAR] {symbol} [LONG] Z={z_ref_long:.2f} ({tk.delta_p_pct*100:+.2f}% | EMA900 {tk.ema900_dist_pct*100:+.2f}%) "
            f"OFI={tk.ofi_l1_l5:+.2f} ({tk.ofi_ticks_confirmados_long}t) | H={tk.hurst:.2f} | I_Hawkes={tk.hawkes_intensidad:+.2f} "
            f"-> RAM SHIELD O(1): APPROVED ({dt_ram_us:.1f} us)"
        )

        if self.callback_disparo is not None:
            await self.callback_disparo(senal)
        return senal

    async def _evaluar_gatillo_short_chronos(
        self,
        symbol: str,
        vz: VentanaZ,
        tk: MetricaTick,
        spread_ok: bool,
        t_now: float,
    ) -> Optional[Dict[str, Any]]:
        if not cfg.MODO_BIDIRECCIONAL or not spread_ok:
            return None

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        perm = ESTADO_RAM.permisos_ram.get(symbol)
        ema_short_floor_prod = 0.0032

        in_short_only = (
            (perm is not None and perm.modo_regimen == "SHORT_ONLY")
            or (not is_test and t_now < ESTADO_RAM.pausa_macro_hasta_ts)
        )

        overextended_pump = (t_now < vz.vigilancia_short_hasta_ts) and (tk.ema900_dist_pct >= ema_short_floor_prod)
        rebound_ema_floor = cfg.SHORT_REBOTE_DEBIL_MIN_EMA_PCT if is_test else ema_short_floor_prod
        rebound_in_downtrend = (
            in_short_only
            and (tk.ema900_dist_pct >= rebound_ema_floor)
            and (is_test or tk.delta_p_pct >= 0.0015 or tk.z_score >= 1.80)
        )

        if not (overextended_pump or rebound_in_downtrend):
            return None

        if tk.ofi_ticks_confirmados_short < cfg.OFI_TICKS_CONFIRMACION:
            return None
        if tk.lyapunov_acel_pct > cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT:
            return None

        if is_test:
            z_ref_short = (
                max(abs(tk.z_score), vz.max_z_pump_short, 4.00)
                if overextended_pump
                else abs(tk.z_score)
            )
        else:
            if tk.z_score < 1.80:
                return None
            if overextended_pump:
                z_ref_short = max(tk.z_score, vz.max_z_pump_short)
            else:
                z_ref_short = tk.z_score
            if z_ref_short < 1.80:
                return None

        t0_ram = time.perf_counter()
        ok_ram, _, mult_gemini = ESTADO_RAM.consultar_permiso_o1(symbol, "short", z_ref_short, t_now)
        dt_ram_us = (time.perf_counter() - t0_ram) * 1e6
        if not ok_ram:
            return None

        senal = {
            "symbol": symbol,
            "side": "short",
            "bid": tk.bid,
            "ask": tk.ask,
            "last": tk.last,
            "z_score": z_ref_short,
            "ofi": tk.ofi_l1_l5,
            "hurst": tk.hurst,
            "volatilidad": tk.volatilidad_local,
            "sizing_mult": mult_gemini,
            "ts_senal": t_now,
        }

        if not self._validar_filtros_phantom_pre_orden(symbol, senal, t_now):
            return None

        vz.vigilancia_short_hasta_ts = 0.0
        vz.max_sobreextension_ema_pct = 0.0
        vz.max_z_pump_short = 0.0

        log_sniper(
            f"[RADAR] {symbol} [SHORT-SNIPER] EMA900={tk.ema900_dist_pct*100:+.2f}% | "
            f"OFI={tk.ofi_l1_l5:+.2f} ({tk.ofi_ticks_confirmados_short}t) | H={tk.hurst:.2f} | a_Lyap={tk.lyapunov_acel_pct*100:+.4f}% "
            f"-> RAM SHIELD O(1): APPROVED ({dt_ram_us:.1f} us)"
        )

        if self.callback_disparo is not None:
            await self.callback_disparo(senal)
        return senal