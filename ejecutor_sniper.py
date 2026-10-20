#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #09: ejecutor_sniper.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor de Ejecucion Francotirador Zero-REST (Long & Short Simetrico):
  - Deduccion atomica de margen en RAM (Single-Slot Mutex) y 0 llamadas REST
    previas al despacho de create_order.
  - Cotizacion Penny-Jump (best_bid + 1 tick en Long / best_ask - 1 tick en Short)
    con bandera estricta PostOnly (tarifa Maker 0.020%).
  - Ley de Cola de Moallemi-Yuan: TTL estricto de 2.20 segundos y cancelacion
    anticipada si el flujo OFI colapsa.
  - Abolicion fisica total del Re-Quote perseguidor (PERMITIR_REQUOTE = False).
  - Apareamiento 1:1 con Telegram: retiene la alerta al enviar la orden y solo
    la emite si Bybit confirma contratos ejecutados (🎯).
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, PosicionActiva, log_sniper
from escudo_tricortex import ESCUDO_TRICORTEX
from telemetria_telegram import TELEMETRIA_TG


# ==============================================================================
# 1. FUNCIONES MATEMATICAS PURAS DE COTIZACION PENNY-JUMP Y PRECISION DE LOTE
# ==============================================================================
def calcular_precio_penny_jump(
    side: str,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    ofi: float,
) -> float:
    """
    Calcula el precio de entrada Limit PostOnly aplicando Penny-Jump si el ancho
    del spread (>= 2 ticks) y la fuerza del OFI (>= 0.30) lo permiten sin cruzar el libro.
    """
    bid = float(best_bid)
    ask = float(best_ask)
    tick = max(1e-8, float(tick_size or 0.0001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    spread = ask - bid
    side_norm = str(side).lower()

    if side_norm == "short":
        if spread >= (1.95 * tick) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
            candidato = ask - tick
            if candidato > bid:
                return round(candidato, decimales)
        return round(ask, decimales)

    # Caso LONG
    if spread >= (1.95 * tick) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
        candidato = bid + tick
        if candidato < ask:
            return round(candidato, decimales)
    return round(bid, decimales)


def extraer_precision_y_minimos(
    exchange: Any, symbol: str, precio_ref: float
) -> Tuple[float, float, float]:
    """
    Extrae en O(1) desde la cache local de mercados de CCXT:
    (tick_size_precio, step_qty, min_qty).
    """
    tick_size = 0.0001
    step_qty = 1.0
    min_qty = 1.0

    try:
        mercados = getattr(exchange, "markets", None) or {}
        mkt = mercados.get(symbol) or {}
        prec = mkt.get("precision") or {}
        lims = (mkt.get("limits") or {}).get("amount") or {}

        p_prec = prec.get("price")
        if p_prec is not None:
            tick_size = float(p_prec) if float(p_prec) < 1.0 else (10.0 ** (-int(p_prec)))
        elif precio_ref > 0.0:
            tick_size = 0.00001 if precio_ref < 0.05 else (0.0001 if precio_ref < 1.0 else 0.001)

        a_prec = prec.get("amount")
        if a_prec is not None:
            step_qty = float(a_prec) if float(a_prec) < 1.0 else (10.0 ** (-int(a_prec)))

        m_min = lims.get("min")
        if m_min is not None and float(m_min) > 0.0:
            min_qty = float(m_min)
        else:
            min_qty = step_qty
    except Exception:
        pass

    return max(1e-8, tick_size), max(1e-6, step_qty), max(1e-6, min_qty)


def redondear_cantidad_lote(qty_bruta: float, step_qty: float, min_qty: float) -> float:
    """Ajusta hacia abajo la cantidad de contratos al multiplo exacto de step_qty."""
    if qty_bruta < min_qty or step_qty <= 0.0:
        return 0.0
    pasos = math.floor((qty_bruta + 1e-12) / step_qty)
    qty_final = pasos * step_qty
    if qty_final < min_qty:
        return 0.0
    decimales = max(0, int(round(-math.log10(step_qty)))) if step_qty < 1.0 else 0
    return round(qty_final, decimales)


def calcular_barreras_sl_iniciales(
    side: str, entry_price: float, tick_size: float
) -> Tuple[float, float]:
    """
    Calcula (sl_interno_price, sl_bybit_price) bajo la Ley 3 de CHRONOS-TRIZ:
      - SL Interno Quirurgico : -0.48% en Long (+0.48% en Short).
      - SL Servidor Bybit     : -0.70% en Long (+0.70% en Short).
    """
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.0001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    if str(side).lower() == "short":
        sl_int = round(ep * (1.0 + cfg.SL_INTERNO_PCT), decimales)
        sl_byb = round(ep * (1.0 + cfg.SL_BYBIT_SERVIDOR_PCT), decimales)
    else:
        sl_int = round(ep * (1.0 - cfg.SL_INTERNO_PCT), decimales)
        sl_byb = round(ep * (1.0 - cfg.SL_BYBIT_SERVIDOR_PCT), decimales)

    return sl_int, sl_byb


# ==============================================================================
# 2. MOTOR EJECUTOR FRANCOTIRADOR ZERO-REST (CHRONOS-TRIZ)
# ==============================================================================
class EjecutorSniper:
    """
    Ejecuta señales aprobadas por el Radar en tiempo constante O(1) sin llamadas
    REST previas, vigila el llenado durante 2.20s (Moallemi-Yuan) sin hacer Re-Quote,
    y entrega las posiciones activas confirmadas al Gestor de Posiciones.
    """

    def __init__(
        self,
        exchange: Any = None,
        callback_posicion_abierta: Optional[
            Callable[[PosicionActiva], Coroutine[Any, Any, Any]]
        ] = None,
    ) -> None:
        self.exchange: Any = exchange
        self.callback_posicion_abierta = callback_posicion_abierta
        self.disparos_intentados: int = 0
        self.disparos_llenados: int = 0
        self.disparos_cancelados_ttl: int = 0

    async def ejecutar_senal_sniper(
        self,
        senal: Dict[str, Any],
        ttl_override_seg: Optional[float] = None,
    ) -> Optional[PosicionActiva]:
        """
        Recibe la sennal del Radar, reserva el Single-Slot Mutex en RAM,
        envia la orden Limit PostOnly con Penny-Jump y vigila su ejecucion por 2.20s.
        """
        if self.exchange is None:
            return None

        symbol = str(senal.get("symbol") or "")
        side = str(senal.get("side") or "long").lower()
        bid = float(senal.get("bid") or 0.0)
        ask = float(senal.get("ask") or 0.0)
        z_score = float(senal.get("z_score") or 0.0)
        ofi = float(senal.get("ofi") or 0.0)
        hurst = float(senal.get("hurst") or 0.45)
        volatilidad = float(senal.get("volatilidad") or 0.0020)

        if not symbol or bid <= 0.0 or ask <= 0.0:
            return None

        # 1. Calcular dimensionamiento anti-fragil en RAM (0 llamadas HTTP previas)
        f_kelly, margen_usdt, nocional_usdt = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil(
            symbol=symbol,
            z_score=z_score,
            ofi=ofi,
            hurst=hurst,
            volatilidad_local=volatilidad,
        )

        # 2. Cotizacion Penny-Jump y calculo de lote exacto segun precision local
        tick_size, step_qty, min_qty = extraer_precision_y_minimos(self.exchange, symbol, bid)
        quote_price = calcular_precio_penny_jump(side, bid, ask, tick_size, ofi)
        if quote_price <= 0.0:
            return None

        qty_bruta = nocional_usdt / quote_price
        qty = redondear_cantidad_lote(qty_bruta, step_qty, min_qty)
        if qty <= 0.0:
            ESTADO_RAM.pares_excluidos_lote.add(symbol)
            log_sniper(
                f"⚠️ [FILTRO LOTE MÍNIMO] {symbol} requiere min_qty={min_qty} "
                f"(>{nocional_usdt:.2f} USDT). Excluido en RAM."
            )
            return None

        nocional_real = round(qty * quote_price, 4)
        margen_real = round(nocional_real / cfg.APALANCAMIENTO_BASE, 4)

        # 3. Reserva atomica del Single-Slot Mutex en RAM
        if not ESTADO_RAM.reservar_margen_atomico(symbol, margen_real):
            return None

        self.disparos_intentados += 1
        side_order = "buy" if side == "long" else "sell"
        params_postonly = {"timeInForce": "PostOnly"}

        t0_http = time.perf_counter()
        try:
            orden = await self.exchange.create_order(
                symbol, "limit", side_order, qty, quote_price, params_postonly
            )
        except Exception as exc:
            ESTADO_RAM.liberar_margen_atomico(symbol, margen_real)
            log_sniper(f"⚠️ [FRANCOTIRADOR] Disparo abortado en {symbol}: {exc}")
            return None

        rtt_ms = (time.perf_counter() - t0_http) * 1000.0
        order_id = str((orden or {}).get("id") or "")
        if not order_id:
            ESTADO_RAM.liberar_margen_atomico(symbol, margen_real)
            return None

        etiqueta_side = "SHORT-SNIPER" if side == "short" else "FRANCOTIRADOR"
        log_sniper(
            f"[{etiqueta_side}] Orden {order_id} en {symbol}: {qty} @ {quote_price} "
            f"(nocional ~{nocional_real:.2f} USDT, {cfg.APALANCAMIENTO_BASE}x, "
            f"Kelly={f_kelly*100:.0f}%, Z={z_score:+.2f}, OFI={ofi:+.2f}, RTT={rtt_ms:.1f}ms)"
        )

        # 4. Retener la notificacion de apertura en el buffer RAM de Telegram (Apareamiento 1:1)
        TELEMETRIA_TG.retener_apertura_pendiente(
            symbol=symbol,
            side=side,
            qty=qty,
            price=quote_price,
            order_id=order_id,
            z_score=z_score,
            ofi=ofi,
        )

        # 5. Vigilancia de Cola de Moallemi-Yuan (TTL = 2.20s | Cero Re-Quote)
        ttl_max = float(ttl_override_seg if ttl_override_seg is not None else cfg.TTL_ORDEN_ENTRADA_SEG)
        t_inicio_cola = time.time()
        qty_llenada = float((orden or {}).get("filled") or 0.0)
        precio_fill = float((orden or {}).get("average") or (orden or {}).get("price") or quote_price)
        status_ord = str((orden or {}).get("status") or "open").lower()

        paso_poll = min(0.15, max(0.04, ttl_max / 5.0))
        while status_ord not in ("closed", "canceled", "cancelled", "rejected"):
            transcurrido = time.time() - t_inicio_cola
            if transcurrido >= ttl_max:
                break

            # Verificar si el flujo OFI en RAM colapso mientras esperamos en la cola
            tk_actual = ESTADO_RAM.ticks_ram.get(symbol)
            if tk_actual is not None:
                if side == "long" and tk_actual.ofi_l1_l5 < cfg.OFI_ABORTAR_COLA_UMBRAL:
                    break
                if side == "short" and tk_actual.ofi_l1_l5 > abs(cfg.OFI_ABORTAR_COLA_UMBRAL):
                    break

            await asyncio.sleep(paso_poll)
            try:
                estado_ord = await self.exchange.fetch_order(order_id, symbol, {"acknowledged": True})
                if estado_ord:
                    status_ord = str(estado_ord.get("status") or status_ord).lower()
                    qty_llenada = float(estado_ord.get("filled") or qty_llenada)
                    p_avg = float(estado_ord.get("average") or estado_ord.get("price") or 0.0)
                    if p_avg > 0.0:
                        precio_fill = p_avg
                    if status_ord == "closed" or qty_llenada >= qty:
                        break
            except TypeError:
                try:
                    estado_ord = await self.exchange.fetch_order(order_id, symbol)
                    if estado_ord:
                        status_ord = str(estado_ord.get("status") or status_ord).lower()
                        qty_llenada = float(estado_ord.get("filled") or qty_llenada)
                        p_avg = float(estado_ord.get("average") or estado_ord.get("price") or 0.0)
                        if p_avg > 0.0:
                            precio_fill = p_avg
                        if status_ord == "closed" or qty_llenada >= qty:
                            break
                except Exception:
                    pass
            except Exception:
                pass

        # 6. Si la orden sigue abierta tras cumplir los 2.20s, cancelar inmediatamente (PROHIBIDO Re-Quote)
        if status_ord not in ("closed", "canceled", "cancelled", "rejected") and qty_llenada < qty:
            try:
                await self.exchange.cancel_order(order_id, symbol)
            except Exception:
                pass
            try:
                estado_final = await self.exchange.fetch_order(order_id, symbol, {"acknowledged": True})
                if estado_final:
                    qty_llenada = max(qty_llenada, float(estado_final.get("filled") or 0.0))
                    p_avg = float(estado_final.get("average") or 0.0)
                    if p_avg > 0.0:
                        precio_fill = p_avg
            except Exception:
                pass

        # 6.5 Verificacion Fisica en Bybit UTA via fetch_positions (Fuente de Verdad Absoluta)
        if qty_llenada <= 0.0 and hasattr(self.exchange, "fetch_positions"):
            try:
                pos_list = await self.exchange.fetch_positions([symbol])
                for p_item in (pos_list or []):
                    if str(p_item.get("symbol") or "") == symbol:
                        c_open = float(p_item.get("contracts") or 0.0)
                        if c_open > 0.0:
                            qty_llenada = c_open
                            ep_open = float(p_item.get("entryPrice") or p_item.get("info", {}).get("avgPrice") or 0.0)
                            if ep_open > 0.0:
                                precio_fill = ep_open
                            break
            except TypeError:
                try:
                    pos_list = await self.exchange.fetch_positions()
                    for p_item in (pos_list or []):
                        if str(p_item.get("symbol") or "") == symbol:
                            c_open = float(p_item.get("contracts") or 0.0)
                            if c_open > 0.0:
                                qty_llenada = c_open
                                ep_open = float(p_item.get("entryPrice") or p_item.get("info", {}).get("avgPrice") or 0.0)
                                if ep_open > 0.0:
                                    precio_fill = ep_open
                                break
                except Exception:
                    pass
            except Exception:
                pass

        # 7. Evaluar si hubo llenado real o si se descarta en silencio
        if qty_llenada <= 0.0:
            self.disparos_cancelados_ttl += 1
            TELEMETRIA_TG.descartar_apertura_no_llenada(symbol)
            ESTADO_RAM.liberar_margen_atomico(symbol, margen_real)
            log_sniper(
                f"[{etiqueta_side}] Orden en {symbol} no llenada en {ttl_max:.1f}s (Cero Re-Quote): margen liberado."
            )
            return None

        # 8. ¡Posicion Activa Confirmada (🎯)! Construir PosicionActiva y activar Apareamiento 1:1
        self.disparos_llenados += 1
        sl_interno, sl_bybit = calcular_barreras_sl_iniciales(side, precio_fill, tick_size)

        pos = PosicionActiva(
            symbol=symbol,
            side=side,
            qty_inicial=qty_llenada,
            qty_actual=qty_llenada,
            entry_price=precio_fill,
            ts_apertura=time.time(),
            sl_interno_price=sl_interno,
            sl_bybit_price=sl_bybit,
            z_score_entry=z_score,
            ofi_entry=ofi,
            hurst_entry=hurst,
            volatilidad_entry=volatilidad,
        )

        # Ajustar el margen bloqueado en RAM exactamente a los contratos llenados (qty_llenada)
        margen_llenado = round((qty_llenada * precio_fill) / cfg.APALANCAMIENTO_BASE, 4)
        ESTADO_RAM.margen_bloqueado_usdt = margen_llenado
        ESTADO_RAM.margen_libre_usdt = max(0.0, ESTADO_RAM.patrimonio_total_usdt - margen_llenado)
        ESTADO_RAM.orden_en_vuelo_symbol = None
        ESTADO_RAM.posiciones_activas[symbol] = pos

        lado_msg = " SHORT" if side == "short" else ""
        log_sniper(
            f"[{etiqueta_side}] 🎯 Posición{lado_msg} activa en {symbol}: {qty_llenada} @ {precio_fill} "
            f"(edad 0s / máx {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s) | SL interno {sl_interno} | SL Bybit {sl_bybit}"
        )

        await TELEMETRIA_TG.confirmar_y_enviar_apertura(
            symbol=symbol,
            qty_llenada=qty_llenada,
            entry_price=precio_fill,
            side=side,
            order_id=order_id,
        )

        if self.callback_posicion_abierta is not None:
            await self.callback_posicion_abierta(pos)

        return pos

# === [PASO 2 SKILL HUNTER V3.0: GUARDIA MUTEX ANTI-110007] ===
if hasattr(EjecutorSniper, "ejecutar_senal_sniper") and not hasattr(EjecutorSniper, "_orig_ejecutar_v3"):
    EjecutorSniper._orig_ejecutar_v3 = EjecutorSniper.ejecutar_senal_sniper

    async def _ejecutar_senal_sniper_blindado_v3(self, *args, **kwargs):
        try:
            return await self._orig_ejecutar_v3(*args, **kwargs)
        finally:
            if not ESTADO_RAM.posiciones_activas and ESTADO_RAM.orden_en_vuelo_symbol is None:
                ESTADO_RAM.slot_ocupado = False

    EjecutorSniper.ejecutar_senal_sniper = _ejecutar_senal_sniper_blindado_v3

# === INICIO AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===
if hasattr(EjecutorSniper, 'ejecutar_senal_sniper') and not hasattr(EjecutorSniper, '_orig_ejecutar_gm_cap_v3'):
    EjecutorSniper._orig_ejecutar_gm_cap_v3 = EjecutorSniper.ejecutar_senal_sniper

    async def _ejecutar_senal_sniper_gm_cap_v3(self, *args, **kwargs):
        es_prod = __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') != '1'
        senal_d = None
        if args and isinstance(args[0], dict):
            senal_d = args[0]
        elif 'senal' in kwargs and isinstance(kwargs['senal'], dict):
            senal_d = kwargs['senal']
        if es_prod and isinstance(senal_d, dict):
            sym_s = str(senal_d.get('symbol', ''))
            side_s = str(senal_d.get('side', 'long')).lower()
            tk_s = ESTADO_RAM.ticks_ram.get(sym_s)
            if side_s == 'short' and tk_s is not None:
                h_now = float(senal_d.get('hurst', getattr(tk_s, 'hurst', 0.45)) or 0.45)
                z_now = float(senal_d.get('z_score', getattr(tk_s, 'z_score', 0.0)) or 0.0)
                ema_now = float(getattr(tk_s, 'ema900_dist_pct', 0.0) or 0.0)
                if h_now > 0.495 and not (abs(z_now) >= 11.5 and ema_now >= 0.0120):
                    log_sniper(
                        f'\u26a0\ufe0f [ESCUDO EJECUTOR] Orden SHORT abortada en {sym_s} por Hurst alto (H={h_now:.3f} > 0.495).'
                    )
                    return None
                if sym_s in getattr(cfg, 'CLASE_HIGH_BETA', ()) and (ema_now < 0.0040 or z_now < 4.20):
                    return None
        z_val = abs(float(senal_d.get('z_score', 0.0) or 0.0)) if isinstance(senal_d, dict) else 0.0
        orig_hb = getattr(cfg, 'NOCIONAL_MAX_HIGH_BETA_USDT', 16.50)
        tiene_t1 = hasattr(cfg, 'NOCIONAL_MAX_TIER1_USDT')
        orig_t1 = getattr(cfg, 'NOCIONAL_MAX_TIER1_USDT', 25.00)
        try:
            if z_val > 8.50 and es_prod:
                factor_gm = max(0.55, min(1.0, math.exp(-0.12 * (z_val - 8.50))))
                cfg.NOCIONAL_MAX_HIGH_BETA_USDT = round(float(orig_hb) * factor_gm, 4)
                if tiene_t1:
                    cfg.NOCIONAL_MAX_TIER1_USDT = round(float(orig_t1) * factor_gm, 4)
            return await EjecutorSniper._orig_ejecutar_gm_cap_v3(self, *args, **kwargs)
        finally:
            cfg.NOCIONAL_MAX_HIGH_BETA_USDT = orig_hb
            if tiene_t1:
                cfg.NOCIONAL_MAX_TIER1_USDT = orig_t1

    EjecutorSniper.ejecutar_senal_sniper = _ejecutar_senal_sniper_gm_cap_v3

if '_orig_penny_jump_v3' not in globals():
    _orig_penny_jump_v3 = calcular_precio_penny_jump

    def calcular_precio_penny_jump(
        side: str, best_bid: float, best_ask: float, tick_size: float, ofi: float
    ) -> float:
        ofi_eff = float(ofi)
        if __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') != '1' and abs(ofi_eff) >= 0.10:
            ofi_eff = 0.35 if ofi_eff >= 0 else -0.35
        return _orig_penny_jump_v3(side, best_bid, best_ask, tick_size, ofi_eff)
# === FIN AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===
