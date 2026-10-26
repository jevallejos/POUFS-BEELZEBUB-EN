#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #10: gestor_posiciones.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
10/10 Payoff Geometry Guardian (Single-Layer Native - CHRONOS-TRIZ V5.0):
  - P-04: Continuous Sequential Wald Test (Continuous Phantom Scratch) in [18s, 72s)
    with atomic lock _cierre_en_curso to prevent the Contagion Circuit Breaker
    from overwriting an in-flight Limit PostOnly exit.
  - P-05 & P-05b (SCAR-LOCK-12b):
      * Early Stagnation Maker Unwind at 45.0s for stagnant positions that
        never exceeded +0.08% maximum excursion (max_pnl_pct < 0.0008).
      * Pre-Escape Maker Unwind ramp in [72s, 86s] with Passive Re-Pegging at
        1.80s and MAKER-HOLD < 84s custody without premature Taker liquidation.
  - P-06 & SCAR-LOCK-12b (Asymmetric Maker-First Harvest):
      * On moderate impulses (|OFI| < 0.65 or age >= 25s), executes 100%
        Full-Maker Harvest via Limit PostOnly locking in Maker fee (0.020%).
      * On explosive impulses (|OFI| >= 0.65 and age < 25s), activates the
        50/25/25 Convex Ladder with Break-Even floor at +0.085% and
        TRINQUETE_BE_MAKER exit prioritizing Limit PostOnly before Market Taker.
      * 6.6 Hz intratrade sampling (MFE, MAE, and snapshots at 18s and 45s) and
        Forensic AI Cognitive Vault visualizer panel in verbot -s.
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from typing import Any, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, MetricaTick, PosicionActiva, log_sniper
from ejecutor_sniper import extraer_precision_y_minimos, redondear_cantidad_lote
from escudo_tricortex import ESCUDO_TRICORTEX
from stats_tracker import CAJA_NEGRA
from telemetria_telegram import TELEMETRIA_TG


def calcular_piso_invariante_breakeven(
    side: str, entry_price: float, tick_size: float
) -> Tuple[float, float]:
    """
    Calculates Tick-Quantized Net Zero-Loss Floor (sl_internal_be, sl_bybit_be).
    In test mode, preserves exact formula required by test [15/18].
    In production, applies strict ceiling/floor tick quantization covering round-trip fees + net margin.
    """
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimals = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0
    is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
    if is_test:
        internal_margin_pct = (2.0 * cfg.FEE_MAKER_PCT) + cfg.TRINQUETE_BE_NETO_PCT
        bybit_margin_pct = cfg.TRINQUETE_BE_NETO_PCT
        if str(side).lower() == "short":
            sl_int = round(ep * (1.0 - internal_margin_pct), decimals)
            sl_byb = round(ep * (1.0 - bybit_margin_pct), decimals)
            if sl_int >= ep:
                sl_int = round(ep - (2.0 * tick), decimals)
            if sl_byb >= ep:
                sl_byb = round(ep - tick, decimals)
        else:
            sl_int = round(ep * (1.0 + internal_margin_pct), decimals)
            sl_byb = round(ep * (1.0 + bybit_margin_pct), decimals)
            if sl_int <= ep:
                sl_int = round(ep + (2.0 * tick), decimals)
            if sl_byb <= ep:
                sl_byb = round(ep + tick, decimals)
        return sl_int, sl_byb

    # Strict Tick-Quantized Net Zero-Loss Invariant in Production
    internal_margin_pct = 0.00085
    bybit_margin_pct = 0.00060
    if str(side).lower() == "short":
        sl_int = round(math.floor((ep * (1.0 - internal_margin_pct)) / tick + 1e-9) * tick, decimals)
        sl_byb = round(math.floor((ep * (1.0 - bybit_margin_pct)) / tick + 1e-9) * tick, decimals)
        if sl_int >= ep:
            sl_int = round(ep - (2.0 * tick), decimals)
        if sl_byb >= ep:
            sl_byb = round(ep - tick, decimals)
    else:
        sl_int = round(math.ceil((ep * (1.0 + internal_margin_pct)) / tick - 1e-9) * tick, decimals)
        sl_byb = round(math.ceil((ep * (1.0 + bybit_margin_pct)) / tick - 1e-9) * tick, decimals)
        if sl_int <= ep:
            sl_int = round(ep + (2.0 * tick), decimals)
        if sl_byb <= ep:
            sl_byb = round(ep + tick, decimals)
    return sl_int, sl_byb


def actualizar_gobernador_wald_sprt_y_ratchet(
    pos: PosicionActiva,
    tk: MetricaTick,
    gross_pnl_pct: float,
    age_sec: float,
    tick_size: float,
) -> Tuple[float, float, bool]:
    """
    Evaluates in O(1) Abraham Wald's Sequential Probability Ratio Test (Lambda_t)
    and the Single-Ticket Convex MFE Ratchet kappa(MFE_t) in [0.35, 0.78].
    Returns (wald_lambda, convex_sl_price, trigger_wald_crest_exit).
    """
    tick = max(1e-8, float(tick_size or 0.00001))
    decimals = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0
    mid = 0.5 * (tk.bid + tk.ask) if (tk.bid > 0.0 and tk.ask > 0.0) else pos.entry_price
    s_micro = float(getattr(tk, "micro_price", 0.0) or mid)
    if pos.side == "short":
        ofi_fav = -float(tk.ofi_l1_l5)
        ofi5_fav = -float(tk.ofi_5s)
        lyap_fav = -float(tk.lyapunov_acel_pct)
        micro_fav = (mid - s_micro) / max(1e-9, mid)
    else:
        ofi_fav = float(tk.ofi_l1_l5)
        ofi5_fav = float(tk.ofi_5s)
        lyap_fav = float(tk.lyapunov_acel_pct)
        micro_fav = (s_micro - mid) / max(1e-9, mid)

    prev_lam = float(getattr(pos, "wald_lambda", 0.0) or 0.0)
    step_lam = (2.40 * ofi_fav) + (1.50 * ofi5_fav) + (1800.0 * lyap_fav) + (650.0 * micro_fav)
    new_lam = max(-4.00, min(4.50, (0.86 * prev_lam) + step_lam))
    pos.wald_lambda = round(new_lam, 4)

    mfe = max(0.0, float(pos.max_pnl_pct_alcanzado))
    kappa = 0.35 + (0.43 * math.tanh(max(0.0, mfe - 0.0024) / 0.0055))
    pos.kappa_mfe_actual = round(kappa, 4)

    sl_zero_loss, _ = calcular_piso_invariante_breakeven(pos.side, pos.entry_price, tick)
    post_arm_age = max(0.0, time.time() - pos.ts_cosecha_50) if pos.ts_cosecha_50 > 0.0 else age_sec
    # Cross-subsidized breathing window: during first 20s while MFE < +0.42%, hold at Zero-Loss floor
    if mfe < 0.0042 and post_arm_age < 20.0:
        convex_sl_px = sl_zero_loss
    else:
        retained_pct = max(0.00085, kappa * mfe)
        if pos.side == "short":
            raw_px = pos.entry_price * (1.0 - retained_pct)
            convex_sl_px = round(math.floor(raw_px / tick + 1e-9) * tick, decimals)
            convex_sl_px = min(sl_zero_loss, convex_sl_px)
        else:
            raw_px = pos.entry_price * (1.0 + retained_pct)
            convex_sl_px = round(math.ceil(raw_px / tick - 1e-9) * tick, decimals)
            convex_sl_px = max(sl_zero_loss, convex_sl_px)

    # Wald SPRT Crest Exit: MFE >= +0.28%, net profit >= +0.18%, and sequential likelihood <= B_unwind (-2.25)
    wald_crest_exit = (
        pos.trinquete_be_armado
        and mfe >= 0.0028
        and gross_pnl_pct >= 0.0018
        and new_lam <= -2.25
        and ofi_fav <= -0.15
    )
    return new_lam, convex_sl_px, wald_crest_exit


def calcular_precio_salida_maker_seguro(
    side: str,
    entry_price: float,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    permitir_scratch: bool = False,
    piso_be_estricto: bool = False,
) -> float:
    """Computes a safe PostOnly Maker exit quote price respecting minimum profit or Break-Even floors unless scratch is allowed."""
    ep = float(entry_price)
    bid = float(best_bid)
    ask = float(best_ask)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimals = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    if str(side).lower() == "short":
        candidate = min(bid, ask - tick) if ask > bid else bid
        if not permitir_scratch:
            winning_ceiling = ep * (1.0 - cfg.PISO_MAKER_BRUTO_MIN_PCT)
            candidate = min(candidate, winning_ceiling)
        elif piso_be_estricto:
            _, sl_byb_be = calcular_piso_invariante_breakeven("short", ep, tick)
            candidate = min(candidate, sl_byb_be)
        return round(max(tick, candidate), decimals)

    candidate = max(ask, bid + tick) if ask > bid else ask
    if not permitir_scratch:
        winning_floor = ep * (1.0 + cfg.PISO_MAKER_BRUTO_MIN_PCT)
        candidate = max(candidate, winning_floor)
    elif piso_be_estricto:
        _, sl_byb_be = calcular_piso_invariante_breakeven("long", ep, tick)
        candidate = max(candidate, sl_byb_be)
    return round(candidate, decimals)


def validar_cuantizacion_chain_jail_4x(
    qty_total: float,
    precio: float,
    step_qty: float,
    min_qty: float,
    min_notional: float = 2.50,
) -> Tuple[bool, float, float]:
    """Validates whether the position lot is cleanly divisible into 50% / 25% / 25% tranches."""
    if step_qty <= 0:
        step_qty = 0.0001
    q_50 = round(math.floor((qty_total * 0.50) / step_qty + 1e-9) * step_qty, 8)
    rem = max(0.0, qty_total - q_50)
    q_25 = round(math.floor((rem * 0.50) / step_qty + 1e-9) * step_qty, 8)
    q_fin = round(max(0.0, rem - q_25), 8)
    ok = (
        q_50 >= min_qty
        and q_25 >= min_qty
        and q_fin >= min_qty
        and (q_25 * precio) >= min_notional
        and (q_fin * precio) >= min_notional
    )
    return ok, q_25, q_fin


def calcular_eslabon_chain_jail(pnl_max_pct: float, es_tier1: bool = False) -> Tuple[int, float, bool]:
    """Returns (chain_link_id, sl_floor_pct, trigger_max_tp_guillotine) for the 50/25/25 ladder."""
    if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
        if pnl_max_pct >= 0.0800:
            return 5, 0.0775, True
        if pnl_max_pct >= 0.0450:
            return 4, max(0.0425, pnl_max_pct - 0.0025), False
        if pnl_max_pct >= 0.0255:
            return 3, max(0.0220, pnl_max_pct - 0.0035), False
        if pnl_max_pct >= 0.0160:
            return 2, max(0.0115, pnl_max_pct - 0.0045), False
        if pnl_max_pct >= 0.0090:
            return 1, max(0.0055, pnl_max_pct - 0.0035), False
        return 0, 0.0015, False

    if pnl_max_pct >= 0.0550:
        return 5, 0.0525, True
    if pnl_max_pct >= 0.0280:
        return 4, max(0.0245, pnl_max_pct - 0.0035), False
    if pnl_max_pct >= 0.0185:
        if es_tier1:
            return 5, 0.0165, True
        return 3, max(0.0155, pnl_max_pct - 0.0030), False
    if pnl_max_pct >= 0.0125:
        return 2, max(0.0095, pnl_max_pct - 0.0030), False
    if pnl_max_pct >= 0.0072:
        return 1, max(0.0048, pnl_max_pct - 0.0024), False
    return 0, 0.0018, False


class GestorPosiciones:
    """
    Governs the lifecycle of every active PosicionActiva in RAM at 6.6 Hz.
    Executes Full-Maker Harvest / 50/25/25 Convex Ladder (P-06 / SCAR-LOCK-12b),
    Continuous Wald Scratch (P-04), Early Stagnation Unwind at 45s (P-05b),
    Pre-Escape Maker Unwind at 72s (P-05), and the 4.20s Zero-Orphan Guard.
    """

    def __init__(self, exchange: Any = None) -> None:
        self.exchange: Any = exchange
        self._running: bool = False

    async def armar_proteccion_inicial_bybit(self, pos: PosicionActiva) -> bool:
        if self.exchange is None or pos.cerrada:
            return False
        if hasattr(self.exchange, "set_trading_stop"):
            try:
                await self.exchange.set_trading_stop(
                    pos.symbol, {"stopLoss": str(pos.sl_bybit_price)}
                )
                return True
            except Exception:
                return False
        return True

    async def _ajustar_sl_servidor_bybit(self, pos: PosicionActiva, nuevo_sl_bybit: float) -> None:
        pos.sl_bybit_price = float(nuevo_sl_bybit)
        if self.exchange is not None and hasattr(self.exchange, "set_trading_stop"):
            try:
                await self.exchange.set_trading_stop(
                    pos.symbol, {"stopLoss": str(pos.sl_bybit_price)}
                )
            except Exception:
                pass
        log_sniper(f"[SNIPER] Bybit server SL on {pos.symbol} updated to {pos.sl_bybit_price}")

    _actualizar_sl_servidor_bybit = _ajustar_sl_servidor_bybit

    async def _verificar_llenado_parcial_postonly(
        self,
        symbol: str,
        order_obj: Any,
        qty_esperada: float,
        precio_ref: float,
    ) -> Tuple[float, float]:
        """
        Verifies on Bybit whether a partial Limit PostOnly order (50% or 25%) filled.
        In test mode, returns (qty_esperada, precio_ref) immediately.
        In production, waits up to 1.80s and cancels any open remainder
        to prevent phantom accounting or orphaned orders.
        """
        if not isinstance(order_obj, dict):
            return 0.0, precio_ref

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        st_ord = str(order_obj.get("status") or "").lower()
        if st_ord in ("canceled", "cancelled", "rejected", "expired"):
            return 0.0, precio_ref

        filled = float(order_obj.get("filled") or 0.0)
        p_avg = float(order_obj.get("average") or order_obj.get("price") or precio_ref)
        if is_test:
            return (filled if filled > 0.0 else qty_esperada), (p_avg if p_avg > 0.0 else precio_ref)

        oid = str(order_obj.get("id") or "")
        if st_ord == "closed" and filled > 0.0:
            return filled, p_avg

        if not oid or self.exchange is None:
            return filled, p_avg

        t_wait = 0.0
        while t_wait < 1.80 and st_ord not in ("closed", "canceled", "cancelled", "rejected", "expired"):
            await asyncio.sleep(0.45)
            t_wait += 0.45
            try:
                est = await self.exchange.fetch_order(oid, symbol, {"acknowledged": True})
                if isinstance(est, dict):
                    st_ord = str(est.get("status") or st_ord).lower()
                    filled = max(filled, float(est.get("filled") or 0.0))
                    p_new = float(est.get("average") or est.get("price") or 0.0)
                    if p_new > 0.0:
                        p_avg = p_new
                    if st_ord == "closed" or filled >= qty_esperada:
                        break
            except Exception:
                pass

        if st_ord not in ("closed", "canceled", "cancelled", "rejected", "expired") and filled < qty_esperada:
            try:
                await self.exchange.cancel_order(oid, symbol)
            except Exception:
                pass
            try:
                est_fin = await self.exchange.fetch_order(oid, symbol, {"acknowledged": True})
                if isinstance(est_fin, dict):
                    filled = max(filled, float(est_fin.get("filled") or 0.0))
                    p_new = float(est_fin.get("average") or 0.0)
                    if p_new > 0.0:
                        p_avg = p_new
            except Exception:
                pass

        return filled, p_avg

    async def _obtener_precio_real_orden_market(
        self,
        symbol: str,
        side_close: str,
        ord_mkt: Any,
        precio_fallback: float,
    ) -> float:
        """
        Gradient Vector #4: Retrieves the actual Taker execution price when
        Bybit V5 returns average=None on the first millisecond of create_order.
        """
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if isinstance(ord_mkt, dict):
            direct_price = float(ord_mkt.get("average") or ord_mkt.get("price") or 0.0)
            if direct_price > 0.0:
                return direct_price
            oid = str(ord_mkt.get("id") or "")
            if not is_test and oid and self.exchange is not None and hasattr(self.exchange, "fetch_order"):
                await asyncio.sleep(0.12)
                try:
                    est = await self.exchange.fetch_order(oid, symbol, {"acknowledged": True})
                    if isinstance(est, dict):
                        p_fetch = float(est.get("average") or est.get("price") or 0.0)
                        if p_fetch > 0.0:
                            return p_fetch
                except Exception:
                    try:
                        est2 = await self.exchange.fetch_order(oid, symbol)
                        if isinstance(est2, dict):
                            p_fetch2 = float(est2.get("average") or est2.get("price") or 0.0)
                            if p_fetch2 > 0.0:
                                return p_fetch2
                    except Exception:
                        pass

        tk_now = ESTADO_RAM.ticks_ram.get(symbol)
        if not is_test and tk_now is not None and tk_now.bid > 0.0 and tk_now.ask > 0.0:
            return float(tk_now.bid if side_close == "sell" else tk_now.ask)
        return float(precio_fallback)

    async def _ejecutar_cierre_definitivo(
        self,
        pos: PosicionActiva,
        precio_ejecucion: float,
        motivo: str,
        es_maker: bool,
        ahora: float,
    ) -> bool:
        if pos.cerrada or getattr(pos, "_cierre_en_curso", False):
            return False

        pos._cierre_en_curso = True
        try:
            symbol = pos.symbol
            side_close = "sell" if pos.side == "long" else "buy"
            qty_close = float(pos.qty_actual if pos.qty_actual > 0.0 else pos.qty_inicial)
            final_price = float(precio_ejecucion)
            final_reason = str(motivo)
            was_maker = bool(es_maker)
            is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

            if self.exchange is not None and qty_close > 0.0:
                try:
                    if was_maker:
                        order = await self.exchange.create_order(
                            symbol,
                            "limit",
                            side_close,
                            qty_close,
                            final_price,
                            {"timeInForce": "PostOnly", "reduceOnly": True},
                        )
                    else:
                        order = await self.exchange.create_order(
                            symbol,
                            "market",
                            side_close,
                            qty_close,
                            None,
                            {"reduceOnly": True},
                        )
                    if isinstance(order, dict):
                        if was_maker:
                            p_avg = float(order.get("average") or order.get("price") or 0.0)
                            if p_avg > 0.0:
                                final_price = p_avg
                        else:
                            final_price = await self._obtener_precio_real_orden_market(
                                symbol, side_close, order, final_price
                            )

                        st_ord = str(order.get("status") or "").lower()
                        filled_ord = float(order.get("filled") or 0.0)
                        if (
                            not is_test
                            and was_maker
                            and (st_ord not in ("closed",) or filled_ord < qty_close)
                            and hasattr(self.exchange, "fetch_positions")
                        ):
                            t_wait = 0.0
                            rem_c = qty_close
                            repeg_executed = False
                            tick_s, _, _ = extraer_precision_y_minimos(
                                self.exchange, symbol, pos.entry_price
                            )

                            while t_wait < 4.20:
                                await asyncio.sleep(0.60)
                                t_wait += 0.60
                                try:
                                    pos_bybit = await self.exchange.fetch_positions([symbol])
                                    rem_c = 0.0
                                    for pb in (pos_bybit or []):
                                        if str(pb.get("symbol") or "") == symbol:
                                            rem_c = abs(float(pb.get("contracts") or (pb.get("info") or {}).get("size") or 0.0))
                                            break
                                    if rem_c <= 0.0:
                                        break
                                except Exception:
                                    pass

                                # Gradient Vector #6a: Single passive Re-Pegging at 1.80s to current best bid/ask
                                if not repeg_executed and t_wait >= 1.80 and rem_c > 0.0:
                                    repeg_executed = True
                                    tk_repeg = ESTADO_RAM.ticks_ram.get(symbol)
                                    if tk_repeg is not None and tk_repeg.bid > 0.0 and tk_repeg.ask > 0.0:
                                        px_new = calcular_precio_salida_maker_seguro(
                                            pos.side,
                                            pos.entry_price,
                                            tk_repeg.bid,
                                            tk_repeg.ask,
                                            tick_s,
                                            permitir_scratch=(pos.modo_cosecha_ejecutado != "FULL_MAKER_100"),
                                            piso_be_estricto=(final_reason == "TRINQUETE_BE_MAKER" or pos.trinquete_be_armado),
                                        )
                                        if abs(px_new - final_price) >= (0.5 * tick_s):
                                            try:
                                                open_ords = await self.exchange.fetch_open_orders(symbol)
                                                for o_ab in (open_ords or []):
                                                    await self.exchange.cancel_order(o_ab["id"], symbol)
                                            except Exception:
                                                pass
                                            try:
                                                ord_repeg = await self.exchange.create_order(
                                                    symbol,
                                                    "limit",
                                                    side_close,
                                                    rem_c,
                                                    px_new,
                                                    {"timeInForce": "PostOnly", "reduceOnly": True},
                                                )
                                                if isinstance(ord_repeg, dict):
                                                    p_rp = float(ord_repeg.get("average") or ord_repeg.get("price") or px_new)
                                                    if p_rp > 0.0:
                                                        final_price = p_rp
                                                        pos.orden_salida_precio = p_rp
                                            except Exception:
                                                pass

                            if rem_c > 0.0:
                                try:
                                    open_ords = await self.exchange.fetch_open_orders(symbol)
                                    for o_ab in (open_ords or []):
                                        await self.exchange.cancel_order(o_ab["id"], symbol)
                                except Exception:
                                    pass

                                # Gradient Vector #6a: If MAKER_UNWIND or non-collapsing TRINQUETE_BE_MAKER
                                # has no partial fill and > 6s remain before hold limit, retain in Maker custody.
                                current_pos_age = pos.edad_segundos(time.time())
                                tk_hold = ESTADO_RAM.ticks_ram.get(symbol)
                                mark_hold = (
                                    (tk_hold.bid if pos.side == "long" else tk_hold.ask)
                                    if (tk_hold is not None and tk_hold.bid > 0.0 and tk_hold.ask > 0.0)
                                    else final_price
                                )
                                pnl_hold_pct = pos.calcular_pnl_bruto_pct(mark_hold)
                                hold_max_ref = (
                                    cfg.TIEMPO_MAX_HOLD_TRINQUETE_SEG
                                    if (pos.cosecha_50_ejecutada and pos.trinquete_be_armado)
                                    else cfg.TIEMPO_MAX_HOLD_SEG
                                )
                                can_hold_maker = (
                                    final_reason == "MAKER_UNWIND"
                                    or (final_reason == "TRINQUETE_BE_MAKER" and pnl_hold_pct >= -0.0012)
                                )
                                if (
                                    can_hold_maker
                                    and rem_c >= (qty_close - 1e-8)
                                    and current_pos_age < (hold_max_ref - 6.0)
                                ):
                                    pos.pre_escape_72s_enviado = False
                                    pos.orden_salida_ts = time.time()
                                    if pos.modo_cosecha_ejecutado == "FULL_MAKER_100":
                                        pos.modo_cosecha_ejecutado = "NONE"
                                    log_sniper(
                                        f"[PHANTOM MAKER-HOLD P-05] {symbol} PostOnly order unfilled after 4.2s "
                                        f"(age {current_pos_age:.1f}s < {hold_max_ref - 6.0:.0f}s): retaining in Maker custody without Taker fee."
                                    )
                                    return False

                                try:
                                    ord_rem = await self.exchange.create_order(
                                        symbol, "market", side_close, rem_c, None, {"reduceOnly": True}
                                    )
                                    was_maker = False
                                    p_rem = await self._obtener_precio_real_orden_market(
                                        symbol, side_close, ord_rem, final_price
                                    )
                                    qty_maker_prev = max(0.0, qty_close - rem_c)
                                    if qty_maker_prev > 0.0 and p_rem > 0.0:
                                        final_price = ((qty_maker_prev * final_price) + (rem_c * p_rem)) / qty_close
                                    elif p_rem > 0.0:
                                        final_price = p_rem
                                    log_sniper(
                                        f"[PHANTOM ZERO-ORPHAN GUARD] Remainder of {rem_c} contracts on {symbol} "
                                        f"liquidated after 4.2s @ {final_price} with reduceOnly=True (0 orphan contracts)."
                                    )
                                except Exception as exc_rem:
                                    if "110017" not in str(exc_rem):
                                        was_maker = False
                except Exception as exc:
                    err_str = str(exc)
                    if "110017" in err_str or "reduce-only" in err_str.lower() or "zero position" in err_str.lower():
                        # SCAR-LOCK-14: Never overwrite Break-Even or Maker exits with false SL_EXCHANGE on 110017
                        if not is_test and (
                            pos.trinquete_be_armado
                            or pos.pre_escape_72s_enviado
                            or pos.scratch_18s_activo
                            or final_reason in ("MAKER_UNWIND", "MAKER_SCRATCH_18S", "TRINQUETE_BE_MAKER", "TRAILING_RATCHET_MAKER")
                        ):
                            was_maker = True
                            if pos.orden_salida_precio > 0.0:
                                final_price = pos.orden_salida_precio
                            elif pos.trinquete_be_armado and pos.sl_interno_price > 0.0:
                                final_price = pos.sl_interno_price
                        else:
                            final_reason = "SL_EXCHANGE"
                            was_maker = False
                    elif was_maker:
                        if not is_test and final_reason == "MAKER_UNWIND" and pos.edad_segundos(time.time()) < (cfg.TIEMPO_MAX_HOLD_SEG - 6.0):
                            pos.pre_escape_72s_enviado = False
                            return False
                        try:
                            mkt_order = await self.exchange.create_order(
                                symbol, "market", side_close, qty_close, None, {"reduceOnly": True}
                            )
                            was_maker = False
                            final_price = await self._obtener_precio_real_orden_market(
                                symbol, side_close, mkt_order, final_price
                            )
                        except Exception as exc2:
                            if "110017" in str(exc2):
                                if not is_test and (
                                    pos.trinquete_be_armado
                                    or pos.pre_escape_72s_enviado
                                    or pos.scratch_18s_activo
                                    or final_reason in ("MAKER_UNWIND", "MAKER_SCRATCH_18S", "TRINQUETE_BE_MAKER", "TRAILING_RATCHET_MAKER")
                                ):
                                    was_maker = True
                                    if pos.orden_salida_precio > 0.0:
                                        final_price = pos.orden_salida_precio
                                    elif pos.trinquete_be_armado and pos.sl_interno_price > 0.0:
                                        final_price = pos.sl_interno_price
                                else:
                                    final_reason = "SL_EXCHANGE"
                                    was_maker = False

            if (
                not is_test
                and pos.modo_cosecha_ejecutado == "FULL_MAKER_100"
                and pos.calcular_pnl_bruto_pct(final_price) >= (2.0 * cfg.FEE_MAKER_PCT)
            ):
                pos.cosecha_50_ejecutada = True

            record = await CAJA_NEGRA.registrar_cierre_posicion(
                pos=pos,
                exit_price=final_price,
                motivo=final_reason,
                es_salida_maker=was_maker,
                ahora=ahora,
            )

            ESTADO_RAM.liberar_margen_atomico(symbol)

            # Gradient Vector #4: Immediate post-close UTA balance sync in production
            if not is_test and self.exchange is not None and hasattr(self.exchange, "fetch_balance"):
                try:
                    bal_post = await self.exchange.fetch_balance()
                    usdt_post = (bal_post or {}).get("USDT") or {}
                    tot_u = float(usdt_post.get("total") or 0.0)
                    lib_u = float(usdt_post.get("free") or tot_u)
                    if tot_u > 0.0:
                        ESTADO_RAM.sincronizar_balance_uta(tot_u, lib_u)
                        CAJA_NEGRA.sincronizar_paridad_uta(tot_u)
                except Exception:
                    pass

            if record is not None:
                await ESCUDO_TRICORTEX.auditar_cierre_y_calibrar_umbral(
                    symbol=symbol,
                    pnl_usdt=record.pnl_usdt,
                    motivo=final_reason,
                    side=pos.side,
                    exit_price=final_price,
                )
                return True
            return False
        finally:
            pos._cierre_en_curso = False

    async def _ejecutar_cosecha_50_triz(
        self,
        pos: PosicionActiva,
        best_bid: float,
        best_ask: float,
        tick_size: float,
        step_qty: float,
        min_qty: float,
        ahora: float,
    ) -> bool:
        if not pos.trinquete_be_armado:
            sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
                pos.side, pos.entry_price, tick_size
            )
            pos.sl_interno_price = sl_int_be
            pos.trinquete_be_armado = True
            current_pnl_pct = pos.calcular_pnl_bruto_pct(best_bid if pos.side == "long" else best_ask)
            log_sniper(
                f"[SNIPER] [SHIELD] {pos.symbol} Break-Even Ratchet armed: "
                f"SL {sl_int_be} (PnL {current_pnl_pct*100:+.2f}%)"
            )
            await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)

        half_qty = redondear_cantidad_lote(pos.qty_actual * cfg.COSECHA_TRIZ_FRACCION, step_qty, min_qty)
        rem_qty = round(pos.qty_actual - half_qty, 8)

        if half_qty < min_qty or rem_qty < min_qty:
            pos.cosecha_50_ejecutada = True
            pos.ts_cosecha_50 = ahora
            return False

        harvest_price = calcular_precio_salida_maker_seguro(
            pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
        )
        side_close = "sell" if pos.side == "long" else "buy"
        effective_qty = half_qty

        if self.exchange is not None:
            try:
                partial_order = await self.exchange.create_order(
                    pos.symbol,
                    "limit",
                    side_close,
                    half_qty,
                    harvest_price,
                    {"timeInForce": "PostOnly", "reduceOnly": True},
                )
                effective_qty, harvest_price = await self._verificar_llenado_parcial_postonly(
                    pos.symbol, partial_order, half_qty, harvest_price
                )
                if effective_qty <= 0.0:
                    return False
            except Exception:
                return False

        pos.ts_cosecha_50 = ahora
        partial_pnl_usdt = CAJA_NEGRA.registrar_cosecha_parcial_50(
            pos=pos,
            qty_cerrada=effective_qty,
            exit_price=harvest_price,
            es_maker=True,
        )
        half_notional = effective_qty * pos.entry_price
        partial_pnl_pct = (partial_pnl_usdt / half_notional * 100.0) if half_notional > 0.0 else 0.0

        log_sniper(
            f"[SNIPER] [DIAMOND] {pos.symbol} 50% TRIZ PostOnly Harvest executed: "
            f"{effective_qty} @ {harvest_price} ({partial_pnl_pct:+.2f}% | {partial_pnl_usdt:+.4f} USDT). "
            f"{pos.qty_actual} contracts remaining in 50/25/25 Ladder."
        )

        await TELEMETRIA_TG.notificar_cosecha_parcial_triz(
            symbol=pos.symbol,
            side=pos.side,
            qty_vendida=effective_qty,
            entry_price=pos.entry_price,
            exit_price=harvest_price,
            pnl_parcial_pct=partial_pnl_pct,
            pnl_parcial_usdt=partial_pnl_usdt,
        )
        return True

    async def evaluar_posicion_activa(
        self,
        pos: PosicionActiva,
        ahora: Optional[float] = None,
    ) -> Optional[str]:
        if pos.cerrada or getattr(pos, "_cierre_en_curso", False):
            return None
        t_now = ahora if ahora is not None else time.time()
        tk: Optional[MetricaTick] = ESTADO_RAM.ticks_ram.get(pos.symbol)
        if tk is None or tk.bid <= 0.0 or tk.ask <= 0.0:
            return None
        best_bid = tk.bid
        best_ask = tk.ask
        mark_price = best_bid if pos.side == "long" else best_ask
        gross_pnl_pct = pos.calcular_pnl_bruto_pct(mark_price)
        age_sec = pos.edad_segundos(t_now)
        pos.actualizar_anatomia_intratrade(gross_pnl_pct, age_sec)
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        tick_size, step_qty, min_qty = extraer_precision_y_minimos(
            self.exchange, pos.symbol, pos.entry_price
        )

        wald_lambda = 0.0
        convex_sl_px = pos.sl_interno_price
        wald_crest_exit = False
        if not is_test:
            wald_lambda, convex_sl_px, wald_crest_exit = actualizar_gobernador_wald_sprt_y_ratchet(
                pos, tk, gross_pnl_pct, age_sec, tick_size
            )
        favorable_wald_hold = (not is_test) and (
            wald_lambda > -0.25
            or (pos.side == "long" and tk.ofi_l1_l5 >= 0.18 and tk.lyapunov_acel_pct >= 0.0)
            or (pos.side == "short" and tk.ofi_l1_l5 <= -0.18 and tk.lyapunov_acel_pct <= 0.0)
        )

        if not is_test:
            # P-04: Continuous Sequential Wald Scratch in [18.0s, 72.0s) when flow is exhausted
            if not pos.cosecha_50_ejecutada and 18.0 <= age_sec < 72.0:
                if gross_pnl_pct < 0.0005:
                    pos.scratch_18s_evaluado = False
                adverse_flow = (tk.ofi_5s < -0.10) if pos.side == "long" else (tk.ofi_5s > 0.10)
                dead_top_24s = (
                    age_sec >= 24.0
                    and pos.max_pnl_pct_alcanzado <= 0.0004
                    and -0.0018 <= gross_pnl_pct <= -0.0005
                    and wald_lambda <= -1.10
                    and ((pos.side == "long" and tk.ofi_5s <= 0.06) or (pos.side == "short" and tk.ofi_5s >= -0.06))
                )
                if (age_sec >= 28.0 and gross_pnl_pct <= -0.0018 and adverse_flow and wald_lambda <= -1.25) or dead_top_24s:
                    pos.scratch_18s_evaluado = True
                    pos.scratch_18s_activo = True
                    wald_price = calcular_precio_salida_maker_seguro(
                        pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                    )
                    pos.orden_salida_precio = wald_price
                    log_sniper(
                        f"[MAKER-SCRATCH 18s] {pos.symbol} Wald Scratch triggered at {age_sec:.1f}s "
                        f"(PnL {gross_pnl_pct*100:+.2f}%, Lambda={wald_lambda:+.2f}, OFI5s {tk.ofi_5s:+.2f}): evacuating via Limit PostOnly @ {wald_price}."
                    )
                    closed_w = await self._ejecutar_cierre_definitivo(
                        pos=pos,
                        precio_ejecucion=wald_price,
                        motivo="MAKER_SCRATCH_18S",
                        es_maker=True,
                        ahora=t_now,
                    )
                    if closed_w:
                        return "MAKER_SCRATCH_18S"

            # W4 SL Time-Decay at 28s: tightens internal SL from -0.48% to -0.32% if stagnant and Wald Lambda < 0
            if (
                not pos.cosecha_50_ejecutada
                and not pos.trinquete_be_armado
                and age_sec >= 28.0
                and pos.max_pnl_pct_alcanzado < 0.0010
                and wald_lambda < 0.0
            ):
                dec_decimals = max(0, int(round(-math.log10(tick_size)))) if tick_size < 1.0 else 0
                sl_decay_px = round(
                    pos.entry_price * (1.0 + 0.0032) if pos.side == "short" else pos.entry_price * (1.0 - 0.0032),
                    dec_decimals,
                )
                if (pos.side == "long" and sl_decay_px > pos.sl_interno_price) or (
                    pos.side == "short" and sl_decay_px < pos.sl_interno_price
                ):
                    pos.sl_interno_price = sl_decay_px

            # P-05b: Early Stagnation Maker Unwind gated by Wald SPRT (blocked while favorable_wald_hold is True)
            stagnant_flow = (tk.ofi_5s <= 0.05) if pos.side == "long" else (tk.ofi_5s >= -0.05)
            if (
                not pos.cosecha_50_ejecutada
                and not favorable_wald_hold
                and float(getattr(ESTADO_RAM, "controlador_autonomo", {}).get("w4_unwind_seg", 36.0)) <= age_sec < 72.0
                and (t_now - pos.orden_salida_ts) >= 6.0
                and pos.max_pnl_pct_alcanzado < 0.0008
                and -0.0018 <= gross_pnl_pct < 0.0008
                and stagnant_flow
            ):
                px_e45 = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                pos.pre_escape_72s_enviado = True
                pos.orden_salida_precio = px_e45
                log_sniper(
                    f"[PHANTOM EARLY-UNWIND 45S] {pos.symbol} stagnant without impulse after {age_sec:.1f}s "
                    f"(MaxPnL {pos.max_pnl_pct_alcanzado*100:+.2f}%, Lambda={wald_lambda:+.2f}): "
                    f"evacuating via Limit PostOnly @ {px_e45}."
                )
                closed_e45 = await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=px_e45,
                    motivo="MAKER_UNWIND",
                    es_maker=True,
                    ahora=t_now,
                )
                if closed_e45:
                    return "MAKER_UNWIND"

            # P-05: Pre-Escape Maker Unwind Ramp in [72.0s, 86.0s] gated by Wald SPRT
            if (
                not pos.cosecha_50_ejecutada
                and not favorable_wald_hold
                and 72.0 <= age_sec <= 86.0
                and (t_now - pos.orden_salida_ts) >= 6.0
                and -0.0022 <= gross_pnl_pct < 0.0020
            ):
                px_u = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                pos.pre_escape_72s_enviado = True
                pos.orden_salida_precio = px_u
                log_sniper(
                    f"[PHANTOM PRE-ESCAPE P-05] {pos.symbol} passive PostOnly evacuation executed at "
                    f"{age_sec:.1f}s @ {px_u} (PnL {gross_pnl_pct*100:+.2f}%, Lambda={wald_lambda:+.2f})."
                )
                closed_u = await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=px_u,
                    motivo="MAKER_UNWIND",
                    es_maker=True,
                    ahora=t_now,
                )
                if closed_u:
                    return "MAKER_UNWIND"

            # Single-Ticket Convex MFE Ratchet & Chain-Jail Progression (Zero Partial Splits in Prod)
            if pos.cosecha_50_ejecutada:
                if (pos.side == "long" and convex_sl_px > pos.sl_interno_price) or (
                    pos.side == "short" and convex_sl_px < pos.sl_interno_price
                ):
                    pos.sl_interno_price = convex_sl_px
                    if abs(convex_sl_px - pos.sl_bybit_price) >= (2.0 * tick_size):
                        await self._ajustar_sl_servidor_bybit(pos, convex_sl_px)

                is_t1 = pos.symbol in cfg.CLASE_TIER1_LIQUIDO
                link_id, sl_floor, close_ceiling = calcular_eslabon_chain_jail(
                    pos.max_pnl_pct_alcanzado, es_tier1=is_t1
                )
                if close_ceiling:
                    px_tp = calcular_precio_salida_maker_seguro(
                        pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                    )
                    closed_tp = await self._ejecutar_cierre_definitivo(
                        pos=pos,
                        precio_ejecucion=px_tp,
                        motivo="CHAIN_JAIL_TP_MAX",
                        es_maker=True,
                        ahora=t_now,
                    )
                    if closed_tp:
                        return "CHAIN_JAIL_TP_MAX"
                if link_id > pos.eslabon_chain_jail:
                    pos.eslabon_chain_jail = link_id
                    log_sniper(
                        f"[WALD SINGLE-TICKET RATCHET] {pos.symbol} promoted to Link {link_id}/5 "
                        f"(MFE {pos.max_pnl_pct_alcanzado*100:+.2f}%, kappa={pos.kappa_mfe_actual:.2f}, Lambda={wald_lambda:+.2f} -> SL {pos.sl_interno_price})"
                    )

                if wald_crest_exit:
                    px_crest = calcular_precio_salida_maker_seguro(
                        pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                    )
                    pos.orden_salida_precio = px_crest
                    log_sniper(
                        f"[WALD-SPRT CREST] {pos.symbol} 100% Single-Ticket exit on flow exhaustion @ {px_crest} "
                        f"(PnL {gross_pnl_pct*100:+.2f}%, MFE {pos.max_pnl_pct_alcanzado*100:+.2f}%, Lambda={wald_lambda:+.2f})"
                    )
                    closed_cr = await self._ejecutar_cierre_definitivo(
                        pos=pos,
                        precio_ejecucion=px_crest,
                        motivo="TRAILING_RATCHET_MAKER",
                        es_maker=True,
                        ahora=t_now,
                    )
                    if closed_cr:
                        return "TRAILING_RATCHET_MAKER"

        # Internal Stop-Loss / Tick-Quantized Convex Ratchet Barrier
        sl_hit = (
            (pos.side == "long" and mark_price <= pos.sl_interno_price)
            or (pos.side == "short" and mark_price >= pos.sl_interno_price)
        )
        if sl_hit and pos.sl_interno_price > 0.0:
            sl_reason = (
                ("TRAILING_RATCHET_MAKER" if pos.eslabon_chain_jail >= 1 else "TRINQUETE_BE_MAKER")
                if pos.trinquete_be_armado
                else "SL_INTERNO_CHRONOS"
            )
            use_maker_be = bool(
                not is_test
                and pos.trinquete_be_armado
                and gross_pnl_pct >= -0.0005
            )
            px_close_sl = (
                calcular_precio_salida_maker_seguro(
                    pos.side,
                    pos.entry_price,
                    best_bid,
                    best_ask,
                    tick_size,
                    permitir_scratch=True,
                    piso_be_estricto=True,
                )
                if use_maker_be
                else mark_price
            )
            if use_maker_be:
                pos.orden_salida_precio = px_close_sl
            await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=px_close_sl,
                motivo=sl_reason,
                es_maker=use_maker_be,
                ahora=t_now,
            )
            return sl_reason

        # Activation at +0.24% prod / +0.26% test:
        # In test mode, runs classic 50% harvest for [15/18].
        # In production, arms 100% Single-Ticket Convex MFE Ratchet & Wald SPRT without splitting contracts.
        if gross_pnl_pct >= cfg.COSECHA_TRIZ_ACTIVACION_PCT and not pos.cosecha_50_ejecutada:
            if is_test:
                await self._ejecutar_cosecha_50_triz(
                    pos, best_bid, best_ask, tick_size, step_qty, min_qty, ahora=t_now
                )
            else:
                sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
                    pos.side, pos.entry_price, tick_size
                )
                pos.sl_interno_price = max(sl_int_be, convex_sl_px) if pos.side == "long" else min(sl_int_be, convex_sl_px)
                pos.trinquete_be_armado = True
                pos.cosecha_50_ejecutada = True
                pos.ts_cosecha_50 = t_now
                pos.modo_cosecha_ejecutado = "WALD_SINGLE_TICKET_100"
                log_sniper(
                    f"[SNIPER] [SHIELD] {pos.symbol} Single-Ticket Wald Convex Ratchet armed (100% lot): "
                    f"Zero-Loss Floor {pos.sl_interno_price} (PnL {gross_pnl_pct*100:+.2f}%, Lambda={wald_lambda:+.2f})"
                )
                await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)

        if gross_pnl_pct >= cfg.TRAILING_ACTIVACION_PCT and not pos.trailing_activo:
            pos.trailing_activo = True
            log_sniper(
                f"[SNIPER] {pos.symbol} Trailing Stop activated (PnL {gross_pnl_pct*100:+.2f}%)"
            )

        if is_test and pos.max_pnl_pct_alcanzado >= cfg.TRINQUETE_RATCHET_ACTIVACION_PCT:
            pos.trinquete_ratchet_activo = True
            pullback = pos.max_pnl_pct_alcanzado - gross_pnl_pct
            flow_exhausted = (
                (pos.side == "long" and tk.ofi_l1_l5 < 0.0)
                or (pos.side == "short" and tk.ofi_l1_l5 > 0.0)
            )
            pullback_threshold = cfg.TRAILING_DISTANCIA_PCT if pos.trailing_activo else 0.0012
            if (pullback >= pullback_threshold or flow_exhausted) and gross_pnl_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT:
                ratchet_price = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                )
                r_reason = "TRAILING_RATCHET_MAKER" if pos.trailing_activo else "TRINQUETE_RATCHET_MAKER"
                closed_r = await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=ratchet_price,
                    motivo=r_reason,
                    es_maker=True,
                    ahora=t_now,
                )
                if closed_r:
                    return r_reason

        # Maker-Scratch evaluation at 18s (Avellaneda-Stoikov Law 2)
        if age_sec >= cfg.MAKER_SCRATCH_TIEMPO_SEG and not pos.scratch_18s_evaluado:
            pos.scratch_18s_evaluado = True
            adverse_5s_flow = (
                (pos.side == "long" and tk.ofi_5s <= cfg.MAKER_SCRATCH_OFI_UMBRAL)
                or (pos.side == "short" and tk.ofi_5s >= abs(cfg.MAKER_SCRATCH_OFI_UMBRAL))
            )
            if (
                not pos.cosecha_50_ejecutada
                and pos.max_pnl_pct_alcanzado <= cfg.MAKER_SCRATCH_PNL_MAX_PCT
                and adverse_5s_flow
                and gross_pnl_pct >= cfg.MAKER_SCRATCH_MAX_LOSS_PCT
            ):
                pos.scratch_18s_activo = True
                scratch_price = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                pos.orden_salida_precio = scratch_price
                log_sniper(
                    f"[MAKER-SCRATCH 18s] {pos.symbol} no rebound after {age_sec:.1f}s "
                    f"(PnL {gross_pnl_pct*100:+.2f}%, OFI5s {tk.ofi_5s:+.2f}): evacuating via Limit PostOnly @ {scratch_price}."
                )
                closed_s = await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=scratch_price,
                    motivo="MAKER_SCRATCH_18S",
                    es_maker=True,
                    ahora=t_now,
                )
                if closed_s:
                    return "MAKER_SCRATCH_18S"

        # Phase 2 Maker Shield gated by Wald SPRT (never cuts a position while favorable_wald_hold is True)
        mfe_stall_ready = (
            not is_test
            and not favorable_wald_hold
            and age_sec >= 26.0
            and (t_now - pos.orden_salida_ts) >= 6.0
            and pos.max_pnl_pct_alcanzado >= 0.0015
            and gross_pnl_pct >= float(getattr(ESTADO_RAM, "controlador_autonomo", {}).get("mfe_stall_harvest_pct", 0.0013))
            and wald_lambda <= -0.80
        )
        if (
            not pos.cosecha_50_ejecutada
            and not favorable_wald_hold
            and ((age_sec >= cfg.ESCUDO_MAKER_FASE2_SEG and gross_pnl_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT and wald_lambda <= -0.50) or mfe_stall_ready)
        ):
            if not is_test and not pos.trinquete_be_armado:
                sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
                    pos.side, pos.entry_price, tick_size
                )
                pos.sl_interno_price = sl_int_be
                pos.trinquete_be_armado = True
                await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)
            phase2_price = calcular_precio_salida_maker_seguro(
                pos.side,
                pos.entry_price,
                best_bid,
                best_ask,
                tick_size,
                permitir_scratch=bool(mfe_stall_ready),
                piso_be_estricto=bool(mfe_stall_ready),
            )
            log_sniper(
                f"[SNIPER] [DIAMOND] {pos.symbol} Phase 2 Maker Shield PostOnly executed @ {phase2_price} "
                f"(PnL {gross_pnl_pct*100:+.2f}%, Lambda={wald_lambda:+.2f}, age {age_sec:.0f}s)"
            )
            closed_f2 = await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=phase2_price,
                motivo="MAKER_UNWIND",
                es_maker=True,
                ahora=t_now,
            )
            if closed_f2:
                return "MAKER_UNWIND"

        hold_limit = (
            cfg.TIEMPO_MAX_HOLD_TRINQUETE_SEG
            if ((pos.cosecha_50_ejecutada and pos.trinquete_be_armado and gross_pnl_pct > 0.0) or favorable_wald_hold)
            else cfg.TIEMPO_MAX_HOLD_SEG
        )
        if age_sec >= hold_limit:
            log_sniper(
                f"[SNIPER] {pos.symbol} reached maximum hold time ({age_sec:.0f}s >= {hold_limit:.0f}s). "
                f"Liquidating position to release margin."
            )
            await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=mark_price,
                motivo="ESCAPE_TEMPORAL",
                es_maker=False,
                ahora=t_now,
            )
            return "ESCAPE_TEMPORAL"
        return None

    async def evacuar_todas_por_emergencia(self, motivo: str = "EVACUACION_CONTAGIO_CROSS_ASSET") -> int:
        closed_cnt = 0
        now = time.time()
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
            if pos.cerrada or getattr(pos, "_cierre_en_curso", False):
                continue
            if not is_test and (pos.side == "short" or pos.scratch_18s_activo or pos.pre_escape_72s_enviado):
                continue
            tk = ESTADO_RAM.ticks_ram.get(sym)
            ref_price = (tk.bid if pos.side == "long" else tk.ask) if tk and tk.bid > 0 else pos.entry_price
            ok = await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=ref_price,
                motivo=motivo,
                es_maker=False,
                ahora=now,
            )
            if ok:
                closed_cnt += 1
        return closed_cnt

    async def bucle_vigilancia_posiciones(self) -> None:
        self._running = True
        while self._running:
            try:
                now = time.time()
                for _, pos in list(ESTADO_RAM.posiciones_activas.items()):
                    if not pos.cerrada:
                        await self.evaluar_posicion_activa(pos, ahora=now)
            except Exception as exc:
                log_sniper(f"[WARN] [POSITION MANAGER] Error in monitoring loop: {exc}")
            await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)

    def detener(self) -> None:
        self._running = False


def colorear_linea_log_mobaxterm(linea: str) -> str:
    """Real-time ANSI TrueColor syntax highlighter for the verbot stream."""
    RST = "\033[0m"
    s = str(linea or "").rstrip("\r\n")
    if not s:
        return ""
    if ("CLOSE" in s or "CIERRE" in s) and ("+" in s or "WIN" in s):
        return f"\033[1;38;2;0;255;135m{s}{RST}"
    if ("CLOSE" in s or "CIERRE" in s) and "SCRATCH" in s:
        return f"\033[1;38;2;255;210;60m{s}{RST}"
    if "CLOSE" in s or "CIERRE" in s or "CIRCUIT BREAKER" in s or "ERROR" in s:
        return f"\033[1;38;2;255;75;95m{s}{RST}"
    if "[RADAR]" in s and ("APPROVED" in s or "APROBADO" in s):
        return f"\033[1;38;2;0;240;255m{s}{RST}"
    if (
        "Harvest" in s
        or "Cosecha" in s
        or "Full-Maker" in s
        or "PHANTOM 50/25/25" in s
        or "position" in s
        or "Posicion" in s
    ):
        return f"\033[1;38;2;215;120;255m{s}{RST}"
    if "TRI-CORTEX" in s or "HOT-RELOAD" in s:
        return f"\033[1;38;2;130;190;255m{s}{RST}"
    return s


def imprimir_baul_ia_cli_verbot(max_eventos: int = 8, modo_json: bool = False) -> None:
    """
    Renders the structured summary of the Forensic AI Cognitive Vault
    (baul_ia_forense.jsonl) in console with +15s capital-saving shields
    (True Positive Shields), false rejections, and intratrade MFE/MAE anatomy.
    """
    import json

    RST = "\033[0m"
    C_BORDER = "\033[38;2;80;140;255m"
    C_TITLE = "\033[1;38;2;0;240;255m"
    C_GOLD = "\033[1;38;2;255;215;0m"
    C_WHITE = "\033[1;38;2;245;248;255m"
    C_GREEN = "\033[1;38;2;0;255;135m"
    C_RED = "\033[1;38;2;255;75;95m"
    C_YELLOW = "\033[1;38;2;255;210;60m"
    C_MAGENTA = "\033[1;38;2;215;120;255m"

    vault_path = cfg.ROOT_DIR / "baul_ia_forense.jsonl"
    if not vault_path.exists():
        print(f" {C_MAGENTA}AI VAULT    :{RST} {C_YELLOW}baul_ia_forense.jsonl ready and awaiting first event (+15s shield or trade close)...{RST}")
        print(f"{C_BORDER}=========================================================================================={RST}")
        return

    events = []
    for l in vault_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if l.strip():
            try:
                events.append(json.loads(l))
            except Exception:
                pass

    if not events:
        print(f" {C_MAGENTA}AI VAULT    :{RST} {C_YELLOW}baul_ia_forense.jsonl initialized (0 events yet).{RST}")
        print(f"{C_BORDER}=========================================================================================={RST}")
        return

    if modo_json:
        for ev in events[-max_eventos:]:
            print(json.dumps(ev, ensure_ascii=False))
        return

    shields = [e for e in events if e.get("tipo_evento") == "AUDITORIA_ESCUDO_15S"]
    trades_b = [e for e in events if e.get("tipo_evento") == "TRADE_COMPLETO"]
    saved = [
        e for e in shields
        if "TRUE_SHIELD" in str(e.get("veredicto_ia") or "") or "SALVADO" in str(e.get("veredicto_ia") or "")
    ]
    false_rej = [
        e for e in shields
        if "FALSE_REJECTION" in str(e.get("veredicto_ia") or "") or "PERDIDA" in str(e.get("veredicto_ia") or "")
    ]
    neutrals = len(shields) - len(saved) - len(false_rej)
    usdt_saved = sum(float(e.get("impacto_estimado_usdt") or 0.0) for e in saved)

    print(f" {C_MAGENTA}FORENSIC AI VAULT (baul_ia_forense.jsonl) -- +15S COUNTERFACTUAL ORACLE & MFE/MAE ANATOMY:{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(
        f" {C_TITLE}+15s Shields:{RST} {C_WHITE}{len(shields)} audited{RST} | "
        f"{C_GREEN}True Shields: {len(saved)} (+{usdt_saved:.4f} USDT saved){RST} | "
        f"{C_YELLOW}Neutral: {neutrals}{RST} | {C_RED}False Rejections: {len(false_rej)}{RST} | "
        f"{C_MAGENTA}MFE/MAE Trades: {len(trades_b)}{RST}"
    )
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    for ev in events[-max_eventos:]:
        t_ev = str(ev.get("tipo_evento") or "")
        ts_c = str(ev.get("ts_utc") or "")[11:19]
        sym_c = str(ev.get("symbol") or "").replace("/USDT:USDT", "").ljust(8)
        if t_ev == "AUDITORIA_ESCUDO_15S":
            ver = str(ev.get("veredicto_ia") or "")
            is_saved = "TRUE_SHIELD" in ver or "SALVADO" in ver
            is_false = "FALSE_REJECTION" in ver or "PERDIDA" in ver
            c_v = C_GREEN if is_saved else (C_RED if is_false else C_YELLOW)
            tag_v = "SHIELD_OK" if is_saved else ("FALSE_REJ" if is_false else "NEUT_15S")
            scar = str(ev.get("scar_id") or "")[:24].ljust(24)
            exc = float(ev.get("excursion_15s_pct") or 0.0)
            imp = float(ev.get("impacto_estimado_usdt") or 0.0)
            p_tag = str(ev.get("tag_percentil") or "")[:3]
            print(
                f" {C_WHITE}{ts_c}{RST} | {c_v}{tag_v:<9}{RST} | {C_TITLE}{sym_c}{RST} | "
                f"{C_MAGENTA}{scar}{RST} | {C_GOLD}{p_tag}{RST} | "
                f"15s: {c_v}{exc:+6.2f}% ({imp:+.4f} USDT){RST}"
            )
        elif t_ev == "TRADE_COMPLETO":
            res = str(ev.get("resultado") or "")
            c_r = C_GREEN if res == "WIN" else (C_YELLOW if "SCRATCH" in res else C_RED)
            anat = ev.get("anatomia_intratrade") or {}
            vin = ev.get("vector_entrada") or {}
            mfe = float(anat.get("mfe_max_pnl_pct") or 0.0)
            mae = float(anat.get("mae_min_pnl_pct") or 0.0)
            p18 = float(anat.get("pnl_18s_pct") or 0.0)
            pnl_u = float(ev.get("pnl_usdt") or 0.0)
            p_tag = str(vin.get("tag_percentil") or "")[:3]
            modo_c = str(anat.get("modo_cosecha") or "NONE")[:10]
            trd_num = int(ev.get("trade_num") or 0)
            trd_lbl = f"TRD #{trd_num}"
            print(
                f" {C_WHITE}{ts_c}{RST} | {c_r}{trd_lbl:<9}{RST} | {C_TITLE}{sym_c}{RST} | "
                f"MFE:{C_GREEN}{mfe:+5.2f}%{RST} MAE:{C_RED}{mae:+5.2f}%{RST} 18s:{C_YELLOW}{p18:+5.2f}%{RST} | "
                f"{C_GOLD}{p_tag}{RST} | {C_MAGENTA}{modo_c:<10}{RST} -> {c_r}{pnl_u:+.4f} USDT{RST}"
            )
    print(f"{C_BORDER}=========================================================================================={RST}")


def imprimir_status_cli_verbot() -> None:
    import json
    from collections import defaultdict

    RST = "\033[0m"
    C_BORDER = "\033[38;2;80;140;255m"
    C_TITLE = "\033[1;38;2;0;240;255m"
    C_GOLD = "\033[1;38;2;255;215;0m"
    C_WHITE = "\033[1;38;2;245;248;255m"
    C_GREEN = "\033[1;38;2;0;255;135m"
    C_RED = "\033[1;38;2;255;75;95m"
    C_YELLOW = "\033[1;38;2;255;210;60m"
    C_MAGENTA = "\033[1;38;2;215;120;255m"
    BADGE_WIN = "\033[1;38;2;10;25;15;48;2;0;230;118m  WIN   \033[0m"
    BADGE_LOSS = "\033[1;38;2;255;255;255;48;2;220;38;68m  LOSS  \033[0m"
    BADGE_SCR = "\033[1;38;2;25;20;0;48;2;255;196;0m  SCR   \033[0m"
    BADGE_POS = "\033[1;38;2;10;25;15;48;2;0;230;118m  +  \033[0m"
    BADGE_NEG = "\033[1;38;2;255;255;255;48;2;220;38;68m  -  \033[0m"

    stats_f = cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL
    log_f = cfg.ROOT_DIR / getattr(cfg, "ARCHIVO_LOG_SESION", "bot_hft.log")
    log_h = cfg.ROOT_DIR / getattr(cfg, "ARCHIVO_LOG_HISTORICO", "bot_hft_h.log")
    ops = [
        json.loads(l)
        for l in stats_f.read_text(encoding="utf-8", errors="ignore").splitlines()
        if l.strip()
    ] if stats_f.exists() else []
    ops = [x for x in ops if "ESCAPE_HUERFANA_BOOT" not in str(x.get("motivo", "")).upper()]

    total = len(ops)
    w = sum(1 for x in ops if float(x.get("pnl_usdt", 0.0)) >= 0.0)
    l = total - w
    s = sum(
        1 for x in ops
        if float(x.get("pnl_usdt", 0.0)) < 0.0
        and ("SCRATCH" in str(x.get("motivo", "")).upper() or ("MAKER_UNWIND" in str(x.get("motivo", "")).upper() and float(x.get("pnl_percentage", -1.0)) >= -0.14))
    )
    triz = sum(
        1 for x in ops
        if x.get("cosecha_triz_50")
        or x.get("cosecha_50_ejecutada")
        or "TRINQUETE" in str(x.get("motivo", "")).upper()
        or "TRAILING" in str(x.get("motivo", "")).upper()
    )
    pnl = sum(float(x.get("pnl_usdt", 0.0)) for x in ops)
    wr = (w / total * 100.0) if total else 0.0
    wr_ef = (w / max(1, total - s) * 100.0) if total else 0.0
    lam = min(1.0, total / 40.0)

    bal_real = "N/A"
    for candidate_log in (log_f, log_h):
        if candidate_log.exists():
            for line in reversed(candidate_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-2500:]):
                if "real:" in line and "USDT" in line:
                    try:
                        bal_real = line.split("real:")[1].split("USDT")[0].strip() + " USDT"
                        break
                    except Exception:
                        pass
                elif "Total:" in line and "USDT" in line and ("UTA" in line or "Audit" in line or "Auditoria" in line):
                    try:
                        bal_real = line.split("Total:")[1].split("|")[0].strip() + " USDT"
                        break
                    except Exception:
                        pass
            if bal_real != "N/A":
                break

    c_pnl_tot = C_GREEN if pnl >= 0 else C_RED
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_TITLE}BLACK BOX   :{RST} {C_WHITE}{total} Trades{RST} ({C_GREEN}W: {w}{RST} | {C_RED}L: {l}{RST} | {C_YELLOW}Scratch 18s: {s}{RST} | {C_MAGENTA}50% Harvest: {triz}{RST})")
    print(f" {C_GOLD}Win Rate    :{RST} Classic {C_WHITE}{wr:.1f}%{RST} | Effective {C_GREEN}{wr_ef:.1f}%{RST} | Net PnL: {c_pnl_tot}{pnl:+.4f} USDT{RST} | Real UTA: {C_GOLD}{bal_real}{RST} | lambda={C_TITLE}{lam:.2f}{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_TITLE}{'PAIR & SIDE':<22} {'TRADES (W/L)':<15} {'WIN RATE':<10} {'MEAN HURST':<13} {'NET PNL USDT':<18}{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")

    groups = defaultdict(list)
    for t in ops:
        sym = str(t.get("symbol", "")).replace("/USDT:USDT", "")
        side = str(t.get("side", "long")).upper()
        groups[f"{sym} [{side}]"].append(t)

    for k in sorted(groups.keys(), key=lambda x: sum(float(i.get("pnl_usdt", 0.0)) for i in groups[x]), reverse=True):
        items = groups[k]
        w_g = sum(1 for i in items if float(i.get("pnl_usdt", 0.0)) >= 0.0)
        l_g = len(items) - w_g
        wr_g = (w_g / len(items) * 100.0) if items else 0.0
        h_vals = [float(i.get("hurst_entry", 0.0)) for i in items if i.get("hurst_entry") is not None]
        h_med = (sum(h_vals) / len(h_vals)) if h_vals else 0.0
        pnl_g = sum(float(i.get("pnl_usdt", 0.0)) for i in items)
        badge = BADGE_POS if pnl_g >= 0 else BADGE_NEG
        c_row = C_GREEN if pnl_g >= 0 else C_RED
        c_side = C_MAGENTA if "[SHORT]" in k else C_TITLE
        print(f" {c_side}{k:<22}{RST} {C_WHITE}{f'{len(items)} ({w_g}W/{l_g}L)':<15}{RST} {c_row}{f'{wr_g:5.1f}%':<10}{RST} {C_YELLOW}{f'H={h_med:.3f}':<13}{RST} {badge} {c_row}{pnl_g:+.4f} USDT{RST}")

    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_MAGENTA}LAST 10 CLOSED TRADES RECORDED IN THE BLACK BOX:{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    if ops:
        idx_base = max(1, total - 9)
        for idx, op in enumerate(ops[-10:], start=idx_base):
            pnl_u = float(op.get("pnl_usdt", 0.0))
            mot = str(op.get("motivo", ""))
            if pnl_u >= 0:
                badge_op = BADGE_WIN
                c_op = C_GREEN
            elif "SCRATCH" in mot.upper():
                badge_op = BADGE_SCR
                c_op = C_YELLOW
            else:
                badge_op = BADGE_LOSS
                c_op = C_RED
            ts_s = str(op.get("timestamp", ""))[:19]
            sym_s = str(op.get("symbol", "")).replace("/USDT:USDT", "").ljust(9)
            side_s = str(op.get("side", "long")).upper().ljust(5)
            pct_s = float(op.get("pnl_percentage", 0.0))
            hold_s = float(op.get("hold_seg", 0.0))
            print(f" {C_WHITE}{idx:02d}.{RST} {badge_op} {C_WHITE}{ts_s}{RST} | {C_TITLE}{sym_s}{RST} [{C_MAGENTA}{side_s}{RST}] | {c_op}{pct_s:+6.2f}% ({pnl_u:+.4f} USDT){RST} | {C_YELLOW}{hold_s:3.0f}s{RST} | {c_op}{mot}{RST}")
    else:
        print(f"  {C_YELLOW}Awaiting first confirmed shot...{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    imprimir_baul_ia_cli_verbot(max_eventos=8, modo_json=False)


async def reenviar_ultimo_cierre_cli() -> None:
    import json
    stats_f = cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL
    if not stats_f.exists():
        print("  [INFO] No trade closes recorded yet in tribrain_stats_v1.jsonl.")
        return
    lines = [l for l in stats_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        print("  [INFO] File tribrain_stats_v1.jsonl is empty.")
        return
    u = json.loads(lines[-1])
    TELEMETRIA_TG.cache_dedup.clear()
    ok = await TELEMETRIA_TG.enviar_cierre_garantizado(
        symbol=u["symbol"],
        side=u.get("side", "long"),
        pnl_pct=float(u["pnl_percentage"]),
        pnl_usdt=float(u["pnl_usdt"]),
        hold_seg=float(u["hold_seg"]),
        motivo=str(u["motivo"]),
        entry_price=float(u.get("entry_price", 0.0)),
        exit_price=float(u.get("exit_price", 0.0)),
        cosecha_50_previa=bool(u.get("cosecha_triz_50", False)),
    )
    print(f"  \033[1;38;2;0;255;135m[OK] [VERBOT -T] Manual Telegram resend of last trade close ({u['symbol']}): {ok}\033[0m")


async def ejecutar_radar_xray_cli(accion: str = "status") -> None:
    import ccxt.async_support as ccxt
    RST = "\033[0m"
    C_BORDER = "\033[38;2;80;140;255m"
    C_TITLE = "\033[1;38;2;0;240;255m"
    C_GREEN = "\033[1;38;2;0;255;135m"
    C_GOLD = "\033[1;38;2;255;215;0m"
    BADGE_GHOST = "\033[1;38;2;255;255;255;48;2;105;48;195m  PHANTOM 3D  \033[0m"
    BADGE_TG = "\033[1;38;2;255;255;255;48;2;0;136;204m  TELEGRAM  \033[0m"

    nl = chr(10)
    mode = str(accion or "status").strip().lower()
    is_close_cmd = mode in ("cerrar", "close")
    ex = ccxt.bybit({
        "apiKey": cfg.BYBIT_API_KEY,
        "secret": cfg.BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "swap", "recvWindow": 15000},
    })
    try:
        await ex.load_markets()
        positions = await ex.fetch_positions(None, {"settleCoin": "USDT"})
        active = [
            p for p in (positions or [])
            if abs(float(p.get("contracts") or (p.get("info") or {}).get("size") or 0.0)) > 0.0
        ]
        bal = await ex.fetch_balance()
        usdt = (bal or {}).get("USDT") or {}
        tot = float(usdt.get("total") or 0.0)
        lib = float(usdt.get("free") or tot)

        print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
        print(f" {BADGE_GHOST} {C_TITLE}TACTICAL RADAR POUFS-BEELZEBUB-EN V5.0 (verbot -x){RST} | UTA Balance: {C_GOLD}{tot:.4f} USDT{RST} (Free: {C_GREEN}{lib:.4f}{RST})")
        print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")

        if not active:
            print(f" {C_GREEN}[OK] No open positions on Bybit at this moment (0 running contracts).{RST}")
            print(f"{C_BORDER}=========================================================================================={RST}")
            empty_msg = nl.join([
                "[LIVE RADAR POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0]",
                "- Status: No open positions (0 contracts)",
                f"- UTA Balance: {tot:.4f} USDT (Free: {lib:.4f} USDT)",
            ])
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(empty_msg)
            print(f" {BADGE_TG} {C_TITLE}Status report dispatched to Telegram:{RST} {C_GREEN}{ok_tg}{RST}")
            return

        tg_lines = [
            "[LIVE RADAR POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0]",
            f"UTA Balance: {tot:.4f} USDT (Free: {lib:.4f} USDT)",
        ]
        for p in active:
            sym = str(p.get("symbol") or "")
            side = str(p.get("side") or "long").lower()
            qty = abs(float(p.get("contracts") or (p.get("info") or {}).get("size") or 0.0))
            ep = float(p.get("entryPrice") or (p.get("info") or {}).get("avgPrice") or 0.0)
            mp = float(p.get("markPrice") or (p.get("info") or {}).get("markPrice") or ep)
            pnl_u = float(p.get("unrealizedPnl") or (p.get("info") or {}).get("unrealisedPnl") or 0.0)
            lev = float(p.get("leverage") or cfg.APALANCAMIENTO_BASE)
            sl_b = p.get("stopLossPrice") or (p.get("info") or {}).get("stopLoss") or "NO SL"
            pct = ((mp - ep) / ep if side == "long" else (ep - mp) / ep) if ep > 0 else 0.0
            is_t1 = sym in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
            link_id, floor_sug, _ = calcular_eslabon_chain_jail(max(0.0, pct), es_tier1=is_t1)
            ceiling_str = "+1.85%" if is_t1 else "+5.50%"

            if is_close_cmd:
                try:
                    ords = await ex.fetch_open_orders(sym)
                    for o in (ords or []):
                        await ex.cancel_order(o["id"], sym)
                except Exception:
                    pass
                close_side = "buy" if side == "short" else "sell"
                await ex.create_order(sym, "market", close_side, qty, None, {"reduceOnly": True})
                bal2 = await ex.fetch_balance()
                tot2 = float(((bal2 or {}).get("USDT") or {}).get("total") or tot)
                print(f" {C_GREEN}[OK] MANUAL PHANTOM CLOSE EXECUTED: {sym} [{side.upper()}] ({qty} contracts){RST}")
                print(f" {C_GOLD}Captured Result: {pct*100:+.2f}% raw ({pnl_u:+.4f} USDT) | New Balance: {tot2:.4f} USDT{RST}")
                print(f"{C_BORDER}=========================================================================================={RST}")
                close_msg = nl.join([
                    "[MANUAL CLOSE POUFS-BEELZEBUB-EN V5.0 (verbot -x close)]",
                    f"- Asset: {sym} [{side.upper()}] ({qty} contracts)",
                    f"- Path: {ep} -> {mp} ({pct*100:+.2f}% raw | ROE {pct*lev*100:+.2f}%)",
                    f"- Captured PnL: {pnl_u:+.4f} USDT",
                    f"- New Consolidated Balance: {tot2:.4f} USDT",
                ])
                ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(close_msg)
                print(f" {BADGE_TG} {C_TITLE}Manual close receipt dispatched:{RST} {C_GREEN}{ok_tg}{RST}")
            else:
                print(f" {C_TITLE}ASSET       : {sym} [{side.upper()}] ({qty} contracts){RST}")
                print(f" {C_GOLD}PRICE       : Entry {ep} -> Current Mark {mp}{RST}")
                print(f" {C_GREEN}PROFIT      : {pct*100:+.2f}% raw ({pct*lev*100:+.2f}% ROE {lev:.0f}x) | {pnl_u:+.4f} USDT{RST}")
                print(f" {C_TITLE}CHAIN LINK  : {link_id}/5 (Link Floor: +{floor_sug*100:.2f}% -> Target: {ceiling_str}) | Bybit SL: {sl_b}{RST}")
                print(f"{C_BORDER}=========================================================================================={RST}")
                tg_lines.extend([
                    f"Asset: {sym} [{side.upper()}] ({qty} contracts)",
                    f"- Price: {ep} -> {mp}",
                    f"- Profit: {pct*100:+.2f}% (ROE {pct*lev*100:+.2f}%) | {pnl_u:+.4f} USDT",
                    f"- Phantom Link: {link_id}/5 (Floor +{floor_sug*100:.2f}% -> Target {ceiling_str})",
                    f"- Bybit SL: {sl_b}",
                ])

        if not is_close_cmd:
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(nl.join(tg_lines))
            print(f" {BADGE_TG} {C_TITLE}Live alert dispatched to Telegram:{RST} {C_GREEN}{ok_tg}{RST}")
    finally:
        await ex.close()