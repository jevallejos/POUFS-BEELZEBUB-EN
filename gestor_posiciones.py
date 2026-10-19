#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #10: gestor_posiciones.py
SISTEMA: TRI-BRAIN-SNIPER (EMPEROR TIME) V1.0 â€” ESTRATEGIA CHRONOS-TRIZ
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
            f"[FRANCOTIRADOR] ðŸ›¡ï¸ {pos.symbol} Trinquete Break-Even armado: "
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
                f"[FRANCOTIRADOR] ðŸ§² {pos.symbol} Trailing Stop activado (PnL {pnl_bruto_pct*100:+.2f}%)"
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
                    f"âœ‚ï¸ [MAKER-SCRATCH 18s] {pos.symbol} sin rebote tras {edad_seg:.1f}s "
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