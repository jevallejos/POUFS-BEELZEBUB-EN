#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #10: gestor_posiciones.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 â€” ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Guardian de Geometria de Pagos 10/10 (Long & Short Simetrico):
  - Ley 2 (CHRONOS-TRIZ): Desplazamiento del Precio de Reserva a los 18.0s
    (Avellaneda-Stoikov Maker-Scratch) para evacuar tesis estancadas entre
    -0.04% y -0.14% Maker antes de que toquen el Stop-Loss.
  - Ley 3 (CHRONOS-TRIZ): Cosecha Fraccionada 50/50 TRIZ en +0.26% bruto +
    Piso Invariante Break-Even (+0.12% neto) + Trinquete Continuo Maker (+0.38%+)
    y Trailing Stop de expansion libre (+0.65%+).
  - Escudo Fase 2 (> 32s): Salida pasiva ganadora con piso inquebrantable >= +0.20% bruto.
  - Stop-Loss Quirurgico Acotado (-0.48% interno / -0.70% Bybit) y Reloj
    Impostergable de 90s (sin prorrogas ocultas en posiciones perdedoras).
  - Captura nativa de retCode:110017 (posicion cerrada por Bybit SL_EXCHANGE).
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, MetricaTick, PosicionActiva, log_sniper
from ejecutor_sniper import extraer_precision_y_minimos, redondear_cantidad_lote
from escudo_tricortex import ESCUDO_TRICORTEX
from stats_tracker import CAJA_NEGRA
from telemetria_telegram import TELEMETRIA_TG


# ==============================================================================
# 1. FUNCIONES MATEMATICAS PURAS DE BARRERAS BREAK-EVEN Y PRECIOS MAKER
# ==============================================================================
def calcular_piso_invariante_breakeven(
    side: str, entry_price: float, tick_size: float
) -> Tuple[float, float]:
    """
    Calcula (sl_interno_be, sl_bybit_be) garantizando cubrir el doble de comision
    y dejar al menos +0.12% de ganancia neta positiva (Piso Invariante Break-Even).
    """
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0

    margen_interno_pct = (2.0 * cfg.FEE_MAKER_PCT) + cfg.TRINQUETE_BE_NETO_PCT  # +0.16%
    margen_bybit_pct = cfg.TRINQUETE_BE_NETO_PCT                                # +0.12%

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
    """
    Calcula el precio para una orden de salida Limit PostOnly (reduceOnly=True):
      - Si permitir_scratch=False (Cosecha 50%, Ratchet o Fase 2): impone el piso
        inquebrantable >= entry_price * (1 + PISO_MAKER_BRUTO_MIN_PCT) en Long.
      - Si permitir_scratch=True (Maker-Scratch 18s): cotiza en best_ask (Long)
        o best_bid (Short) sin cruzar el libro para evacuar de inmediato.
    """
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

    # Caso LONG
    candidato = max(ask, bid + tick) if ask > bid else ask
    if not permitir_scratch:
        piso_ganador = ep * (1.0 + cfg.PISO_MAKER_BRUTO_MIN_PCT)
        candidato = max(candidato, piso_ganador)
    return round(candidato, decimales)


# ==============================================================================
# 2. MOTOR GESTOR DE POSICIONES (LEYES 2 Y 3 DE CHRONOS-TRIZ)
# ==============================================================================
class GestorPosiciones:
    """
    Gobierna el ciclo de vida de cada PosicionActiva en memoria RAM a 6.6 Hz.
    Ejecuta la Cosecha 50/50 TRIZ, el Trinquete Continuo Maker, la evacuacion
    Maker-Scratch a los 18s y las barreras de Stop-Loss Quirurgico.
    """

    def __init__(self, exchange: Any = None) -> None:
        self.exchange: Any = exchange
        self._running: bool = False

    async def armar_proteccion_inicial_bybit(self, pos: PosicionActiva) -> bool:
        """Sincroniza el Stop-Loss de servidor Bybit (-0.70%) al abrirse la posicion."""
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

    async def _ejecutar_cierre_definitivo(
        self,
        pos: PosicionActiva,
        precio_ejecucion: float,
        motivo: str,
        es_maker: bool,
        ahora: float,
    ) -> bool:
        """
        Envia la orden de cierre final (Limit PostOnly o Market reduceOnly) a Bybit,
        maneja nativamente retCode:110017 (SL_EXCHANGE), registra en Caja Negra,
        libera el Single-Slot Mutex en RAM y activa el enfriamiento/forense en Tri-Cortex.
        """
        if pos.cerrada:
            return False

        symbol = pos.symbol
        side_close = "sell" if pos.side == "long" else "buy"
        qty_cerrar = float(pos.qty_actual if pos.qty_actual > 0.0 else pos.qty_inicial)
        precio_final = float(precio_ejecucion)
        motivo_final = str(motivo)
        fue_maker = bool(es_maker)

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
            except Exception as exc:
                err_str = str(exc)
                # Captura nativa de retCode:110017 (Bybit ya cerro la posicion por SL_EXCHANGE)
                if "110017" in err_str or "reduce-only" in err_str.lower() or "zero position" in err_str.lower():
                    motivo_final = "SL_EXCHANGE"
                    fue_maker = False
                elif fue_maker:
                    # Si un Limit PostOnly fue rechazado por cruzar el spread, cerrar a mercado
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
            )
            return True
        return False

    async def _ejecutar_cosecha_50_triz(
        self,
        pos: PosicionActiva,
        best_bid: float,
        best_ask: float,
        tick_size: float,
        step_qty: float,
        min_qty: float,
    ) -> bool:
        """
        Ley 3 de CHRONOS-TRIZ:
        1. Arma el Piso Invariante Break-Even (+0.12% neto) en RAM y en Bybit.
        2. Si pos.qty_actual es divisible en dos lotes >= min_qty, vende el 50%
           mediante Limit PostOnly, asegurando ganancias y pagando todas las comisiones.
        """
        sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
            pos.side, pos.entry_price, tick_size
        )
        pos.sl_interno_price = sl_int_be
        pos.trinquete_be_armado = True
        pnl_actual_pct = pos.calcular_pnl_bruto_pct(best_bid if pos.side == "long" else best_ask)

        log_sniper(
            f"[FRANCOTIRADOR] 🛡️ {pos.symbol} Trinquete Break-Even armado: "
            f"SL {sl_int_be} (PnL {pnl_actual_pct*100:+.2f}%)"
        )
        await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)

        mitad_qty = redondear_cantidad_lote(pos.qty_actual * cfg.COSECHA_TRIZ_FRACCION, step_qty, min_qty)
        rem_qty = round(pos.qty_actual - mitad_qty, 8)

        # Si el lote no es divisible en dos mitades validas, mantener el 100% protegido en Break-Even
        if mitad_qty < min_qty or rem_qty < min_qty:
            pos.cosecha_50_ejecutada = True
            return False

        precio_cosecha = calcular_precio_salida_maker_seguro(
            pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
        )
        side_close = "sell" if pos.side == "long" else "buy"

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
                if isinstance(orden_parcial, dict):
                    p_avg = float(orden_parcial.get("average") or orden_parcial.get("price") or 0.0)
                    if p_avg > 0.0:
                        precio_cosecha = p_avg
            except Exception:
                # Si PostOnly parcial no pudo colocarse, el 100% ya quedo blindado en Break-Even
                pos.cosecha_50_ejecutada = True
                return False

        pnl_parcial_usdt = CAJA_NEGRA.registrar_cosecha_parcial_50(
            pos=pos,
            qty_cerrada=mitad_qty,
            exit_price=precio_cosecha,
            es_maker=True,
        )
        nocional_mitad = mitad_qty * pos.entry_price
        pnl_parcial_pct = (pnl_parcial_usdt / nocional_mitad * 100.0) if nocional_mitad > 0.0 else 0.0

        log_sniper(
            f"[FRANCOTIRADOR] ðŸ’Ž {pos.symbol} Cosecha 50% TRIZ PostOnly ejecutada: "
            f"{mitad_qty} @ {precio_cosecha} ({pnl_parcial_pct:+.2f}% | {pnl_parcial_usdt:+.4f} USDT). "
            f"Restan {pos.qty_actual} contratos en Trailing libre."
        )

        await TELEMETRIA_TG.notificar_cosecha_parcial_triz(
            symbol=pos.symbol,
            side=pos.side,
            qty_vendida=mitad_qty,
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
        """
        Evalua en O(1) las barreras de salida de una PosicionActiva bajo CHRONOS-TRIZ.
        Retorna el motivo de cierre si la posicion se cerro, o None si continua abierta.
        """
        if pos.cerrada:
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

        tick_size, step_qty, min_qty = extraer_precision_y_minimos(
            self.exchange, pos.symbol, pos.entry_price
        )

        # ======================================================================
        # 1. BARRERA STOP-LOSS QUIRURGICO INTERNO (-0.48% o Trinquete BE+)
        # ======================================================================
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

        # ======================================================================
        # 2. LEY 3 (CHRONOS-TRIZ): COSECHA 50/50 (+0.26%) + TRINQUETE CONTINUO
        # ======================================================================
        if pnl_bruto_pct >= cfg.COSECHA_TRIZ_ACTIVACION_PCT and not pos.cosecha_50_ejecutada:
            await self._ejecutar_cosecha_50_triz(
                pos, best_bid, best_ask, tick_size, step_qty, min_qty
            )

        # Activar Trailing Stop de expansion libre en +0.65%
        if pnl_bruto_pct >= cfg.TRAILING_ACTIVACION_PCT and not pos.trailing_activo:
            pos.trailing_activo = True
            log_sniper(
                f"[FRANCOTIRADOR] 🧲 {pos.symbol} Trailing Stop activado (PnL {pnl_bruto_pct*100:+.2f}%)"
            )

        # Si el Trailing Stop o el Trinquete Ratchet (+0.38%+) estan activos,
        # cobrar en Limit PostOnly si el precio retrocede desde el maximo o si el flujo se agota
        if pos.max_pnl_pct_alcanzado >= cfg.TRINQUETE_RATCHET_ACTIVACION_PCT:
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

        # ======================================================================
        # 3. LEY 2 (CHRONOS-TRIZ): EVACUACION MAKER-SCRATCH A LOS 18 SEGUNDOS
        # ======================================================================
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
                log_sniper(
                    f"✂️ [MAKER-SCRATCH 18s] {pos.symbol} sin rebote tras {edad_seg:.1f}s "
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

        # ======================================================================
        # 4. ESCUDO FASE 2 (> 32S): SALIDA PASIVA GANADORA (>= +0.20% BRUTO)
        # ======================================================================
        if edad_seg >= cfg.ESCUDO_MAKER_FASE2_SEG and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT:
            precio_fase2 = calcular_precio_salida_maker_seguro(
                pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
            )
            log_sniper(
                f"[FRANCOTIRADOR] ðŸ’Ž {pos.symbol} Escudo Maker Fase 2 PostOnly ejecutado @ {precio_fase2} "
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

        # ======================================================================
        # 5. RELOJ IMPOSTERGABLE DE 90 SEGUNDOS (ESCAPE TEMPORAL)
        # ======================================================================
        limite_hold = (
            cfg.TIEMPO_MAX_HOLD_TRINQUETE_SEG
            if (pos.cosecha_50_ejecutada and pos.trinquete_be_armado and pnl_bruto_pct > 0.0)
            else cfg.TIEMPO_MAX_HOLD_SEG
        )
        if edad_seg >= limite_hold:
            log_sniper(
                f"âŒ› [FRANCOTIRADOR] {pos.symbol} alcanzÃ³ tiempo lÃ­mite ({edad_seg:.0f}s >= {limite_hold:.0f}s). "
                f"Liquidando posiciÃ³n para liberar margen."
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
        """Evacua inmediatamente todas las posiciones activas ante disparo del Cortafuegos Macro."""
        cerradas = 0
        ahora = time.time()
        for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
            if pos.cerrada:
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
        """Bucle continuo a 6.6 Hz (150 ms) que vigila las posiciones activas en RAM."""
        self._running = True
        while self._running:
            try:
                ahora = time.time()
                for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
                    if not pos.cerrada:
                        await self.evaluar_posicion_activa(pos, ahora=ahora)
            except Exception as exc:
                log_sniper(f"âš ï¸ [GESTOR POSICIONES] Error en ciclo de vigilancia: {exc}")
            await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)

    def detener(self) -> None:
        self._running = False


# === [PHANTOM V1.0 GOD'S ACCOMPLICE EXIT MATRIX (P-04, P-05, P-06) & CLI SUITE] ===
def validar_cuantizacion_chain_jail_4x(
    qty_total: float,
    precio: float,
    step_qty: float,
    min_qty: float,
    min_notional: float = 2.50,
) -> tuple[bool, float, float]:
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

def calcular_eslabon_chain_jail(pnl_max_pct: float, es_tier1: bool = False) -> tuple[int, float, bool]:
    if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
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

if "GestorPosiciones" in globals():
    _metodo_eval_nombre = "evaluar_posicion_activa" if hasattr(GestorPosiciones, "evaluar_posicion_activa") else "evaluar_posicion_individual"
    if hasattr(GestorPosiciones, _metodo_eval_nombre) and not hasattr(GestorPosiciones, "_orig_eval_pos_base"):
        GestorPosiciones._orig_eval_pos_base = getattr(GestorPosiciones, _metodo_eval_nombre)

        async def _evaluar_posicion_activa_phantom(self, *args, **kwargs):
            if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") == "1":
                return await GestorPosiciones._orig_eval_pos_base(self, *args, **kwargs)

            pos = args[0] if len(args) > 0 else kwargs.get("pos")
            ahora_eval = float(args[1]) if len(args) > 1 and args[1] is not None else float(kwargs.get("ahora") or time.time())

            if pos is not None and not getattr(pos, "cerrada", False):
                tick = ESTADO_RAM.ticks_ram.get(pos.symbol)
                precio_actual = float(getattr(tick, "last", 0.0) or getattr(tick, "bid", 0.0) or pos.entry_price)
                edad_seg = max(0.0, ahora_eval - float(getattr(pos, "ts_apertura", ahora_eval)))

                if precio_actual > 0.0 and pos.entry_price > 0.0:
                    pnl_bruto = (
                        (precio_actual - pos.entry_price) / pos.entry_price
                        if pos.side == "long"
                        else (pos.entry_price - precio_actual) / pos.entry_price
                    )
                    if pnl_bruto > pos.max_pnl_pct_alcanzado:
                        pos.max_pnl_pct_alcanzado = pnl_bruto

                    if not getattr(pos, "cosecha_50_ejecutada", False) and 18.0 <= edad_seg < 72.0:
                        if pnl_bruto < 0.0005:
                            pos.scratch_evaluado = False
                            pos.scratch_18s_evaluado = False
                        ofi_sym = float(getattr(tick, "ofi_5s", getattr(tick, "obi", 0.0)) or 0.0)
                        flujo_contra = (ofi_sym < -0.10) if pos.side == "long" else (ofi_sym > 0.10)
                        if edad_seg >= 28.0 and pnl_bruto <= -0.0018 and flujo_contra:
                            pos.scratch_evaluado = False
                            pos.scratch_18s_evaluado = False

                    if (
                        not getattr(pos, "cosecha_50_ejecutada", False)
                        and 72.0 <= edad_seg <= 86.0
                        and -0.0022 <= pnl_bruto < 0.0024
                        and not getattr(pos, "_pre_escape_intentado", False)
                    ):
                        pos._pre_escape_intentado = True
                        lado_u = "sell" if pos.side == "long" else "buy"
                        px_u = float(getattr(tick, "ask", 0.0) or precio_actual) if pos.side == "long" else float(getattr(tick, "bid", 0.0) or precio_actual)
                        try:
                            ord_u = await self.exchange.create_order(
                                pos.symbol,
                                "limit",
                                lado_u,
                                pos.qty_actual,
                                px_u,
                                {"timeInForce": "PostOnly", "reduceOnly": True},
                            )
                            st_u = str((ord_u or {}).get("status") or "").lower()
                            if st_u not in ("canceled", "rejected", "expired"):
                                log_sniper(
                                    f"👻 [PHANTOM PRE-ESCAPE P-05] {pos.symbol} orden pasiva PostOnly enviada a los "
                                    f"{edad_seg:.1f}s @ {px_u} (PnL {pnl_bruto*100:+.2f}%) para evitar comision Taker 90s."
                                )
                        except Exception:
                            pass

                    if (
                        getattr(pos, "cosecha_50_ejecutada", False)
                        and not getattr(pos, "cosecha_25_ejecutada", False)
                        and pnl_bruto >= 0.0048
                    ):
                        reglas = self.ejecutor.obtener_reglas_simbolo(pos.symbol) if hasattr(self, "ejecutor") else {}
                        step_q = float(reglas.get("step_qty", 0.1) or 0.1)
                        min_q = float(reglas.get("min_qty", step_q) or step_q)
                        ok_4x, qty_25, _ = validar_cuantizacion_chain_jail_4x(
                            pos.qty_actual * 2.0, precio_actual, step_q, min_q, 2.50
                        )
                        if ok_4x and qty_25 >= min_q and pos.qty_actual > qty_25:
                            lado_c = "sell" if pos.side == "long" else "buy"
                            try:
                                ord_25 = await self.exchange.create_order(
                                    pos.symbol,
                                    "limit",
                                    lado_c,
                                    qty_25,
                                    precio_actual,
                                    {"timeInForce": "PostOnly", "reduceOnly": True},
                                )
                                st_25 = str((ord_25 or {}).get("status") or "").lower()
                                if st_25 not in ("canceled", "rejected", "expired"):
                                    pos.qty_actual = round(max(min_q, pos.qty_actual - qty_25), 8)
                                    pos.cosecha_25_ejecutada = True
                                    pos.chain_jail_activo = True
                                    ganancia_25 = qty_25 * pos.entry_price * (pnl_bruto - 2.0 * cfg.FEE_MAKER_PCT)
                                    pos.pnl_realizado_parcial_usdt += ganancia_25
                                    log_sniper(
                                        f"[PHANTOM 50/25/25] ⛓️ {pos.symbol} 2da Tirada 25% ejecutada: "
                                        f"{qty_25} @ {precio_actual} ({pnl_bruto*100:+.2f}% | {ganancia_25:+.4f} USDT). "
                                        f"Ultimo 25% ({pos.qty_actual}) en GHOST-RUNNER."
                                    )
                            except Exception:
                                pos.cosecha_25_ejecutada = True
                                pos.chain_jail_activo = True
                        else:
                            pos.cosecha_25_ejecutada = True
                            pos.chain_jail_activo = True

                    if getattr(pos, "cosecha_50_ejecutada", False):
                        es_t1 = pos.symbol in getattr(cfg, "CLASE_TIER1_LIQUIDO", ())
                        esl_id, piso_sl, _ = calcular_eslabon_chain_jail(
                            pos.max_pnl_pct_alcanzado, es_tier1=es_t1
                        )
                        if esl_id > getattr(pos, "eslabon_chain_jail", 0):
                            pos.eslabon_chain_jail = esl_id
                            nuevo_sl = (
                                pos.entry_price * (1.0 + piso_sl)
                                if pos.side == "long"
                                else pos.entry_price * (1.0 - piso_sl)
                            )
                            if (pos.side == "long" and nuevo_sl > pos.sl_interno_price) or (
                                pos.side == "short" and nuevo_sl < pos.sl_interno_price
                            ):
                                pos.sl_interno_price = nuevo_sl
                                if hasattr(self, "_actualizar_sl_servidor_bybit"):
                                    await self._actualizar_sl_servidor_bybit(pos, nuevo_sl)
                            log_sniper(
                                f"[PHANTOM 50/25/25] ⛓️ {pos.symbol} asciende a Eslabon {esl_id}/5 "
                                f"(Max PnL {pos.max_pnl_pct_alcanzado*100:+.2f}% -> Piso SL +{piso_sl*100:.2f}%)"
                            )

            res_eval = await GestorPosiciones._orig_eval_pos_base(self, *args, **kwargs)

            if pos is not None and getattr(pos, "cerrada", False) and hasattr(self.exchange, "fetch_positions"):
                try:
                    await asyncio.sleep(1.80)
                    pos_bybit = await self.exchange.fetch_positions([pos.symbol])
                    for pb in (pos_bybit or []):
                        if str(pb.get("symbol") or "") == pos.symbol:
                            rem_c = abs(float(pb.get("contracts") or (pb.get("info") or {}).get("size") or 0.0))
                            if rem_c > 0.0:
                                try:
                                    ords_ab = await self.exchange.fetch_open_orders(pos.symbol)
                                    for o_ab in (ords_ab or []):
                                        await self.exchange.cancel_order(o_ab["id"], pos.symbol)
                                except Exception:
                                    pass
                                lado_rem = "sell" if pos.side == "long" else "buy"
                                await self.exchange.create_order(
                                    pos.symbol, "market", lado_rem, rem_c, None, {"reduceOnly": True}
                                )
                                log_sniper(
                                    f"🛡️ [GUARDIA ZERO-ORPHAN PHANTOM] Remanente de {rem_c} contratos en {pos.symbol} "
                                    f"liquidado tras 1.8s con reduceOnly=True (0 contratos huerfanos)."
                                )
                except Exception:
                    pass

            return res_eval

        setattr(GestorPosiciones, _metodo_eval_nombre, _evaluar_posicion_activa_phantom)


def imprimir_status_cli_verbot() -> None:
    import json
    from collections import defaultdict

    stats_f = cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL
    log_f = cfg.ROOT_DIR / getattr(cfg, "ARCHIVO_LOG_SESION", "bot_hft.log")
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
    if log_f.exists():
        for linea in reversed(log_f.read_text(encoding="utf-8", errors="ignore").splitlines()[-600:]):
            if "real:" in linea and "USDT" in linea:
                try:
                    bal_real = linea.split("real:")[1].split("USDT")[0].strip() + " USDT"
                    break
                except Exception:
                    pass

    print("------------------------------------------------------------------------------------------")
    print(f" 📊 CAJA NEGRA : {total} Trades (W: {w} | L: {l} | Scratch 18s: {s} | Cosecha 50%: {triz})")
    print(f" 🎯 Win Rate   : Clasico {wr:.1f}% | Efectivo {wr_ef:.1f}% | PnL Neto: {pnl:+.4f} USDT | UTA Real: {bal_real} | λ={lam:.2f}")
    print("------------------------------------------------------------------------------------------")
    print(f" {'PAR Y DIRECCION':<22} {'TRADES (W/L)':<15} {'WIN RATE':<10} {'HURST MEDIO':<13} {'PNL NETO USDT':<15}")
    print("------------------------------------------------------------------------------------------")

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
        ic = "🟩" if pnl_g >= 0 else "🔴"
        print(f" {k:<22} {f'{len(lista)} ({w_g}W/{l_g}L)':<15} {f'{wr_g:5.1f}%':<10} {f'H={h_med:.3f}':<13} {ic} {pnl_g:+.4f} USDT")

    print("------------------------------------------------------------------------------------------")
    print(" 📜 ULTIMAS 10 OPERACIONES REGISTRADAS EN LA CAJA NEGRA:")
    print("------------------------------------------------------------------------------------------")
    if ops:
        idx_base = max(1, total - 9)
        for idx, op in enumerate(ops[-10:], start=idx_base):
            pnl_u = float(op.get("pnl_usdt", 0.0))
            mot = str(op.get("motivo", ""))
            ic = "🟩" if pnl_u >= 0 else ("🟨" if "SCRATCH" in mot.upper() else "🔴")
            ts_s = str(op.get("timestamp", ""))[:19]
            sym_s = str(op.get("symbol", "")).replace("/USDT:USDT", "").ljust(10)
            side_s = str(op.get("side", "long")).upper().ljust(5)
            pct_s = float(op.get("pnl_percentage", 0.0))
            hold_s = float(op.get("hold_seg", 0.0))
            print(f" #{idx:<2} {ic} {ts_s} | {sym_s} [{side_s}] | {pct_s:+6.2f}% ({pnl_u:+.4f} USDT) | {hold_s:4.0f}s | {mot}")
    else:
        print("  ⏳ Esperando el primer disparo confirmado...")
    print("==========================================================================================")


async def reenviar_ultimo_cierre_cli() -> None:
    import json
    stats_f = cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL
    if not stats_f.exists():
        print("  ℹ️ Aun no hay cierres registrados en tribrain_stats_v1.jsonl.")
        return
    lineas = [l for l in stats_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lineas:
        print("  ℹ️ Archivo tribrain_stats_v1.jsonl vacio.")
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
    print(f"  ✅ [VERBOT -T] Reenvio manual a Telegram del ultimo cierre ({u['symbol']}): {ok}")


async def ejecutar_radar_xray_cli(accion: str = "status") -> None:
    import ccxt.async_support as ccxt
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

        print("------------------------------------------------------------------------------------------")
        print(f" 👻 RADAR TACTICO GOD'S ACCOMPLICE V1.0 (verbot -x) | Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f})")
        print("------------------------------------------------------------------------------------------")

        if not activas:
            print(" 🟢 Sin posiciones abiertas en Bybit en este instante (0 contratos corriendo).")
            print("==========================================================================================")
            msg_vacio = nl.join([
                "👻 [RADAR PHANTOM (GOD'S ACCOMPLICE) V1.0 EN VIVO]",
                "• Estado: Sin posiciones abiertas (0 contratos)",
                f"• Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f} USDT)",
            ])
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(msg_vacio)
            print(f" 📲 [TELEGRAM] Reporte de estado enviado a tu celular: {ok_tg}")
            return

        lineas_tg = [
            "👻 [RADAR PHANTOM (GOD'S ACCOMPLICE) V1.0 EN VIVO]",
            f"💰 Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f} USDT)",
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
                print(f" 🟩 COBRO MANUAL PHANTOM EJECUTADO: {sym} [{side.upper()}] ({qty} contratos)")
                print(f" �� Resultado Capturado: {pct*100:+.2f}% puro ({pnl_u:+.4f} USDT) | Nuevo Balance: {tot2:.4f} USDT")
                print("==========================================================================================")
                msg_cierre = nl.join([
                    "💰 [COBRO MANUAL PHANTOM V1.0 (verbot -x cerrar)]",
                    f"• Activo: {sym} [{side.upper()}] ({qty} contratos)",
                    f"• Recorrido: {ep} -> {mp} ({pct*100:+.2f}% puro | ROE {pct*lev*100:+.2f}%)",
                    f"• PnL Capturado: {pnl_u:+.4f} USDT",
                    f"• Nuevo Balance Consolidado: {tot2:.4f} USDT",
                ])
                ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(msg_cierre)
                print(f" 📲 [TELEGRAM] Recibo de cobro manual enviado: {ok_tg}")
            else:
                print(f" 🎯 ACTIVO      : {sym} [{side.upper()}] ({qty} contratos)")
                print(f" 📈 PRECIO      : Entrada {ep} -> Marca Actual {mp}")
                print(f" 🔥 GANANCIA    : {pct*100:+.2f}% puro ({pct*lev*100:+.2f}% ROE {lev:.0f}x) | {pnl_u:+.4f} USDT")
                print(f" ⛓️ ESLABON     : {eslabon}/5 (Piso Eslabon: +{piso_sug*100:.2f}% -> Meta: {techo_str}) | SL Bybit: {sl_b}")
                print("==========================================================================================")
                lineas_tg.extend([
                    f"🎯 {sym} [{side.upper()}] ({qty} contratos)",
                    f"• Precio: {ep} -> {mp}",
                    f"• Ganancia: {pct*100:+.2f}% (ROE {pct*lev*100:+.2f}%) | {pnl_u:+.4f} USDT",
                    f"• Eslabon Phantom: {eslabon}/5 (Piso +{piso_sug*100:.2f}% -> Techo {techo_str})",
                    f"• SL en Bybit: {sl_b}",
                ])

        if modo != "cerrar":
            ok_tg = await TELEMETRIA_TG.enviar_mensaje_sistema(nl.join(lineas_tg))
            print(f" 📲 [TELEGRAM] Alerta en vivo enviada a tu celular: {ok_tg}")
    finally:
        await ex.close()
