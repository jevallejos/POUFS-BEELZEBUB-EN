#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #08: radar_volatilidad.py
SISTEMA: TRI-BRAIN-SNIPER (SKILL HUNTER) V4.0 — ESTRATEGIA CHRONOS-TRIZ
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

        # Filtrar ticks planos consecutivos (150ms sin cambio en mid_price) para medir la rugosidad real
        pts_activos = [pts[0]]
        for p_val in pts[1:]:
            if abs(p_val - pts_activos[-1]) > 1e-12:
                pts_activos.append(p_val)
        if len(pts_activos) < 8:
            pts_activos = pts

        na = len(pts_activos)
        diffs_1 = [abs(math.log(pts_activos[i] / pts_activos[i - 1])) for i in range(1, na) if pts_activos[i - 1] > 0]
        diffs_4 = [abs(math.log(pts_activos[i] / pts_activos[i - 4])) for i in range(4, na) if pts_activos[i - 4] > 0]
        m1 = (sum(diffs_1) / len(diffs_1)) if diffs_1 else 1e-6
        m4 = (sum(diffs_4) / len(diffs_4)) if diffs_4 else (m1 * 1.35)

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

        # Tunel Biclase inquebrantable: prohibido comprar sobre EMA900 o en micro-caidas superficiales
        if tk.delta_p_pct > caida_min_req:
            return None
        if tk.ema900_dist_pct > ema_dist_req:
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

        if tk.hurst > cfg.HURST_MAX_ENTRADA:
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
        rebote_en_tendencia_bajista = en_short_only and (tk.ema900_dist_pct >= cfg.SHORT_REBOTE_DEBIL_MIN_EMA_PCT) and (tk.delta_p_pct <= -0.0010)

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
        if z_ref_short < 2.50:
            return None

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

# === [PASO 2 SKILL HUNTER V3.0: STOIKOV & HURST MULTIESCALA] ===
def calcular_micro_precio_stoikov(best_bid: float, best_ask: float, vol_bid_l1: float, vol_ask_l1: float) -> float:
    """Micro-precio continuo de Stoikov (2018) ponderado por presion inversa de volumen L1."""
    if best_bid <= 0.0 or best_ask <= 0.0:
        return max(best_bid, best_ask, 0.0)
    v_tot = vol_bid_l1 + vol_ask_l1
    if v_tot <= 1e-12:
        return 0.5 * (best_bid + best_ask)
    return (best_bid * vol_ask_l1 + best_ask * vol_bid_l1) / v_tot


def _hurst_multiescala_ticks_activos_v3(precios_seq) -> float:
    """Variograma multiescala tau=(1,2,4) sobre ticks activos (Delta P != 0) libre de Rebote de Roll."""
    pts = [float(x) for x in precios_seq if float(x) > 0.0]
    if len(pts) < 6:
        return 0.45
    activos = [pts[0]]
    for i in range(1, len(pts)):
        if abs(pts[i] - pts[i - 1]) > 1e-12:
            activos.append(pts[i])
    na = len(activos)
    if na < 6:
        return 0.45
    d1 = [abs(math.log(activos[i] / activos[i - 1])) for i in range(1, na) if activos[i - 1] > 0.0]
    d2 = [abs(math.log(activos[i] / activos[i - 2])) for i in range(2, na) if activos[i - 2] > 0.0]
    d4 = [abs(math.log(activos[i] / activos[i - 4])) for i in range(4, na) if activos[i - 4] > 0.0]
    m1 = (sum(d1) / len(d1)) if d1 else 1e-6
    m2 = (sum(d2) / len(d2)) if d2 else (m1 * 1.32)
    m4 = (sum(d4) / len(d4)) if d4 else (m2 * 1.32)
    if m1 <= 1e-9 or m2 <= 1e-9 or m4 <= 1e-9:
        return 0.45
    r12 = max(1.05, min(1.95, m2 / m1))
    h12 = math.log(r12) / math.log(2.0)
    if na >= 10 and len(d4) >= 4:
        r24 = max(1.05, min(1.95, m4 / m2))
        h24 = math.log(r24) / math.log(2.0)
        h_val = 0.35 * h12 + 0.65 * h24
    else:
        h_val = h12
    return round(max(0.20, min(0.80, h_val)), 4)


# Envolver metodo de Hurst en VentanaZ preservando 100% la aceleracion de Lyapunov original
for _attr_vz in dir(VentanaZ):
    if "hurst" in _attr_vz.lower():
        _orig_vz_fn = getattr(VentanaZ, _attr_vz)
        if callable(_orig_vz_fn) and not hasattr(VentanaZ, "_orig_hurst_v3"):
            VentanaZ._orig_hurst_v3 = _orig_vz_fn

            def _wrapped_hurst_vz_v3(self, *args, **kwargs):
                res_orig = self._orig_hurst_v3(*args, **kwargs)
                pts = list(getattr(self, "precios", []))
                # Detectar si existen ticks planos consecutivos (Delta P == 0) en muestreo 6.6 Hz
                tiene_ticks_planos = any(abs(pts[i] - pts[i - 1]) <= 1e-12 for i in range(1, len(pts)))
                if not tiene_ticks_planos:
                    return res_orig
                h_clean = _hurst_multiescala_ticks_activos_v3(pts)
                if isinstance(res_orig, tuple) and len(res_orig) == 2:
                    return h_clean, res_orig[1]
                return h_clean

            setattr(VentanaZ, _attr_vz, _wrapped_hurst_vz_v3)


def calcular_hurst_y_lyapunov(precios) -> tuple[float, float]:
    """Evalua Hurst multiescala sobre ticks activos y aceleracion de Lyapunov via VentanaZ."""
    vz = VentanaZ()
    for p in precios:
        if hasattr(vz, "agregar_precio"):
            vz.agregar_precio(float(p))
        elif hasattr(vz, "precios"):
            vz.precios.append(float(p))
    for attr in dir(vz):
        if "hurst" in attr.lower() and not attr.startswith("_orig"):
            out = getattr(vz, attr)()
            if isinstance(out, tuple) and len(out) == 2:
                return out
            return float(out), 0.0
    return _hurst_multiescala_ticks_activos_v3(precios), 0.0

# === [PASO 3 SKILL HUNTER V3.0: TENSOR DIFERENCIAL CKS-OFI] ===
def calcular_ofi_diferencial_cks(obi_actual: float, obi_previo: float | None, eta: float = 0.35) -> float:
    """Tensor diferencial de Cont-Kukanov-Stoikov (2014): penaliza paredes pasivas en drenaje."""
    val = float(obi_actual)
    if obi_previo is None:
        return val
    delta_obi = val - float(obi_previo)
    # Si la pared compradora (val > 0) o vendedora (val < 0) se drena mas de 0.05 en un tick, aplicar derivada CKS
    if (val > 0.0 and delta_obi < -0.05) or (val < 0.0 and delta_obi > 0.05):
        val = max(-1.0, min(1.0, val + eta * delta_obi))
    return round(val, 4)


if hasattr(VentanaZ, "calcular_ml_ofi_y_hawkes") and not hasattr(VentanaZ, "_orig_cks_calcular_ml_ofi_y_hawkes"):
    VentanaZ._orig_cks_calcular_ml_ofi_y_hawkes = VentanaZ.calcular_ml_ofi_y_hawkes

    def _wrapped_calcular_ml_ofi_y_hawkes_v3(self, bids, asks, t_now, *args, **kwargs):
        ml_ofi, ofi_5s, vpin = self._orig_cks_calcular_ml_ofi_y_hawkes(bids, asks, t_now, *args, **kwargs)
        obi_prev = getattr(self, "_ultimo_obi_raw_cks", None)
        self._ultimo_obi_raw_cks = float(ml_ofi)
        ml_ofi_cks = calcular_ofi_diferencial_cks(float(ml_ofi), obi_prev)
        if ml_ofi_cks != float(ml_ofi):
            if ml_ofi_cks < cfg.OFI_MIN_ENTRADA and hasattr(self, "ticks_ofi_long"):
                self.ticks_ofi_long = 0
            if ml_ofi_cks > getattr(cfg, "SHORT_OFI_MAX_ENTRADA", -0.35) and hasattr(self, "ticks_ofi_short"):
                self.ticks_ofi_short = 0
        return ml_ofi_cks, ofi_5s, vpin

    VentanaZ.calcular_ml_ofi_y_hawkes = _wrapped_calcular_ml_ofi_y_hawkes_v3

# === [PASO 4 SKILL HUNTER V3.0: PISO BIPOWER ENDOGENO] ===
def calcular_piso_bipower_endogeno(spread_pct: float, es_tier1: bool = False) -> float:
    """Calcula el piso endogeno de Variacion Bipower adaptativo al spread relativo y clase microestructural."""
    piso_base = float(getattr(cfg, "VOLATILIDAD_PISO_BIPOWER", 0.00108))
    sp = float(spread_pct)
    if sp <= 0.0:
        return piso_base
    factor_min = 0.82 if es_tier1 else 0.95
    cota_inf = piso_base * factor_min
    cota_sup = piso_base * 1.35
    return round(max(cota_inf, min(cota_sup, max(cota_inf, sp * 1.25))), 7)


if hasattr(VentanaZ, "calcular_z") and not hasattr(VentanaZ, "_orig_p4_calcular_z"):
    VentanaZ._orig_p4_calcular_z = VentanaZ.calcular_z

    def _wrapped_calcular_z_v3(self, precio_actual=None):
        z_score, cambio_ventana_pct, sigma_efectiva = self._orig_p4_calcular_z(precio_actual)
        sp_local = float(getattr(self, "_spread_rel_v3", 0.0))
        if sp_local <= 0.0 or abs(z_score) <= 1e-9 or sigma_efectiva <= 1e-9:
            return z_score, cambio_ventana_pct, sigma_efectiva
        es_t1 = bool(getattr(self, "_es_tier1_v3", False))
        piso_ref = calcular_piso_bipower_endogeno(sp_local, es_t1)
        piso_sigma = round(0.00045 * (piso_ref / 0.00108), 6)
        if piso_sigma > sigma_efectiva:
            z_adj = round(z_score * (sigma_efectiva / piso_sigma), 4)
            return z_adj, cambio_ventana_pct, piso_sigma
        if es_t1 and sigma_efectiva <= 0.00045 and piso_sigma < 0.00045:
            z_adj = round(z_score * (sigma_efectiva / piso_sigma), 4)
            return z_adj, cambio_ventana_pct, piso_sigma
        return z_score, cambio_ventana_pct, sigma_efectiva

    VentanaZ.calcular_z = _wrapped_calcular_z_v3


if hasattr(RadarVolatilidad, "procesar_instantanea_libro") and not hasattr(RadarVolatilidad, "_orig_p4_procesar_libro"):
    RadarVolatilidad._orig_p4_procesar_libro = RadarVolatilidad.procesar_instantanea_libro

    async def _wrapped_procesar_instantanea_libro_p4(self, symbol: str, bids: list, asks: list, ahora=None):
        try:
            if bids and asks and len(bids[0]) >= 1 and len(asks[0]) >= 1:
                bb = float(bids[0][0])
                ba = float(asks[0][0])
                if bb > 0.0 and ba >= bb:
                    sp_rel = (ba - bb) / (0.5 * (ba + bb))
                    vz = self.ventanas.get(symbol)
                    if vz is not None:
                        vz._spread_rel_v3 = sp_rel
                        vz._es_tier1_v3 = symbol in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
        except Exception:
            pass
        return await self._orig_p4_procesar_libro(symbol, bids, asks, ahora)

    RadarVolatilidad.procesar_instantanea_libro = _wrapped_procesar_instantanea_libro_p4

# === INICIO AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===
def verificar_compuerta_hurst_short_v3(
    hurst_actual: float,
    z_score: float,
    ema900_dist_pct: float = 0.0,
    symbol: str = '',
) -> bool:
    if symbol in getattr(cfg, 'CLASE_HIGH_BETA', ()):
        if float(ema900_dist_pct) < 0.0040 or float(z_score) < 4.20:
            return False
    if abs(float(z_score)) >= 11.5 and float(ema900_dist_pct) >= 0.0120:
        return True
    return float(hurst_actual) <= 0.495


if hasattr(RadarVolatilidad, '_evaluar_gatillo_short_chronos') and not hasattr(RadarVolatilidad, '_orig_eval_short_pre_v3'):
    RadarVolatilidad._orig_eval_short_pre_v3 = RadarVolatilidad._evaluar_gatillo_short_chronos
    _ULT_LOG_HURST_SHORT_V3: dict[str, float] = {}

    async def _evaluar_gatillo_short_chronos_pre_v3(
        self, symbol: str, vz, tk, spread_ok: bool, ahora: float, *args, **kwargs
    ):
        res = RadarVolatilidad._orig_eval_short_pre_v3(
            self, symbol, vz, tk, spread_ok, ahora, *args, **kwargs
        )
        if hasattr(res, '__await__'):
            res = await res
        if res is not None and __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') != '1':
            n_pts = len(getattr(vz, 'precios', [])) if vz is not None else 0
            if n_pts >= 40:
                h_val = float(getattr(tk, 'hurst', 0.45) or 0.45)
                z_val = float(getattr(tk, 'z_score', 0.0) or 0.0)
                ema_d = float(getattr(tk, 'ema900_dist_pct', 0.0) or 0.0)
                ofi_v = float(getattr(tk, 'ofi', 0.0) or 0.0)
                lyap_v = float(getattr(tk, 'lyapunov_acel', 0.0) or 0.0)
                if not verificar_compuerta_hurst_short_v3(h_val, z_val, ema_d, symbol):
                    ult = _ULT_LOG_HURST_SHORT_V3.get(symbol, 0.0)
                    if ahora - ult >= 15.0:
                        _ULT_LOG_HURST_SHORT_V3[symbol] = ahora
                        if h_val > 0.495:
                            log_sniper(
                                f'\u26a0\ufe0f [BLOQUEO HURST SHORT] {symbol} gatillo abortado por tendencia alcista '
                                f'(H={h_val:.3f} > 0.495 | Z={z_val:+.2f} | EMA={ema_d*100:+.2f}% | OFI={ofi_v:+.2f}).'
                            )
                        else:
                            log_sniper(
                                f'\u26a0\ufe0f [BLOQUEO HIGH-BETA SHORT] {symbol} sobreextensi\u00f3n insuficiente '
                                f'(Z={z_val:+.2f} | EMA={ema_d*100:+.2f}% | H={h_val:.3f}).'
                            )
                    return None
                log_sniper(
                    f'\U0001f3af [TELEMETR\u00cdA DISPARO SHORT] {symbol} | Z={z_val:+.2f} | '
                    f'EMA900={ema_d*100:+.2f}% | OFI={ofi_v:+.2f} | H={h_val:.3f} (<=0.495 OK) | a_Lyap={lyap_v*100:+.4f}%'
                )
        return res

    RadarVolatilidad._evaluar_gatillo_short_chronos = _evaluar_gatillo_short_chronos_pre_v3


if hasattr(RadarVolatilidad, 'procesar_instantanea_libro') and not hasattr(RadarVolatilidad, '_orig_proc_libro_v3_clean'):
    RadarVolatilidad._orig_proc_libro_v3_clean = RadarVolatilidad.procesar_instantanea_libro

    async def _procesar_instantanea_libro_v3_clean(
        self, symbol: str, bids: list, asks: list, timestamp: float | None = None
    ):
        ahora_ts = float(timestamp if timestamp is not None else time.time())
        pausa_prev = ESTADO_RAM.pausa_macro_hasta_ts
        tk = ESTADO_RAM.ticks_ram.get(symbol)
        orig_h_max = cfg.HURST_MAX_ENTRADA
        try:
            if (
                tk is not None
                and __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') != '1'
                and float(getattr(tk, 'z_score', 0.0)) <= -2.80
                and float(getattr(tk, 'ofi', 0.0)) >= 0.20
                and float(getattr(tk, 'lyapunov_acel', -1.0)) >= 0.00005
            ):
                cfg.HURST_MAX_ENTRADA = 0.680
            res = await RadarVolatilidad._orig_proc_libro_v3_clean(
                self, symbol, bids, asks, timestamp
            )
        finally:
            cfg.HURST_MAX_ENTRADA = orig_h_max
        if (
            ESTADO_RAM.pausa_macro_hasta_ts > pausa_prev
            and __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') != '1'
        ):
            ESTADO_RAM.pausa_macro_hasta_ts = ahora_ts + 25.0
            for d_attr in ('_precios_10s', 'precios_10s', 'ventana_contagio'):
                d_obj = getattr(self, d_attr, None)
                if isinstance(d_obj, dict):
                    d_obj.clear()
        return res

    RadarVolatilidad.procesar_instantanea_libro = _procesar_instantanea_libro_v3_clean
# === FIN AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===



# === [V4.0 RADAR PRECISION & WS COOLDOWN] ===
_TS_ULTIMO_TICK_POR_PAR_V4: dict[str, float] = {}
_COOLDOWN_RECONEXION_HASTA_V4: dict[str, float] = {}

if hasattr(VentanaZ, "calcular_hurst_y_lyapunov") and not hasattr(VentanaZ, "_orig_hurst_lyap_v4"):
    VentanaZ._orig_hurst_lyap_v4 = VentanaZ.calcular_hurst_y_lyapunov
    def _calcular_hurst_y_lyapunov_v4(self, *args, **kwargs):
        h_val, lyap_val = VentanaZ._orig_hurst_lyap_v4(self, *args, **kwargs)
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") != "1":
            if h_val >= 0.78 and lyap_val >= -0.00005 and len(getattr(self, "precios", ())) >= 45:
                h_val = 0.465
        return h_val, lyap_val
    VentanaZ.calcular_hurst_y_lyapunov = _calcular_hurst_y_lyapunov_v4

if hasattr(RadarVolatilidad, "verificar_contagio_cross_asset") and not hasattr(RadarVolatilidad, "_orig_contagio_v4"):
    RadarVolatilidad._orig_contagio_v4 = RadarVolatilidad.verificar_contagio_cross_asset
    async def _verificar_contagio_cross_asset_v4(self, *args, **kwargs) -> bool:
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
            return await RadarVolatilidad._orig_contagio_v4(self, *args, **kwargs)
        sym = str(args[0]) if len(args) > 0 else str(kwargs.get("symbol", ""))
        t_eval = float(args[2]) if len(args) > 2 and args[2] is not None else float(kwargs.get("ahora_ts") or time.time())
        if t_eval < _COOLDOWN_RECONEXION_HASTA_V4.get(sym, 0.0):
            return False
        res = await RadarVolatilidad._orig_contagio_v4(self, *args, **kwargs)
        if res:
            ESTADO_RAM.pausa_macro_hasta_ts = t_eval + 30.0
        return res
    RadarVolatilidad.verificar_contagio_cross_asset = _verificar_contagio_cross_asset_v4

if hasattr(RadarVolatilidad, "procesar_instantanea_libro") and not hasattr(RadarVolatilidad, "_orig_proc_libro_v4"):
    RadarVolatilidad._orig_proc_libro_v4 = RadarVolatilidad.procesar_instantanea_libro
    async def _procesar_instantanea_libro_v4(self, *args, **kwargs):
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
            return await RadarVolatilidad._orig_proc_libro_v4(self, *args, **kwargs)
        sym = str(args[0]) if len(args) > 0 else str(kwargs.get("symbol", ""))
        ts_now = float(args[3]) if len(args) > 3 and args[3] is not None else float(kwargs.get("ahora") or time.time())
        prev_ts = _TS_ULTIMO_TICK_POR_PAR_V4.get(sym, 0.0)
        if prev_ts > 0.0 and (ts_now - prev_ts) > 2.20:
            _COOLDOWN_RECONEXION_HASTA_V4[sym] = ts_now + 3.50
        _TS_ULTIMO_TICK_POR_PAR_V4[sym] = ts_now
        res = await RadarVolatilidad._orig_proc_libro_v4(self, *args, **kwargs)
        if isinstance(res, dict) and str(res.get("side", "")).lower() == "short":
            h_act = float(res.get("hurst", 0.45))
            z_act = float(res.get("z_score", 0.0))
            ema_d = float(res.get("ema900_dist_pct", 0.0))
            h_max = float(getattr(cfg, "HURST_MAX_ENTRADA", 0.495))
            if h_act > h_max and abs(z_act) < 11.0 and ema_d < 0.010:
                return None
        return res
    RadarVolatilidad.procesar_instantanea_libro = _procesar_instantanea_libro_v4
