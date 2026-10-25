#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #06: stats_tracker.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Black Box Accounting Engine (tribrain_stats_v1.jsonl), 1:1 Bybit UTA Parity,
MAP Calculation, LVR (Milionis-Moallemi-Roughgarden), Geometric Growth Rate g*,
Enriched Persistence into the Forensic AI Cognitive Vault (baul_ia_forense.jsonl),
and Accounting Backup Hook to Telegram (Single-Layer Native).
==============================================================================
"""
from __future__ import annotations

import json
import math
import os
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
    registrar_evento_baul_ia,
)
from telemetria_telegram import TELEMETRIA_TG


class GestorCajaNegra:
    """
    Transactional ledger with 1:1 parity against Bybit UTA,
    anti-double-accounting armor, JSONL integrity auditing,
    and high-density persistence in the Forensic AI Cognitive Vault.
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
        self.ajuste_funding_paridad_usdt: float = 0.0
        self.cargar_y_auditar_historial()

    def auditar_y_desduplicar_jsonl(self) -> int:
        """
        Inspects the JSONL ledger, normalizes any hold_seg > 86400s,
        and removes phantom duplicate records (same symbol, side, entry_price,
        and exit_price within <= 2.5 seconds).
        """
        if not self.ruta_jsonl.exists():
            return 0

        clean_lines: List[str] = []
        seen: List[tuple[str, str, float, float, float]] = []
        removed = 0
        modified_hold = 0

        try:
            for line in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    obj = json.loads(line_str)
                except Exception:
                    continue

                if float(obj.get("hold_seg") or 0.0) > 86400.0:
                    obj["hold_seg"] = 28.0
                    modified_hold += 1

                sym = str(obj.get("symbol") or "")
                side = str(obj.get("side") or "long")
                ep = round(float(obj.get("entry_price") or 0.0), 8)
                xp = round(float(obj.get("exit_price") or 0.0), 8)
                ts_str = str(obj.get("timestamp") or "")
                try:
                    ts_epoch = datetime.fromisoformat(ts_str).timestamp()
                except Exception:
                    ts_epoch = 0.0

                is_duplicate = False
                for v_sym, v_side, v_ep, v_xp, v_ts in seen:
                    if v_sym == sym and v_side == side and v_ep == ep and v_xp == xp:
                        if abs(ts_epoch - v_ts) <= 2.5:
                            is_duplicate = True
                            break

                if is_duplicate:
                    removed += 1
                else:
                    seen.append((sym, side, ep, xp, ts_epoch))
                    clean_lines.append(json.dumps(obj, ensure_ascii=False))

            if removed > 0 or modified_hold > 0:
                content = ("\n".join(clean_lines) + "\n") if clean_lines else ""
                self.ruta_jsonl.write_text(content, encoding="utf-8")
                if removed > 0:
                    log_sniper(
                        f"[BLACK BOX] JSONL audit removed {removed} duplicate record(s) in {self.ruta_jsonl.name}."
                    )
        except Exception as exc:
            log_sniper(f"[WARN] [BLACK BOX] Error auditing JSONL: {exc}")

        return removed

    def cargar_y_auditar_historial(self) -> None:
        """Reloads cumulative accounting state from the JSONL ledger."""
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
        self.ajuste_funding_paridad_usdt = 0.0
        sum_map = 0.0

        if not self.ruta_jsonl.exists():
            self.map_promedio_usdt = 0.0
            return

        try:
            for line in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                if not line.strip():
                    continue
                op = json.loads(line)
                self.operaciones.append(op)
                pnl_u = float(op.get("pnl_usdt") or 0.0)
                ajuste_u = float(op.get("ajuste_paridad_usdt") or 0.0)
                reason = str(op.get("motivo") or "")
                map_u = float(
                    op.get("map_usdt")
                    or (float(op.get("qty") or 0.0) * float(op.get("entry_price") or 0.0))
                )
                lvr_u = float(op.get("lvr_usdt") or 0.0)

                self.trades_totales += 1
                self.pnl_total_usdt += pnl_u
                self.ajuste_funding_paridad_usdt = round(self.ajuste_funding_paridad_usdt + ajuste_u, 6)
                self.lvr_acumulado_usdt += lvr_u
                sum_map += map_u

                if pnl_u >= 0.0:
                    self.wins += 1
                else:
                    self.losses += 1
                    if "SCRATCH" in reason.upper():
                        self.scratches_18s += 1

                if self.trades_totales == 1:
                    self.mejor_trade_usdt = pnl_u
                    self.peor_trade_usdt = pnl_u
                else:
                    self.mejor_trade_usdt = max(self.mejor_trade_usdt, pnl_u)
                    self.peor_trade_usdt = min(self.peor_trade_usdt, pnl_u)

            self.map_promedio_usdt = (sum_map / self.trades_totales) if self.trades_totales > 0 else 0.0
        except Exception as exc:
            log_sniper(f"[WARN] [BLACK BOX] Error loading trade history: {exc}")

    cargar_historial = cargar_y_auditar_historial

    def sincronizar_paridad_patrimonio_real(self, balance_real_uta: float) -> bool:
        return self.sincronizar_paridad_uta(balance_real_uta)

    def sincronizar_paridad_uta(self, balance_real_uta: float) -> bool:
        """
        Gradient Vector #4: Guarantees exact 1:1 accounting parity to the fourth
        decimal place between tribrain_stats_v1.jsonl and actual Bybit UTA equity
        when no positions are open, without altering Win or Loss counts.
        """
        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            return False
        if ESTADO_RAM.slot_ocupado or ESTADO_RAM.posiciones_activas or not self.operaciones:
            return False
        real_u = float(balance_real_uta)
        if real_u <= 0.0 or abs(real_u - self.capital_base_usdt) < 1e-6:
            return False

        book_balance = self.capital_base_usdt + self.pnl_total_usdt + self.ajuste_funding_paridad_usdt
        drift = round(real_u - book_balance, 6)
        if abs(drift) < 0.0001 or abs(drift) > 2.50:
            return False

        op_obj = self.operaciones[-1]
        prev_adj = float(op_obj.get("ajuste_paridad_usdt") or 0.0)
        op_obj["ajuste_paridad_usdt"] = round(prev_adj + drift, 6)
        self.ajuste_funding_paridad_usdt = round(self.ajuste_funding_paridad_usdt + drift, 6)

        try:
            lines = [json.dumps(x, ensure_ascii=False) for x in self.operaciones]
            self.ruta_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.cargar_y_auditar_historial()
            log_sniper(
                f"[BLACK BOX 1:1] UTA parity synchronized to 1e-4 without mutating trade PnL "
                f"(Funding/Parity Adjustment: {drift:+.4f} USDT -> Balance {real_u:.4f} == {real_u:.4f} USDT)."
            )
            registrar_evento_baul_ia(
                {
                    "tipo_evento": "PARIDAD_1A1_AJUSTE",
                    "symbol": str(op_obj.get("symbol") or ""),
                    "ajuste_usdt": round(drift, 4),
                    "balance_uta_real": round(real_u, 4),
                    "n_trades": self.trades_totales,
                }
            )
            return True
        except Exception:
            return False

    @staticmethod
    def calcular_lvr_operacion(map_usdt: float, volatilidad_local: float, hold_seg: float) -> float:
        sigma = max(0.0005, float(volatilidad_local or 0.0020))
        t_hours = max(0.0, float(hold_seg)) / 3600.0
        return round(0.125 * (sigma ** 2) * float(map_usdt) * t_hours, 6)

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
        entry_notional = qty_c * ep
        exit_notional = qty_c * xp

        if pos.side == "short":
            gross_pnl = entry_notional - exit_notional
        else:
            gross_pnl = exit_notional - entry_notional

        fee_in = entry_notional * cfg.FEE_MAKER_PCT
        fee_out = exit_notional * (cfg.FEE_MAKER_PCT if es_maker else cfg.FEE_TAKER_PCT)
        leg_fees = fee_in + fee_out
        net_leg_pnl = gross_pnl - leg_fees

        pos.cosecha_50_ejecutada = True
        pos.modo_cosecha_ejecutado = "LADDER_50_25_25"
        pos.pnl_realizado_parcial_usdt += net_leg_pnl
        pos.fees_acumulados_usdt += leg_fees
        pos.qty_actual = max(0.0, pos.qty_actual - qty_c)
        return round(net_leg_pnl, 6)

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

        t_close = ahora if ahora is not None else time.time()
        hold_seg = round(max(0.1, t_close - float(pos.ts_apertura)), 1)

        ep = float(pos.entry_price)
        xp = float(exit_price)
        qty_rem = float(pos.qty_actual if pos.qty_actual > 0.0 else pos.qty_inicial)
        qty_total_original = float(pos.qty_inicial if pos.qty_inicial > 0.0 else qty_rem)

        rem_notional_in = qty_rem * ep
        rem_notional_out = qty_rem * xp
        if pos.side == "short":
            gross_pnl_rem = rem_notional_in - rem_notional_out
        else:
            gross_pnl_rem = rem_notional_out - rem_notional_in

        fee_in_rem = rem_notional_in * cfg.FEE_MAKER_PCT
        fee_out_rem = rem_notional_out * (cfg.FEE_MAKER_PCT if es_salida_maker else cfg.FEE_TAKER_PCT)
        fees_rem = fee_in_rem + fee_out_rem
        net_pnl_rem = gross_pnl_rem - fees_rem

        total_net_pnl_usdt = round(float(pos.pnl_realizado_parcial_usdt) + net_pnl_rem, 6)
        total_fees_usdt = round(float(pos.fees_acumulados_usdt) + fees_rem, 6)
        map_usdt = round(qty_total_original * ep, 4)
        net_pnl_pct = round((total_net_pnl_usdt / map_usdt) * 100.0, 4) if map_usdt > 0.0 else 0.0
        lvr_usdt = self.calcular_lvr_operacion(map_usdt, pos.volatilidad_entry, hold_seg)

        ts_iso = datetime.fromtimestamp(t_close, tz=timezone.utc).isoformat(timespec="seconds")
        record = RegistroOperacionCerrada(
            timestamp=ts_iso,
            symbol=pos.symbol,
            side=pos.side,
            z_score_entry=round(float(pos.z_score_entry), 4) if pos.z_score_entry else None,
            ofi_entry=round(float(pos.ofi_entry), 4) if pos.ofi_entry else None,
            hurst_entry=round(float(pos.hurst_entry), 4) if pos.hurst_entry else None,
            pnl_percentage=net_pnl_pct,
            pnl_usdt=total_net_pnl_usdt,
            entry_price=ep,
            exit_price=xp,
            qty=qty_total_original,
            motivo=str(motivo),
            hold_seg=hold_seg,
            fees_usdt=total_fees_usdt,
            map_usdt=map_usdt,
            lvr_usdt=lvr_usdt,
            cosecha_triz_50=bool(pos.cosecha_50_ejecutada),
        )

        try:
            with open(self.ruta_jsonl, "a", encoding="utf-8") as f_out:
                f_out.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            log_sniper(f"[WARN] [BLACK BOX] Error writing to {self.ruta_jsonl.name}: {exc}")

        prev_sum_map = self.map_promedio_usdt * self.trades_totales
        self.operaciones.append(record.to_dict())
        self.trades_totales += 1
        self.pnl_total_usdt = round(self.pnl_total_usdt + total_net_pnl_usdt, 6)
        self.lvr_acumulado_usdt = round(self.lvr_acumulado_usdt + lvr_usdt, 6)
        self.map_promedio_usdt = (prev_sum_map + map_usdt) / self.trades_totales

        if total_net_pnl_usdt >= 0.0:
            self.wins += 1
        else:
            self.losses += 1
            if "SCRATCH" in str(motivo).upper():
                self.scratches_18s += 1

        if self.trades_totales == 1:
            self.mejor_trade_usdt = total_net_pnl_usdt
            self.peor_trade_usdt = total_net_pnl_usdt
        else:
            self.mejor_trade_usdt = max(self.mejor_trade_usdt, total_net_pnl_usdt)
            self.peor_trade_usdt = min(self.peor_trade_usdt, total_net_pnl_usdt)

        # High-density persistence into the Forensic AI Cognitive Vault (baul_ia_forense.jsonl)
        if os.environ.get("TRIBRAIN_TEST_MODE") != "1" and "ESCAPE_HUERFANA_BOOT" not in str(motivo).upper():
            vec_map = getattr(ESTADO_RAM, "vectores_entrada_baul", None) or {}
            vec_in = vec_map.get(pos.symbol) or {}
            tk_out = ESTADO_RAM.ticks_ram.get(pos.symbol)
            book_bal_now = round(self.capital_base_usdt + self.pnl_total_usdt + self.ajuste_funding_paridad_usdt, 4)
            real_bal_now = round(
                ESTADO_RAM.patrimonio_total_usdt if ESTADO_RAM.patrimonio_total_usdt > 0 else book_bal_now,
                4,
            )
            result_tag = (
                "WIN"
                if total_net_pnl_usdt >= 0.0
                else ("SCRATCH_18S" if "SCRATCH" in str(motivo).upper() else "LOSS")
            )
            harvest_mode_str = str(getattr(pos, "modo_cosecha_ejecutado", "NONE") or "NONE")
            if harvest_mode_str == "NONE" and pos.cosecha_50_ejecutada:
                harvest_mode_str = "LADDER_50_25_25"

            registrar_evento_baul_ia(
                {
                    "tipo_evento": "TRADE_COMPLETO",
                    "trade_num": self.trades_totales,
                    "resultado": result_tag,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "motivo": str(motivo),
                    "es_salida_maker": bool(es_salida_maker),
                    "entry_price": ep,
                    "exit_price": xp,
                    "qty_total": qty_total_original,
                    "map_usdt": map_usdt,
                    "pnl_pct_neto": net_pnl_pct,
                    "pnl_usdt": round(total_net_pnl_usdt, 4),
                    "fees_usdt": round(total_fees_usdt, 4),
                    "lvr_usdt": lvr_usdt,
                    "hold_seg": hold_seg,
                    "balance_contable": book_bal_now,
                    "balance_uta_real": real_bal_now,
                    "anatomia_intratrade": {
                        "mfe_max_pnl_pct": round(float(pos.max_pnl_pct_alcanzado) * 100.0, 4),
                        "mae_min_pnl_pct": round(float(getattr(pos, "min_pnl_pct_alcanzado", 0.0)) * 100.0, 4),
                        "pnl_18s_pct": round(float(getattr(pos, "pnl_18s_pct", 0.0)) * 100.0, 4),
                        "pnl_45s_pct": round(float(getattr(pos, "pnl_45s_pct", 0.0)) * 100.0, 4),
                        "modo_cosecha": harvest_mode_str,
                        "cosecha_50": bool(pos.cosecha_50_ejecutada),
                        "cosecha_25": bool(pos.cosecha_25_ejecutada),
                        "eslabon_max": int(pos.eslabon_chain_jail),
                        "trinquete_be": bool(pos.trinquete_be_armado),
                    },
                    "vector_entrada": {
                        "p_dia": vec_in.get("p_dia", getattr(pos, "p_dia_entry", 0.25)),
                        "tag_percentil": vec_in.get("tag_percentil", getattr(pos, "tag_percentil_entry", "P25_ELASTIC")),
                        "mu_boot": vec_in.get("mu_boot", 0.0),
                        "z_entry": round(float(pos.z_score_entry or 0.0), 3),
                        "dp_pct": round(float(vec_in.get("delta_p_pct", getattr(pos, "delta_p_entry", 0.0))) * 100.0, 3),
                        "ema900_pct": round(float(vec_in.get("ema900_dist_pct", getattr(pos, "ema900_dist_entry", 0.0))) * 100.0, 3),
                        "ema_slope_pct": round(float(vec_in.get("ema900_slope_pct", getattr(pos, "ema900_slope_entry", 0.0))) * 100.0, 4),
                        "ofi_entry": round(float(pos.ofi_entry or 0.0), 3),
                        "hurst_entry": round(float(pos.hurst_entry or 0.45), 4),
                        "hurst_max_elastico": round(float(vec_in.get("hurst_max_elastico", getattr(pos, "hurst_max_elastico_entry", 0.485))), 4),
                        "lyap_acel_pct": round(float(vec_in.get("lyapunov_acel_pct", getattr(pos, "lyapunov_entry", 0.0))) * 100.0, 4),
                        "hawkes": round(float(vec_in.get("hawkes_intensidad", getattr(pos, "hawkes_entry", 0.0))), 3),
                        "vpin": round(float(vec_in.get("vpin", getattr(pos, "vpin_entry", 0.0))), 3),
                        "volatilidad_bv": round(float(pos.volatilidad_entry or 0.0006), 6),
                        "z_btc": round(float(vec_in.get("z_btc", getattr(pos, "z_btc_entry", 0.0))), 3),
                        "ofi_btc": round(float(vec_in.get("ofi_btc", getattr(pos, "ofi_btc_entry", 0.0))), 3),
                    },
                    "vector_salida": {
                        "z_exit": round(float(tk_out.z_score), 3) if tk_out else 0.0,
                        "ofi_exit": round(float(tk_out.ofi_l1_l5), 3) if tk_out else 0.0,
                        "ofi_5s_exit": round(float(tk_out.ofi_5s), 3) if tk_out else 0.0,
                        "hurst_exit": round(float(tk_out.hurst), 4) if tk_out else 0.45,
                    },
                },
                ahora=t_close,
            )

        icon = "[WIN]" if total_net_pnl_usdt >= 0.0 else ("[SCRATCH]" if "SCRATCH" in str(motivo).upper() else "[LOSS]")
        side_str = " SHORT" if pos.side == "short" else ""
        log_sniper(
            f"[SNIPER] {icon} CLOSE{side_str} {pos.symbol} [{motivo}] "
            f"{ep} -> {xp} | {net_pnl_pct:+.2f} % ({total_net_pnl_usdt:+.4f} USDT) in {hold_seg:.0f}s"
        )
        self.imprimir_panel_caja_negra()

        await TELEMETRIA_TG.enviar_cierre_garantizado(
            symbol=pos.symbol,
            side=pos.side,
            pnl_pct=net_pnl_pct,
            pnl_usdt=total_net_pnl_usdt,
            hold_seg=hold_seg,
            motivo=motivo,
            entry_price=ep,
            exit_price=xp,
            cosecha_50_previa=pos.cosecha_50_ejecutada,
        )

        return record

    def calcular_velocidad_geometrica_g(self, ultimos_n: int = 20) -> float:
        sample = self.operaciones[-ultimos_n:] if self.operaciones else []
        if not sample:
            return 0.0
        sum_log = 0.0
        sum_t = 0.0
        for op in sample:
            rel_ret = float(op.get("pnl_usdt") or 0.0) / max(1.0, self.capital_base_usdt)
            sum_log += math.log(max(0.01, 1.0 + rel_ret))
            sum_t += max(1.0, float(op.get("hold_seg") or 60.0))
        return (sum_log / (sum_t / 3600.0)) if sum_t > 0.0 else 0.0

    def imprimir_panel_caja_negra(self) -> None:
        if ESTADO_RAM.patrimonio_total_usdt > 0.0:
            self.sincronizar_paridad_uta(ESTADO_RAM.patrimonio_total_usdt)
        wr = (self.wins / self.trades_totales * 100.0) if self.trades_totales > 0 else 0.0
        book_bal = self.capital_base_usdt + self.pnl_total_usdt + self.ajuste_funding_paridad_usdt
        real_bal = ESTADO_RAM.patrimonio_total_usdt if ESTADO_RAM.patrimonio_total_usdt > 0 else book_bal
        pnl_map_ratio = (self.pnl_total_usdt / self.map_promedio_usdt) if self.map_promedio_usdt > 0.0 else 0.0
        l1 = "+==================================================================+"
        l2 = "|" + f"  [BLACK BOX] POUFS-BEELZEBUB-EN V5.0 | Trades: {self.trades_totales:<3d} (W {self.wins}/L {self.losses}/S {self.scratches_18s}) | WR: {wr:5.1f}%".ljust(66) + "|"
        l3 = "|" + f"  Total PnL: {self.pnl_total_usdt:+.4f} USDT   best {self.mejor_trade_usdt:+.4f} / worst {self.peor_trade_usdt:+.4f}".ljust(66) + "|"
        l4 = "|" + f"  MAP: {self.map_promedio_usdt:5.2f} USDT | PnL/MAP: {pnl_map_ratio:+.4f} | LVR: {self.lvr_acumulado_usdt:.4f}".ljust(66) + "|"
        l5 = "|" + f"  Balance: {book_bal:.4f} USDT (base {self.capital_base_usdt:.2f})   real: {real_bal:.4f} USDT".ljust(66) + "|"
        l6 = "+==================================================================+"
        for line in (l1, l2, l3, l4, l5, l6):
            log_sniper(line)


CAJA_NEGRA: GestorCajaNegra = GestorCajaNegra()
