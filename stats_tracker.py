#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #06: stats_tracker.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor Contable de Caja Negra (tribrain_stats_v1.jsonl), Paridad 1:1 Bybit UTA,
Calculo de MAP, LVR (Milionis-Moallemi-Roughgarden), Velocidad Geometrica g*
y Gancho de Respaldo Contable hacia Telegram (Single-Layer Nativo).
==============================================================================
"""
from __future__ import annotations

import json
import math
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config_parametros as cfg
from core_estado_ram import (
    ESTADO_RAM,
    PosicionActiva,
    RegistroOperacionCerrada,
    log_sniper,
)
from telemetria_telegram import TELEMETRIA_TG


class GestorCajaNegra:
    """
    Libro mayor transaccional con paridad 1:1 frente a Bybit UTA,
    blindaje anti-doble-contabilizacion y auditoria de integridad JSONL.
    """

    def __init__(self, ruta_jsonl: Optional[pathlib.Path] = None) -> None:
        self.ruta_jsonl: pathlib.Path = ruta_jsonl or (cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL)
        self.capital_base_usdt: float = cfg.CAPITAL_BASE_USDT
        self.operaciones: List[Dict[str, Any]] = []
        self.trades_totales: int = 0
        self.wins: int = 0
        self.losses: int = 0
        self.scratches_18s: int = 0
        self.pnl_total_usdt: float = 0.0
        self.mejor_trade_usdt: float = 0.0
        self.peor_trade_usdt: float = 0.0
        self.map_promedio_usdt: float = 0.0
        self.lvr_acumulado_usdt: float = 0.0
        self.cargar_y_auditar_historial()

    def auditar_y_desduplicar_jsonl(self) -> int:
        """
        Inspecciona el archivo JSONL, normaliza cualquier hold_seg > 86400s
        y elimina registros duplicados fantasma (mismo symbol, side, entry_price
        y exit_price en <= 2.5 segundos).
        """
        if not self.ruta_jsonl.exists():
            return 0

        lineas_limpias: List[str] = []
        vistos: List[tuple[str, str, float, float, float]] = []
        eliminados = 0
        modificados_hold = 0

        try:
            for linea in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                linea_str = linea.strip()
                if not linea_str:
                    continue
                try:
                    obj = json.loads(linea_str)
                except Exception:
                    continue

                if float(obj.get("hold_seg") or 0.0) > 86400.0:
                    obj["hold_seg"] = 28.0
                    modificados_hold += 1

                sym = str(obj.get("symbol") or "")
                side = str(obj.get("side") or "long")
                ep = round(float(obj.get("entry_price") or 0.0), 8)
                xp = round(float(obj.get("exit_price") or 0.0), 8)
                ts_str = str(obj.get("timestamp") or "")
                try:
                    ts_epoch = datetime.fromisoformat(ts_str).timestamp()
                except Exception:
                    ts_epoch = 0.0

                es_duplicado = False
                for v_sym, v_side, v_ep, v_xp, v_ts in vistos:
                    if v_sym == sym and v_side == side and v_ep == ep and v_xp == xp:
                        if abs(ts_epoch - v_ts) <= 2.5:
                            es_duplicado = True
                            break

                if es_duplicado:
                    eliminados += 1
                else:
                    vistos.append((sym, side, ep, xp, ts_epoch))
                    lineas_limpias.append(json.dumps(obj, ensure_ascii=False))

            if eliminados > 0 or modificados_hold > 0:
                contenido = ("\n".join(lineas_limpias) + "\n") if lineas_limpias else ""
                self.ruta_jsonl.write_text(contenido, encoding="utf-8")
                if eliminados > 0:
                    log_sniper(
                        f"[CAJA NEGRA] Auditoria JSONL elimino {eliminados} registro(s) duplicado(s) en {self.ruta_jsonl.name}."
                    )
        except Exception as exc:
            log_sniper(f"[WARN] [CAJA NEGRA] Error auditando JSONL: {exc}")

        return eliminados

    def cargar_y_auditar_historial(self) -> None:
        """Recarga el estado contable acumulado desde el archivo JSONL."""
        self.auditar_y_desduplicar_jsonl()
        self.operaciones.clear()
        self.trades_totales = 0
        self.wins = 0
        self.losses = 0
        self.scratches_18s = 0
        self.pnl_total_usdt = 0.0
        self.mejor_trade_usdt = 0.0
        self.peor_trade_usdt = 0.0
        self.lvr_acumulado_usdt = 0.0
        suma_map = 0.0

        if not self.ruta_jsonl.exists():
            self.map_promedio_usdt = 0.0
            return

        try:
            for linea in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                if not linea.strip():
                    continue
                op = json.loads(linea)
                self.operaciones.append(op)
                pnl_u = float(op.get("pnl_usdt") or 0.0)
                motivo = str(op.get("motivo") or "")
                map_u = float(
                    op.get("map_usdt")
                    or (float(op.get("qty") or 0.0) * float(op.get("entry_price") or 0.0))
                )
                lvr_u = float(op.get("lvr_usdt") or 0.0)

                self.trades_totales += 1
                self.pnl_total_usdt += pnl_u
                self.lvr_acumulado_usdt += lvr_u
                suma_map += map_u

                if pnl_u >= 0.0:
                    self.wins += 1
                else:
                    self.losses += 1
                    if "SCRATCH" in motivo.upper():
                        self.scratches_18s += 1

                if self.trades_totales == 1:
                    self.mejor_trade_usdt = pnl_u
                    self.peor_trade_usdt = pnl_u
                else:
                    self.mejor_trade_usdt = max(self.mejor_trade_usdt, pnl_u)
                    self.peor_trade_usdt = min(self.peor_trade_usdt, pnl_u)

            self.map_promedio_usdt = (suma_map / self.trades_totales) if self.trades_totales > 0 else 0.0
        except Exception as exc:
            log_sniper(f"[WARN] [CAJA NEGRA] Error cargando historial: {exc}")

    cargar_historial = cargar_y_auditar_historial

    @staticmethod
    def calcular_lvr_operacion(map_usdt: float, volatilidad_local: float, hold_seg: float) -> float:
        sigma = max(0.0005, float(volatilidad_local or 0.0020))
        t_horas = max(0.0, float(hold_seg)) / 3600.0
        return round(0.125 * (sigma ** 2) * float(map_usdt) * t_horas, 6)

    def registrar_cosecha_parcial_50(
        self,
        pos: PosicionActiva,
        qty_cerrada: float,
        exit_price: float,
        es_maker: bool = True,
    ) -> float:
        qty_c = float(qty_cerrada)
        ep = float(pos.entry_price)
        xp = float(exit_price)
        nocional_entrada = qty_c * ep
        nocional_salida = qty_c * xp

        if pos.side == "short":
            pnl_bruto = nocional_entrada - nocional_salida
        else:
            pnl_bruto = nocional_salida - nocional_entrada

        fee_in = nocional_entrada * cfg.FEE_MAKER_PCT
        fee_out = nocional_salida * (cfg.FEE_MAKER_PCT if es_maker else cfg.FEE_TAKER_PCT)
        fees_tramo = fee_in + fee_out
        pnl_neto_tramo = pnl_bruto - fees_tramo

        pos.cosecha_50_ejecutada = True
        pos.pnl_realizado_parcial_usdt += pnl_neto_tramo
        pos.fees_acumulados_usdt += fees_tramo
        pos.qty_actual = max(0.0, pos.qty_actual - qty_c)
        return round(pnl_neto_tramo, 6)

    async def registrar_cierre_posicion(
        self,
        pos: PosicionActiva,
        exit_price: float,
        motivo: str,
        es_salida_maker: bool = False,
        ahora: Optional[float] = None,
    ) -> Optional[RegistroOperacionCerrada]:
        if pos.cerrada:
            return None
        pos.cerrada = True

        t_cierre = ahora if ahora is not None else time.time()
        hold_seg = round(max(0.1, t_cierre - float(pos.ts_apertura)), 1)

        ep = float(pos.entry_price)
        xp = float(exit_price)
        qty_rem = float(pos.qty_actual if pos.qty_actual > 0.0 else pos.qty_inicial)
        qty_total_original = float(pos.qty_inicial if pos.qty_inicial > 0.0 else qty_rem)

        nocional_rem_in = qty_rem * ep
        nocional_rem_out = qty_rem * xp
        if pos.side == "short":
            pnl_bruto_rem = nocional_rem_in - nocional_rem_out
        else:
            pnl_bruto_rem = nocional_rem_out - nocional_rem_in

        fee_in_rem = nocional_rem_in * cfg.FEE_MAKER_PCT
        fee_out_rem = nocional_rem_out * (cfg.FEE_MAKER_PCT if es_salida_maker else cfg.FEE_TAKER_PCT)
        fees_rem = fee_in_rem + fee_out_rem
        pnl_neto_rem = pnl_bruto_rem - fees_rem

        pnl_neto_total_usdt = round(float(pos.pnl_realizado_parcial_usdt) + pnl_neto_rem, 6)
        fees_totales_usdt = round(float(pos.fees_acumulados_usdt) + fees_rem, 6)
        map_usdt = round(qty_total_original * ep, 4)
        pnl_pct_neto = round((pnl_neto_total_usdt / map_usdt) * 100.0, 4) if map_usdt > 0.0 else 0.0
        lvr_usdt = self.calcular_lvr_operacion(map_usdt, pos.volatilidad_entry, hold_seg)

        ts_iso = datetime.fromtimestamp(t_cierre, tz=timezone.utc).isoformat(timespec="seconds")
        registro = RegistroOperacionCerrada(
            timestamp=ts_iso,
            symbol=pos.symbol,
            side=pos.side,
            z_score_entry=round(float(pos.z_score_entry), 4) if pos.z_score_entry else None,
            ofi_entry=round(float(pos.ofi_entry), 4) if pos.ofi_entry else None,
            hurst_entry=round(float(pos.hurst_entry), 4) if pos.hurst_entry else None,
            pnl_percentage=pnl_pct_neto,
            pnl_usdt=pnl_neto_total_usdt,
            entry_price=ep,
            exit_price=xp,
            qty=qty_total_original,
            motivo=str(motivo),
            hold_seg=hold_seg,
            fees_usdt=fees_totales_usdt,
            map_usdt=map_usdt,
            lvr_usdt=lvr_usdt,
            cosecha_triz_50=bool(pos.cosecha_50_ejecutada),
        )

        try:
            with open(self.ruta_jsonl, "a", encoding="utf-8") as f_out:
                f_out.write(json.dumps(registro.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            log_sniper(f"[WARN] [CAJA NEGRA] Error escribiendo en {self.ruta_jsonl.name}: {exc}")

        prev_suma_map = self.map_promedio_usdt * self.trades_totales
        self.operaciones.append(registro.to_dict())
        self.trades_totales += 1
        self.pnl_total_usdt = round(self.pnl_total_usdt + pnl_neto_total_usdt, 6)
        self.lvr_acumulado_usdt = round(self.lvr_acumulado_usdt + lvr_usdt, 6)
        self.map_promedio_usdt = (prev_suma_map + map_usdt) / self.trades_totales

        if pnl_neto_total_usdt >= 0.0:
            self.wins += 1
        else:
            self.losses += 1
            if "SCRATCH" in str(motivo).upper():
                self.scratches_18s += 1

        if self.trades_totales == 1:
            self.mejor_trade_usdt = pnl_neto_total_usdt
            self.peor_trade_usdt = pnl_neto_total_usdt
        else:
            self.mejor_trade_usdt = max(self.mejor_trade_usdt, pnl_neto_total_usdt)
            self.peor_trade_usdt = min(self.peor_trade_usdt, pnl_neto_total_usdt)

        icono = "[WIN]" if pnl_neto_total_usdt >= 0.0 else ("[SCRATCH]" if "SCRATCH" in str(motivo).upper() else "[LOSS]")
        lado_str = " SHORT" if pos.side == "short" else ""
        log_sniper(
            f"[FRANCOTIRADOR] {icono} CIERRE{lado_str} {pos.symbol} [{motivo}] "
            f"{ep} -> {xp} | {pnl_pct_neto:+.2f} % ({pnl_neto_total_usdt:+.4f} USDT) en {hold_seg:.0f}s"
        )
        self.imprimir_panel_caja_negra()

        await TELEMETRIA_TG.enviar_cierre_garantizado(
            symbol=pos.symbol,
            side=pos.side,
            pnl_pct=pnl_pct_neto,
            pnl_usdt=pnl_neto_total_usdt,
            hold_seg=hold_seg,
            motivo=motivo,
            entry_price=ep,
            exit_price=xp,
            cosecha_50_previa=pos.cosecha_50_ejecutada,
        )

        return registro

    def calcular_velocidad_geometrica_g(self, ultimos_n: int = 20) -> float:
        muestra = self.operaciones[-ultimos_n:] if self.operaciones else []
        if not muestra:
            return 0.0
        suma_log = 0.0
        suma_t = 0.0
        for op in muestra:
            ret_rel = float(op.get("pnl_usdt") or 0.0) / max(1.0, self.capital_base_usdt)
            suma_log += math.log(max(0.01, 1.0 + ret_rel))
            suma_t += max(1.0, float(op.get("hold_seg") or 60.0))
        return (suma_log / (suma_t / 3600.0)) if suma_t > 0.0 else 0.0

    def imprimir_panel_caja_negra(self) -> None:
        wr = (self.wins / self.trades_totales * 100.0) if self.trades_totales > 0 else 0.0
        bal_contable = self.capital_base_usdt + self.pnl_total_usdt
        bal_real = ESTADO_RAM.patrimonio_total_usdt if ESTADO_RAM.patrimonio_total_usdt > 0 else bal_contable
        pnl_map_ratio = (self.pnl_total_usdt / self.map_promedio_usdt) if self.map_promedio_usdt > 0.0 else 0.0

        l1 = "╔══════ [CAJA NEGRA] TRI-BRAIN-PHANTOM V1.0 [GOD'S ACCOMPLICE] ═══════╗"
        l2 = f"║ Trades: {self.trades_totales:<3d} (W {self.wins} / L {self.losses} / S {self.scratches_18s}) | Win Rate: {wr:5.1f} %".ljust(65) + "║"
        l3 = f"║ PnL total: {self.pnl_total_usdt:+.4f} USDT   mejor {self.mejor_trade_usdt:+.4f} / peor {self.peor_trade_usdt:+.4f}".ljust(65) + "║"
        l4 = f"║ MAP: {self.map_promedio_usdt:5.2f} USDT | PnL/MAP: {pnl_map_ratio:+.4f} | LVR: {self.lvr_acumulado_usdt:.4f}".ljust(65) + "║"
        l5 = f"║ Balance: {bal_contable:.4f} USDT (base {self.capital_base_usdt:.2f})   real: {bal_real:.4f} USDT".ljust(65) + "║"
        l6 = "╚════════════════════════════════════════════════════════════════╝"

        for linea in (l1, l2, l3, l4, l5, l6):
            log_sniper(linea)


CAJA_NEGRA: GestorCajaNegra = GestorCajaNegra()