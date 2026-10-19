#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #10: gestor_posiciones.py
SISTEMA: TRI-BRAIN-SNIPER (CHAIN-JAIL) V2.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Guardian de Geometria de Pagos 10/10 con Protocolo "FREE-RUNNER 50%":
  - Ley 2 (CHRONOS-TRIZ): Desplazamiento del Precio de Reserva a los 18.0s
    (Avellaneda-Stoikov Maker-Scratch) para evacuar tesis estancadas entre
    -0.04% y -0.14% Maker antes de que toquen el Stop-Loss.
  - Ley 3 (CHRONOS-TRIZ + FREE-RUNNER 50%):
      * En +0.26% bruto vende el primer 50% mediante Limit PostOnly (pagando
        todas las comisiones de la operacion).
      * El segundo 50% entra en modo FREE-RUNNER: sin limite de tiempo (apaga
        el corte de 32s y el de 90s), con SL de holgura anti-ruido (+0.05%
        interno / +0.03% en servidor Bybit) y Trailing Stop escalonado que
        persigue corridas de +1%, +3%, +8%+ sincronizando el SL en Bybit.
  - Evacuacion Direccional Inteligente: Ante contagio macro o crash de BTC,
    evacua posiciones LONG pero mantiene abiertas las posiciones SHORT.
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
    y dejar al menos +0.12% de ganancia neta positiva cuando el 100% del lote sigue abierto.
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


def calcular_piso_free_runner_50(
    side: str, entry_price: float, tick_size: float
) -> Tuple[float, float]:
    """
    Calcula (sl_interno_runner, sl_bybit_runner) para el segundo 50% una vez que
    el primer 50% ya fue cosechado en efectivo (+0.26%+). Otorga holgura anti-ruido
    (+0.05% interno / +0.03% servidor Bybit, minimo 1 tick a favor) para evitar
    que el ruido del spread expulse al Runner antes de capturar tendencias largas.
    """
    ep = float(entry_price)
    tick = max(1e-8, float(tick_size or 0.00001))
    decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0
    holgura_int = getattr(cfg, "FREE_RUNNER_SL_HOLGURA_PCT", 0.0005)
    holgura_byb = max(0.0003, holgura_int * 0.60)

    if str(side).lower() == "short":
        sl_int = round(min(ep - tick, ep * (1.0 - holgura_int)), decimales)
        sl_byb = round(min(ep - tick, ep * (1.0 - holgura_byb)), decimales)
    else:
        sl_int = round(max(ep + tick, ep * (1.0 + holgura_int)), decimales)
        sl_byb = round(max(ep + tick, ep * (1.0 + holgura_byb)), decimales)

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
      - Si permitir_scratch=False: impone el piso >= entry_price * (1 + PISO_MAKER_BRUTO_MIN_PCT).
      - Si permitir_scratch=True (Maker-Scratch 18s): cotiza en best_ask (Long) o best_bid (Short).
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

    candidato = max(ask, bid + tick) if ask > bid else ask
    if not permitir_scratch:
        piso_ganador = ep * (1.0 + cfg.PISO_MAKER_BRUTO_MIN_PCT)
        candidato = max(candidato, piso_ganador)
    return round(candidato, decimales)


# ==============================================================================
# 2. MOTOR GESTOR DE POSICIONES (CHRONOS-TRIZ & FREE-RUNNER 50%)
# ==============================================================================

def calcular_eslabon_chain_jail(pnl_max_pct: float) -> tuple[int, float, bool]:
    """
    Escalera matematica fria del Protocolo Chain-Jail v2.0 sobre el 25% final:
      - Eslabon 5 (>= +8.00%): Guillotina Take-Profit duro inmediato (+8.00%).
      - Eslabon 4 (>= +4.50%): Hiper-compresion a 0.25% de distancia del pico.
      - Eslabon 3 (>= +2.55%): Meta +2% extra -> Piso minimo +2.20%, cadena a 0.35%.
      - Eslabon 2 (>= +1.60%): Escudo Tier-1  -> Piso minimo +1.15%, cadena a 0.45%.
      - Eslabon 1 (>= +0.90%): Candado +0.55% -> Prohibido retroceder bajo +0.55%.
      - Eslabon 0 (<  +0.90%): Zona Oxigeno   -> Piso en +0.15% para soportar rebote.
    Retorna: (eslabon_id, piso_sl_pct, cerrar_por_techo_8pct)
    """
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


class GestorPosiciones:
    """
    Gobierna el ciclo de vida de cada PosicionActiva en memoria RAM a 6.6 Hz.
    Ejecuta la Cosecha 50/50 TRIZ, el protocolo Free-Runner 50% sin limite de tiempo,
    la evacuacion Maker-Scratch a los 18s y las barreras de Stop-Loss Quirurgico.
    """

    def __init__(self, exchange: Any = None) -> None:
        self.exchange: Any = exchange
        self._running: bool = False

    async def armar_proteccion_inicial_bybit(self, pos: PosicionActiva) -> bool:
        """Sincroniza el Stop-Loss inicial de servidor Bybit (-0.70%) al abrirse la posicion."""
        if self.exchange is None or pos.cerrada:
            return False
        pos.sl_bybit_ultimo_sync_price = pos.sl_bybit_price
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
        pos.sl_bybit_ultimo_sync_price = float(nuevo_sl_bybit)
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
                if "110017" in err_str or "reduce-only" in err_str.lower() or "zero position" in err_str.lower():
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
        Ley 3 de CHRONOS-TRIZ + Activacion de FREE-RUNNER 50%:
        1. Si el lote es divisible en dos mitades >= min_qty, vende el primer 50%
           en Limit PostOnly (+0.26%+), asegurando caja y cubriendo todas las comisiones.
        2. Sincroniza el SL del segundo 50% (Free-Runner) con holgura anti-ruido
           (+0.05% interno / +0.03% Bybit) para que pueda correr sin limite de tiempo.
        3. Si el lote no era divisible, blinda el 100% en el Piso Invariante BE (+0.16% / +0.12%).
        """
        pnl_actual_pct = pos.calcular_pnl_bruto_pct(best_bid if pos.side == "long" else best_ask)
        mitad_qty = redondear_cantidad_lote(pos.qty_actual * cfg.COSECHA_TRIZ_FRACCION, step_qty, min_qty)
        rem_qty = round(pos.qty_actual - mitad_qty, 8)

        # Caso A: Lote indivisible -> Blindar el 100% con el Piso Invariante Break-Even completo
        if mitad_qty < min_qty or rem_qty < min_qty:
            sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
                pos.side, pos.entry_price, tick_size
            )
            pos.sl_interno_price = sl_int_be
            pos.trinquete_be_armado = True
            pos.cosecha_50_ejecutada = True
            log_sniper(
                f"[FRANCOTIRADOR] 🛡️ {pos.symbol} Lote indivisible blindado en Break-Even: "
                f"SL {sl_int_be} (PnL {pnl_actual_pct*100:+.2f}%)"
            )
            await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)
            return False

        # Caso B: Lote divisible -> Ejecutar Cosecha 50% PostOnly y activar Free-Runner 50%
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
                sl_int_be, sl_byb_be = calcular_piso_invariante_breakeven(
                    pos.side, pos.entry_price, tick_size
                )
                pos.sl_interno_price = sl_int_be
                pos.trinquete_be_armado = True
                pos.cosecha_50_ejecutada = True
                await self._ajustar_sl_servidor_bybit(pos, sl_byb_be)
                return False

        pnl_parcial_usdt = CAJA_NEGRA.registrar_cosecha_parcial_50(
            pos=pos,
            qty_cerrada=mitad_qty,
            exit_price=precio_cosecha,
            es_maker=True,
        )
        nocional_mitad = mitad_qty * pos.entry_price
        pnl_parcial_pct = (pnl_parcial_usdt / nocional_mitad * 100.0) if nocional_mitad > 0.0 else 0.0

        sl_int_runner, sl_byb_runner = calcular_piso_free_runner_50(
            pos.side, pos.entry_price, tick_size
        )
        pos.sl_interno_price = sl_int_runner
        pos.trinquete_be_armado = True

        log_sniper(
            f"[FRANCOTIRADOR] 🛡️ {pos.symbol} Trinquete Free-Runner armado: "
            f"SL {sl_int_runner} (PnL {pnl_actual_pct*100:+.2f}%)"
        )
        await self._ajustar_sl_servidor_bybit(pos, sl_byb_runner)

        log_sniper(
            f"[FRANCOTIRADOR] 💎 {pos.symbol} Cosecha 50% TRIZ PostOnly ejecutada: "
            f"{mitad_qty} @ {precio_cosecha} ({pnl_parcial_pct:+.2f}% | {pnl_parcial_usdt:+.4f} USDT). "
            f"Restan {pos.qty_actual} contratos en FREE-RUNNER (sin limite de tiempo)."
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
        Evalua en O(1) las barreras de salida de una PosicionActiva bajo CHRONOS-TRIZ
        y el protocolo FREE-RUNNER 50%.
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
        # 1. BARRERA STOP-LOSS QUIRURGICO INTERNO (-0.48% o Trinquete BE/Runner)
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
        # 2. LEY 3 (CHRONOS-TRIZ): COSECHA 50/50 (+0.26%) + FREE-RUNNER 50%
        # ======================================================================
        if pnl_bruto_pct >= cfg.COSECHA_TRIZ_ACTIVACION_PCT and not pos.cosecha_50_ejecutada:
            await self._ejecutar_cosecha_50_triz(
                pos, best_bid, best_ask, tick_size, step_qty, min_qty
            )

        # Activar Trailing Stop de expansion libre en +0.65%
        if pnl_bruto_pct >= cfg.TRAILING_ACTIVACION_PCT and not pos.trailing_activo:
            pos.trailing_activo = True
            log_sniper(
                f"[FRANCOTIRADOR] 🧲 {pos.symbol} Trailing Stop Free-Runner activado (PnL {pnl_bruto_pct*100:+.2f}%)"
            )

        # Gobernanza del Segundo 50% en modo FREE-RUNNER:
        if pos.trailing_activo:
            pos.trinquete_ratchet_activo = True
            retroceso = pos.max_pnl_pct_alcanzado - pnl_bruto_pct
            flujo_agotado_fuerte = (
                (pos.side == "long" and tk.ofi_l1_l5 <= -0.10 and retroceso >= 0.0008)
                or (pos.side == "short" and tk.ofi_l1_l5 >= 0.10 and retroceso >= 0.0008)
            )
            decimales = max(0, int(round(-math.log10(tick_size)))) if tick_size < 1.0 else 0
            piso_trail_pct = max(0.0020, pos.max_pnl_pct_alcanzado - cfg.TRAILING_DISTANCIA_PCT)

            if pos.side == "short":
                nuevo_sl_runner = round(pos.entry_price * (1.0 - piso_trail_pct), decimales)
                if nuevo_sl_runner < pos.sl_interno_price:
                    pos.sl_interno_price = nuevo_sl_runner
                    if pos.sl_bybit_ultimo_sync_price <= 0.0 or (
                        (pos.sl_bybit_ultimo_sync_price - nuevo_sl_runner) / pos.entry_price >= 0.0025
                    ):
                        await self._ajustar_sl_servidor_bybit(pos, nuevo_sl_runner)
            else:
                nuevo_sl_runner = round(pos.entry_price * (1.0 + piso_trail_pct), decimales)
                if nuevo_sl_runner > pos.sl_interno_price:
                    pos.sl_interno_price = nuevo_sl_runner
                    if pos.sl_bybit_ultimo_sync_price <= 0.0 or (
                        (nuevo_sl_runner - pos.sl_bybit_ultimo_sync_price) / pos.entry_price >= 0.0025
                    ):
                        await self._ajustar_sl_servidor_bybit(pos, nuevo_sl_runner)

            if (retroceso >= cfg.TRAILING_DISTANCIA_PCT or flujo_agotado_fuerte) and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT:
                precio_ratchet = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                )
                await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=precio_ratchet,
                    motivo="TRAILING_RATCHET_MAKER",
                    es_maker=True,
                    ahora=t_now,
                )
                return "TRAILING_RATCHET_MAKER"
        elif not pos.cosecha_50_ejecutada and pos.max_pnl_pct_alcanzado >= cfg.TRINQUETE_RATCHET_ACTIVACION_PCT:
            pos.trinquete_ratchet_activo = True
            retroceso = pos.max_pnl_pct_alcanzado - pnl_bruto_pct
            if retroceso >= 0.0014 and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT:
                precio_ratchet = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
                )
                await self._ejecutar_cierre_definitivo(
                    pos=pos,
                    precio_ejecucion=precio_ratchet,
                    motivo="TRINQUETE_RATCHET_MAKER",
                    es_maker=True,
                    ahora=t_now,
                )
                return "TRINQUETE_RATCHET_MAKER"

        # ======================================================================
        # 3. LEY 2 (CHRONOS-TRIZ): EVACUACION MAKER-SCRATCH (VENTANA 18S A 65S)
        # ======================================================================
        if (
            cfg.MAKER_SCRATCH_TIEMPO_SEG <= edad_seg <= 65.0
            and not pos.scratch_18s_evaluado
            and not pos.cosecha_50_ejecutada
        ):
            flujo_5s_adverso = (
                (pos.side == "long" and tk.ofi_5s <= cfg.MAKER_SCRATCH_OFI_UMBRAL)
                or (pos.side == "short" and tk.ofi_5s >= abs(cfg.MAKER_SCRATCH_OFI_UMBRAL))
            )
            if (
                pos.max_pnl_pct_alcanzado <= cfg.MAKER_SCRATCH_PNL_MAX_PCT
                and flujo_5s_adverso
                and cfg.MAKER_SCRATCH_MAX_LOSS_PCT <= pnl_bruto_pct < 0.0
            ):
                pos.scratch_18s_evaluado = True
                pos.scratch_18s_activo = True
                precio_scratch = calcular_precio_salida_maker_seguro(
                    pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=True
                )
                log_sniper(
                    f"✂️ [MAKER-SCRATCH 18s] {pos.symbol} sin rebote tras {edad_seg:.1f}s "
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
        # 4. ESCUDO FASE 2 (> 32S): SOLO SI AUN NO SE HA EJECUTADO COSECHA 50%
        # ======================================================================
        if (
            not pos.cosecha_50_ejecutada
            and edad_seg >= cfg.ESCUDO_MAKER_FASE2_SEG
            and pnl_bruto_pct >= cfg.PISO_MAKER_BRUTO_MIN_PCT
        ):
            precio_fase2 = calcular_precio_salida_maker_seguro(
                pos.side, pos.entry_price, best_bid, best_ask, tick_size, permitir_scratch=False
            )
            log_sniper(
                f"[FRANCOTIRADOR] 💎 {pos.symbol} Escudo Maker Fase 2 PostOnly ejecutado @ {precio_fase2} "
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
        # 5. RELOJ IMPOSTERGABLE DE 90S (DESACTIVADO EN MODO FREE-RUNNER 50%)
        # ======================================================================
        if pos.cosecha_50_ejecutada and pos.trinquete_be_armado:
            return None

        if edad_seg >= cfg.TIEMPO_MAX_HOLD_SEG:
            log_sniper(
                f"⌛ [FRANCOTIRADOR] {pos.symbol} alcanzo tiempo limite ({edad_seg:.0f}s >= {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s). "
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
        """
        Evacua inmediatamente las posiciones LONG ante un desplome del Cortafuegos Macro.
        Protege y mantiene abiertas las posiciones SHORT, ya que un colapso del mercado
        juega directamente a favor de un SHORT (evitando cerrar ganancias en ARB/TAO).
        """
        cerradas = 0
        ahora = time.time()
        for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
            if pos.cerrada:
                continue
            if pos.side == "short" and "CONTAGIO" in str(motivo).upper():
                log_sniper(
                    f"🛡️ [FREE-RUNNER SHORT] Manteniendo {sym} [SHORT] abierto durante {motivo} (desplome a favor)."
                )
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
                log_sniper(f"⚠️ [GESTOR POSICIONES] Error en ciclo de vigilancia: {exc}")
            await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)

    def detener(self) -> None:
        self._running = False
