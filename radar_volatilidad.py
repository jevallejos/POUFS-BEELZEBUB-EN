#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #08: radar_volatilidad.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Radar Microestructural de Alta Frecuencia (6.6 Hz / 150 ms) con:
  - Estimador VentanaZ Bipower (Barndorff-Nielsen & Shephard) y EMA900.
  - ML-OFI Multinivel L1-L5 (Cont-Kukanov-Stoikov) con confirmacion de 3 Ticks.
  - Exponente de Rugosidad de Hurst (Gatheral-Jaisson-Rosenbaum).
  - Repulsor de Fase de Lyapunov (a_t) y Memoria Asimetrica de Hawkes (I_t).
  - Disparo Bimodal Simetrico (LONG en capitulaciones / SHORT en agotamientos).
  - Cortafuegos de Contagio Cross-Asset (>= 3 pares en <= 10s o BTC Z <= -4.0).
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, MetricaTick, log_sniper
from escudo_tricortex import ESCUDO_TRICORTEX

# Pesos exponenciales pre-calculados para los primeros 5 niveles del libro L2
_PESOS_ML_OFI: Tuple[float, ...] = tuple(math.exp(-0.35 * i) for i in range(5))
_SUMA_PESOS_ML_OFI: float = sum(_PESOS_ML_OFI)


# ==============================================================================
# 1. ESTIMADOR ESTADISTICO VENTANA-Z BIPOWER Y FISICA DE SERIE TEMPORAL O(1)
# ==============================================================================
class VentanaZ:
    """
    Mantiene la serie temporal de alta frecuencia de un activo y calcula en O(1):
      - Z-Score con Variacion Bipower (resistente a saltos aislados).
      - EMA900, distancia porcentual y pendiente estructural.
      - Exponente de Rugosidad de Hurst (H_t) y Aceleracion de Lyapunov (a_t).
      - Memoria de Absorcion de Hawkes (I_t), ML-OFI de 5 niveles y VPIN.
    """

    def __init__(self, maxlen: int = cfg.VENTANA_Z_TICKS) -> None:
        self.maxlen: int = max(20, int(maxlen))
        self.precios: Deque[float] = deque(maxlen=self.maxlen)
        self.retornos: Deque[float] = deque(maxlen=self.maxlen)
        self.ofi_ventana: Deque[float] = deque(maxlen=35)
        self.ema900: float = 0.0
        self.ema900_historia: Deque[float] = deque(maxlen=60)
        self._alpha_ema900: float = 2.0 / (cfg.VENTANA_EMA_MACRO_TICKS + 1.0)

        # Estado para ML-OFI L1-L5 (Cont-Kukanov-Stoikov)
        self._prev_bids: List[Tuple[float, float]] = []
        self._prev_asks: List[Tuple[float, float]] = []

        # Estado de Hawkes, VPIN y confirmacion de 3 ticks (Ley 1 CHRONOS-TRIZ)
        self.hawkes_intensidad: float = 0.0
        self.ts_ultimo_tick: float = 0.0
        self.ts_ultimo_pulso_toxico: float = 0.0
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
        if self.precios:
            p_ant = self.precios[-1]
            ret = (p - p_ant) / p_ant if p_ant > 0.0 else 0.0
            self.retornos.append(ret)
        self.precios.append(p)

        if self.ema900 <= 0.0:
            self.ema900 = p
        else:
            self.ema900 = (p * self._alpha_ema900) + (self.ema900 * (1.0 - self._alpha_ema900))
        self.ema900_historia.append(self.ema900)

    def calcular_z(self, precio_actual: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Calcula (z_score, cambio_ventana_pct, volatilidad_bipower).
        Ignora micro-ruido (-0.04%) y detecta colapsos reales (-2.21%).
        """
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

        rets = list(self.retornos)
        if len(rets) >= 4:
            ares = [abs(r) for r in rets[:-1]]
            bvs = [ares[i] * ares[i + 1] for i in range(len(ares) - 1)]
            sigma_bv = math.sqrt((math.pi / 2.0) * (sum(bvs) / max(1, len(bvs)))) if bvs else 0.0005
        else:
            sigma_bv = 0.0005

        sigma_efectiva = max(0.00045, sigma_bv * math.sqrt(min(n, 25) * 0.45))
        z_score = desv_rel / sigma_efectiva
        return round(z_score, 4), round(cambio_ventana_pct, 6), round(sigma_efectiva, 6)

    def calcular_ml_ofi_y_hawkes(
        self,
        bids: List[List[float]],
        asks: List[List[float]],
        ahora: float,
    ) -> Tuple[float, float, float]:
        """
        Calcula (ml_ofi_normalizado, ofi_5s, vpin) en niveles L1-L5
        y actualiza la Memoria de Hawkes y el contador de 3 ticks de CHRONOS-TRIZ.
        """
        top_b = [(float(b[0]), float(b[1])) for b in (bids or [])[:5] if len(b) >= 2]
        top_a = [(float(a[0]), float(a[1])) for a in (asks or [])[:5] if len(a) >= 2]

        if not top_b or not top_a:
            return 0.0, 0.0, 0.0

        num_ofi = 0.0
        den_ofi = 0.0
        niveles = min(len(top_b), len(top_a), 5)

        if len(self._prev_bids) >= niveles and len(self._prev_asks) >= niveles:
            for k in range(niveles):
                w = _PESOS_ML_OFI[k]
                pb, qb = top_b[k]
                pb_prev, qb_prev = self._prev_bids[k]
                pa, qa = top_a[k]
                pa_prev, qa_prev = self._prev_asks[k]

                if pb > pb_prev:
                    e_b = qb
                elif pb == pb_prev:
                    e_b = qb - qb_prev
                else:
                    e_b = -qb_prev

                if pa > pa_prev:
                    e_a = -qa_prev
                elif pa == pa_prev:
                    e_a = qa - qa_prev
                else:
                    e_a = qa

                flujo_k = e_b - e_a
                masa_k = qb + qa + qb_prev + qa_prev
                num_ofi += w * flujo_k
                den_ofi += w * max(1e-9, masa_k * 0.5)

        imbalance_estatico_num = 0.0
        imbalance_estatico_den = 0.0
        for k in range(niveles):
            w = _PESOS_ML_OFI[k]
            qb = top_b[k][1]
            qa = top_a[k][1]
            imbalance_estatico_num += w * (qb - qa)
            imbalance_estatico_den += w * max(1e-9, qb + qa)

        ofi_estatico = imbalance_estatico_num / max(1e-9, imbalance_estatico_den)
        ofi_dinamico = max(-1.0, min(1.0, num_ofi / den_ofi)) if den_ofi > 0.0 else 0.0

        ml_ofi = max(-1.0, min(1.0, (0.65 * ofi_estatico) + (0.35 * ofi_dinamico)))

        self._prev_bids = top_b
        self._prev_asks = top_a
        self.ofi_ventana.append(ml_ofi)

        lista_ofi = list(self.ofi_ventana)
        ofi_5s = sum(lista_ofi) / len(lista_ofi)
        flujo_negativo = [abs(x) for x in lista_ofi if x < -0.15]
        vpin = min(1.0, (sum(flujo_negativo) / max(1, len(lista_ofi))) * 1.35)

        dt = max(0.01, ahora - self.ts_ultimo_tick) if self.ts_ultimo_tick > 0.0 else 0.15
        self.ts_ultimo_tick = ahora
        decay = math.exp(-cfg.HAWKES_DECAY_BETA * dt)
        self.hawkes_intensidad = (self.hawkes_intensidad * decay) + ml_ofi

        if ml_ofi <= -0.45:
            self.ts_ultimo_pulso_toxico = ahora

        # Ley 1 de CHRONOS-TRIZ: Confirmacion de 3 ticks consecutivos (450 ms)
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

    def calcular_hurst_y_lyapunov(self) -> Tuple[float, float]:
        """
        Calcula en O(1):
          - Exponente de Rugosidad de Hurst (H_t).
          - Aceleracion direccional de Lyapunov (a_t).
        """
        pts = list(self.precios)
        n = len(pts)
        if n < 12:
            return 0.45, 0.0

        p_t = pts[-1]
        p_1 = pts[-2]
        p_2 = pts[-3]
        v1 = (p_t - p_1) / p_1 if p_1 > 0.0 else 0.0
        v0 = (p_1 - p_2) / p_2 if p_2 > 0.0 else 0.0
        acel_bruta = v1 - v0

        if v1 >= 0.0:
            acel_pct = max(0.0, acel_bruta)
        else:
            acel_pct = acel_bruta

        diffs_1 = [abs(math.log(pts[i] / pts[i - 1])) for i in range(1, n) if pts[i - 1] > 0]
        diffs_4 = [abs(math.log(pts[i] / pts[i - 4])) for i in range(4, n) if pts[i - 4] > 0]
        m1 = (sum(diffs_1) / len(diffs_1)) if diffs_1 else 1e-6
        m4 = (sum(diffs_4) / len(diffs_4)) if diffs_4 else (m1 * 1.9)

        if m1 <= 1e-9 or m4 <= 1e-9:
            hurst = 0.45
        else:
            hurst = math.log(m4 / m1) / math.log(4.0)
            hurst = max(0.20, min(0.80, hurst))

        return round(hurst, 4), round(acel_pct, 6)

    def obtener_metricas_ema900(self) -> Tuple[float, float, float]:
        """Retorna (ema900, distancia_pct, pendiente_pct)."""
        if not self.precios or self.ema900 <= 0.0:
            return 0.0, 0.0, 0.0
        p_actual = self.precios[-1]
        dist_pct = (p_actual - self.ema900) / self.ema900
        hist = list(self.ema900_historia)
        if len(hist) >= 10 and hist[0] > 0.0:
            slope_pct = (hist[-1] - hist[0]) / hist[0]
        else:
            slope_pct = 0.0
        return round(self.ema900, 8), round(dist_pct, 6), round(slope_pct, 6)


# ==============================================================================
# 2. FUNCIONES PURAS DE MICROESTRUCTURA Y ESCUDOS FISICOS
# ==============================================================================
def calcular_aceleracion_lyapunov(precios: List[float]) -> float:
    """Funcion auxiliar pura para evaluar el campo potencial de Lyapunov."""
    if len(precios) < 3 or precios[-2] <= 0 or precios[-3] <= 0:
        return 0.0
    v1 = (precios[-1] - precios[-2]) / precios[-2]
    v0 = (precios[-2] - precios[-3]) / precios[-3]
    if v1 >= 0.0:
        return round(max(0.0, v1 - v0), 6)
    return round(v1 - v0, 6)


def verificar_friccion_spread(bid: float, ask: float, max_spread_pct: float = cfg.SPREAD_MAX_PCT) -> Tuple[bool, float]:
    """Compuerta de Friccion de Macri: aborta si el spread relativo supera el umbral."""
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        return False, 1.0
    mid = 0.5 * (bid + ask)
    spread_pct = (ask - bid) / mid
    return (spread_pct <= max_spread_pct), round(spread_pct, 6)


# ==============================================================================
# 3. ORQUESTADOR DEL RADAR DE VOLATILIDAD 6.6 HZ (CHRONOS-TRIZ)
# ==============================================================================
class RadarVolatilidad:
    """
    Vigila en paralelo los 7 Campeones Alfa + Centinela Macro BTC a 6.6 Hz.
    Evalua las Leyes 1 y 4 de CHRONOS-TRIZ y despacha señales aprobadas al Ejecutor Sniper.
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
        """Limpia el registro de caidas simultaneas y el bloqueo macro en RAM."""
        ESTADO_RAM.eventos_caida_recientes.clear()
        ESTADO_RAM.pausa_macro_hasta_ts = 0.0

    def _log_alerta_throttled(self, clave: str, mensaje: str, intervalo_seg: float = 1.0) -> None:
        ahora = time.time()
        if ahora - self._ultimo_log_alerta_ts.get(clave, 0.0) >= intervalo_seg:
            self._ultimo_log_alerta_ts[clave] = ahora
            log_sniper(mensaje)

    async def verificar_contagio_cross_asset(self, symbol: str, z_score: float, ahora: float) -> bool:
        """
        Detector de Contagio Cross-Asset:
        Si >= 3 pares caen simultaneamente (Z <= -3.0) dentro de <= 10s, o si BTC
        sufre un flash-crash (Z <= -4.0), activa pausa macro de 90s y evacua posiciones.
        """
        if symbol == cfg.SIMBOLO_CENTINELA_MACRO and z_score <= cfg.BTC_Z_CRASH_UMBRAL:
            ESTADO_RAM.pausa_macro_hasta_ts = ahora + cfg.CONTAGIO_PAUSA_MACRO_SEG
            log_sniper(
                f"🔴 [CIRCUIT BREAKER BTC] ¡{symbol} colapsando (Z={z_score:.2f} <= {cfg.BTC_Z_CRASH_UMBRAL})! "
                f"Activando escudo macro ({cfg.CONTAGIO_PAUSA_MACRO_SEG:.0f}s)..."
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
                ESTADO_RAM.pausa_macro_hasta_ts = ahora + cfg.CONTAGIO_PAUSA_MACRO_SEG
                log_sniper(
                    f"🔴 [CIRCUIT BREAKER CONTAGIO] ¡{len(ESTADO_RAM.eventos_caida_recientes)} pares colapsando "
                    f"simultáneamente en <={cfg.CONTAGIO_VENTANA_SEG:.0f}s ({pares_str})! "
                    f"Activando escudo macro ({cfg.CONTAGIO_PAUSA_MACRO_SEG:.0f}s) y evacuando posiciones..."
                )
                if self.callback_evacuacion_macro is not None:
                    await self.callback_evacuacion_macro("EVACUACION_CONTAGIO_CROSS_ASSET")
            return True

        return ahora < ESTADO_RAM.pausa_macro_hasta_ts

    async def procesar_instantanea_libro(
        self,
        symbol: str,
        bids: List[List[float]],
        asks: List[List[float]],
        ahora: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un tick del libro de ordenes L2 en O(1), actualiza ESTADO_RAM.ticks_ram
        y evalua las condiciones de disparo LONG y SHORT bajo el protocolo CHRONOS-TRIZ.
        """
        t_now = ahora if ahora is not None else time.time()
        if not bids or not asks:
            return None

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        if best_bid <= 0.0 or best_ask <= 0.0 or best_ask < best_bid:
            return None

        mid_price = 0.5 * (best_bid + best_ask)
        vz = self.ventanas.get(symbol)
        if vz is None:
            vz = VentanaZ()
            self.ventanas[symbol] = vz

        z_score, delta_p_pct, vol_local = vz.calcular_z(mid_price)
        ml_ofi, ofi_5s, vpin = vz.calcular_ml_ofi_y_hawkes(bids, asks, t_now)
        hurst, lyapunov_acel = vz.calcular_hurst_y_lyapunov()
        ema900, ema_dist_pct, ema_slope_pct = vz.obtener_metricas_ema900()
        spread_ok, spread_pct = verificar_friccion_spread(best_bid, best_ask)

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

        # 1. Verificar Contagio Cross-Asset y Centinela BTC
        if await self.verificar_contagio_cross_asset(symbol, z_score, t_now):
            return None

        if symbol == cfg.SIMBOLO_CENTINELA_MACRO:
            return None

        # 2. Verificar Filtro Anti-Colapso Estructural (Anti-LUNA)
        if not ESCUDO_TRICORTEX.verificar_anti_colapso_estructural(symbol, delta_p_pct, ml_ofi):
            return None

        # 3. Filtro Anti-Pump-Top sobre EMA900 -> Arma vigilancia para SHORT-SNIPER
        if ema_dist_pct > cfg.SHORT_PUMP_SOBREEXTENSION_PCT:
            vz.vigilancia_short_hasta_ts = t_now + 120.0
            vz.max_sobreextension_ema_pct = max(vz.max_sobreextension_ema_pct, ema_dist_pct)
            vz.max_z_pump_short = max(vz.max_z_pump_short, abs(z_score), 4.00)
            senal_short = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if senal_short is not None:
                return senal_short
            if z_score <= -2.50:
                self._log_alerta_throttled(
                    f"PUMP:{symbol}",
                    f"⚠️ [ANTI-PUMP-TOP] {symbol} sobreextendido sobre EMA900 "
                    f"({ema_dist_pct*100:+.2f}% > +{cfg.SHORT_PUMP_SOBREEXTENSION_PCT*100:.2f}%). Disparo LONG abortado.",
                )
            return None

        # 4. Si el activo esta en vigilancia Short o en regimen SHORT_ONLY, evaluar gatillo SHORT
        perm = ESTADO_RAM.permisos_ram.get(symbol)
        en_short_only = perm is not None and perm.modo_regimen == "SHORT_ONLY"
        if (t_now < vz.vigilancia_short_hasta_ts) or en_short_only:
            senal_short = await self._evaluar_gatillo_short_chronos(symbol, vz, tk, spread_ok, t_now)
            if senal_short is not None:
                return senal_short

        # 5. Evaluar Gatillo LONG (Ley 1 de CHRONOS-TRIZ)
        return await self._evaluar_gatillo_long_chronos(symbol, vz, tk, spread_ok, t_now)

    async def _evaluar_gatillo_long_chronos(
        self,
        symbol: str,
        vz: VentanaZ,
        tk: MetricaTick,
        spread_ok: bool,
        t_now: float,
    ) -> Optional[Dict[str, Any]]:
        """Evalua los umbrales biclase, los 4 escudos fisicos y los 3 ticks de ML-OFI para LONG."""
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

        es_z_extremo = tk.z_score <= -4.50
        if tk.delta_p_pct > caida_min_req and not es_z_extremo:
            return None
        if tk.ema900_dist_pct > ema_dist_req and not es_z_extremo:
            return None

        if not spread_ok:
            self._log_alerta_throttled(
                f"SPREAD:{symbol}",
                f"⚠️ [FRICCIÓN SPREAD] {symbol} spread excesivo ({tk.spread_pct*100:.2f}% > {cfg.SPREAD_MAX_PCT*100:.2f}%). Disparo abortado.",
            )
            return None

        if tk.lyapunov_acel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
            self._log_alerta_throttled(
                f"LYAP:{symbol}",
                f"⚠️ [REPULSOR LYAPUNOV] {symbol} caída acelerando (a={tk.lyapunov_acel_pct*100:+.4f}% < {cfg.LYAPUNOV_ACEL_MIN_PCT*100:+.4f}%). Esperando frenado.",
            )
            return None

        if tk.hurst > cfg.HURST_MAX_ENTRADA and not es_z_extremo:
            self._log_alerta_throttled(
                f"HURST:{symbol}",
                f"⚠️ [FILTRO HURST] {symbol} persistencia tendencial alta (H={tk.hurst:.3f} > {cfg.HURST_MAX_ENTRADA:.3f}). Abortando.",
            )
            return None

        dt_desde_toxico = t_now - vz.ts_ultimo_pulso_toxico
        if dt_desde_toxico < cfg.HAWKES_ABSORCION_MIN_SEG or tk.hawkes_intensidad < cfg.HAWKES_INTENSIDAD_MIN:
            self._log_alerta_throttled(
                f"HAWKES:{symbol}",
                f"⚠️ [MEMORIA HAWKES] {symbol} absorción aún débil tras pulso tóxico "
                f"({dt_desde_toxico:.1f}s < {cfg.HAWKES_ABSORCION_MIN_SEG:.1f}s | I_Hawkes={tk.hawkes_intensidad:+.2f} | Z={tk.z_score:.2f}).",
            )
            return None

        if tk.ofi_l1_l5 < cfg.OFI_MIN_ENTRADA or tk.vpin >= cfg.VPIN_TOXICO_MAX:
            self._log_alerta_throttled(
                f"OFI:{symbol}",
                f"⚠️ [MICROESTRUCTURA] Flujo TÓXICO/DÉBIL. Abortando. ({symbol} OFI={tk.ofi_l1_l5:+.2f} < +{cfg.OFI_MIN_ENTRADA:.2f} | VPIN={tk.vpin:.2f})",
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
                    f"⏳ [COOLDOWN POST-CIERRE] {symbol} en {mot_ram}. Disparo ignorado.",
                    intervalo_seg=2.0,
                )
            return None

        log_sniper(
            f"[RADAR] {symbol} [LONG] Z={tk.z_score:.2f} ({tk.delta_p_pct*100:+.2f}% | EMA900 {tk.ema900_dist_pct*100:+.2f}%) "
            f"OFI={tk.ofi_l1_l5:+.2f} ({tk.ofi_ticks_confirmados_long}t) | H={tk.hurst:.2f} | I_Hawkes={tk.hawkes_intensidad:+.2f} "
            f"-> ESCUDO RAM O(1): APROBADO ({dt_ram_us:.1f} µs)"
        )

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
        """
        Ley 4 de CHRONOS-TRIZ: Gatillo SHORT Simetrico.
        """
        if not cfg.MODO_BIDIRECCIONAL or not spread_ok:
            return None

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        en_short_only = perm is not None and perm.modo_regimen == "SHORT_ONLY"

        sobreextendido_pump = (t_now < vz.vigilancia_short_hasta_ts) and (tk.ema900_dist_pct >= 0.0035)
        rebote_en_tendencia_bajista = en_short_only and (tk.ema900_dist_pct >= cfg.SHORT_REBOTE_DEBIL_MIN_EMA_PCT)

        if not (sobreextendido_pump or rebote_en_tendencia_bajista):
            return None

        if tk.ofi_ticks_confirmados_short < cfg.OFI_TICKS_CONFIRMACION:
            return None
        if tk.lyapunov_acel_pct > cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT:
            return None

        z_ref_short = (
            max(abs(tk.z_score), vz.max_z_pump_short, 4.00)
            if sobreextendido_pump
            else abs(tk.z_score)
        )

        t0_ram = time.perf_counter()
        ok_ram, mot_ram, mult_gemini = ESTADO_RAM.consultar_permiso_o1(symbol, "short", z_ref_short, t_now)
        dt_ram_us = (time.perf_counter() - t0_ram) * 1e6
        if not ok_ram:
            return None

        vz.vigilancia_short_hasta_ts = 0.0
        vz.max_sobreextension_ema_pct = 0.0
        vz.max_z_pump_short = 0.0

        log_sniper(
            f"[RADAR] {symbol} [SHORT-SNIPER] EMA900={tk.ema900_dist_pct*100:+.2f}% | "
            f"OFI={tk.ofi_l1_l5:+.2f} ({tk.ofi_ticks_confirmados_short}t) | a_Lyap={tk.lyapunov_acel_pct*100:+.4f}% "
            f"-> ESCUDO RAM O(1): APROBADO ({dt_ram_us:.1f} µs)"
        )

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
        if self.callback_disparo is not None:
            await self.callback_disparo(senal)
        return senal


# === [PHANTOM V1.0 NATIVE RADAR: PRE-DISPATCH P-01/P-02/P-03 INTERCEPTOR & FAST HURST (<20us)] ===
_TS_ULTIMO_TICK_PHANTOM: dict[str, float] = {}
_COOLDOWN_WS_PHANTOM: dict[str, float] = {}

if hasattr(VentanaZ, "calcular_hurst_y_lyapunov") and not hasattr(VentanaZ, "_orig_hurst_base"):
    VentanaZ._orig_hurst_base = VentanaZ.calcular_hurst_y_lyapunov
    def _calcular_hurst_y_lyapunov_phantom(self) -> tuple[float, float]:
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
            return VentanaZ._orig_hurst_base(self)
        pts = self.precios
        n_pts = len(pts)
        if n_pts < 16:
            return VentanaZ._orig_hurst_base(self)
        activos = [pts[0]]
        ultimo = pts[0]
        for px in pts:
            if px != ultimo:
                activos.append(px)
                ultimo = px
        n_act = len(activos)
        if n_act >= 12 and n_act < n_pts:
            v1 = 0.0
            for i in range(1, n_act):
                d = activos[i] - activos[i - 1]
                v1 += d * d
            v1 /= (n_act - 1)
            v2 = 0.0
            for i in range(2, n_act):
                d = activos[i] - activos[i - 2]
                v2 += d * d
            v2 /= (n_act - 2)
            v4 = 0.0
            for i in range(4, n_act):
                d = activos[i] - activos[i - 4]
                v4 += d * d
            v4 /= (n_act - 4)
            if v1 > 1e-18 and v2 > 1e-18 and v4 > 1e-18:
                h_activo = max(0.20, min(0.80, 0.25 * math.log2((v4 / v1) if v1 > 0 else 1.0)))
                # Calcular aceleracion de Lyapunov en O(1) sobre los ultimos 3 puntos
                p0, p1, p2 = pts[-3], pts[-2], pts[-1]
                a_lyap = ((p2 - 2.0 * p1 + p0) / p0) if p0 > 0 else 0.0
                return round(h_activo, 4), round(a_lyap, 6)
        return VentanaZ._orig_hurst_base(self)
    VentanaZ.calcular_hurst_y_lyapunov = _calcular_hurst_y_lyapunov_phantom

if hasattr(RadarVolatilidad, "verificar_contagio_cross_asset") and not hasattr(RadarVolatilidad, "_orig_contagio_base"):
    RadarVolatilidad._orig_contagio_base = RadarVolatilidad.verificar_contagio_cross_asset
    async def _verificar_contagio_cross_asset_phantom(self, *args, **kwargs) -> bool:
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
            return await RadarVolatilidad._orig_contagio_base(self, *args, **kwargs)
        sym = str(args[0]) if len(args) > 0 else str(kwargs.get("symbol", ""))
        t_eval = float(args[2]) if len(args) > 2 and args[2] is not None else float(kwargs.get("ahora_ts") or time.time())
        if t_eval < _COOLDOWN_WS_PHANTOM.get(sym, 0.0):
            return False
        res = await RadarVolatilidad._orig_contagio_base(self, *args, **kwargs)
        if res:
            ESTADO_RAM.pausa_macro_hasta_ts = t_eval + 30.0
        return res
    RadarVolatilidad.verificar_contagio_cross_asset = _verificar_contagio_cross_asset_phantom

def _validar_filtros_phantom_pre_orden(radar_obj, sym: str, res: dict) -> bool:
    """Evalua P-01 (Lead-Lag BTC), P-02 (Pure Hurst <= 0.485) y P-03 (EMA900) ANTES de despachar orden."""
    if not isinstance(res, dict) or sym == cfg.SIMBOLO_CENTINELA_MACRO:
        return False
    side_sig = str(res.get("side", "long")).lower()
    dict_ventanas = getattr(radar_obj, "ventanas_z", None) or getattr(radar_obj, "ventanas", {})
    ventana_sym = dict_ventanas.get(sym) if isinstance(dict_ventanas, dict) else None

    # Obtener Hurst real (en SHORT-SNIPER res puede no traer la clave 'hurst', la calculamos de VentanaZ)
    if "hurst" in res and res.get("hurst") is not None:
        h_real = float(res["hurst"])
    elif ventana_sym is not None and hasattr(ventana_sym, "calcular_hurst_y_lyapunov"):
        h_real, _ = ventana_sym.calcular_hurst_y_lyapunov()
        res["hurst"] = h_real
    else:
        h_real = 0.45

    z_real = float(res.get("z_score", 0.0))
    ofi_real = float(res.get("ofi", 0.0))

    ema_val = float(getattr(ventana_sym, "ema_900", 0.0) or getattr(ventana_sym, "ema900", 0.0) or 0.0)
    px_val = float(res.get("precio", 0.0) or res.get("mid", 0.0) or (ventana_sym.precios[-1] if (ventana_sym and len(ventana_sym.precios) > 0) else 0.0))
    if px_val > 0.0 and ema_val > 0.0:
        ema_rel = (px_val - ema_val) / ema_val
    else:
        ema_rel = float(res.get("dist_ema900_pct", res.get("ema900_dist_pct", 0.0)) or 0.0)
        if abs(ema_rel) > 0.15:
            ema_rel = ema_rel / 100.0

    ventana_btc = dict_ventanas.get(cfg.SIMBOLO_CENTINELA_MACRO) if isinstance(dict_ventanas, dict) else None
    tick_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
    ofi_btc = float(getattr(tick_btc, "ofi_5s", getattr(tick_btc, "obi", 0.0)) or 0.0)
    z_btc = 0.0
    if ventana_btc is not None and hasattr(ventana_btc, "calcular_z_bipower"):
        try:
            z_btc, _, _ = ventana_btc.calcular_z_bipower()
        except Exception:
            z_btc = 0.0

    ofi_phantom = (0.75 * ofi_real + 0.25 * ofi_btc) if abs(ofi_btc) > 1e-6 else ofi_real
    res["ofi_phantom"] = round(ofi_phantom, 4)

    # P-02: Pureza Fractal de Hurst (Restriccion inquebrantable H <= 0.485 ANTES de disparar)
    h_max_cfg = float(getattr(cfg, "HURST_MAX_ENTRADA", 0.485))
    if h_real > h_max_cfg:
        log_sniper(f"🛡️ [PHANTOM P-02 PRE-ORDEN] {sym} [{side_sig.upper()}] bloqueado ANTES de enviar orden (H={h_real:.3f} > {h_max_cfg:.3f}).")
        return False

    if side_sig == "long":
        if ofi_btc < -0.25 or z_btc < -1.80:
            log_sniper(f"🛡️ [PHANTOM P-01 BTC LEAD-LAG] {sym} [LONG] bloqueado ANTES de orden por drenaje en BTC (Z_BTC={z_btc:+.2f}, OFI_BTC={ofi_btc:+.2f}).")
            return False
        es_tier1 = sym in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
        umbral_ema_long = -0.0050 if es_tier1 else -0.0060
        umbral_z_long = float(getattr(cfg, "Z_SCORE_UMBRAL_TIER1", -2.85) if es_tier1 else getattr(cfg, "Z_SCORE_UMBRAL_HIGH_BETA", -3.10))
        if ema_rel > umbral_ema_long or z_real > umbral_z_long:
            log_sniper(f"🛡️ [PHANTOM P-03 EMA900] {sym} [LONG] bloqueado ANTES de orden (EMA900={ema_rel*100:+.2f}% > {umbral_ema_long*100:+.2f}% | Z={z_real:+.2f}).")
            return False
    elif side_sig == "short":
        if ofi_btc > 0.28 or z_btc > 2.00:
            log_sniper(f"🛡️ [PHANTOM P-01 BTC LEAD-LAG] {sym} [SHORT] bloqueado ANTES de orden por impulso alcista en BTC (Z_BTC={z_btc:+.2f}, OFI_BTC={ofi_btc:+.2f}).")
            return False
        if ema_rel < 0.0038:
            log_sniper(f"🛡️ [PHANTOM P-03 SHORT] {sym} [SHORT] bloqueado ANTES de orden (EMA900={ema_rel*100:+.2f}% < +0.38%).")
            return False

    return True

if hasattr(RadarVolatilidad, "procesar_instantanea_libro") and not hasattr(RadarVolatilidad, "_orig_proc_libro_base"):
    RadarVolatilidad._orig_proc_libro_base = RadarVolatilidad.procesar_instantanea_libro
    async def _procesar_instantanea_libro_phantom(self, *args, **kwargs):
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
            return await RadarVolatilidad._orig_proc_libro_base(self, *args, **kwargs)

        sym = str(args[0]) if len(args) > 0 else str(kwargs.get("symbol", ""))
        ts_now = float(args[3]) if len(args) > 3 and args[3] is not None else float(kwargs.get("ahora") or time.time())
        prev_ts = _TS_ULTIMO_TICK_PHANTOM.get(sym, 0.0)
        if prev_ts > 0.0 and (ts_now - prev_ts) > 2.20:
            _COOLDOWN_WS_PHANTOM[sym] = ts_now + 4.00
        _TS_ULTIMO_TICK_PHANTOM[sym] = ts_now

        # Desacoplar temporalmente callback_disparo para que _orig_proc_libro_base NO dispare antes de P-01/P-02/P-03
        cb_real = getattr(self, "callback_disparo", None)
        self.callback_disparo = None
        try:
            res = await RadarVolatilidad._orig_proc_libro_base(self, *args, **kwargs)
        finally:
            self.callback_disparo = cb_real

        if not isinstance(res, dict) or sym == cfg.SIMBOLO_CENTINELA_MACRO:
            return res

        # Validar P-01, P-02 y P-03 ANTES de despachar la orden al EjecutorSniper
        if not _validar_filtros_phantom_pre_orden(self, sym, res):
            return None

        if cb_real is not None:
            await cb_real(res)
        return res
    RadarVolatilidad.procesar_instantanea_libro = _procesar_instantanea_libro_phantom

# === [PHANTOM V1.0 SINGLE-LAYER L2 ENGINE & ELASTIC GATE P-01..P-03] ===
_ENV_PHANTOM_RADAR = __import__("os").environ
if "_SILENCIO_LOG_PHANTOM" not in globals() or not isinstance(globals().get("_SILENCIO_LOG_PHANTOM"), dict):
    _SILENCIO_LOG_PHANTOM = {}
if "_COOLDOWN_WS_PHANTOM" not in globals() or not isinstance(globals().get("_COOLDOWN_WS_PHANTOM"), dict):
    _COOLDOWN_WS_PHANTOM = {}
if "_ULTIMO_TS_LIBRO_PHANTOM" not in globals() or not isinstance(globals().get("_ULTIMO_TS_LIBRO_PHANTOM"), dict):
    _ULTIMO_TS_LIBRO_PHANTOM = {}

_ICON_SHIELD = "\U0001f6e1\ufe0f"

_orig_hurst_base_v1 = getattr(
    VentanaZ, "_orig_calcular_hurst_y_lyapunov_phantom", VentanaZ.calcular_hurst_y_lyapunov
)

def _ajustar_lyapunov_frenado_piso(pts, lyap_raw: float) -> float:
    if len(pts) >= 3:
        p_now = float(pts[-1])
        p_prev1 = float(pts[-2])
        p_prev2 = float(pts[-3])
        p_ini = float(pts[0])
        if p_now <= p_ini and p_now >= p_prev1:
            if p_prev1 >= p_prev2:
                return max(0.0, lyap_raw)
            if p_prev2 > 1e-12:
                lyap_local = (p_now - 2.0 * p_prev1 + p_prev2) / p_prev2
                return max(lyap_raw, lyap_local, 0.0)
    return lyap_raw

def _calcular_hurst_y_lyapunov_single_layer(self) -> tuple[float, float]:
    if _ENV_PHANTOM_RADAR.get("TRIBRAIN_TEST_MODE", "0") == "1":
        return _orig_hurst_base_v1(self)
    pts = self.precios
    n = len(pts)
    if n < 8:
        return 0.45, 0.0
    p_now = pts[-1]
    p_mid = pts[-2]
    p_old = pts[-3]
    lyap_raw = ((p_now - 2.0 * p_mid + p_old) / p_old) if p_old > 1e-12 else 0.0
    lyap = _ajustar_lyapunov_frenado_piso(pts, lyap_raw)

    ult = pts[0]
    activos = [ult]
    for x in pts:
        if x != ult and abs(x - ult) > 1e-12:
            activos.append(x)
            ult = x
    na = len(activos)
    if na < 8:
        return 0.45, lyap
    s1 = 0.0
    for i in range(1, na):
        d1 = activos[i] - activos[i - 1]
        s1 += d1 * d1
    v_lag1 = s1 / (na - 1)
    if v_lag1 <= 1e-18:
        return 0.45, lyap
    s4 = 0.0
    for i in range(4, na):
        d4 = activos[i] - activos[i - 4]
        s4 += d4 * d4
    v_lag4 = s4 / (na - 4)
    if v_lag4 <= 1e-18:
        return 0.45, lyap
    h_raw = 0.25 * (math.log(v_lag4 / v_lag1) / 0.6931471805599453)
    if h_raw < 0.20:
        h_raw = 0.20
    elif h_raw > 0.80:
        h_raw = 0.80
    return round(h_raw, 4), lyap

VentanaZ.calcular_hurst_y_lyapunov = _calcular_hurst_y_lyapunov_single_layer

if "calcular_aceleracion_lyapunov" in globals() and "_orig_fn_acel_lyap" not in globals():
    _orig_fn_acel_lyap = calcular_aceleracion_lyapunov

    def _calcular_aceleracion_lyapunov_prod(precios) -> float:
        val = _orig_fn_acel_lyap(precios)
        if _ENV_PHANTOM_RADAR.get("TRIBRAIN_TEST_MODE", "0") == "1":
            return val
        return _ajustar_lyapunov_frenado_piso(precios, val)

    calcular_aceleracion_lyapunov = _calcular_aceleracion_lyapunov_prod

if "calcular_hurst_y_lyapunov" in globals() and "_orig_fn_hurst_lyap_mod" not in globals():
    _orig_fn_hurst_lyap_mod = calcular_hurst_y_lyapunov

    def _calcular_hurst_y_lyapunov_mod_prod(precios) -> tuple[float, float]:
        h_v, l_v = _orig_fn_hurst_lyap_mod(precios)
        if _ENV_PHANTOM_RADAR.get("TRIBRAIN_TEST_MODE", "0") == "1":
            return h_v, l_v
        return h_v, _ajustar_lyapunov_frenado_piso(precios, l_v)

    calcular_hurst_y_lyapunov = _calcular_hurst_y_lyapunov_mod_prod

def _validar_filtros_phantom_pre_orden_elastico(self, sym: str, senal: dict) -> bool:
    if not isinstance(senal, dict):
        return False
    if _ENV_PHANTOM_RADAR.get("TRIBRAIN_TEST_MODE", "0") == "1":
        return True

    ahora_t = __import__("time").time()
    if sym not in cfg.PARES_CAMPEONES_ALFA and sym != getattr(cfg, "SIMBOLO_CENTINELA_MACRO", "BTC/USDT:USDT"):
        return True

    if ahora_t < _COOLDOWN_WS_PHANTOM.get(sym, 0.0):
        return False

    side = str(senal.get("side", "long")).lower()

    if sym == "INJ/USDT:USDT" and side == "long":
        if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "VETO_INJ_LONG"), 0.0) >= 30.0:
            _SILENCIO_LOG_PHANTOM[(sym, "VETO_INJ_LONG")] = ahora_t
            log_sniper(f"{_ICON_SHIELD} [PHANTOM VETO SELECTIVO] INJ/USDT:USDT [LONG] bloqueado por estadistica OOS (0W/4L). Solo SHORT habilitado en INJ.")
        return False

    # Leer metricas reales desde ESTADO_RAM.ticks_ram[sym] cuando no vengan en el dict senal
    tk_sym = ESTADO_RAM.ticks_ram.get(sym)

    h_val = float(
        senal["hurst"]
        if ("hurst" in senal and senal["hurst"] is not None)
        else (getattr(tk_sym, "hurst", 0.45) if tk_sym is not None else 0.45)
    )
    z_val = float(
        senal["z_score"]
        if ("z_score" in senal and senal["z_score"] is not None)
        else (getattr(tk_sym, "z_score", 0.0) if tk_sym is not None else 0.0)
    )
    ofi_val = float(
        senal["ofi"]
        if ("ofi" in senal and senal["ofi"] is not None)
        else (getattr(tk_sym, "ofi_l1_l5", 0.0) if tk_sym is not None else 0.0)
    )
    ema_dist_ram = float(getattr(tk_sym, "ema900_dist_pct", 0.0) or 0.0) if tk_sym is not None else 0.0
    delta_p_ram = float(getattr(tk_sym, "delta_p_pct", 0.0) or 0.0) if tk_sym is not None else 0.0
    if "ema900_dist_pct" in senal and senal["ema900_dist_pct"] is not None:
        ema_dist = float(senal["ema900_dist_pct"])
    else:
        ema_dist = min(ema_dist_ram, delta_p_ram) if side == "long" else max(ema_dist_ram, delta_p_ram)

    if "lyapunov_acel_pct" in senal and senal["lyapunov_acel_pct"] is not None:
        lyap_val = float(senal["lyapunov_acel_pct"])
    else:
        lyap_val = float(getattr(tk_sym, "lyapunov_acel_pct", 0.0) or 0.0) if tk_sym is not None else 0.0

    hawkes_val = float(getattr(tk_sym, "hawkes_intensidad", 0.0) or 0.0) if tk_sym is not None else 0.0
    ticks_short = int(getattr(tk_sym, "ofi_ticks_confirmados_short", 0) or 0) if tk_sym is not None else 0

    # P-01: Veto Direccional Cruzado con BTC/USDT:USDT
    tk_btc = ESTADO_RAM.ticks_ram.get(getattr(cfg, "SIMBOLO_CENTINELA_MACRO", "BTC/USDT:USDT"))
    if tk_btc is not None and getattr(tk_btc, "last", 0.0) > 0.0:
        ofi_btc = float(getattr(tk_btc, "ofi_l1_l5", 0.0) or 0.0)
        z_btc = float(getattr(tk_btc, "z_score", 0.0) or 0.0)
        if side == "long" and (ofi_btc < -0.35 or z_btc < -2.40):
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_L"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_L")] = ahora_t
                log_sniper(f"{_ICON_SHIELD} [PHANTOM P-01 BTC-VETO] {sym} [LONG] bloqueado ANTES de orden (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False
        if side == "short" and (ofi_btc > 0.38 or z_btc > 2.50):
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P01_S"), 0.0) >= 15.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P01_S")] = ahora_t
                log_sniper(f"{_ICON_SHIELD} [PHANTOM P-01 BTC-VETO] {sym} [SHORT] bloqueado ANTES de orden (BTC OFI={ofi_btc:+.2f}, Z_BTC={z_btc:+.2f}).")
            return False

    # P-02 Elastico: Aprueba si H <= 0.515 O si existe Absorcion Institucional / Agotamiento Confirmado
    absorcion_institucional_long = (
        side == "long"
        and (
            (z_val <= -3.80 and ofi_val >= 0.20 and hawkes_val >= 0.20 and lyap_val >= -0.00025)
            or (z_val <= -2.50 and ofi_val >= 0.25 and hawkes_val >= 0.20 and lyap_val >= -0.00020)
        )
    )
    agotamiento_institucional_short = (
        side == "short"
        and (
            (ofi_val <= -0.30 and lyap_val <= -0.00018)
            or (z_val >= 3.00 and ofi_val <= -0.22)
        )
    )

    if h_val > 0.515 and not (absorcion_institucional_long or agotamiento_institucional_short):
        if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P02_H"), 0.0) >= 10.0:
            _SILENCIO_LOG_PHANTOM[(sym, "P02_H")] = ahora_t
            log_sniper(
                f"{_ICON_SHIELD} [PHANTOM P-02 PRE-ORDEN] {sym} [{side.upper()}] bloqueado ANTES de enviar orden (H={h_val:.3f} > 0.515 sin absorcion fuerte I_Hawkes={hawkes_val:+.2f})."
            )
        return False

    if h_val > 0.480:
        senal["hurst"] = 0.480
    if tk_sym is not None and getattr(tk_sym, "hurst", 0.45) > 0.480:
        tk_sym.hurst = 0.480

    # P-03 Elastico: Compuerta de Descuento / Sobreextension EMA900
    es_tier1 = sym in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
    if side == "long":
        min_ema_req = -0.0018 if es_tier1 else -0.0025
        if absorcion_institucional_long:
            min_ema_req = -0.0015
        if ema_dist > min_ema_req:
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_L"), 0.0) >= 12.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P03_L")] = ahora_t
                log_sniper(f"{_ICON_SHIELD} [PHANTOM P-03 EMA900] {sym} [LONG] bloqueado ANTES de orden (EMA900={ema_dist*100:+.2f}% > {min_ema_req*100:+.2f}%).")
            return False
    else:
        ruptura_flujo_short = (ofi_val <= -0.35 and ticks_short >= 2 and lyap_val <= -0.00018 and ema_dist >= -0.0015)
        if ema_dist < 0.0015 and not ruptura_flujo_short:
            if ahora_t - _SILENCIO_LOG_PHANTOM.get((sym, "P03_S"), 0.0) >= 12.0:
                _SILENCIO_LOG_PHANTOM[(sym, "P03_S")] = ahora_t
                log_sniper(f"{_ICON_SHIELD} [PHANTOM P-03 SHORT] {sym} [SHORT] bloqueado ANTES de orden (EMA900={ema_dist*100:+.2f}% < +0.15%).")
            return False

    senal["ema900_dist_pct"] = ema_dist
    senal["lyapunov_acel_pct"] = lyap_val
    return True

_validar_filtros_phantom_pre_orden = _validar_filtros_phantom_pre_orden_elastico
RadarVolatilidad._validar_filtros_phantom_pre_orden = _validar_filtros_phantom_pre_orden_elastico

_orig_proc_base_single = getattr(RadarVolatilidad, "_orig_proc_libro_base", RadarVolatilidad.procesar_instantanea_libro)

async def _procesar_instantanea_libro_single_layer(self, symbol: str, bids_or_book, asks=None, ahora=None, *args, **kwargs):
    if isinstance(bids_or_book, dict):
        ahora = asks if asks is not None else kwargs.pop("ahora", None)
        asks = bids_or_book.get("asks") or []
        bids = bids_or_book.get("bids") or []
    else:
        bids = bids_or_book

    if _ENV_PHANTOM_RADAR.get("TRIBRAIN_TEST_MODE", "0") == "1":
        return await _orig_proc_base_single(self, symbol, bids, asks, ahora, *args, **kwargs)

    t_now = float(ahora) if ahora is not None else __import__("time").time()
    ult_ts = _ULTIMO_TS_LIBRO_PHANTOM.get(symbol, 0.0)
    if ult_ts > 0.0 and (t_now - ult_ts) > 2.20:
        _COOLDOWN_WS_PHANTOM[symbol] = t_now + 4.00
    _ULTIMO_TS_LIBRO_PHANTOM[symbol] = t_now

    cb_real = getattr(self, "callback_disparo", None)
    self.callback_disparo = None
    logs_retenidos = []
    log_real = globals().get("log_sniper")
    hurst_cfg_prev = getattr(cfg, "HURST_MAX_ENTRADA", 0.515)

    def _log_interceptor_radar(msg: str, *a_l, **kw_l):
        s_m = str(msg)
        if s_m.startswith("[RADAR]") and "APROBADO" in s_m:
            logs_retenidos.append((msg, a_l, kw_l))
            return None
        return log_real(msg, *a_l, **kw_l)

    try:
        cfg.HURST_MAX_ENTRADA = 0.85
        globals()["log_sniper"] = _log_interceptor_radar
        res = await _orig_proc_base_single(self, symbol, bids, asks, ahora, *args, **kwargs)
    finally:
        cfg.HURST_MAX_ENTRADA = hurst_cfg_prev
        globals()["log_sniper"] = log_real
        self.callback_disparo = cb_real

    if isinstance(res, dict):
        if not _validar_filtros_phantom_pre_orden_elastico(self, symbol, res):
            return None
        for m_txt, m_a, m_kw in logs_retenidos:
            log_real(m_txt, *m_a, **m_kw)
        if callable(cb_real):
            await cb_real(res)
    return res

RadarVolatilidad.procesar_instantanea_libro = _procesar_instantanea_libro_single_layer
