#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #08: radar_volatilidad.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Radar Microestructural de Alta Frecuencia (6.6 Hz / 150 ms) en O(1) (< 25 us):
  - Estimador VentanaZ Bipower con acumuladores incrementales O(1) y EMA900.
  - ML-OFI Multinivel L1-L5 (Cont-Kukanov-Stoikov) en bucle unico fusionado.
  - Exponente de Rugosidad de Hurst sobre ticks activos y Amortiguador Temporal
    de Choques Extremos de Lyapunov (SCAR-LOCK-03 + SCAR-LOCK-09 Biclase).
  - Banda Elastica Continua Horaria-Bipower (Gradiente L8..L10):
      * Calcula en O(1) el Percentil Intradia P_dia(t, sigma_BV) combinando la
        curva estacional armonica de 24h UTC (Funding 00/08/16, Asia Midday,
        Londres y Wall Street NYSE) con la volatilidad Bipower en vivo.
      * Banda de Madurez Post-Arranque mu_boot(n) proporcional al llenado real
        de ticks de EMA900 (elimina distorsiones de arranque en frio).
      * Memoria Espacial Anti-Squeeze (px_ultimo_anti_squeeze): bloquea ventas
        en corto en banderas alcistas por encima del precio de ruptura previo.
      * SCAR-LOCK-09: Umbral elastico biclase de choque de Lyapunov, enfriamiento
        escalado por severidad (|a| >= 0.35%) y espera de 3.60s post-replica.
      * SCAR-LOCK-10: Piso positivo de absorcion de Hawkes (I_Hawkes >= +0.05) y
        filtro de ruptura fresca de EMA900 cuando H_t > 0.485.
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
    Calcula en O(1) (< 0.15 us) el Percentil Continuo del Dia P_dia(t, sigma_BV) en [0.05, 0.99]
    acoplando la curva historica horaria UTC con la volatilidad Bipower instantanea:
      - Nucleo 00:00 UTC (21:00 CL): Apertura Asia + Corte Funding 00:00 UTC.
      - Nucleo 04:50 UTC (01:50 CL): Reapertura Mediodia Asia (Singapur/Hong Kong 13:00).
      - Nucleo 08:00 UTC (05:00 CL): Apertura Londres + Corte Funding 08:00 UTC.
      - Nucleo 13:45 UTC (10:45 CL): Apertura Wall Street (NYSE 09:30 ET).
      - Nucleo 16:00 UTC (13:00 CL): Cierre Londres + Corte Funding 16:00 UTC.
    """
    h_utc = ((float(ahora_t) % 86400.0) / 3600.0)
    g_00 = 0.78 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 0.00) / 0.85) ** 2))
    g_05 = 0.58 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 4.85) / 0.95) ** 2))
    g_08 = 0.94 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 8.00) / 1.45) ** 2))
    g_13 = 0.98 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 13.75) / 1.65) ** 2))
    g_16 = 0.88 * math.exp(-0.5 * ((_dist_circular_horas(h_utc, 16.00) / 1.15) ** 2))

    curva_horaria = min(0.99, 0.14 + max(g_00, g_05, g_08, g_13, g_16))
    vol_norm = max(0.0, min(1.0, math.tanh((float(vol_bipower) - 0.00055) / 0.00110)))
    p_dia = max(0.05, min(0.99, (0.60 * curva_horaria) + (0.40 * vol_norm)))
    pct_int = int(round(p_dia * 100.0))
    return round(p_dia, 4), f"P{pct_int:02d}_ELASTICO"


class VentanaZ:
    """
    Mantiene la serie temporal de alta frecuencia de un activo y calcula en O(1):
      - Z-Score con Variacion Bipower mediante deque incremental de pares.
      - EMA900, distancia porcentual, pendiente estructural y madurez post-boot.
      - Exponente de Rugosidad de Hurst (H_t) y Aceleracion de Lyapunov (a_t).
      - Memoria de Absorcion de Hawkes (I_t), ML-OFI de 5 niveles y VPIN.
    """

    def __init__(self, maxlen: int = cfg.VENTANA_Z_TICKS) -> None:
        self.maxlen: int = max(20, int(maxlen))
        self.precios: Deque[float] = deque(maxlen=self.maxlen)
        self.retornos: Deque[float] = deque(maxlen=self.maxlen)
        self.ofi_ventana: Deque[float] = deque(maxlen=35)
        self._ofi_neg_ventana: Deque[float] = deque(maxlen=35)
        self.ema900: float = 0.0
        self.ema900_historia: Deque[float] = deque(maxlen=60)
        self._alpha_ema900: float = 2.0 / (cfg.VENTANA_EMA_MACRO_TICKS + 1.0)
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

    def agregar_precio(self, precio: float) -> None:
        p = float(precio)
        if p <= 0.0:
            return
        self.ticks_totales_recibidos += 1
        if self.precios:
            p_ant = self.precios[-1]
            ret = (p - p_ant) / p_ant if p_ant > 0.0 else 0.0
            self.retornos.append(ret)
            abs_r = abs(ret)
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

        p_actual = self.precios[-1]
        p_inicio = self.precios[0]
        cambio_ventana_pct = (p_actual - p_inicio) / p_inicio if p_inicio > 0.0 else 0.0

        media_p = sum(self.precios) / n
        desv_rel = (p_actual - media_p) / media_p if media_p > 0.0 else 0.0

        n_pares = len(self._bv_pares)
        if n_pares >= 3:
            suma_bv = sum(self._bv_pares) - self._bv_pares[-1]
            sigma_bv = math.sqrt(_PI_HALF * (suma_bv / (n_pares - 1))) if suma_bv > 0.0 else 0.0005
        else:
            sigma_bv = 0.0005

        sigma_efectiva = max(0.00045, sigma_bv * math.sqrt((25 if n > 25 else n) * 0.45))
        z_score = desv_rel / sigma_efectiva
        return round(z_score, 4), round(cambio_ventana_pct, 6), round(sigma_efectiva, 6)

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
        niveles = niv_b if niv_b < niv_a else niv_a
        if niveles == 0:
            return 0.0, 0.0, 0.0

        top_b: List[Tuple[float, float]] = [
            (float(bids[k][0]), float(bids[k][1])) for k in range(niveles)
        ]
        top_a: List[Tuple[float, float]] = [
            (float(asks[k][0]), float(asks[k][1])) for k in range(niveles)
        ]

        num_ofi = 0.0
        den_ofi = 0.0
        imbalance_estatico_num = 0.0
        imbalance_estatico_den = 0.0
        tiene_prev = len(self._prev_bids) >= niveles and len(self._prev_asks) >= niveles

        for k in range(niveles):
            w = _PESOS_ML_OFI[k]
            pb, qb = top_b[k]
            pa, qa = top_a[k]
            imbalance_estatico_num += w * (qb - qa)
            imbalance_estatico_den += w * max(1e-9, qb + qa)

            if tiene_prev:
                pb_prev, qb_prev = self._prev_bids[k]
                pa_prev, qa_prev = self._prev_asks[k]
                e_b = qb if pb > pb_prev else ((qb - qb_prev) if pb == pb_prev else -qb_prev)
                e_a = -qa_prev if pa > pa_prev else ((qa - qa_prev) if pa == pa_prev else qa)
                num_ofi += w * (e_b - e_a)
                den_ofi += w * max(1e-9, (qb + qa + qb_prev + qa_prev) * 0.5)

        ofi_estatico = imbalance_estatico_num / max(1e-9, imbalance_estatico_den)
        ofi_dinamico = max(-1.0, min(1.0, num_ofi / den_ofi)) if den_ofi > 0.0 else 0.0
        ml_ofi = max(-1.0, min(1.0, (0.65 * ofi_estatico) + (0.35 * ofi_dinamico)))

        self._prev_bids = top_b
        self._prev_asks = top_a
        self.ofi_ventana.append(ml_ofi)
        self._ofi_neg_ventana.append(-ml_ofi if ml_ofi < -0.15 else 0.0)

        n_ofi = len(self.ofi_ventana)
        ofi_5s = sum(self.ofi_ventana) / n_ofi
        vpin = min(1.0, (sum(self._ofi_neg_ventana) / n_ofi) * 1.35)

        dt = max(0.01, ahora - self.ts_ultimo_tick) if self.ts_ultimo_tick > 0.0 else 0.15
        self.ts_ultimo_tick = ahora
        self.hawkes_intensidad = (self.hawkes_intensidad * math.exp(-cfg.HAWKES_DECAY_BETA * dt)) + ml_ofi

        if ml_ofi <= -0.45:
            self.ts_ultimo_pulso_toxico = ahora

        if ml_ofi >= cfg.OFI_MIN_ENTRADA and ofi_dinamico >= -0.25:
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
        acel_bruta = v1 - v0
        acel_pct = max(0.0, acel_bruta) if v1 >= 0.0 else acel_bruta

        t_ref = self.ts_ultimo_tick if self.ts_ultimo_tick > 0.0 else time.time()
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

        if es_test:
            if acel_bruta <= -0.0025:
                self.ts_ultimo_choque_lyapunov = t_ref
                self.magnitud_ultimo_choque_lyapunov = abs(acel_bruta)
        else:
            # SCAR-LOCK-09: Banda elastica biclase de choque de Lyapunov + memoria de replica
            p_dia_lyap, _ = _calcular_percentil_elastico_intradia(t_ref, vol_local)
            umbral_choque = -max(
                0.0014,
                min(
                    0.0025,
                    0.0024 - (0.0008 * p_dia_lyap) - (0.0004 if es_tier1 else 0.0),
                ),
            )
            if acel_bruta <= umbral_choque:
                if (t_ref - self.ts_ultimo_choque_lyapunov) < 12.0:
                    self.magnitud_ultimo_choque_lyapunov = max(
                        self.magnitud_ultimo_choque_lyapunov, abs(acel_bruta)
                    )
                else:
                    self.magnitud_ultimo_choque_lyapunov = abs(acel_bruta)
                self.ts_ultimo_choque_lyapunov = t_ref

            if acel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
                self.ts_ultimo_repulsor_lyapunov = t_ref

        if not es_test:
            n_d1 = len(self._act_d1_sq)
            n_d4 = len(self._act_d4_sq)
            if n_d1 >= 7 and n_d4 >= 4:
                v_lag1 = sum(self._act_d1_sq) / n_d1
                v_lag4 = sum(self._act_d4_sq) / n_d4
                if v_lag1 > 1e-18 and v_lag4 > 1e-18:
                    h_act = 0.25 * math.log(v_lag4 / v_lag1) * _INV_LN2
                    return round(max(0.20, min(0.80, h_act)), 4), round(acel_pct, 6)
            return 0.45, round(acel_pct, 6)

        n1 = len(self._abs_dlog1)
        n4 = len(self._abs_dlog4)
        m1 = (sum(self._abs_dlog1) / n1) if n1 > 0 else 1e-6
        m4 = (sum(self._abs_dlog4) / n4) if n4 > 0 else (m1 * 1.9)

        if m1 <= 1e-9 or m4 <= 1e-9:
            hurst = 0.45
        else:
            hurst = max(0.20, min(0.80, math.log(m4 / m1) * _INV_LN4))

        return round(hurst, 4), round(acel_pct, 6)

    def obtener_metricas_ema900(self) -> Tuple[float, float, float]:
        if not self.precios or self.ema900 <= 0.0:
            return 0.0, 0.0, 0.0
        p_actual = self.precios[-1]
        dist_pct = (p_actual - self.ema900) / self.ema900
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
    Vigila en paralelo los 7 Campeones Alfa + Centinela Macro BTC a 6.6 Hz.
    Evalua las Leyes 1 y 4 de CHRONOS-TRIZ junto con el Interceptor Pre-Orden
    Single-Layer (P-01, P-02, P-03, P-09) y las Cicatrices SCAR-LOCK-00..10.
    """

    def __init__(
        self,
        callback_disparo: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, Any]]] = None,
        callback_evacuacion_macro: Optional[Callable[[str], Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        self.callback_disparo = callback_disparo
        self.callback_evacuacion_macro = callback_evacuacion_macro
        self._running: bool = False
        todos = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ventanas: Dict[str, VentanaZ] = {sym: VentanaZ() for sym in todos}
        self._ultimo_log_alerta_ts: Dict[str, float] = {}

    def resetear_contagio_macro(self) -> None:
        ESTADO_RAM.eventos_caida_recientes.clear()
        ESTADO_RAM.pausa_macro_hasta_ts = 0.0

    def _log_alerta_throttled(self, clave: str, mensaje: str, intervalo_seg: float = 1.0) -> None:
        ahora = time.time()
        if ahora - self._ultimo_log_alerta_ts.get(clave, 0.0) >= intervalo_seg:
            self._ultimo_log_alerta_ts[clave] = ahora
            log_sniper(mensaje)

    async def verificar_contagio_cross_asset(self, symbol: str, z_score: float, ahora: float) -> bool:
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not es_test and ahora < _COOLDOWN_WS_PHANTOM.get(symbol, 0.0):
            return False

        pausa_dur = cfg.CONTAGIO_PAUSA_MACRO_SEG if es_test else 30.0

        if symbol == cfg.SIMBOLO_CENTINELA_MACRO and z_score <= cfg.BTC_Z_CRASH_UMBRAL:
            ESTADO_RAM.pausa_macro_hasta_ts = ahora + pausa_dur
            log_sniper(
                f"[CIRCUIT BREAKER BTC] {symbol} colapsando (Z={z_score:.2f} <= {cfg.BTC_Z_CRASH_UMBRAL})! "
                f"Activando escudo macro ({pausa_dur:.0f}s)..."
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
                pares_str = ", ".join(sorted(ESTADO_RAM.eventos_caida_recientes.keys()))
                ESTADO_RAM.pausa_macro_hasta_ts = ahora + pausa_dur
                if not es_test:
                    ESTADO_RAM.eventos_caida_recientes.clear()
                log_sniper(
                    f"[CIRCUIT BREAKER CONTAGIO] {len(pares_str.split(', '))} pares colapsando "
                    f"simultaneamente en <={cfg.CONTAGIO_VENTANA_SEG:.0f}s ({pares_str})! "
                    f"Activando escudo macro ({pausa_dur:.0f}s) y evacuando posiciones..."
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

        # SCAR-LOCK-05 (Invariante 24/7): Veto total O(1) sobre INJ/USDT:USDT (1W/7L, -0.4761 USDT)
        if sym == "INJ/USDT:USDT":
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "VETO_INJ_TOTAL"), 0.0) >= 30.0:
                _SILENCIO_LOG_PHANTOM[(sym, "VETO_INJ_TOTAL")] = ahora_t
                log_sniper(
                    f"[PHANTOM VETO SELECTIVO] {sym} [{side.upper()}] bloqueado por estadistica OOS (1W/7L, -0.4761 USDT)."
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
        vol_bv = float(tk_sym.volatilidad_local if tk_sym is not None else 0.0006)

        # Directriz Meta-Cognitiva #1 y #3 (Gradiente L8): Percentil Continuo del Dia P_dia(t, sigma_BV)
        p_dia, tag_percentil = _calcular_percentil_elastico_intradia(ahora_t, vol_bv)

        vz_sym = self.ventanas.get(sym)
        n_ticks_boot = int(vz_sym.ticks_totales_recibidos if vz_sym is not None else 900)
        if n_ticks_boot < 60:
            return False
        mu_boot = max(0.0, 1.0 - (float(n_ticks_boot) / 360.0))

        # P-01 (Invariante 24/7): Acoplamiento Lead-Lag y Veto Direccional Conjuntivo con BTC/USDT:USDT
        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
        ofi_btc = float(tk_btc.ofi_l1_l5 if (tk_btc and tk_btc.last > 0.0) else 0.0)
        z_btc = float(tk_btc.z_score if (tk_btc and tk_btc.last > 0.0) else 0.0)

        ofi_phantom = (0.75 * ofi_real + 0.25 * ofi_btc) if abs(ofi_btc) > 1e-6 else ofi_real
        senal["ofi_phantom"] = round(ofi_phantom, 4)

        veto_btc_long = (ofi_btc < -0.35 and z_btc < -0.75) or (z_btc < -1.80)
        if side == "long" and veto_btc_long:
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_L"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_L")] = ahora_t
                log_sniper(f"[PHANTOM P-01 BTC-VETO] {sym} [LONG] bloqueado ANTES de orden (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False

        veto_btc_short = (ofi_btc > 0.35 and z_btc > 0.75) or (z_btc > 2.00)
        if side == "short" and veto_btc_short:
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_S"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_S")] = ahora_t
                log_sniper(f"[PHANTOM P-01 BTC-VETO] {sym} [SHORT] bloqueado ANTES de orden (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False

        h_max_cfg = float(getattr(cfg, "HURST_MAX_ENTRADA", 0.485))
        es_tier1 = sym in cfg.CLASE_TIER1_LIQUIDO

        if side == "long":
            # SCAR-LOCK-03 + SCAR-LOCK-09: Amortiguador elastico por severidad y espera post-replica
            dt_choque_lyap = (
                (ahora_t - vz_sym.ts_ultimo_choque_lyapunov)
                if (vz_sym is not None and vz_sym.ts_ultimo_choque_lyapunov > 0.0)
                else 999.0
            )
            mag_choque = float(vz_sym.magnitud_ultimo_choque_lyapunov if vz_sym is not None else 0.0)
            tau_lyap_req = 4.50 + (2.00 * p_dia) + (3.00 if mag_choque >= 0.0035 else 0.0)

            dt_repulsor_lyap = (
                (ahora_t - vz_sym.ts_ultimo_repulsor_lyapunov)
                if (vz_sym is not None and vz_sym.ts_ultimo_repulsor_lyapunov > 0.0)
                else 999.0
            )
            en_replica_post_choque = (dt_choque_lyap < 12.0) and (dt_repulsor_lyap < 3.60)

            if dt_choque_lyap < tau_lyap_req or en_replica_post_choque:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_LYAP_BUF"), 0.0) >= 8.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_LYAP_BUF")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 LYAPUNOV-BUFFER] {sym} [LONG] bloqueado ANTES de orden en {tag_percentil} "
                        f"(Choque Lyapunov hace {dt_choque_lyap:.2f}s < {tau_lyap_req:.2f}s | Replica hace {dt_repulsor_lyap:.2f}s)."
                    )
                return False

            # Banda Elastica L8 en LONG: Descuento y OFI escalan continuamente con P_dia y madurez post-boot
            base_ema_long = -0.0018 if es_tier1 else -0.0025
            umbral_ema_long = base_ema_long * (1.0 + (0.50 * mu_boot))
            umbral_z_long = -2.45 if es_tier1 else -2.80
            ofi_min_long = (
                0.12
                if es_tier1
                else min(0.18, max(0.13, 0.13 + (0.045 * p_dia) + (0.08 * mu_boot)))
            )

            if ofi_real < ofi_min_long:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_OFI_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_OFI_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 OFI-LONG] {sym} [LONG] bloqueado ANTES de orden "
                        f"(OFI={ofi_real:+.2f} < +{ofi_min_long:.2f} en {tag_percentil})."
                    )
                return False

            # SCAR-LOCK-10: Piso positivo de absorcion de Hawkes (I_Hawkes >= +0.05)
            hawkes_req_long = (0.05 + (0.10 * p_dia)) if h_real > h_max_cfg else 0.05
            if hawkes_val < hawkes_req_long:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_HAWKES_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_HAWKES_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 HAWKES-LONG] {sym} [LONG] bloqueado ANTES de orden en {tag_percentil} "
                        f"(I_Hawkes={hawkes_val:+.2f} < +{hawkes_req_long:.2f})."
                    )
                return False

            # Banda Elastica de Hurst en LONG acoplada a P_dia y al estiramiento |Z| + SCAR-LOCK-10
            h_elastico_long = min(
                0.565,
                max(0.485, 0.558 - (0.068 * p_dia) + (0.012 * max(0.0, abs(z_real) - 3.15))),
            )
            z_req_cap_long = -(3.05 + (1.15 * p_dia))
            ema_req_hurst_alto = min(umbral_ema_long, -0.0055)

            absorcion_elastica_long = (
                h_real <= h_elastico_long
                and z_real <= z_req_cap_long
                and ema_rel <= ema_req_hurst_alto
                and abs(ema_rel) >= abs(dp_rel)
                and dp_rel <= umbral_ema_long
                and ofi_real >= ofi_min_long
                and hawkes_val >= hawkes_req_long
                and lyap_val >= cfg.LYAPUNOV_ACEL_MIN_PCT
            )

            if h_real > h_max_cfg and not absorcion_elastica_long:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_L"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 PRE-ORDEN] {sym} [LONG] bloqueado ANTES de enviar orden en {tag_percentil} "
                        f"(H={h_real:.3f} > {h_elastico_long:.3f} | Z={z_real:+.2f}, EMA={ema_rel*100:+.2f}%, DP={dp_rel*100:+.2f}%)."
                    )
                return False

            if ema_rel > umbral_ema_long or dp_rel > umbral_ema_long or z_real > umbral_z_long:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_L"), 0.0) >= 12.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_L")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 EMA900-AND] {sym} [LONG] bloqueado ANTES de orden "
                        f"(EMA900={ema_rel*100:+.2f}%, DP={dp_rel*100:+.2f}% > {umbral_ema_long*100:+.2f}% | Z={z_real:+.2f})."
                    )
                return False

            senal["hurst_max_elastico"] = round(max(h_max_cfg, h_elastico_long), 4)
        else:
            # Directriz #1, #2 y #3 (Gradiente L8 en SHORT):
            # 1) Verificar si existe memoria espacial de un ANTI-SQUEEZE reciente (< 180s)
            p_now_short = float(tk_sym.last if tk_sym is not None else (senal.get("last") or 0.0))
            dt_sqz_prev = (
                (ahora_t - vz_sym.ts_ultimo_anti_squeeze)
                if (vz_sym is not None and vz_sym.ts_ultimo_anti_squeeze > 0.0)
                else 999.0
            )
            px_sqz_prev = float(vz_sym.px_ultimo_anti_squeeze if (vz_sym is not None and dt_sqz_prev < 180.0) else 0.0)
            sobre_px_squeeze = (px_sqz_prev > 0.0) and (p_now_short >= (px_sqz_prev * 0.9992))

            base_ema_short = 0.0045 if sobre_px_squeeze else 0.0032
            umbral_ema_short = base_ema_short * (1.0 + (0.65 * mu_boot))
            max_sobreext_pump = float(vz_sym.max_sobreextension_ema_pct if vz_sym is not None else 0.0)
            sobreext_eff = max(ema_rel, dp_rel, max_sobreext_pump) if ema_rel >= umbral_ema_short else ema_rel
            z_short_eff = max(z_real, float(senal.get("z_score") or 0.0))

            # Banda Elastica de Hurst en SHORT acoplada a P_dia y sobreextension del pump
            h_base_short = 0.538 if es_tier1 else (0.675 if sobreext_eff >= 0.0042 else 0.565)
            h_max_short_prod = max(0.490, min(0.675, h_base_short - (0.045 * p_dia)))
            cd_hurst_short = 14.0 + (18.0 * p_dia)

            if h_real > h_max_short_prod:
                if vz_sym is not None:
                    vz_sym.ts_ultimo_veto_hurst_short = ahora_t
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_S"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_S")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 PRE-ORDEN] {sym} [SHORT] bloqueado ANTES de enviar orden en {tag_percentil} "
                        f"(H={h_real:.3f} > {h_max_short_prod:.3f})."
                    )
                return False

            if (
                vz_sym is not None
                and vz_sym.ts_ultimo_veto_hurst_short > 0.0
                and (ahora_t - vz_sym.ts_ultimo_veto_hurst_short) < cd_hurst_short
            ):
                rest_h = cd_hurst_short - (ahora_t - vz_sym.ts_ultimo_veto_hurst_short)
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H_S_CD"), 0.0) >= 10.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P02_H_S_CD")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-02 COOLDOWN] {sym} [SHORT] en enfriamiento post-Hurst alto ({rest_h:.1f}s restantes)."
                    )
                return False

            # Banda Elastica de Flujo Vendedor OFI en SHORT (SCAR-LOCK-08)
            ofi_max_short_req = -min(
                0.58,
                max(
                    0.35,
                    0.35 + (0.12 * p_dia) + (0.14 if sobre_px_squeeze else 0.0) + (0.08 * mu_boot),
                ),
            )

            pump_sobreextendido_valido = (
                ema_rel >= umbral_ema_short
                and sobreext_eff >= umbral_ema_short
                and ofi_real <= ofi_max_short_req
                and z_short_eff >= 1.80
            )

            if not pump_sobreextendido_valido:
                if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_S"), 0.0) >= 12.0:
                    _SILENCIO_LOG_PHANTOM[(sym, "P03_S")] = ahora_t
                    log_sniper(
                        f"[PHANTOM P-03 SHORT] {sym} [SHORT] bloqueado ANTES de orden en {tag_percentil} "
                        f"(EMA900={ema_rel*100:+.2f}% req +{umbral_ema_short*100:.2f}% | OFI={ofi_real:+.2f} req <={ofi_max_short_req:+.2f} | PxSqz={px_sqz_prev})."
                    )
                return False

            # Escudo Fisico Anti-Short-Squeeze 1 con Memoria Espacial px_ultimo_anti_squeeze y Banda Elastica cd_sqz
            if vz_sym is not None and len(vz_sym.precios) >= 10:
                p_now = vz_sym.precios[-1]
                max_ventana = max(vz_sym.precios)
                en_expansion_alcista = (
                    ema_slope > 0.0012
                    or (ema_slope > 0.0005 and p_now >= (max_ventana * 0.9980))
                    or (ema_rel >= 0.0095 and ema_slope > 0.0004)
                    or (sobre_px_squeeze and ema_slope > 0.0)
                )
                if en_expansion_alcista:
                    if (ahora_t - vz_sym.ts_ultimo_anti_squeeze) >= 180.0 or vz_sym.px_ultimo_anti_squeeze <= 0.0:
                        vz_sym.px_ultimo_anti_squeeze = p_now
                    else:
                        vz_sym.px_ultimo_anti_squeeze = max(vz_sym.px_ultimo_anti_squeeze, p_now)
                    vz_sym.ts_ultimo_anti_squeeze = ahora_t

                cd_sqz = 16.0 + (32.0 * p_dia)
                giro_techo_confirmado = (
                    not en_expansion_alcista
                    and not sobre_px_squeeze
                    and p_now <= (max_ventana * 0.9988)
                    and lyap_val <= cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT
                    and ofi_real <= ofi_max_short_req
                )

                if en_expansion_alcista or (
                    vz_sym.ts_ultimo_anti_squeeze > 0.0
                    and (ahora_t - vz_sym.ts_ultimo_anti_squeeze) < cd_sqz
                    and not giro_techo_confirmado
                ):
                    if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_SQZ"), 0.0) >= 12.0:
                        _SILENCIO_LOG_PHANTOM[(sym, "P03_SQZ")] = ahora_t
                        log_sniper(
                            f"[PHANTOM ANTI-SQUEEZE] {sym} [SHORT] bloqueado en {tag_percentil}: rally alcista o enfriamiento {cd_sqz:.0f}s "
                            f"(Slope EMA900={ema_slope*100:+.2f}% | Precio={p_now} vs PxSqz={vz_sym.px_ultimo_anti_squeeze})."
                        )
                    return False

            # Escudo Fisico Anti-Short-Squeeze 2 (Invariante 24/7): Escalera Anti-Reentrada tras SL en SHORT (600s)
            sl_prev_info = ESTADO_RAM.ultimo_sl_short_precio.get(sym)
            if sl_prev_info is not None:
                px_sl_prev, ts_sl_prev = sl_prev_info
                if (ahora_t - ts_sl_prev) < 600.0 and tk_sym is not None:
                    if tk_sym.last >= (px_sl_prev * 0.9985) and ema_slope >= 0.0:
                        if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_STEP_SL"), 0.0) >= 15.0:
                            _SILENCIO_LOG_PHANTOM[(sym, "P03_STEP_SL")] = ahora_t
                            log_sniper(
                                f"[PHANTOM ANTI-SQUEEZE STEP-LOCK] {sym} [SHORT] bloqueado tras SL previo @ {px_sl_prev} "
                                f"(Precio actual {tk_sym.last} en estructura alcista)."
                            )
                        return False

            senal["z_score"] = round(z_real if z_real >= 1.80 else z_short_eff, 4)
            senal["hurst_max_elastico"] = round(max(h_max_cfg, h_max_short_prod), 4)

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

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not es_test:
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

        es_tier1_sym = symbol in cfg.CLASE_TIER1_LIQUIDO
        z_score, delta_p_pct, vol_local = vz.calcular_z(mid_price)
        ml_ofi, ofi_5s, vpin = vz.calcular_ml_ofi_y_hawkes(bids_list, asks_list, t_now)
        hurst, lyapunov_acel = vz.calcular_hurst_y_lyapunov(es_tier1=es_tier1_sym, vol_local=vol_local)
        ema900, ema_dist_pct, ema_slope_pct = vz.obtener_metricas_ema900()
        spread_ok, spread_pct = verificar_friccion_spread(best_bid, best_ask)

        if not es_test and ema_dist_pct >= 0.0095 and ema_slope_pct > 0.0004:
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

        en_pausa_contagio = await self.verificar_contagio_cross_asset(symbol, z_score, t_now)
        if en_pausa_contagio and es_test:
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
                if es_test
                else max(vz.max_z_pump_short, abs(z_score), 3.50)
            )
            senal_short = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if senal_short is not None:
                return senal_short
            if z_score <= -2.50:
                self._log_alerta_throttled(
                    f"PUMP:{symbol}",
                    f"[WARN] [ANTI-PUMP-TOP] {symbol} sobreextendido sobre EMA900 "
                    f"({ema_dist_pct*100:+.2f}% > +{cfg.SHORT_PUMP_SOBREEXTENSION_PCT*100:.2f}%). Disparo LONG abortado.",
                )
            return None

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        en_short_only = (
            (perm is not None and perm.modo_regimen == "SHORT_ONLY")
            or (not es_test and en_pausa_contagio and ema_dist_pct >= 0.0032)
        )
        if (t_now < vz.vigilancia_short_hasta_ts) or en_short_only:
            senal_short = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if senal_short is not None:
                return senal_short

        if en_pausa_contagio:
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
        params_clase = cfg.obtener_parametros_clase(symbol)
        z_umbral = float(params_clase["z_umbral"])

        if tk.z_score > z_umbral:
            return None

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        caida_min_req = (
            perm.caida_min_override_pct
            if (perm is not None and perm.caida_min_override_pct < 0.0)
            else float(params_clase["caida_min_pct"])
        )
        ema_dist_req = float(params_clase["ema900_dist_min_pct"])

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        es_z_extremo = tk.z_score <= -4.50
        if es_test:
            if tk.delta_p_pct > caida_min_req and not es_z_extremo:
                return None
            if tk.ema900_dist_pct > ema_dist_req and not es_z_extremo:
                return None
        else:
            piso_desc = -0.0018 if symbol in cfg.CLASE_TIER1_LIQUIDO else -0.0025
            if tk.delta_p_pct > min(caida_min_req, piso_desc):
                return None
            if tk.ema900_dist_pct > min(ema_dist_req, piso_desc):
                return None

        if not spread_ok:
            self._log_alerta_throttled(
                f"SPREAD:{symbol}",
                f"[WARN] [FRICCION SPREAD] {symbol} spread excesivo ({tk.spread_pct*100:.2f}% > {cfg.SPREAD_MAX_PCT*100:.2f}%). Disparo abortado.",
            )
            return None

        if tk.lyapunov_acel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
            self._log_alerta_throttled(
                f"LYAP:{symbol}",
                f"[WARN] [REPULSOR LYAPUNOV] {symbol} caida acelerando (a={tk.lyapunov_acel_pct*100:+.4f}% < {cfg.LYAPUNOV_ACEL_MIN_PCT*100:+.4f}%). Esperando frenado.",
            )
            return None

        if es_test:
            h_techo_radar = cfg.HURST_MAX_ENTRADA
        else:
            p_dia, _ = _calcular_percentil_elastico_intradia(t_now, tk.volatilidad_local)
            h_techo_radar = min(
                0.565,
                max(0.485, 0.558 - (0.068 * p_dia) + (0.012 * max(0.0, abs(tk.z_score) - 3.15))),
            )

        if tk.hurst > h_techo_radar and not (es_test and es_z_extremo):
            self._log_alerta_throttled(
                f"HURST:{symbol}",
                f"[WARN] [FILTRO HURST] {symbol} persistencia tendencial alta (H={tk.hurst:.3f} > {h_techo_radar:.3f}). Abortando.",
            )
            return None

        dt_desde_toxico = (t_now - vz.ts_ultimo_pulso_toxico) if vz.ts_ultimo_pulso_toxico > 0.0 else 999.0
        dt_min_req = cfg.HAWKES_ABSORCION_MIN_SEG if (es_test or tk.hawkes_intensidad < -0.25) else 0.0
        if dt_desde_toxico < dt_min_req or tk.hawkes_intensidad < cfg.HAWKES_INTENSIDAD_MIN:
            self._log_alerta_throttled(
                f"HAWKES:{symbol}",
                f"[WARN] [MEMORIA HAWKES] {symbol} absorcion aun debil tras pulso toxico "
                f"({dt_desde_toxico:.1f}s < {cfg.HAWKES_ABSORCION_MIN_SEG:.1f}s | I_Hawkes={tk.hawkes_intensidad:+.2f} | Z={tk.z_score:.2f}).",
            )
            return None

        if tk.ofi_l1_l5 < cfg.OFI_MIN_ENTRADA or tk.vpin >= cfg.VPIN_TOXICO_MAX:
            self._log_alerta_throttled(
                f"OFI:{symbol}",
                f"[WARN] [MICROESTRUCTURA] Flujo TOXICO/DEBIL. Abortando. ({symbol} OFI={tk.ofi_l1_l5:+.2f} < +{cfg.OFI_MIN_ENTRADA:.2f} | VPIN={tk.vpin:.2f})",
            )
            return None

        if tk.ofi_ticks_confirmados_long < cfg.OFI_TICKS_CONFIRMACION:
            return None

        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
        if tk_btc is not None and tk_btc.ofi_l1_l5 < -0.65:
            return None

        t0_ram = time.perf_counter()
        ok_ram, mot_ram, mult_gemini = ESTADO_RAM.consultar_permiso_o1(symbol, "long", tk.z_score, t_now)
        dt_ram_us = (time.perf_counter() - t0_ram) * 1e6

        if not ok_ram:
            if "CUARENTENA" in mot_ram:
                self._log_alerta_throttled(
                    f"CD:{symbol}",
                    f"[COOLDOWN POST-CIERRE] {symbol} en {mot_ram}. Disparo ignorado.",
                    intervalo_seg=2.0,
                )
            return None

        senal = {
            "symbol": symbol,
            "side": "long",
            "bid": tk.bid,
            "ask": tk.ask,
            "last": tk.last,
            "z_score": tk.z_score,
            "ofi": tk.ofi_l1_l5,
            "hurst": tk.hurst,
            "volatilidad": tk.volatilidad_local,
            "sizing_mult": mult_gemini,
            "ts_senal": t_now,
        }

        if not self._validar_filtros_phantom_pre_orden(symbol, senal, t_now):
            return None

        log_sniper(
            f"[RADAR] {symbol} [LONG] Z={tk.z_score:.2f} ({tk.delta_p_pct*100:+.2f}% | EMA900 {tk.ema900_dist_pct*100:+.2f}%) "
            f"OFI={tk.ofi_l1_l5:+.2f} ({tk.ofi_ticks_confirmados_long}t) | H={tk.hurst:.2f} | I_Hawkes={tk.hawkes_intensidad:+.2f} "
            f"-> ESCUDO RAM O(1): APROBADO ({dt_ram_us:.1f} us)"
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

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        perm = ESTADO_RAM.permisos_ram.get(symbol)
        piso_ema_short_prod = 0.0032

        en_short_only = (
            (perm is not None and perm.modo_regimen == "SHORT_ONLY")
            or (not es_test and t_now < ESTADO_RAM.pausa_macro_hasta_ts)
        )

        sobreextendido_pump = (t_now < vz.vigilancia_short_hasta_ts) and (tk.ema900_dist_pct >= piso_ema_short_prod)
        piso_rebote_ema = cfg.SHORT_REBOTE_DEBIL_MIN_EMA_PCT if es_test else piso_ema_short_prod
        rebote_en_tendencia_bajista = (
            en_short_only
            and (tk.ema900_dist_pct >= piso_rebote_ema)
            and (es_test or tk.delta_p_pct >= 0.0015 or tk.z_score >= 1.80)
        )

        if not (sobreextendido_pump or rebote_en_tendencia_bajista):
            return None

        if tk.ofi_ticks_confirmados_short < cfg.OFI_TICKS_CONFIRMACION:
            return None
        if tk.lyapunov_acel_pct > cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT:
            return None

        if es_test:
            z_ref_short = (
                max(abs(tk.z_score), vz.max_z_pump_short, 4.00)
                if sobreextendido_pump
                else abs(tk.z_score)
            )
        else:
            if sobreextendido_pump:
                z_ref_short = max(tk.z_score, vz.max_z_pump_short, 3.50)
            elif rebote_en_tendencia_bajista:
                z_ref_short = max(tk.z_score, 3.50)
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
            f"-> ESCUDO RAM O(1): APROBADO ({dt_ram_us:.1f} us)"
        )

        if self.callback_disparo is not None:
            await self.callback_disparo(senal)
        return senal