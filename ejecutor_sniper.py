#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #09: ejecutor_sniper.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Zero-REST Sniper Execution Engine (Single-Layer Native):
  - Atomic RAM margin deduction (Single-Slot Mutex) with guaranteed release
    upon any cancellation or asynchronous exception.
  - Second physical Pre-Order gate P-02 coupled to the Elastic Hurst Band
    (hurst_max_elastico / HURST_MAX_ENTRADA) without truncating real H.
  - Penny-Jump quoting with strict PostOnly flag (Maker 0.020%).
  - Moallemi-Yuan Queue Law (TTL = 3.80s in prod / 2.20s in test) and
    total physical abolition of price-chasing Re-Quote (PERMITIR_REQUOTE = False).
  - Strict 1:1 Telegram pairing confirmed exclusively after real exchange fill.
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
    """Computes the optimal Maker quote price using 1-tick Penny-Jump when spread and OFI allow."""
    bid = float(best_bid)
    ask = float(best_ask)
    tick = max(1e-8, float(tick_size or 0.0001))
    decimals = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    spread = ask - bid
    side_norm = str(side).lower()

    if side_norm == "short":
        if spread >= (1.95 * tick) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
            candidate = ask - tick
            if candidate > bid:
                return round(candidate, decimals)
        return round(ask, decimals)

    if spread >= (1.95 * tick) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
        candidate = bid + tick
        if candidate < ask:
            return round(candidate, decimals)
    return round(bid, decimals)


def extraer_precision_y_minimos(
    exchange: Any, symbol: str, precio_ref: float
) -> Tuple[float, float, float]:
    """Extracts (tick_size, step_qty, min_qty) in O(1) from preloaded exchange markets."""
    tick_size = 0.0001
    step_qty = 1.0
    min_qty = 1.0

    try:
        markets = getattr(exchange, "markets", None) or {}
        mkt = markets.get(symbol) or {}
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
    """Rounds raw contract quantity down to the exact exchange step_qty and validates min_qty."""
    if qty_bruta < min_qty or step_qty <= 0.0:
        return 0.0
    steps = math.floor((qty_bruta + 1e-12) / step_qty)
    final_qty = steps * step_qty
    if final_qty < min_qty:
        return 0.0
    decimals = max(0, int(round(-math.log10(step_qty)))) if step_qty < 1.0 else 0
    return round(final_qty, decimals)


def calcular_barreras_sl_iniciales(
    side: str, entry_price: float, tick_size: float
) -> Tuple[float, float]:
    """Calculates (internal_sl_price, bybit_server_sl_price) quantized to tick_size."""
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.0001))
    decimals = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    if str(side).lower() == "short":
        sl_int = round(ep * (1.0 + cfg.SL_INTERNO_PCT), decimals)
        sl_byb = round(ep * (1.0 + cfg.SL_BYBIT_SERVIDOR_PCT), decimals)
    else:
        sl_int = round(ep * (1.0 - cfg.SL_INTERNO_PCT), decimals)
        sl_byb = round(ep * (1.0 - cfg.SL_BYBIT_SERVIDOR_PCT), decimals)

    return sl_int, sl_byb


class EjecutorSniper:
    """
    Executes Radar-approved signals in O(1) constant time with zero prior REST calls,
    monitors queue fills without Re-Quoting, and hands off confirmed active positions
    to the Position Manager.
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

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if not is_test:
            h_s = float(senal.get("hurst", 0.45) or 0.45)
            h_max = float(
                senal.get("hurst_max_elastico")
                or getattr(cfg, "HURST_MAX_ENTRADA", 0.485)
            )
            if h_s > h_max:
                log_sniper(
                    f"[EXECUTOR P-02 VETO] {senal.get('symbol')} aborted at order gate (H={h_s:.3f} > {h_max:.3f})."
                )
                return None

        symbol = str(senal.get("symbol") or "")
        side = str(senal.get("side") or "long").lower()
        bid = float(senal.get("bid") or 0.0)
        ask = float(senal.get("ask") or 0.0)
        z_score = float(senal.get("z_score") or 0.0)
        ofi = float(senal.get("ofi") or 0.0)
        hurst = float(senal.get("hurst") or 0.45)
        volatility = float(senal.get("volatilidad") or 0.0020)

        if not symbol or bid <= 0.0 or ask <= 0.0:
            return None

        f_kelly, margin_usdt, notional_usdt = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil(
            symbol=symbol,
            z_score=z_score,
            ofi=ofi,
            hurst=hurst,
            volatilidad_local=volatility,
        )

        tick_size, step_qty, min_qty = extraer_precision_y_minimos(self.exchange, symbol, bid)
        quote_price = calcular_precio_penny_jump(side, bid, ask, tick_size, ofi)
        if quote_price <= 0.0:
            return None

        raw_qty = notional_usdt / quote_price
        qty = redondear_cantidad_lote(raw_qty, step_qty, min_qty)
        if qty <= 0.0:
            ESTADO_RAM.pares_excluidos_lote.add(symbol)
            log_sniper(
                f"[WARN] [MIN LOT FILTER] {symbol} requires min_qty={min_qty} "
                f"(>{notional_usdt:.2f} USDT). Excluded in RAM."
            )
            return None

        real_notional = round(qty * quote_price, 4)
        real_margin = round(real_notional / cfg.APALANCAMIENTO_BASE, 4)

        if not ESTADO_RAM.reservar_margen_atomico(symbol, real_margin):
            return None

        position_confirmed = False
        try:
            self.disparos_intentados += 1
            side_order = "buy" if side == "long" else "sell"
            params_postonly = {"timeInForce": "PostOnly"}

            t0_http = time.perf_counter()
            try:
                order = await self.exchange.create_order(
                    symbol, "limit", side_order, qty, quote_price, params_postonly
                )
            except Exception as exc:
                log_sniper(f"[WARN] [SNIPER] Shot aborted on {symbol}: {exc}")
                return None

            rtt_ms = (time.perf_counter() - t0_http) * 1000.0
            order_id = str((order or {}).get("id") or "")
            if not order_id:
                return None

            side_label = "SHORT-SNIPER" if side == "short" else "SNIPER"
            log_sniper(
                f"[{side_label}] Order {order_id} on {symbol}: {qty} @ {quote_price} "
                f"(notional ~{real_notional:.2f} USDT, {cfg.APALANCAMIENTO_BASE}x, "
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
            t_queue_start = time.time()
            filled_qty = float((order or {}).get("filled") or 0.0)
            fill_price = float((order or {}).get("average") or (order or {}).get("price") or quote_price)
            ord_status = str((order or {}).get("status") or "open").lower()

            poll_step = min(0.15, max(0.04, ttl_max / 5.0))
            while ord_status not in ("closed", "canceled", "cancelled", "rejected"):
                elapsed = time.time() - t_queue_start
                if elapsed >= ttl_max:
                    break

                current_tk = ESTADO_RAM.ticks_ram.get(symbol)
                if current_tk is not None:
                    if side == "long" and current_tk.ofi_l1_l5 < cfg.OFI_ABORTAR_COLA_UMBRAL:
                        break
                    if side == "short" and current_tk.ofi_l1_l5 > abs(cfg.OFI_ABORTAR_COLA_UMBRAL):
                        break

                await asyncio.sleep(poll_step)
                try:
                    ord_state = await self.exchange.fetch_order(order_id, symbol, {"acknowledged": True})
                    if ord_state:
                        ord_status = str(ord_state.get("status") or ord_status).lower()
                        filled_qty = float(ord_state.get("filled") or filled_qty)
                        p_avg = float(ord_state.get("average") or ord_state.get("price") or 0.0)
                        if p_avg > 0.0:
                            fill_price = p_avg
                        if ord_status == "closed" or filled_qty >= qty:
                            break
                except TypeError:
                    try:
                        ord_state = await self.exchange.fetch_order(order_id, symbol)
                        if ord_state:
                            ord_status = str(ord_state.get("status") or ord_status).lower()
                            filled_qty = float(ord_state.get("filled") or filled_qty)
                            p_avg = float(ord_state.get("average") or ord_state.get("price") or 0.0)
                            if p_avg > 0.0:
                                fill_price = p_avg
                            if ord_status == "closed" or filled_qty >= qty:
                                break
                    except Exception:
                        pass
                except Exception:
                    pass

            if ord_status not in ("closed", "canceled", "cancelled", "rejected") and filled_qty < qty:
                try:
                    await self.exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
                try:
                    final_state = await self.exchange.fetch_order(order_id, symbol, {"acknowledged": True})
                    if final_state:
                        filled_qty = max(filled_qty, float(final_state.get("filled") or 0.0))
                        p_avg = float(final_state.get("average") or 0.0)
                        if p_avg > 0.0:
                            fill_price = p_avg
                except Exception:
                    pass

            if filled_qty <= 0.0 and hasattr(self.exchange, "fetch_positions"):
                try:
                    pos_list = await self.exchange.fetch_positions([symbol])
                    for p_item in (pos_list or []):
                        if str(p_item.get("symbol") or "") == symbol:
                            c_open = float(p_item.get("contracts") or 0.0)
                            if c_open > 0.0:
                                filled_qty = c_open
                                ep_open = float(p_item.get("entryPrice") or p_item.get("info", {}).get("avgPrice") or 0.0)
                                if ep_open > 0.0:
                                    fill_price = ep_open
                                break
                except TypeError:
                    try:
                        pos_list = await self.exchange.fetch_positions()
                        for p_item in (pos_list or []):
                            if str(p_item.get("symbol") or "") == symbol:
                                c_open = float(p_item.get("contracts") or 0.0)
                                if c_open > 0.0:
                                    filled_qty = c_open
                                    ep_open = float(p_item.get("entryPrice") or p_item.get("info", {}).get("avgPrice") or 0.0)
                                    if ep_open > 0.0:
                                        fill_price = ep_open
                                    break
                    except Exception:
                        pass
                except Exception:
                    pass

            if filled_qty <= 0.0:
                self.disparos_cancelados_ttl += 1
                TELEMETRIA_TG.descartar_apertura_no_llenada(symbol)
                log_sniper(
                    f"[{side_label}] Order on {symbol} unfilled after {ttl_max:.1f}s (Zero Re-Quote): margin released."
                )
                return None

            position_confirmed = True
            self.disparos_llenados += 1
            sl_internal, sl_bybit = calcular_barreras_sl_iniciales(side, fill_price, tick_size)

            pos = PosicionActiva(
                symbol=symbol,
                side=side,
                qty_inicial=filled_qty,
                qty_actual=filled_qty,
                entry_price=fill_price,
                ts_apertura=time.time(),
                sl_interno_price=sl_internal,
                sl_bybit_price=sl_bybit,
                z_score_entry=z_score,
                ofi_entry=ofi,
                hurst_entry=hurst,
                volatilidad_entry=volatility,
            )

            ESTADO_RAM.orden_en_vuelo_symbol = None
            ESTADO_RAM.posiciones_activas[symbol] = pos

            side_msg = " SHORT" if side == "short" else ""
            log_sniper(
                f"[{side_label}] [TARGET] Active{side_msg} position on {symbol}: {filled_qty} @ {fill_price} "
                f"(age 0s / max {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s) | Internal SL {sl_internal} | Bybit SL {sl_bybit}"
            )

            await TELEMETRIA_TG.confirmar_y_enviar_apertura(
                symbol=symbol,
                qty_llenada=filled_qty,
                entry_price=fill_price,
                side=side,
                order_id=order_id,
            )

            if self.callback_posicion_abierta is not None:
                await self.callback_posicion_abierta(pos)

            return pos
        finally:
            if not position_confirmed:
                ESTADO_RAM.liberar_margen_atomico(symbol, real_margin)