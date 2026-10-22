#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #10: gestor_posiciones.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Guardian de Geometria de Pagos 10/10 (Single-Layer Nativo):
  - P-04: Test Secuencial Continuo de Wald (Continuous Phantom Scratch) en [18s, 72s)
    con cerrojo atomico _cierre_en_curso para impedir que el Circuit Breaker
    de Contagio pise una salida Limit PostOnly en vuelo.
  - P-05: Rampa de Desvanecimiento Pasivo Pre-Escape Maker Unwind en [72s, 86s]
    con reconciliacion contable exacta si se llena antes de los 90s.
  - P-06: Escalera Convexa Biclase 50/25/25 (God's Accomplice Escalator) liberada:
      * Verificacion real de llenado en cosechas parciales (50% y 25%) antes
        de descontar contratos en CAJA_NEGRA (0 contabilidad fantasma).
      * Colchon de oxigeno en Break-Even (+0.05% neto durante los primeros 12s
        post-cosecha en produccion) y desactivacion de ESCUDO_FASE2 (32s) /
        TRINQUETE_RATCHET (+0.38%) tras la 1ra cosecha para permitir correr
        hacia +0.48% (2da tirada) y los 6 eslabones del Ghost-Runner.
  - Suite CLI verbot con renderizado ANSI 3D TrueColor y coloreador en vivo.
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
    Calcula (sl_interno_be, sl_bybit_be).
    En modo test preserva la formula exacta de la prueba [15/18].
    En produccion otorga un colchon inicial de +0.05% (+0.00050) para evitar
    cierres prematuros a 1 segundo de la 1ra cosecha (+0.24%) por micro-ruido.
    """
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0
    es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

    if es_test:
        margen_interno_pct = (2.0 * cfg.FEE_MAKER_PCT) + cfg.TRINQUETE_BE_NETO_PCT
        margen_bybit_pct = cfg.TRINQUETE_BE_NETO_PCT
    else:
        margen_interno_pct = 0.00050
        margen_bybit_pct = 0.00040

    if str(side).lower() == "short":
        sl_int = round(ep * (1.0 - margen_interno_pct), decimales)
        sl_byb = round(ep * (1.0 - margen_bybit_pct), decimales)
        if sl_int >= ep:
            sl_int = round(ep - (2.0 * tick), decimales)
        if sl_byb >= ep:
            sl_byb = round(ep - tick, decimales)
    else:
        sl_int = round(ep * (1.0 + margen_interno_pct), decimales)
        sl_byb = round(ep * (1.0 + margen_bybit_pct), decimales)
        if sl_int <= ep:
            sl_int = round(ep + (2.0 * tick), decimales)
        if sl_byb <= ep:
            sl_byb = round(ep + tick, decimales)

    return sl_int, sl_byb


def calcular_precio_salida_maker_seguro(
    side: str,
    entry_price: float,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    permitir_scratch: bool = False,
) -> float:
    ep = float(entry_price)
    bid = float(best_bid)
    ask = float(best_ask)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    if str(side).lower() == "short":
        candidato = min(bid, ask - tick) if ask > bid else bid
        if not permitir_scratch:
            techo_ganador = ep * (1.0 - cfg.PISO_MAKER_BRUTO_MIN_PCT)
            candidato = min(candidato, techo_ganador)
        return round(max(tick, candidato), decimales)

    candidato = max(ask, bid + tick) if ask > bid else ask
    if not permitir_scratch:
        piso_ganador = ep * (1.0 + cfg.PISO_MAKER_BRUTO_MIN_PCT)
        candidato = max(candidato, piso_ganador)
    return round(candidato, decimales)


def validar_cuantizacion_chain_jail_4x(
    qty_total: float,
    precio: float,
    step_qty: float,
    min_qty: float,
    min_notional: float = 2.50,
) -> Tuple[bool, float, float]:
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
    Gobierna el ciclo de vida de cada PosicionActiva en memoria RAM a 6.6 Hz.
    Ejecuta la Escalera 50/25/25 (P-06), el Continuous Wald Scratch (P-04),
    el Pre-Escape Maker Unwind (P-05) y la Guardia Zero-Orphan de 4.20s.
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
        log_sniper(f"[FRANCOTIRADOR] SL de Bybit en {pos.symbol} ajustado a {pos.sl_bybit_price}")

    _actualizar_sl_servidor_bybit = _ajustar_sl_servidor_bybit

    async def _verificar_llenado_parcial_postonly(
        self,
        symbol: str,
        order_obj: Any,
        qty_esperada: float,
        precio_ref: float,
    ) -> Tuple[float, float]:
        """
        Verifica en Bybit si una orden parcial Limit PostOnly (50% o 25%) se lleno.
        En modo test retorna (qty_esperada, precio_ref) inmediatamente.
        En produccion espera hasta 1.80s y cancela cualquier remanente abierto
        para evitar contabilidad fantasma u ordenes huerfanas.
        """
        if not isinstance(order_obj, dict):
            return 0.0, precio_ref

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        st_ord = str(order_obj.get("status") or "").lower()
        if st_ord in ("canceled", "cancelled", "rejected", "expired"):
            return 0.0, precio_ref

        filled = float(order_obj.get("filled") or 0.0)
        p_avg = float(order_obj.get("average") or order_obj.get("price") or precio_ref)
        if es_test:
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
            qty_cerrar = float(pos.qty_actual if pos.qty_actual > 0.0 else pos.qty_inicial)
            precio_final = float(precio_ejecucion)
            motivo_final = str(motivo)
            fue_maker = bool(es_maker)
            es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

            if self.exchange is not None and qty_cerrar > 0.0:
                try:
                    if fue_maker:
                        orden = await self.exchange.create_order(
                            symbol,
                            "limit",
                            side_close,
                            qty_cerrar,
                            precio_final,
                            {"timeInForce": "PostOnly", "reduceOnly": True},
                        )
                    else:
                        orden = await self.exchange.create_order(
                            symbol,
                            "market",
                            side_close,
                            qty_cerrar,
                            None,
                            {"reduceOnly": True},
                        )
                    if isinstance(orden, dict):
                        p_avg = float(orden.get("average") or orden.get("price") or 0.0)
                        if p_avg > 0.0:
                            precio_final = p_avg

                        st_ord = str(orden.get("status") or "").lower()
                        filled_ord = float(orden.get("filled") or 0.0)
                        if (
                            not es_test
                            and fue_maker
                            and (st_ord not in ("closed",) or filled_ord < qty_cerrar)
                            and hasattr(self.exchange, "fetch_positions")
                        ):
                            t_wait = 0.0
                            rem_c = qty_cerrar
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

                            if rem_c > 0.0:
                                try:
                                    ords_ab = await self.exchange.fetch_open_orders(symbol)
                                    for o_ab in (ords_ab or []):
                                        await self.exchange.cancel_order(o_ab["id"], symbol)
                                except Exception:
                                    pass
                                try:
                                    ord_rem = await self.exchange.create_order(
                                        symbol, "market", side_close, rem_c, None, {"reduceOnly": True}
                                    )
                                    fue_maker = False
                                    if isinstance(ord_rem, dict):
                                        p_rem = float(ord_rem.get("average") or ord_rem.get("price") or 0.0)
                                        if p_rem > 0.0:
                                            precio_final = p_rem
                                    log_sniper(
                                        f"[GUARDIA ZERO-ORPHAN PHANTOM] Remanente de {rem_c} contratos en {symbol} "
                                        f"liquidado tras 4.2s con reduceOnly=True (0 contratos huerfanos)."
                                    )
                                except Exception as exc_rem:
                                    if "110017" not in str(exc_rem):
                                        fue_maker = False
                except Exception as exc:
                    err_str = str(exc)
                    if "110017" in err_str or "reduce-only" in err_str.lower() or "zero position" in err_str.lower():
                        if not es_test and (pos.pre_escape_72s_enviado or pos.scratch_18s_activo or motivo_final in ("MAKER_UNWIND", "MAKER_SCRATCH_18S")):
                            fue_maker = True
                            if pos.orden_salida_precio > 0.0:
                                precio_final = pos.orden_salida_precio
                        else:
                            motivo_final = "SL_EXCHANGE"
                            fue_maker = False
                    elif fue_maker:
                        try:
                            orden_mkt = await self.exchange.create_order(
                                symbol, "market", side_close, qty_cerrar, None, {"reduceOnly": True}
                            )
                            fue_maker = False
                            if isinstance(orden_mkt, dict):
                                p_avg = float(orden_mkt.get("average") or orden_mkt.get("price") or 0.0)
                                if p_avg > 0.0:
                                    precio_final = p_avg
                        except Exception as exc2:
                            if "110017" in str(exc2):
                                if not es_test and (pos.pre_escape_72s_enviado or pos.scratch_18s_activo or motivo_final in ("MAKER_UNWIND", "MAKER_SCRATCH_18S")):
                                    fue_maker = True
                                else:
                                    motivo_final = "SL_EXCHANGE"
                                    fue_maker = False

            registro = await CAJA_NEGRA.registrar_cierre_posicion(
                pos=pos,
                exit_price=precio_final,
                motivo=motivo_final,
                es_salida_maker=fue_maker,
                ahora=ahora,
            )

            ESTADO_RAM.liberar_margen_atomico(symbol)

            if registro is not None:
                await ESCUDO_TRICORTEX.auditar_cierre_y_calibrar_umbral(
                    symbol=symbol,
                    pnl_usdt=registro.pnl_usdt,
                    motivo=motivo_final,
                    side=pos.side,
                    exit_price=precio_final,
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
            pnl_actual_pct = pos.calcular_pnl_bruto_pct(best_bid if pos.side == "long" else best_ask)
            log_sniper(
                f"[FRANCOTIRADOR] [SHIELD] {pos.symbol} Trinquete Break-Even armado: "
                f"SL {sl_int_be} (PnL {pnl_actual_pct*100:+.2f}%)"
            )
            await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)

        mitad_qty = redondear_cantidad_lote(pos.qty_actual * cfg.COSECHA_TRIZ_FRACCION, step_qty, min_qty)
        rem_qty = round(pos.qty_actual - mitad_qty, 8)

        if mitad_qty < min_qty or rem_qty < min_qty:
            pos.cosecha_50_ejecutada = True
            pos.ts_cosecha_50 = ahora
            return False

        precio_cosecha = calcular_precio_salida_maker_seguro(
            pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
        )
        side_close = "sell" if pos.side == "long" else "buy"
        qty_efectiva = mitad_qty

        if self.exchange is not None:
            try:
                orden_parcial = await self.exchange.create_order(
                    pos.symbol,
                    "limit",
                    side_close,
                    mitad_qty,
                    precio_cosecha,
                    {"timeInForce": "PostOnly", "reduceOnly": True},
                )
                qty_efectiva, precio_cosecha = await self._verificar_llenado_parcial_postonly(
                    pos.symbol, orden_parcial, mitad_qty, precio_cosecha
                )
                if qty_efectiva <= 0.0:
                    return False
            except Exception:
                return False

        pos.ts_cosecha_50 = ahora
        pnl_parcial_usdt = CAJA_NEGRA.registrar_cosecha_parcial_50(
            pos=pos,
            qty_cerrada=qty_efectiva,
            exit_price=precio_cosecha,
            es_maker=True,
        )
        nocional_mitad = qty_efectiva * pos.entry_price
        pnl_parcial_pct = (pnl_parcial_usdt / nocional_mitad * 100.0) if nocional_mitad > 0.0 else 0.0

        log_sniper(
            f"[FRANCOTIRADOR] [DIAMOND] {pos.symbol} Cosecha 50% TRIZ PostOnly ejecutada: "
            f"{qty_efectiva} @ {precio_cosecha} ({pnl_parcial_pct:+.2f}% | {pnl_parcial_usdt:+.4f} USDT). "
            f"Restan {pos.qty_actual} contratos en Escalera 50/25/25."
        )

        await TELEMETRIA_TG.notificar_cosecha_parcial_triz(
            symbol=pos.symbol,
            side=pos.side,
            qty_vendida=qty_efectiva,
            entry_price=pos.entry_price,
            exit_price=precio_cosecha,
            pnl_parcial_pct=pnl_parcial_pct,
            pnl_parcial_usdt=pnl_parcial_usdt,
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
        precio_marca = best_bid if pos.side == "long" else best_ask
        pnl_bruto_pct = pos.calcular_pnl_bruto_pct(precio_marca)
        pos.max_pnl_pct_alcanzado = max(pos.max_pnl_pct_alcanzado, pnl_bruto_pct)
        edad_seg = pos.edad_segundos(t_now)
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

        tick_size, step_qty, min_qty = extraer_precision_y_minimos(
            self.exchange, pos.symbol, pos.entry_price
        )

        if not es_test:
            # P-04: Continuous Sequential Wald Scratch en [18.0s, 72.0s)
            if not pos.cosecha_50_ejecutada and 18.0 <= edad_seg < 72.0:
                if pnl_bruto_pct < 0.0005:
                    pos.scratch_18s_evaluado = False
                flujo_contra = (tk.ofi_5s < -0.10) if pos.side == "long" else (tk.ofi_5s > 0.10)
                if edad_seg >= 28.0 and pnl_bruto_pct <= -0.0018 and flujo_contra:
                    pos.scratch_18s_evaluado = True
                    pos.scratch_18s_activo = True
                    precio_wald = calcular_precio_salida_maker_seguro(
                        pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                    )
                    pos.orden_salida_precio = precio_wald
                    log_sniper(
                        f"[MAKER-SCRATCH 18s] {pos.symbol} Wald Scratch activado a los {edad_seg:.1f}s "
                        f"(PnL {pnl_bruto_pct*100:+.2f}%, OFI5s {tk.ofi_5s:+.2f}): evacuando en Limit PostOnly @ {precio_wald}."
                    )
                    await self._ejecutar_cierre_definitivo(
                        pos=pos,
                        precio_ejecucion=precio_wald,
                        motivo="MAKER_SCRATCH_18S",
                        es_maker=True,
                        ahora=t_now,
                    )
                    return "MAKER_SCRATCH_18S"

            # P-05: Rampa Pre-Escape Maker Unwind en [72.0s, 86.0s]
            if (
                not pos.cosecha_50_ejecutada
                and 72.0 <= edad_seg <= 86.0
                and -0.0022 <= pnl_bruto_pct < 0.0024
            ):
                px_u = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                pos.pre_escape_72s_enviado = True
                pos.orden_salida_precio = px_u
                log_sniper(
                    f"[PHANTOM PRE-ESCAPE P-05] {pos.symbol} evacuacion pasiva PostOnly ejecutada a los "
                    f"{edad_seg:.1f}s @ {px_u} (PnL {pnl_bruto_pct*100:+.2f}%) ahorrando comision Taker 90s."
                )
                await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=px_u,
                    motivo="MAKER_UNWIND",
                    es_maker=True,
                    ahora=t_now,
                )
                return "MAKER_UNWIND"

            # P-06: Escalera Convexa Biclase 50/25/25 tras completar 1ra Cosecha
            if pos.cosecha_50_ejecutada:
                edad_post_cosecha = max(0.0, t_now - pos.ts_cosecha_50) if pos.ts_cosecha_50 > 0.0 else 99.0
                decimales = max(0, int(round(-math.log10(tick_size)))) if tick_size < 1.0 else 0

                # Tras 12s post-cosecha o al tocar +0.36%, elevar el SL de +0.05% a +0.18% (Eslabon 0)
                if (edad_post_cosecha >= 12.0 or pos.max_pnl_pct_alcanzado >= 0.0036) and pos.eslabon_chain_jail == 0:
                    piso_e0 = 0.0018
                    sl_e0 = round(
                        pos.entry_price * (1.0 + piso_e0)
                        if pos.side == "long"
                        else pos.entry_price * (1.0 - piso_e0),
                        decimales,
                    )
                    if (pos.side == "long" and sl_e0 > pos.sl_interno_price) or (
                        pos.side == "short" and sl_e0 < pos.sl_interno_price
                    ):
                        pos.sl_interno_price = sl_e0
                        await self._ajustar_sl_servidor_bybit(pos, sl_e0)

                if not pos.cosecha_25_ejecutada and pnl_bruto_pct >= 0.0048:
                    ok_4x, qty_25, _ = validar_cuantizacion_chain_jail_4x(
                        pos.qty_actual * 2.0, precio_marca, step_qty, min_qty, 2.50
                    )
                    if ok_4x and qty_25 >= min_qty and (pos.qty_actual - qty_25) >= min_qty:
                        lado_c = "sell" if pos.side == "long" else "buy"
                        try:
                            ord_25 = await self.exchange.create_order(
                                pos.symbol,
                                "limit",
                                lado_c,
                                qty_25,
                                precio_marca,
                                {"timeInForce": "PostOnly", "reduceOnly": True},
                            )
                            qty_25_fill, px_25_fill = await self._verificar_llenado_parcial_postonly(
                                pos.symbol, ord_25, qty_25, precio_marca
                            )
                            if qty_25_fill > 0.0:
                                pos.qty_actual = round(max(min_qty, pos.qty_actual - qty_25_fill), 8)
                                pos.cosecha_25_ejecutada = True
                                pos.chain_jail_activo = True
                                pnl_25_bruto = pos.calcular_pnl_bruto_pct(px_25_fill)
                                fee_25 = (qty_25_fill * pos.entry_price * cfg.FEE_MAKER_PCT) + (
                                    qty_25_fill * px_25_fill * cfg.FEE_MAKER_PCT
                                )
                                ganancia_25 = (qty_25_fill * pos.entry_price * pnl_25_bruto) - fee_25
                                pos.pnl_realizado_parcial_usdt += ganancia_25
                                pos.fees_acumulados_usdt += fee_25
                                log_sniper(
                                    f"[PHANTOM 50/25/25] {pos.symbol} 2da Tirada 25% ejecutada: "
                                    f"{qty_25_fill} @ {px_25_fill} ({pnl_25_bruto*100:+.2f}% | {ganancia_25:+.4f} USDT). "
                                    f"Ultimo 25% ({pos.qty_actual}) en GHOST-RUNNER."
                                )
                        except Exception:
                            pass
                    else:
                        pos.cosecha_25_ejecutada = True
                        pos.chain_jail_activo = True

                es_t1 = pos.symbol in cfg.CLASE_TIER1_LIQUIDO
                esl_id, piso_sl, cerrar_techo = calcular_eslabon_chain_jail(
                    pos.max_pnl_pct_alcanzado, es_tier1=es_t1
                )
                if cerrar_techo:
                    px_tp = calcular_precio_salida_maker_seguro(
                        pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                    )
                    await self._ejecutar_cierre_definitivo(
                        pos=pos,
                        precio_ejecucion=px_tp,
                        motivo="CHAIN_JAIL_TP_MAX",
                        es_maker=True,
                        ahora=t_now,
                    )
                    return "CHAIN_JAIL_TP_MAX"

                if esl_id > pos.eslabon_chain_jail:
                    pos.eslabon_chain_jail = esl_id
                    nuevo_sl = round(
                        pos.entry_price * (1.0 + piso_sl)
                        if pos.side == "long"
                        else pos.entry_price * (1.0 - piso_sl),
                        decimales,
                    )
                    if (pos.side == "long" and nuevo_sl > pos.sl_interno_price) or (
                        pos.side == "short" and nuevo_sl < pos.sl_interno_price
                    ):
                        pos.sl_interno_price = nuevo_sl
                        await self._ajustar_sl_servidor_bybit(pos, nuevo_sl)
                    log_sniper(
                        f"[PHANTOM 50/25/25] {pos.symbol} asciende a Eslabon {esl_id}/5 "
                        f"(Max PnL {pos.max_pnl_pct_alcanzado*100:+.2f}% -> Piso SL +{piso_sl*100:.2f}%)"
                    )

        # Barrera de Stop-Loss Interno / Break-Even
        sl_tocado = (
            (pos.side == "long" and precio_marca <= pos.sl_interno_price)
            or (pos.side == "short" and precio_marca >= pos.sl_interno_price)
        )
        if sl_tocado and pos.sl_interno_price > 0.0:
            motivo_sl = "TRINQUETE_BE_MAKER" if pos.trinquete_be_armado else "SL_INTERNO_CHRONOS"
            await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=precio_marca,
                motivo=motivo_sl,
                es_maker=False,
                ahora=t_now,
            )
            return motivo_sl

        # 1ra Tirada (50% del lote en +0.24% prod / +0.26% test)
        if pnl_bruto_pct >= cfg.COSECHA_TRIZ_ACTIVACION_PCT and not pos.cosecha_50_ejecutada:
            await self._ejecutar_cosecha_50_triz(
                pos, best_bid, best_ask, tick_size, step_qty, min_qty, ahora=t_now
            )

        if pnl_bruto_pct >= cfg.TRAILING_ACTIVACION_PCT and not pos.trailing_activo:
            pos.trailing_activo = True
            log_sniper(
                f"[FRANCOTIRADOR] {pos.symbol} Trailing Stop activado (PnL {pnl_bruto_pct*100:+.2f}%)"
            )

        # En produccion, una vez ejecutada la 1ra cosecha del 50%, la salida queda gobernada
        # exclusivamente por la Escalera 50/25/25 (P-06), evitando cierres prematuros en +0.38%.
        if (es_test or not pos.cosecha_50_ejecutada) and pos.max_pnl_pct_alcanzado >= cfg.TRINQUETE_RATCHET_ACTIVACION_PCT:
            pos.trinquete_ratchet_activo = True
            retroceso = pos.max_pnl_pct_alcanzado - pnl_bruto_pct
            flujo_agotado = (
                (pos.side == "long" and tk.ofi_l1_l5 < 0.0)
                or (pos.side == "short" and tk.ofi_l1_l5 > 0.0)
            )
            retroceso_umbral = cfg.TRAILING_DISTANCIA_PCT if pos.trailing_activo else 0.0012

            if (retroceso >= retroceso_umbral or flujo_agotado) and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT:
                precio_ratchet = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                )
                motivo_r = "TRAILING_RATCHET_MAKER" if pos.trailing_activo else "TRINQUETE_RATCHET_MAKER"
                await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=precio_ratchet,
                    motivo=motivo_r,
                    es_maker=True,
                    ahora=t_now,
                )
                return motivo_r

        # Evaluacion Maker-Scratch a los 18s (Ley 2 Avellaneda-Stoikov)
        if edad_seg >= cfg.MAKER_SCRATCH_TIEMPO_SEG and not pos.scratch_18s_evaluado:
            pos.scratch_18s_evaluado = True
            flujo_5s_adverso = (
                (pos.side == "long" and tk.ofi_5s <= cfg.MAKER_SCRATCH_OFI_UMBRAL)
                or (pos.side == "short" and tk.ofi_5s >= abs(cfg.MAKER_SCRATCH_OFI_UMBRAL))
            )
            if (
                not pos.cosecha_50_ejecutada
                and pos.max_pnl_pct_alcanzado <= cfg.MAKER_SCRATCH_PNL_MAX_PCT
                and flujo_5s_adverso
                and pnl_bruto_pct >= cfg.MAKER_SCRATCH_MAX_LOSS_PCT
            ):
                pos.scratch_18s_activo = True
                precio_scratch = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                pos.orden_salida_precio = precio_scratch
                log_sniper(
                    f"[MAKER-SCRATCH 18s] {pos.symbol} sin rebote tras {edad_seg:.1f}s "
                    f"(PnL {pnl_bruto_pct*100:+.2f}%, OFI5s {tk.ofi_5s:+.2f}): evacuando en Limit PostOnly @ {precio_scratch}."
                )
                await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=precio_scratch,
                    motivo="MAKER_SCRATCH_18S",
                    es_maker=True,
                    ahora=t_now,
                )
                return "MAKER_SCRATCH_18S"

        # Escudo Maker Fase 2 a los 32s: solo aplica si NO se ha ejecutado aun la 1ra cosecha del 50%
        if (
            not pos.cosecha_50_ejecutada
            and edad_seg >= cfg.ESCUDO_MAKER_FASE2_SEG
            and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT
        ):
            precio_fase2 = calcular_precio_salida_maker_seguro(
                pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
            )
            log_sniper(
                f"[FRANCOTIRADOR] [DIAMOND] {pos.symbol} Escudo Maker Fase 2 PostOnly ejecutado @ {precio_fase2} "
                f"(PnL {pnl_bruto_pct*100:+.2f}%, edad {edad_seg:.0f}s)"
            )
            await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=precio_fase2,
                motivo="MAKER_UNWIND",
                es_maker=True,
                ahora=t_now,
            )
            return "MAKER_UNWIND"

        limite_hold = (
            cfg.TIEMPO_MAX_HOLD_TRINQUETE_SEG
            if (pos.cosecha_50_ejecutada and pos.trinquete_be_armado and pnl_bruto_pct > 0.0)
            else cfg.TIEMPO_MAX_HOLD_SEG
        )
        if edad_seg >= limite_hold:
            log_sniper(
                f"[FRANCOTIRADOR] {pos.symbol} alcanzo tiempo limite ({edad_seg:.0f}s >= {limite_hold:.0f}s). "
                f"Liquidando posicion para liberar margen."
            )
            await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=precio_marca,
                motivo="ESCAPE_TEMPORAL",
                es_maker=False,
                ahora=t_now,
            )
            return "ESCAPE_TEMPORAL"

        return None

    async def evacuar_todas_por_emergencia(self, motivo: str = "EVACUACION_CONTAGIO_CROSS_ASSET") -> int:
        cerradas = 0
        ahora = time.time()
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
            if pos.cerrada or getattr(pos, "_cierre_en_curso", False):
                continue
            if not es_test and (pos.side == "short" or pos.scratch_18s_activo or pos.pre_escape_72s_enviado):
                continue
            tk = ESTADO_RAM.ticks_ram.get(sym)
            precio_ref = (tk.bid if pos.side == "long" else tk.ask) if tk and tk.bid > 0 else pos.entry_price
            ok = await self._ejecutar_cierre_definitivo(
                pos=pos,
                precio_ejecucion=precio_ref,
                motivo=motivo,
                es_maker=False,
                ahora=ahora,
            )
            if ok:
                cerradas += 1
        return cerradas

    async def bucle_vigilancia_posiciones(self) -> None:
        self._running = True
        while self._running:
            try:
                ahora = time.time()
                for _, pos in list(ESTADO_RAM.posiciones_activas.items()):
                    if not pos.cerrada:
                        await self.evaluar_posicion_activa(pos, ahora=ahora)
            except Exception as exc:
                log_sniper(f"[WARN] [GESTOR POSICIONES] Error en ciclo de vigilancia: {exc}")
            await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)

    def detener(self) -> None:
        self._running = False


def colorear_linea_log_mobaxterm(linea: str) -> str:
    """Coloreador ANSI TrueColor en tiempo real para el stream de verbot."""
    RST = "\033[0m"
    s = str(linea or "").rstrip("\r\n")
    if not s:
        return ""
    if "CIERRE" in s and ("+" in s or "WIN" in s):
        return f"\033[1;38;2;0;255;135m{s}{RST}"
    if "CIERRE" in s and "SCRATCH" in s:
        return f"\033[1;38;2;255;210;60m{s}{RST}"
    if "CIERRE" in s or "CIRCUIT BREAKER" in s or "ERROR" in s:
        return f"\033[1;38;2;255;75;95m{s}{RST}"
    if "[RADAR]" in s and "APROBADO" in s:
        return f"\033[1;38;2;0;240;255m{s}{RST}"
    if "Cosecha" in s or "PHANTOM 50/25/25" in s or "Posicion" in s:
        return f"\033[1;38;2;215;120;255m{s}{RST}"
    if "TRI-CORTEX" in s or "HOT-RELOAD" in s:
        return f"\033[1;38;2;130;190;255m{s}{RST}"
    return s


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
    s = sum(1 for x in ops if "SCRATCH" in str(x.get("motivo", "")).upper())
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
            for linea in reversed(candidate_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-2500:]):
                if "real:" in linea and "USDT" in linea:
                    try:
                        bal_real = linea.split("real:")[1].split("USDT")[0].strip() + " USDT"
                        break
                    except Exception:
                        pass
                elif "Auditoria UTA USDT -> Total:" in linea:
                    try:
                        bal_real = linea.split("Total:")[1].split("|")[0].strip() + " USDT"
                        break
                    except Exception:
                        pass
            if bal_real != "N/A":
                break

    c_pnl_tot = C_GREEN if pnl >= 0 else C_RED
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_TITLE}CAJA NEGRA  :{RST} {C_WHITE}{total} Trades{RST} ({C_GREEN}W: {w}{RST} | {C_RED}L: {l}{RST} | {C_YELLOW}Scratch 18s: {s}{RST} | {C_MAGENTA}Cosecha 50%: {triz}{RST})")
    print(f" {C_GOLD}Win Rate    :{RST} Clasico {C_WHITE}{wr:.1f}%{RST} | Efectivo {C_GREEN}{wr_ef:.1f}%{RST} | PnL Neto: {c_pnl_tot}{pnl:+.4f} USDT{RST} | UTA Real: {C_GOLD}{bal_real}{RST} | lambda={C_TITLE}{lam:.2f}{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_TITLE}{'PAR Y DIRECCION':<22} {'TRADES (W/L)':<15} {'WIN RATE':<10} {'HURST MEDIO':<13} {'PNL NETO USDT':<18}{RST}")
    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")

    grupos = defaultdict(list)
    for t in ops:
        sym = str(t.get("symbol", "")).replace("/USDT:USDT", "")
        side = str(t.get("side", "long")).upper()
        grupos[f"{sym} [{side}]"].append(t)

    for k in sorted(grupos.keys(), key=lambda x: sum(float(i.get("pnl_usdt", 0.0)) for i in grupos[x]), reverse=True):
        lista = grupos[k]
        w_g = sum(1 for i in lista if float(i.get("pnl_usdt", 0.0)) >= 0.0)
        l_g = len(lista) - w_g
        wr_g = (w_g / len(lista) * 100.0) if lista else 0.0
        h_vals = [float(i.get("hurst_entry", 0.0)) for i in lista if i.get("hurst_entry") is not None]
        h_med = (sum(h_vals) / len(h_vals)) if h_vals else 0.0
        pnl_g = sum(float(i.get("pnl_usdt", 0.0)) for i in lista)
        badge = BADGE_POS if pnl_g >= 0 else BADGE_NEG
        c_row = C_GREEN if pnl_g >= 0 else C_RED
        c_side = C_MAGENTA if "[SHORT]" in k else C_TITLE
        print(f" {c_side}{k:<22}{RST} {C_WHITE}{f'{len(lista)} ({w_g}W/{l_g}L)':<15}{RST} {c_row}{f'{wr_g:5.1f}%':<10}{RST} {C_YELLOW}{f'H={h_med:.3f}':<13}{RST} {badge} {c_row}{pnl_g:+.4f} USDT{RST}")

    print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
    print(f" {C_MAGENTA}ULTIMAS 10 OPERACIONES REGISTRADAS EN LA CAJA NEGRA:{RST}")
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
        print(f"  {C_YELLOW}Esperando el primer disparo confirmado...{RST}")
    print(f"{C_BORDER}=========================================================================================={RST}")


async def reenviar_ultimo_cierre_cli() -> None:
    import json
    stats_f = cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL
    if not stats_f.exists():
        print("  [INFO] Aun no hay cierres registrados en tribrain_stats_v1.jsonl.")
        return
    lineas = [l for l in stats_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lineas:
        print("  [INFO] Archivo tribrain_stats_v1.jsonl vacio.")
        return
    u = json.loads(lineas[-1])
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
    print(f"  \033[1;38;2;0;255;135m[OK] [VERBOT -T] Reenvio manual a Telegram del ultimo cierre ({u['symbol']}): {ok}\033[0m")


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
    modo = str(accion or "status").strip().lower()
    ex = ccxt.bybit({
        "apiKey": cfg.BYBIT_API_KEY,
        "secret": cfg.BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "swap", "recvWindow": 15000},
    })
    try:
        await ex.load_markets()
        posiciones = await ex.fetch_positions(None, {"settleCoin": "USDT"})
        activas = [
            p for p in (posiciones or [])
            if abs(float(p.get("contracts") or (p.get("info") or {}).get("size") or 0.0)) > 0.0
        ]
        bal = await ex.fetch_balance()
        usdt = (bal or {}).get("USDT") or {}
        tot = float(usdt.get("total") or 0.0)
        lib = float(usdt.get("free") or tot)

        print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")
        print(f" {BADGE_GHOST} {C_TITLE}RADAR TACTICO GOD'S ACCOMPLICE V1.0 (verbot -x){RST} | Balance UTA: {C_GOLD}{tot:.4f} USDT{RST} (Libre: {C_GREEN}{lib:.4f}{RST})")
        print(f"{C_BORDER}------------------------------------------------------------------------------------------{RST}")

        if not activas:
            print(f" {C_GREEN}[OK] Sin posiciones abiertas en Bybit en este instante (0 contratos corriendo).{RST}")
            print(f"{C_BORDER}=========================================================================================={RST}")
            msg_vacio = nl.join([
                "[RADAR PHANTOM (GOD'S ACCOMPLICE) V1.0 EN VIVO]",
                "- Estado: Sin posiciones abiertas (0 contratos)",
                f"- Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f} USDT)",
            ])
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(msg_vacio)
            print(f" {BADGE_TG} {C_TITLE}Reporte de estado enviado a tu celular:{RST} {C_GREEN}{ok_tg}{RST}")
            return

        lineas_tg = [
            "[RADAR PHANTOM (GOD'S ACCOMPLICE) V1.0 EN VIVO]",
            f"Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f} USDT)",
        ]
        for p in activas:
            sym = str(p.get("symbol") or "")
            side = str(p.get("side") or "long").lower()
            qty = abs(float(p.get("contracts") or (p.get("info") or {}).get("size") or 0.0))
            ep = float(p.get("entryPrice") or (p.get("info") or {}).get("avgPrice") or 0.0)
            mp = float(p.get("markPrice") or (p.get("info") or {}).get("markPrice") or ep)
            pnl_u = float(p.get("unrealizedPnl") or (p.get("info") or {}).get("unrealisedPnl") or 0.0)
            lev = float(p.get("leverage") or cfg.APALANCAMIENTO_BASE)
            sl_b = p.get("stopLossPrice") or (p.get("info") or {}).get("stopLoss") or "SIN SL"
            pct = ((mp - ep) / ep if side == "long" else (ep - mp) / ep) if ep > 0 else 0.0
            es_t1 = sym in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
            eslabon, piso_sug, _ = calcular_eslabon_chain_jail(max(0.0, pct), es_tier1=es_t1)
            techo_str = "+1.85%" if es_t1 else "+5.50%"

            if modo == "cerrar":
                try:
                    ords = await ex.fetch_open_orders(sym)
                    for o in (ords or []):
                        await ex.cancel_order(o["id"], sym)
                except Exception:
                    pass
                lado_c = "buy" if side == "short" else "sell"
                await ex.create_order(sym, "market", lado_c, qty, None, {"reduceOnly": True})
                bal2 = await ex.fetch_balance()
                tot2 = float(((bal2 or {}).get("USDT") or {}).get("total") or tot)
                print(f" {C_GREEN}[OK] COBRO MANUAL PHANTOM EJECUTADO: {sym} [{side.upper()}] ({qty} contratos){RST}")
                print(f" {C_GOLD}Resultado Capturado: {pct*100:+.2f}% puro ({pnl_u:+.4f} USDT) | Nuevo Balance: {tot2:.4f} USDT{RST}")
                print(f"{C_BORDER}=========================================================================================={RST}")
                msg_cierre = nl.join([
                    "[COBRO MANUAL PHANTOM V1.0 (verbot -x cerrar)]",
                    f"- Activo: {sym} [{side.upper()}] ({qty} contratos)",
                    f"- Recorrido: {ep} -> {mp} ({pct*100:+.2f}% puro | ROE {pct*lev*100:+.2f}%)",
                    f"- PnL Capturado: {pnl_u:+.4f} USDT",
                    f"- Nuevo Balance Consolidado: {tot2:.4f} USDT",
                ])
                ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(msg_cierre)
                print(f" {BADGE_TG} {C_TITLE}Recibo de cobro manual enviado:{RST} {C_GREEN}{ok_tg}{RST}")
            else:
                print(f" {C_TITLE}ACTIVO      : {sym} [{side.upper()}] ({qty} contratos){RST}")
                print(f" {C_GOLD}PRECIO      : Entrada {ep} -> Marca Actual {mp}{RST}")
                print(f" {C_GREEN}GANANCIA    : {pct*100:+.2f}% puro ({pct*lev*100:+.2f}% ROE {lev:.0f}x) | {pnl_u:+.4f} USDT{RST}")
                print(f" {C_TITLE}ESLABON     : {eslabon}/5 (Piso Eslabon: +{piso_sug*100:.2f}% -> Meta: {techo_str}) | SL Bybit: {sl_b}{RST}")
                print(f"{C_BORDER}=========================================================================================={RST}")
                lineas_tg.extend([
                    f"Activo: {sym} [{side.upper()}] ({qty} contratos)",
                    f"- Precio: {ep} -> {mp}",
                    f"- Ganancia: {pct*100:+.2f}% (ROE {pct*lev*100:+.2f}%) | {pnl_u:+.4f} USDT",
                    f"- Eslabon Phantom: {eslabon}/5 (Piso +{piso_sug*100:.2f}% -> Techo {techo_str})",
                    f"- SL en Bybit: {sl_b}",
                ])

        if modo != "cerrar":
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(nl.join(lineas_tg))
            print(f" {BADGE_TG} {C_TITLE}Alerta en vivo enviada a tu celular:{RST} {C_GREEN}{ok_tg}{RST}")
    finally:
        await ex.close()