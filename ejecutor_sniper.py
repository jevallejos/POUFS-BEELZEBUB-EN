#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #09: ejecutor_sniper.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor de Ejecucion Francotirador Zero-REST (Single-Layer Nativo):
  - Deduccion atomica de margen en RAM (Single-Slot Mutex) con liberacion
    garantizada ante cualquier cancelacion o excepcion asincrona.
  - Segundo cerrojo fisico Pre-Orden P-02 (Hurst <= HURST_MAX_ENTRADA).
  - Cotizacion Penny-Jump con bandera estricta PostOnly (Maker 0.020%).
  - Ley de Cola de Moallemi-Yuan (TTL = 3.80s en prod / 2.20s en test) y
    abolicion fisica total del Re-Quote perseguidor (PERMITIR_REQUOTE = False).
  - Apareamiento 1:1 con Telegram confirmado unicamente tras llenado real.
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, PosicionActiva, log_sniper
from escudo_tricortex import ESCUDO_TRICORTEX
from telemetria_telegram import TELEMETRIA_TG


def calcular_precio_penny_jump(
    side: str,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    ofi: float,
) -> float:
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

    if spread >= (1.95 * tick) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
        candidato = bid + tick
        if candidato < ask:
            return round(candidato, decimales)
    return round(bid, decimales)


def extraer_precision_y_minimos(
    exchange: Any, symbol: str, precio_ref: float
) -> Tuple[float, float, float]:
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


class EjecutorSniper:
    """
    Ejecuta sennales aprobadas por el Radar en tiempo constante O(1) sin llamadas
    REST previas, vigila el llenado sin hacer Re-Quote y entrega las posiciones
    activas confirmadas al Gestor de Posiciones.
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
        if self.exchange is None or not isinstance(senal, dict):
            return None

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not es_test:
            h_s = float(senal.get("hurst", 0.45) or 0.45)
            h_max = float(getattr(cfg, "HURST_MAX_ENTRADA", 0.485))
            if h_s > h_max:
                log_sniper(
                    f"[EJECUTOR P-02 VETO] {senal.get('symbol')} abortado en puerta de orden (H={h_s:.3f} > {h_max:.3f})."
                )
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

        f_kelly, margen_usdt, nocional_usdt = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil(
            symbol=symbol,
            z_score=z_score,
            ofi=ofi,
            hurst=hurst,
            volatilidad_local=volatilidad,
        )

        tick_size, step_qty, min_qty = extraer_precision_y_minimos(self.exchange, symbol, bid)
        quote_price = calcular_precio_penny_jump(side, bid, ask, tick_size, ofi)
        if quote_price <= 0.0:
            return None

        qty_bruta = nocional_usdt / quote_price
        qty = redondear_cantidad_lote(qty_bruta, step_qty, min_qty)
        if qty <= 0.0:
            ESTADO_RAM.pares_excluidos_lote.add(symbol)
            log_sniper(
                f"[WARN] [FILTRO LOTE MINIMO] {symbol} requiere min_qty={min_qty} "
                f"(>{nocional_usdt:.2f} USDT). Excluido en RAM."
            )
            return None

        nocional_real = round(qty * quote_price, 4)
        margen_real = round(nocional_real / cfg.APALANCAMIENTO_BASE, 4)

        if not ESTADO_RAM.reservar_margen_atomico(symbol, margen_real):
            return None

        posicion_confirmada = False
        try:
            self.disparos_intentados += 1
            side_order = "buy" if side == "long" else "sell"
            params_postonly = {"timeInForce": "PostOnly"}

            t0_http = time.perf_counter()
            try:
                orden = await self.exchange.create_order(
                    symbol, "limit", side_order, qty, quote_price, params_postonly
                )
            except Exception as exc:
                log_sniper(f"[WARN] [FRANCOTIRADOR] Disparo abortado en {symbol}: {exc}")
                return None

            rtt_ms = (time.perf_counter() - t0_http) * 1000.0
            order_id = str((orden or {}).get("id") or "")
            if not order_id:
                return None

            etiqueta_side = "SHORT-SNIPER" if side == "short" else "FRANCOTIRADOR"
            log_sniper(
                f"[{etiqueta_side}] Orden {order_id} en {symbol}: {qty} @ {quote_price} "
                f"(nocional ~{nocional_real:.2f} USDT, {cfg.APALANCAMIENTO_BASE}x, "
                f"Kelly={f_kelly*100:.0f}%, Z={z_score:+.2f}, OFI={ofi:+.2f}, RTT={rtt_ms:.1f}ms)"
            )

            TELEMETRIA_TG.retener_apertura_pendiente(
                symbol=symbol,
                side=side,
                qty=qty,
                price=quote_price,
                order_id=order_id,
                z_score=z_score,
                ofi=ofi,
            )

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

            if qty_llenada <= 0.0:
                self.disparos_cancelados_ttl += 1
                TELEMETRIA_TG.descartar_apertura_no_llenada(symbol)
                log_sniper(
                    f"[{etiqueta_side}] Orden en {symbol} no llenada en {ttl_max:.1f}s (Cero Re-Quote): margen liberado."
                )
                return None

            posicion_confirmada = True
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

            ESTADO_RAM.orden_en_vuelo_symbol = None
            ESTADO_RAM.posiciones_activas[symbol] = pos

            lado_msg = " SHORT" if side == "short" else ""
            log_sniper(
                f"[{etiqueta_side}] [TARGET] Posicion{lado_msg} activa en {symbol}: {qty_llenada} @ {precio_fill} "
                f"(edad 0s / max {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s) | SL interno {sl_interno} | SL Bybit {sl_bybit}"
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
        finally:
            if not posicion_confirmada:
                ESTADO_RAM.liberar_margen_atomico(symbol, margen_real)
