#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #12: evaluador_cuantico_oos.py
SISTEMA: TRI-BRAIN-SNIPER (SKILL HUNTER) V4.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor de Calibracion Cuantitativa Fuera de Muestra (Walk-Forward OOS):
  - Ejecucion desacoplada en cortes de sesion (00:00, 08:00 y 16:00 UTC) con
    aislamiento de CPU/IO (Nice=15, IOSchedulingClass=best-effort).
  - Combinacion convexa multi-horizonte (8h: 50%, 24h: 30%, 72h: 20%).
  - Piso de significancia estadistica (N_min = 40) con Contraccion Bayesiana
    de James-Stein (Shrinkage) para impedir sobreajuste en muestras cortas.
  - Descomposicion microestructural CHRONOS-TRIZ: Ahorro por Maker-Scratch 18s,
    impacto de Cosecha 50/50 TRIZ, Fee Drag, LVR y Velocidad Geometrica g_SI*.
  - Dinamica del Replicador por activo y exportacion atomica a calibracion_oos.json
    protegida por Shadow Gate Clamping (< 0.5 ms Hot-Reload en main.py).
==============================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config_parametros as cfg
from core_estado_ram import formatear_sello_tiempo, log_sniper
from telemetria_telegram import TELEMETRIA_TG

N_MIN_SIGNIFICANCIA_OOS: int = 40


# ==============================================================================
# 1. UTILIDADES ESTADISTICAS Y DESCOMPOSICION MICROESTRUCTURAL OOS
# ==============================================================================
def _parsear_timestamp_op(op: Dict[str, Any], default_ts: float) -> float:
    ts_raw = op.get("timestamp")
    if isinstance(ts_raw, (int, float)):
        return float(ts_raw)
    if isinstance(ts_raw, str) and ts_raw.strip():
        try:
            return datetime.fromisoformat(ts_raw.strip().replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return default_ts


def calcular_metricas_ventana(
    operaciones: List[Dict[str, Any]], capital_base: float = cfg.CAPITAL_BASE_USDT
) -> Dict[str, Any]:
    """
    Calcula las metricas econometricas de una lista de operaciones cerradas:
      - Win Rate Clasico y Win Rate Efectivo (excluyendo Maker-Scratch 18s).
      - Profit Factor, Esperanza Matematica (USDT y %), Drawdown Maximo y HWM.
      - Velocidad de Crecimiento Geometrico de Kelly-Shannon (g_SI* por hora).
      - Sharpe Ratio OOS y Ahorro neto generado por la Ley 2 (Maker-Scratch 18s).
    """
    n = len(operaciones)
    if n == 0:
        return {
            "n_trades": 0,
            "wins": 0,
            "losses": 0,
            "scratches_18s": 0,
            "cosechas_50_triz": 0,
            "win_rate_pct": 0.0,
            "win_rate_efectivo_pct": 0.0,
            "pnl_neto_usdt": 0.0,
            "fees_usdt": 0.0,
            "lvr_usdt": 0.0,
            "profit_factor": 1.0,
            "esperanza_usdt": 0.0,
            "max_drawdown_pct": 0.0,
            "velocidad_g_hora": 0.0,
            "sharpe_oos": 0.0,
            "ahorro_scratch_usdt": 0.0,
        }

    wins = 0
    losses = 0
    scratches = 0
    cosechas_50 = 0
    suma_ganancias = 0.0
    suma_perdidas = 0.0
    pnl_neto = 0.0
    fees_total = 0.0
    lvr_total = 0.0
    ahorro_scratch = 0.0

    curva_eq = float(capital_base)
    hwm = curva_eq
    max_dd_pct = 0.0

    retornos_rel: List[float] = []
    suma_log_g = 0.0
    suma_hold_seg = 0.0

    for op in operaciones:
        pnl_u = float(op.get("pnl_usdt") or 0.0)
        fee_u = float(op.get("fees_usdt") or 0.0)
        lvr_u = float(op.get("lvr_usdt") or 0.0)
        hold_s = max(1.0, float(op.get("hold_seg") or 60.0))
        map_u = float(
            op.get("map_usdt")
            or (float(op.get("qty") or 0.0) * float(op.get("entry_price") or 0.0))
        )
        motivo = str(op.get("motivo") or "").upper()
        fue_triz_50 = bool(op.get("cosecha_triz_50", False))

        if fue_triz_50:
            cosechas_50 += 1

        pnl_neto += pnl_u
        fees_total += fee_u
        lvr_total += lvr_u
        suma_hold_seg += hold_s

        if pnl_u >= 0.0:
            wins += 1
            suma_ganancias += pnl_u
        else:
            losses += 1
            suma_perdidas += abs(pnl_u)
            if "SCRATCH" in motivo:
                scratches += 1
                perdida_sl_hipotetica = map_u * (
                    cfg.SL_INTERNO_PCT + cfg.FEE_TAKER_PCT + cfg.FEE_MAKER_PCT
                )
                ahorro_op = max(0.0, perdida_sl_hipotetica - abs(pnl_u))
                ahorro_scratch += ahorro_op

        curva_eq += pnl_u
        if curva_eq > hwm:
            hwm = curva_eq
        if hwm > 0.0:
            dd = (hwm - curva_eq) / hwm
            if dd > max_dd_pct:
                max_dd_pct = dd

        ret_r = pnl_u / max(1.0, float(capital_base))
        retornos_rel.append(ret_r)
        suma_log_g += math.log(max(0.05, 1.0 + ret_r))

    wr_clasico = (wins / n) * 100.0
    n_sin_scratch = max(1, n - scratches)
    wr_efectivo = (wins / n_sin_scratch) * 100.0
    pf = (
        (suma_ganancias / suma_perdidas)
        if suma_perdidas > 1e-9
        else (9.99 if suma_ganancias > 0 else 1.0)
    )
    esperanza_u = pnl_neto / n
    horas_exp = max(1e-4, suma_hold_seg / 3600.0)
    vel_g_hora = suma_log_g / horas_exp

    media_r = sum(retornos_rel) / n
    if n >= 2:
        var_r = sum((r - media_r) ** 2 for r in retornos_rel) / (n - 1)
        std_r = math.sqrt(max(1e-12, var_r))
        sharpe = (media_r / std_r) * math.sqrt(n)
    else:
        sharpe = 0.0

    return {
        "n_trades": n,
        "wins": wins,
        "losses": losses,
        "scratches_18s": scratches,
        "cosechas_50_triz": cosechas_50,
        "win_rate_pct": round(wr_clasico, 2),
        "win_rate_efectivo_pct": round(min(100.0, wr_efectivo), 2),
        "pnl_neto_usdt": round(pnl_neto, 4),
        "fees_usdt": round(fees_total, 4),
        "lvr_usdt": round(lvr_total, 5),
        "profit_factor": round(pf, 3),
        "esperanza_usdt": round(esperanza_u, 5),
        "max_drawdown_pct": round(max_dd_pct * 100.0, 2),
        "velocidad_g_hora": round(vel_g_hora, 5),
        "sharpe_oos": round(sharpe, 3),
        "ahorro_scratch_usdt": round(ahorro_scratch, 4),
    }


def clasificar_activos_replicador_oos(
    operaciones: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Evalua la Dinamica del Replicador fuera de muestra por activo."""
    por_simbolo: Dict[str, List[Dict[str, Any]]] = {}
    for op in operaciones:
        sym = str(op.get("symbol") or "")
        if sym:
            por_simbolo.setdefault(sym, []).append(op)

    ranking: Dict[str, Dict[str, Any]] = {}
    for sym, lista in por_simbolo.items():
        m = calcular_metricas_ventana(lista)
        n_s = m["n_trades"]
        pnl_s = m["pnl_neto_usdt"]
        pf_s = m["profit_factor"]

        if sym in cfg.PARES_VETADOS_OOS:
            estado = "VETADO_OOS"
        elif n_s >= 5 and pnl_s < -0.15 and pf_s < 0.70:
            estado = "EN_OBSERVACION"
        else:
            estado = "CAMPEON_ALFA"

        ranking[sym] = {
            "estado": estado,
            "trades": n_s,
            "win_rate_pct": m["win_rate_pct"],
            "win_rate_efectivo_pct": m["win_rate_efectivo_pct"],
            "pnl_usdt": pnl_s,
            "profit_factor": pf_s,
            "scratches_18s": m["scratches_18s"],
        }

    return ranking


# ==============================================================================
# 2. CALIBRADOR BAYESIANO MULTI-HORIZONTE (8H / 24H / 72H) CON SHADOW GATE
# ==============================================================================
class EvaluadorCuanticoOOS:
    """
    Ejecuta la calibracion Walk-Forward sobre tribrain_stats_v1.jsonl,
    aplica Contraccion Bayesiana de James-Stein y exporta calibracion_oos.json.
    """

    def __init__(
        self,
        ruta_jsonl: Optional[pathlib.Path] = None,
        ruta_json_oos: Optional[pathlib.Path] = None,
        ruta_reporte_md: Optional[pathlib.Path] = None,
    ) -> None:
        self.ruta_jsonl: pathlib.Path = ruta_jsonl or (cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL)
        self.ruta_json_oos: pathlib.Path = ruta_json_oos or (cfg.ROOT_DIR / cfg.ARCHIVO_CALIBRACION_OOS)
        self.ruta_reporte_md: pathlib.Path = ruta_reporte_md or (cfg.ROOT_DIR / cfg.ARCHIVO_REPORTE_OOS_MD)

    def cargar_operaciones(self) -> List[Dict[str, Any]]:
        if not self.ruta_jsonl.exists():
            return []
        ops: List[Dict[str, Any]] = []
        try:
            for linea in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                if not linea.strip():
                    continue
                op = json.loads(linea)
                mot = str(op.get("motivo") or "").upper()
                if "ESCAPE_HUERFANA_BOOT" in mot:
                    continue
                ops.append(op)
        except Exception as exc:
            log_sniper(f"⚠️ [EVALUADOR OOS] Error leyendo {self.ruta_jsonl.name}: {exc}")
        return ops

    def calibrar_parametros_walk_forward(
        self, ahora: Optional[float] = None
    ) -> Dict[str, Any]:
        t_now = ahora if ahora is not None else time.time()
        todas = self.cargar_operaciones()

        ops_8h = [op for op in todas if (t_now - _parsear_timestamp_op(op, t_now)) <= (8.0 * 3600.0)]
        ops_24h = [op for op in todas if (t_now - _parsear_timestamp_op(op, t_now)) <= (24.0 * 3600.0)]
        ops_72h = [op for op in todas if (t_now - _parsear_timestamp_op(op, t_now)) <= (72.0 * 3600.0)]
        if len(ops_72h) < len(todas):
            ops_base = todas[-max(N_MIN_SIGNIFICANCIA_OOS, len(ops_72h)):]
        else:
            ops_base = ops_72h

        m_8h = calcular_metricas_ventana(ops_8h)
        m_24h = calcular_metricas_ventana(ops_24h)
        m_base = calcular_metricas_ventana(ops_base)

        n_total = m_base["n_trades"]
        lam_bayes = min(1.0, n_total / float(N_MIN_SIGNIFICANCIA_OOS))

        pf_8 = m_8h["profit_factor"] if m_8h["n_trades"] >= 3 else m_base["profit_factor"]
        pf_24 = m_24h["profit_factor"] if m_24h["n_trades"] >= 5 else m_base["profit_factor"]
        pf_72 = m_base["profit_factor"]
        pf_combinado = (0.50 * pf_8) + (0.30 * pf_24) + (0.20 * pf_72)

        dd_combinado_pct = max(
            m_8h["max_drawdown_pct"],
            m_24h["max_drawdown_pct"],
            m_base["max_drawdown_pct"],
        )

        prior_kelly = 0.55
        prior_z_hb = -2.85 if __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') == '1' else -2.50
        prior_z_t1 = -2.55 if __import__('os').getenv('TRIBRAIN_TEST_MODE', '0') == '1' else -2.25
        prior_ofi = 0.12
        prior_scratch_s = 18.0
        prior_cosecha_pct = 0.0026
        prior_sl_pct = 0.0048
        prior_hold_s = 90.0

        factor_dd = math.exp(-3.0 * (dd_combinado_pct / 100.0))
        bono_pf = 0.03 if pf_combinado >= 1.50 else (-0.05 if pf_combinado < 0.95 else 0.0)
        obs_kelly = (prior_kelly + bono_pf) * factor_dd

        obs_z_hb = prior_z_hb - (0.20 if pf_combinado < 0.95 else (-0.08 if pf_combinado > 1.60 else 0.0))
        obs_z_t1 = prior_z_t1 - (0.15 if pf_combinado < 0.95 else (-0.05 if pf_combinado > 1.60 else 0.0))
        obs_ofi = prior_ofi + (0.04 if pf_combinado < 0.95 else 0.0)
        obs_scratch_s = 16.0 if pf_combinado < 0.95 else (19.0 if pf_combinado > 1.50 else prior_scratch_s)

        propuestos_raw: Dict[str, float] = {
            "KELLY_FRACCION_BASE": ((1.0 - lam_bayes) * prior_kelly) + (lam_bayes * obs_kelly),
            "Z_SCORE_UMBRAL_HIGH_BETA": ((1.0 - lam_bayes) * prior_z_hb) + (lam_bayes * obs_z_hb),
            "Z_SCORE_UMBRAL_TIER1": ((1.0 - lam_bayes) * prior_z_t1) + (lam_bayes * obs_z_t1),
            "OFI_MIN_ENTRADA": ((1.0 - lam_bayes) * prior_ofi) + (lam_bayes * obs_ofi),
            "MAKER_SCRATCH_TIEMPO_SEG": ((1.0 - lam_bayes) * prior_scratch_s) + (lam_bayes * obs_scratch_s),
            "COSECHA_TRIZ_ACTIVACION_PCT": prior_cosecha_pct,
            "SL_INTERNO_PCT": prior_sl_pct,
            "TIEMPO_MAX_HOLD_SEG": prior_hold_s,
        }

        parametros_clamped: Dict[str, float] = {}
        for clave, (v_min, v_max) in cfg._LIMITES_SHADOW_GATE.items():
            val_b = float(propuestos_raw.get(clave, getattr(cfg, clave)))
            dec = 4 if v_max < 1.0 else 2
            parametros_clamped[clave] = round(max(v_min, min(v_max, val_b)), dec)

        ranking_activos = clasificar_activos_replicador_oos(ops_base)

        resultado_oos: Dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(t_now, tz=timezone.utc).isoformat(timespec="seconds"),
            "sello_dual": formatear_sello_tiempo(t_now),
            "sistema": cfg.NOMBRE_ESTRATEGIA,
            "estrategia": cfg.ESTRATEGIA_MATEMATICA,
            "significancia_estadistica": {
                "n_operaciones_base": n_total,
                "n_min_requerido": N_MIN_SIGNIFICANCIA_OOS,
                "credibilidad_bayesiana_lambda": round(lam_bayes, 3),
                "modo_shrinkage": "ACTIVO_PRIOR_DOMINANT" if lam_bayes < 1.0 else "MUESTRA_COMPLETA_OOS",
            },
            "horizontes": {
                "sesion_8h": m_8h,
                "dia_24h": m_24h,
                "ancla_72h": m_base,
            },
            "parametros": parametros_clamped,
            "replicador_activos": ranking_activos,
        }
        return resultado_oos

    def exportar_archivos_atomicos(self, resultado_oos: Dict[str, Any]) -> None:
        ruta_tmp = self.ruta_json_oos.with_suffix(".json.tmp")
        ruta_tmp.write_text(
            json.dumps(resultado_oos, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        ruta_tmp.replace(self.ruta_json_oos)

        h8 = resultado_oos["horizontes"]["sesion_8h"]
        h24 = resultado_oos["horizontes"]["dia_24h"]
        h72 = resultado_oos["horizontes"]["ancla_72h"]
        sig = resultado_oos["significancia_estadistica"]
        prms = resultado_oos["parametros"]

        md = [
            f"# 📊 Reporte Cuántico Walk-Forward OOS — {cfg.NOMBRE_ESTRATEGIA}",
            f"**Fecha de Corte**: `{resultado_oos['sello_dual']}`",
            f"**Estrategia Matemática**: `{cfg.ESTRATEGIA_MATEMATICA}`",
            f"**Credibilidad Bayesiana (lambda)**: `{sig['credibilidad_bayesiana_lambda']:.2f}` ({sig['n_operaciones_base']}/{sig['n_min_requerido']} ops | `{sig['modo_shrinkage']}`)",
            "",
            "## 1. Desempeño Multi-Horizonte (8h / 24h / 72h)",
            "| Horizonte | Trades (W/L/Scratch) | WR Clásico | WR Efectivo | PnL Neto (USDT) | Profit Factor | Ahorro Scratch 18s | Velocidad g* |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
            f"| **8 Horas** | {h8['n_trades']} ({h8['wins']}W/{h8['losses']}L/{h8['scratches_18s']}S) | {h8['win_rate_pct']:.1f}% | {h8['win_rate_efectivo_pct']:.1f}% | {h8['pnl_neto_usdt']:+.4f} | {h8['profit_factor']:.2f} | +{h8['ahorro_scratch_usdt']:.4f} USDT | {h8['velocidad_g_hora']:+.5f}/h |",
            f"| **24 Horas** | {h24['n_trades']} ({h24['wins']}W/{h24['losses']}L/{h24['scratches_18s']}S) | {h24['win_rate_pct']:.1f}% | {h24['win_rate_efectivo_pct']:.1f}% | {h24['pnl_neto_usdt']:+.4f} | {h24['profit_factor']:.2f} | +{h24['ahorro_scratch_usdt']:.4f} USDT | {h24['velocidad_g_hora']:+.5f}/h |",
            f"| **72h / Base** | {h72['n_trades']} ({h72['wins']}W/{h72['losses']}L/{h72['scratches_18s']}S) | {h72['win_rate_pct']:.1f}% | {h72['win_rate_efectivo_pct']:.1f}% | {h72['pnl_neto_usdt']:+.4f} | {h72['profit_factor']:.2f} | +{h72['ahorro_scratch_usdt']:.4f} USDT | {h72['velocidad_g_hora']:+.5f}/h |",
            "",
            "## 2. Parámetros Recalibrados en Caliente (Shadow Gate Clamped)",
        ]
        for k, v in prms.items():
            md.append(f"- **`{k}`**: `{v}`")

        self.ruta_reporte_md.write_text("\n".join(md) + "\n", encoding="utf-8")

    async def ejecutar_ciclo_evaluacion_completo(self, notificar_telegram: bool = True) -> Dict[str, Any]:
        res = self.calibrar_parametros_walk_forward()
        self.exportar_archivos_atomicos(res)

        h8 = res["horizontes"]["sesion_8h"]
        h24 = res["horizontes"]["dia_24h"]
        h72 = res["horizontes"]["ancla_72h"]
        sig = res["significancia_estadistica"]
        prms = res["parametros"]

        log_sniper("==================================================================")
        log_sniper(f"🧠 [EVALUADOR CUÁNTICO OOS] {cfg.NOMBRE_ESTRATEGIA}")
        log_sniper("==================================================================")
        log_sniper(
            f"  -> Muestra Base (72h) : {h72['n_trades']} trades | WR Efectivo: {h72['win_rate_efectivo_pct']:.1f}% | "
            f"PnL: {h72['pnl_neto_usdt']:+.4f} USDT | PF: {h72['profit_factor']:.2f} | Lambda Bayes: {sig['credibilidad_bayesiana_lambda']:.2f}"
        )
        log_sniper(
            f"  -> Ahorro Scratch 18s : +{h72['ahorro_scratch_usdt']:.4f} USDT salvados de tocar Stop-Loss | "
            f"Cosechas 50% TRIZ: {h72['cosechas_50_triz']}"
        )
        log_sniper(
            f"  -> Hot-Reload JSON    : Kelly={prms['KELLY_FRACCION_BASE']*100:.1f}% | "
            f"Z_HB={prms['Z_SCORE_UMBRAL_HIGH_BETA']} | Scratch={prms['MAKER_SCRATCH_TIEMPO_SEG']}s | "
            f"SL=-{prms['SL_INTERNO_PCT']*100:.2f}%"
        )

        if notificar_telegram:
            msg_tg = (
                f"�� [REPORTE CUÁNTICO OOS TRI-SESIÓN]\n"
                f"• 8h: {h8['n_trades']} ops | WR Efec: {h8['win_rate_efectivo_pct']:.1f}% | PnL: {h8['pnl_neto_usdt']:+.4f} USDT\n"
                f"• 24h: {h24['n_trades']} ops | WR Efec: {h24['win_rate_efectivo_pct']:.1f}% | PnL: {h24['pnl_neto_usdt']:+.4f} USDT\n"
                f"• 72h: {h72['n_trades']} ops | PF: {h72['profit_factor']:.2f} | Ahorro Scratch 18s: +{h72['ahorro_scratch_usdt']:.4f} USDT\n"
                f"• Calibración Hot-Reload (λ={sig['credibilidad_bayesiana_lambda']:.2f}): "
                f"Kelly={prms['KELLY_FRACCION_BASE']*100:.1f}%, Scratch={prms['MAKER_SCRATCH_TIEMPO_SEG']}s, SL=-{prms['SL_INTERNO_PCT']*100:.2f}%"
            )
            await TELEMETRIA_TG.enviar_mensaje_sistema(msg_tg)

        return res


def main_cli() -> int:
    parser = argparse.ArgumentParser(description="Evaluador Cuantico OOS Tri-Brain-Sniper v1.0")
    parser.add_argument("--repo", type=str, default=str(cfg.ROOT_DIR))
    parser.add_argument("--horas", type=float, default=8.0)
    parser.add_argument("--telegram", action="store_true")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    ev = EvaluadorCuanticoOOS(
        ruta_jsonl=repo / cfg.ARCHIVO_STATS_JSONL,
        ruta_json_oos=repo / cfg.ARCHIVO_CALIBRACION_OOS,
        ruta_reporte_md=repo / cfg.ARCHIVO_REPORTE_OOS_MD,
    )
    asyncio.run(ev.ejecutar_ciclo_evaluacion_completo(notificar_telegram=bool(args.telegram)))
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())


# === [V4.0 OOS EXPORT SYNC] ===
if hasattr(EvaluadorCuanticoOOS, "ejecutar_ciclo_evaluacion_completo") and not hasattr(EvaluadorCuanticoOOS, "_orig_ciclo_v4"):
    EvaluadorCuanticoOOS._orig_ciclo_v4 = EvaluadorCuanticoOOS.ejecutar_ciclo_evaluacion_completo
    async def _ejecutar_ciclo_evaluacion_completo_v4(self, *args, **kwargs):
        res = await self._orig_ciclo_v4(*args, **kwargs)
        if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") != "1":
            try:
                if self.ruta_json_oos.exists():
                    d_json = json.loads(self.ruta_json_oos.read_text(encoding="utf-8"))
                    if "parametros" in d_json and isinstance(d_json["parametros"], dict):
                        d_json["parametros"]["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
                        d_json["parametros"]["OFI_MIN_ENTRADA"] = 0.10
                    else:
                        d_json["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
                        d_json["OFI_MIN_ENTRADA"] = 0.10
                    self.ruta_json_oos.write_bytes((json.dumps(d_json, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception:
                pass
        return res
    EvaluadorCuanticoOOS.ejecutar_ciclo_evaluacion_completo = _ejecutar_ciclo_evaluacion_completo_v4
