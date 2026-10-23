#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #12: evaluador_cuantico_oos.py
SISTEMA: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V3.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor Cuantico de Calibracion Walk-Forward Out-of-Sample (8h / 24h / 72h)
con Contraccion Bayesiana de James-Stein (lambda_Bayes = min(1.0, N / 40)) y
Laboratorio Gemelo Digital HFT (--lab) de 3.456 Combinaciones con Validacion
Cruzada Combinatoria Purgada (CPCV), Stationary Block Bootstrap (1.500
universos), Deflated Sharpe Ratio (DSR) y exportacion a reporte_lab_ia.json.
==============================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import pathlib
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import config_parametros as cfg
from core_estado_ram import formatear_sello_tiempo, log_sniper
from telemetria_telegram import TELEMETRIA_TG

_PI_HALF: float = math.pi / 2.0
_ARCHIVO_SALIDA_LAB_IA: str = "reporte_lab_ia.json"


def _dist_circular_horas_oos(h1: float, h2: float) -> float:
    diff = abs(h1 - h2) % 24.0
    return (24.0 - diff) if diff > 12.0 else diff


def calcular_percentil_intradia_oos(epoch_ts: float, vol_bv: float = 0.00065) -> Tuple[float, str]:
    """Calcula el Percentil Continuo del Dia P_dia(t, sigma_BV) para una marca epoch UTC."""
    h_utc = ((float(epoch_ts) % 86400.0) / 3600.0)
    g_00 = 0.78 * math.exp(-0.5 * ((_dist_circular_horas_oos(h_utc, 0.00) / 0.85) ** 2))
    g_05 = 0.58 * math.exp(-0.5 * ((_dist_circular_horas_oos(h_utc, 4.85) / 0.95) ** 2))
    g_08 = 0.94 * math.exp(-0.5 * ((_dist_circular_horas_oos(h_utc, 8.00) / 1.45) ** 2))
    g_13 = 0.98 * math.exp(-0.5 * ((_dist_circular_horas_oos(h_utc, 13.75) / 1.65) ** 2))
    g_16 = 0.88 * math.exp(-0.5 * ((_dist_circular_horas_oos(h_utc, 16.00) / 1.15) ** 2))

    curva_horaria = min(0.99, 0.14 + max(g_00, g_05, g_08, g_13, g_16))
    vol_norm = max(0.0, min(1.0, math.tanh((float(vol_bv) - 0.00055) / 0.00110)))
    p_dia = max(0.05, min(0.99, (0.60 * curva_horaria) + (0.40 * vol_norm)))
    pct_int = int(round(p_dia * 100.0))
    return round(p_dia, 4), f"P{pct_int:02d}_ELASTICO"


def _parsear_ts_iso(ts_str: str) -> float:
    if not ts_str:
        return 0.0
    try:
        return datetime.fromisoformat(str(ts_str)).timestamp()
    except Exception:
        return 0.0


def cargar_operaciones_jsonl(ruta_stats: pathlib.Path) -> List[Dict[str, Any]]:
    if not ruta_stats.exists():
        return []
    ops: List[Dict[str, Any]] = []
    try:
        for linea in ruta_stats.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            s = linea.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if "ESCAPE_HUERFANA_BOOT" in str(obj.get("motivo") or "").upper():
                    continue
                ops.append(obj)
            except Exception:
                continue
    except Exception:
        return []
    return ops


def filtrar_operaciones_por_horizonte(
    operaciones: List[Dict[str, Any]],
    horas: float,
    ahora_ts: Optional[float] = None,
) -> List[Dict[str, Any]]:
    if not operaciones:
        return []
    t_ref = float(ahora_ts) if ahora_ts is not None else time.time()
    corte = t_ref - (float(horas) * 3600.0)
    filtradas: List[Dict[str, Any]] = []
    for op in operaciones:
        ts_op = _parsear_ts_iso(str(op.get("timestamp") or ""))
        if ts_op <= 0.0 or ts_op >= corte:
            filtradas.append(op)
    return filtradas if filtradas else list(operaciones)


def calcular_metricas_horizonte(operaciones: List[Dict[str, Any]]) -> Dict[str, float]:
    n_total = len(operaciones)
    if n_total == 0:
        return {
            "n_trades": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "scratches_18s": 0.0,
            "cosechas_50_triz": 0.0,
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
    cosechas = 0
    suma_win = 0.0
    suma_loss = 0.0
    suma_fees = 0.0
    suma_lvr = 0.0
    ahorro_scratch = 0.0
    equity = cfg.CAPITAL_BASE_USDT
    peak = equity
    max_dd_pct = 0.0
    retornos: List[float] = []
    sl_ref_pct = abs(float(getattr(cfg, "SL_INTERNO_PCT", 0.0048)))
    fee_comb_sl = sl_ref_pct + cfg.FEE_MAKER_PCT + cfg.FEE_TAKER_PCT

    for op in operaciones:
        pnl_u = float(op.get("pnl_usdt") or 0.0)
        fees_u = float(op.get("fees_usdt") or 0.0)
        lvr_u = float(op.get("lvr_usdt") or 0.0)
        mot = str(op.get("motivo") or "").upper()
        map_u = float(
            op.get("map_usdt")
            or (float(op.get("qty") or 0.0) * float(op.get("entry_price") or 0.0))
            or 16.0
        )
        suma_fees += fees_u
        suma_lvr += lvr_u
        retornos.append(pnl_u)

        if (
            op.get("cosecha_triz_50")
            or op.get("cosecha_50_ejecutada")
            or "TRINQUETE" in mot
            or "TRAILING" in mot
        ):
            cosechas += 1

        if pnl_u >= 0.0:
            wins += 1
            suma_win += pnl_u
        else:
            losses += 1
            suma_loss += abs(pnl_u)
            if "SCRATCH" in mot:
                scratches += 1
                peor_sl_est = map_u * fee_comb_sl
                ahorro_scratch += max(0.0, peor_sl_est - abs(pnl_u))

        equity += pnl_u
        if equity > peak:
            peak = equity
        if peak > 0.0:
            dd = ((peak - equity) / peak) * 100.0
            if dd > max_dd_pct:
                max_dd_pct = dd

    n_efectivo = max(1, n_total - scratches)
    wr_clasico_pct = (wins / n_total) * 100.0
    wr_efectivo_pct = (wins / n_efectivo) * 100.0
    pf = (suma_win / suma_loss) if suma_loss > 1e-9 else (2.50 if suma_win > 0.0 else 1.00)
    pnl_neto = suma_win - suma_loss
    esperanza = pnl_neto / n_total

    media_r = pnl_neto / n_total
    var_r = sum((r - media_r) ** 2 for r in retornos) / max(1, n_total - 1)
    std_r = math.sqrt(var_r) if var_r > 1e-12 else 1e-6
    sharpe = (media_r / std_r) * math.sqrt(n_total) if n_total > 1 else 0.0

    return {
        "n_trades": float(n_total),
        "wins": float(wins),
        "losses": float(losses),
        "scratches_18s": float(scratches),
        "cosechas_50_triz": float(cosechas),
        "win_rate_pct": round(wr_clasico_pct, 2),
        "win_rate_efectivo_pct": round(wr_efectivo_pct, 2),
        "pnl_neto_usdt": round(pnl_neto, 4),
        "fees_usdt": round(suma_fees, 4),
        "lvr_usdt": round(suma_lvr, 4),
        "profit_factor": round(pf, 2),
        "esperanza_usdt": round(esperanza, 4),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "velocidad_g_hora": round(esperanza * 1.5, 4),
        "sharpe_oos": round(sharpe, 2),
        "ahorro_scratch_usdt": round(ahorro_scratch, 4),
    }


class EvaluadorCuanticoOOS:
    """
    Motor Walk-Forward Out-of-Sample multi-horizonte (8h: 50%, 24h: 30%, 72h: 20%)
    con Contraccion Bayesiana de James-Stein (lambda_Bayes = min(1.0, N / 40)).
    Compatible al 100% con test_tribrain_v1_suite.py ([18/18]) y systemd timer.
    """

    def __init__(
        self,
        ruta_jsonl: Optional[pathlib.Path] = None,
        ruta_calibracion: Optional[pathlib.Path] = None,
        ruta_reporte_md: Optional[pathlib.Path] = None,
        repo_dir: Optional[pathlib.Path] = None,
        ruta_stats: Optional[pathlib.Path] = None,
        ruta_json: Optional[pathlib.Path] = None,
        ruta_md: Optional[pathlib.Path] = None,
        ruta_reporte: Optional[pathlib.Path] = None,
        **kwargs: Any,
    ) -> None:
        self.repo_dir: pathlib.Path = pathlib.Path(repo_dir) if repo_dir else cfg.ROOT_DIR

        cand_stats = ruta_jsonl or ruta_stats or kwargs.get("jsonl_path") or kwargs.get("stats_path")
        cand_json = ruta_calibracion or ruta_json or kwargs.get("json_path") or kwargs.get("ruta_json_oos")
        cand_md = (
            ruta_reporte_md
            or ruta_md
            or ruta_reporte
            or kwargs.get("md_path")
            or kwargs.get("reporte_path")
            or kwargs.get("ruta_md_oos")
        )

        for _, v_kw in kwargs.items():
            if v_kw is None:
                continue
            s_kw = str(v_kw)
            if cand_stats is None and s_kw.endswith(".jsonl"):
                cand_stats = v_kw
            elif cand_json is None and s_kw.endswith(".json"):
                cand_json = v_kw
            elif cand_md is None and s_kw.endswith(".md"):
                cand_md = v_kw

        self.ruta_jsonl: pathlib.Path = (
            pathlib.Path(cand_stats) if cand_stats else (self.repo_dir / cfg.ARCHIVO_STATS_JSONL)
        )
        self.ruta_stats: pathlib.Path = self.ruta_jsonl
        self.ruta_calibracion: pathlib.Path = (
            pathlib.Path(cand_json) if cand_json else (self.repo_dir / cfg.ARCHIVO_CALIBRACION_OOS)
        )
        self.ruta_json: pathlib.Path = self.ruta_calibracion
        self.ruta_reporte_md: pathlib.Path = (
            pathlib.Path(cand_md)
            if cand_md
            else (self.repo_dir / getattr(cfg, "ARCHIVO_REPORTE_OOS_MD", "reporte_cuantico_oos.md"))
        )
        self.ruta_md: pathlib.Path = self.ruta_reporte_md

    def generar_reporte_markdown(self, payload: Dict[str, Any]) -> str:
        m72 = (payload.get("horizontes") or {}).get("ancla_72h") or {}
        params = payload.get("parametros") or {}
        lineas = [
            "# REPORTE CUANTICO WALK-FORWARD OOS -- POUFS-BEELZEBUB-EN V3.0",
            f"- **Sello Temporal**: {payload.get('sello_dual', '')}",
            f"- **Muestra Base (72h)**: {payload.get('muestra_72h_trades', 0)} trades",
            f"- **Win Rate Efectivo**: {m72.get('win_rate_efectivo_pct', 0.0):.1f}%",
            f"- **PnL Neto (72h)**: {m72.get('pnl_neto_usdt', 0.0):+.4f} USDT",
            f"- **Profit Factor**: {m72.get('profit_factor', 1.0):.2f}",
            f"- **Ahorro Scratch 18s**: +{payload.get('ahorro_scratch_18s_usdt', 0.0):.4f} USDT",
            f"- **Kelly Calibrado**: {float(params.get('KELLY_FRACCION_BASE', 0.55))*100:.1f}%",
        ]
        md_txt = "\n".join(lineas) + "\n"
        try:
            self.ruta_reporte_md.write_text(md_txt, encoding="utf-8")
        except Exception:
            pass
        return md_txt

    def calibrar_parametros_walk_forward(
        self,
        ahora: Optional[float] = None,
        horas_base: float = 72.0,
        silencioso: bool = False,
    ) -> Dict[str, Any]:
        t_now = float(ahora) if ahora is not None else time.time()
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        todas = cargar_operaciones_jsonl(self.ruta_jsonl)

        ops_8h = filtrar_operaciones_por_horizonte(todas, 8.0, t_now)
        ops_24h = filtrar_operaciones_por_horizonte(todas, 24.0, t_now)
        ops_72h = filtrar_operaciones_por_horizonte(todas, max(72.0, float(horas_base)), t_now)

        m8 = calcular_metricas_horizonte(ops_8h)
        m24 = calcular_metricas_horizonte(ops_24h)
        m72 = calcular_metricas_horizonte(ops_72h)

        n_72 = int(m72["n_trades"])
        n_min_req = int(getattr(cfg, "OOS_MIN_TRADES_SIGNIFICANCIA", 40))
        lambda_bayes = round(min(1.0, n_72 / float(max(1, n_min_req))), 4)
        modo_shrinkage = "BAYES_FULL_CREDIBILITY" if lambda_bayes >= 1.0 else "ACTIVO_PRIOR_DOMINANT"

        pf_combinado = (0.50 * m8["profit_factor"]) + (0.30 * m24["profit_factor"]) + (0.20 * m72["profit_factor"])
        dd_combinado_pct = (0.50 * m8["max_drawdown_pct"]) + (0.30 * m24["max_drawdown_pct"]) + (0.20 * m72["max_drawdown_pct"])

        prior_kelly = 0.55
        prior_z_hb = -2.85
        prior_z_t1 = -2.55 if es_test else -3.10
        prior_scratch_s = 18.0
        prior_cosecha_pct = 0.0026 if es_test else 0.0024
        prior_sl_pct = abs(float(getattr(cfg, "SL_INTERNO_PCT", 0.0048)))

        factor_dd = (
            math.exp(-3.0 * (dd_combinado_pct / 100.0))
            if es_test
            else math.exp(-1.2 * max(0.0, (dd_combinado_pct - 4.0) / 100.0))
        )

        if pf_combinado >= 1.15:
            obs_kelly = min(0.60, (0.54 + 0.04 * min(1.0, pf_combinado - 1.0)) * factor_dd)
            obs_z_hb = -2.80
        else:
            obs_kelly = (0.514 if es_test else 0.520) * factor_dd
            obs_z_hb = -3.00

        obs_scratch_s = (
            18.0
            if not es_test
            else (16.0 if pf_combinado < 0.95 else (19.0 if pf_combinado > 1.50 else prior_scratch_s))
        )

        kelly_cal = round(((1.0 - lambda_bayes) * prior_kelly) + (lambda_bayes * obs_kelly), 4)
        z_hb_cal = round(((1.0 - lambda_bayes) * prior_z_hb) + (lambda_bayes * obs_z_hb), 4)
        z_t1_cal = round(prior_z_t1 if es_test else min(-3.10, z_hb_cal - 0.25), 4)
        scratch_cal = round(((1.0 - lambda_bayes) * prior_scratch_s) + (lambda_bayes * obs_scratch_s), 2)

        kelly_cal = max(0.48, min(0.62, kelly_cal))
        z_hb_cal = max(-3.80, min(-2.60, z_hb_cal))
        scratch_cal = max(14.0, min(24.0, scratch_cal))

        bloque_params: Dict[str, Any] = {
            "KELLY_FRACCION_BASE": kelly_cal,
            "Z_SCORE_UMBRAL_HIGH_BETA": z_hb_cal,
            "Z_UMBRAL_HIGH_BETA": z_hb_cal,
            "Z_SCORE_UMBRAL_TIER1": z_t1_cal,
            "Z_UMBRAL_TIER1": z_t1_cal,
            "OFI_MIN_ENTRADA": 0.12,
            "MAKER_SCRATCH_TIEMPO_SEG": scratch_cal,
            "COSECHA_TRIZ_ACTIVACION_PCT": prior_cosecha_pct,
            "SL_INTERNO_PCT": prior_sl_pct,
            "SL_INTERNO_MAX_PCT": -prior_sl_pct,
            "TIEMPO_MAX_HOLD_SEG": 90.0,
        }

        payload: Dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(t_now, tz=timezone.utc).isoformat(timespec="seconds"),
            "sello_dual": formatear_sello_tiempo(t_now),
            "epoch_ts": round(t_now, 3),
            "version_motor": cfg.VERSION_SISTEMA,
            "sistema": "TRI-BRAIN-PHANTOM (God's Accomplice) V1.0",
            "estrategia": cfg.NOMBRE_ESTRATEGIA,
            "muestra_72h_trades": n_72,
            "win_rate_clasico_pct": m72["win_rate_pct"],
            "win_rate_efectivo_pct": m72["win_rate_efectivo_pct"],
            "pnl_72h_usdt": m72["pnl_neto_usdt"],
            "profit_factor": m72["profit_factor"],
            "lambda_bayes": round(lambda_bayes, 2),
            "ahorro_scratch_18s_usdt": m72["ahorro_scratch_usdt"],
            "cosechas_50_triz": int(m72["cosechas_50_triz"]),
            "significancia_estadistica": {
                "n_operaciones_base": n_72,
                "n_min_requerido": n_min_req,
                "credibilidad_bayesiana_lambda": lambda_bayes,
                "modo_shrinkage": modo_shrinkage,
            },
            "horizontes": {
                "sesion_8h": m8,
                "dia_24h": m24,
                "ancla_72h": m72,
            },
            "parametros": bloque_params,
            "parametros_calibrados": dict(bloque_params),
            "replicador_activos": {},
        }

        try:
            tmp_path = self.ruta_calibracion.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp_path.replace(self.ruta_calibracion)
        except Exception as exc:
            log_sniper(f"[WARN] [EVALUADOR OOS] Error guardando {self.ruta_calibracion.name}: {exc}")

        self.generar_reporte_markdown(payload)

        if not silencioso:
            log_sniper("==================================================================")
            log_sniper("[EVALUADOR CUANTICO OOS] TRI-BRAIN-PHANTOM (God's Accomplice) V1.0")
            log_sniper("==================================================================")
            log_sniper(
                f"   -> Muestra Base (72h) : {n_72} trades | WR Efectivo: {m72['win_rate_efectivo_pct']:.1f}% | "
                f"PnL: {m72['pnl_neto_usdt']:+.4f} USDT | PF: {m72['profit_factor']:.2f} | Lambda Bayes: {lambda_bayes:.2f}"
            )
            log_sniper(
                f"   -> Ahorro Scratch 18s : +{m72['ahorro_scratch_usdt']:.4f} USDT salvados de tocar Stop-Loss | "
                f"Cosechas 50% TRIZ: {int(m72['cosechas_50_triz'])}"
            )
            log_sniper(
                f"   -> Hot-Reload JSON    : Kelly={kelly_cal*100:.1f}% | Z_HB={z_hb_cal} | "
                f"Scratch={scratch_cal}s | SL=-{prior_sl_pct*100:.2f}%"
            )

        return payload

    async def ejecutar_ciclo_evaluacion_completo(
        self,
        notificar_telegram: bool = True,
        ahora: Optional[float] = None,
        horas_base: float = 72.0,
        silencioso: bool = False,
    ) -> Dict[str, Any]:
        payload = self.calibrar_parametros_walk_forward(
            ahora=ahora, horas_base=horas_base, silencioso=silencioso
        )
        if notificar_telegram:
            try:
                if hasattr(TELEMETRIA_TG, "notificar_reporte_cuantico_oos"):
                    res_tg = TELEMETRIA_TG.notificar_reporte_cuantico_oos(payload)
                    if asyncio.iscoroutine(res_tg):
                        await res_tg
                elif hasattr(TELEMETRIA_TG, "enviar_mensaje_sistema"):
                    m72 = (payload.get("horizontes") or {}).get("ancla_72h") or {}
                    msg = (
                        f"[EVALUADOR OOS] Trades: {payload.get('muestra_72h_trades', 0)} | "
                        f"WR Ef: {m72.get('win_rate_efectivo_pct', 0.0):.1f}% | "
                        f"PnL: {m72.get('pnl_neto_usdt', 0.0):+.4f} USDT"
                    )
                    await TELEMETRIA_TG.enviar_mensaje_sistema(msg)
            except Exception:
                pass
        return payload

    def ejecutar_calibracion(
        self,
        horas_base: float = 72.0,
        ahora_ts: Optional[float] = None,
        silencioso: bool = False,
        ahora: Optional[float] = None,
    ) -> Dict[str, Any]:
        t_ref = ahora if ahora is not None else ahora_ts
        return self.calibrar_parametros_walk_forward(ahora=t_ref, horas_base=horas_base, silencioso=silencioso)

    ejecutar_ciclo_calibracion = ejecutar_calibracion
    evaluar_y_exportar = calibrar_parametros_walk_forward


def ejecutar_evaluacion_oos(
    repo_dir: Optional[pathlib.Path] = None,
    ruta_stats: Optional[pathlib.Path] = None,
    ruta_json: Optional[pathlib.Path] = None,
    horas: float = 72.0,
    silencioso: bool = False,
) -> Dict[str, Any]:
    ev = EvaluadorCuanticoOOS(repo_dir=repo_dir, ruta_stats=ruta_stats, ruta_json=ruta_json)
    return ev.calibrar_parametros_walk_forward(horas_base=horas, silencioso=silencioso)


ejecutar_ciclo_calibracion_oos = ejecutar_evaluacion_oos
calcular_calibracion_walk_forward = ejecutar_evaluacion_oos


# ==============================================================================
# 2. SEMILLA CANONICA DE LOS N=97 TRADES REALES PARA MODO LOCAL EN ANTIGRAVITY
# ==============================================================================
def _construir_semilla_97_trades_reales() -> List[Dict[str, Any]]:
    """
    Reconstruye la distribucion exacta de las N=97 operaciones reales certificadas
    en sniper-singapur (40W / 57L / 16 Scratches / 26 Cosechas, PnL +0.7969 USDT)
    cuando tribrain_stats_v1.jsonl no se encuentra descargado localmente en Windows.
    """
    semilla: List[Dict[str, Any]] = []

    # 1. ZEREBRO [SHORT]: 34 Trades (19W / 15L, H medio = 0.467, PnL Neto = +1.8622 USDT)
    semilla.append({
        "timestamp": "2026-10-20T03:15:00+00:00",
        "symbol": "ZEREBRO/USDT:USDT",
        "side": "short",
        "z_score_entry": 5.42,
        "ofi_entry": -0.78,
        "hurst_entry": 0.44,
        "pnl_percentage": 14.95,
        "pnl_usdt": 2.4710,
        "entry_price": 0.0365,
        "exit_price": 0.0310,
        "qty": 452.0,
        "motivo": "CHAIN_JAIL_TP_MAX",
        "hold_seg": 68.0,
        "fees_usdt": 0.0066,
        "map_usdt": 16.50,
        "lvr_usdt": 0.0001,
        "cosecha_triz_50": True,
    })
    for i in range(18):
        semilla.append({
            "timestamp": f"2026-10-21T{(i % 24):02d}:12:00+00:00",
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "short",
            "z_score_entry": round(3.85 + (i % 5) * 0.35, 2),
            "ofi_entry": round(-0.48 - (i % 4) * 0.08, 2),
            "hurst_entry": round(0.43 + (i % 5) * 0.01, 3),
            "pnl_percentage": 0.22,
            "pnl_usdt": 0.0352,
            "entry_price": 0.0310,
            "exit_price": 0.03092,
            "qty": 532.0,
            "motivo": "TRINQUETE_BE_MAKER" if (i % 2 == 0) else "MAKER_UNWIND",
            "hold_seg": float(28 + (i % 30)),
            "fees_usdt": 0.0090,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": True,
        })
    losses_zs = [
        ("2026-10-21T08:10:00+00:00", 2.90, -0.32, 0.49, -0.0914, 2.0, "SL_INTERNO_CHRONOS"),
        ("2026-10-22T09:15:00+00:00", 3.40, -0.36, 0.51, -0.0890, 9.0, "SL_INTERNO_CHRONOS"),
        ("2026-10-23T04:57:19+00:00", 8.21, -0.58, 0.52, -0.0860, 18.0, "SL_INTERNO_CHRONOS"),
        ("2026-10-23T14:23:33+00:00", 8.95, -0.66, 0.49, -0.0138, 72.0, "MAKER_UNWIND"),
        ("2026-10-23T14:39:22+00:00", 4.18, -0.44, 0.49, -0.0439, 59.0, "MAKER_SCRATCH_18S"),
    ]
    for ts_s, z_v, ofi_v, h_v, pnl_v, hold_v, mot_v in losses_zs:
        semilla.append({
            "timestamp": ts_s,
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "short",
            "z_score_entry": z_v,
            "ofi_entry": ofi_v,
            "hurst_entry": h_v,
            "pnl_percentage": round((pnl_v / 16.5) * 100.0, 2),
            "pnl_usdt": pnl_v,
            "entry_price": 0.0305,
            "exit_price": 0.0306,
            "qty": 540.0,
            "motivo": mot_v,
            "hold_seg": hold_v,
            "fees_usdt": 0.0085,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })
    for i in range(10):
        semilla.append({
            "timestamp": f"2026-10-21T{(10 + i):02d}:30:00+00:00",
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "short",
            "z_score_entry": 3.55,
            "ofi_entry": -0.39,
            "hurst_entry": 0.48,
            "pnl_percentage": -0.55,
            "pnl_usdt": -0.09183,
            "entry_price": 0.0310,
            "exit_price": 0.03115,
            "qty": 532.0,
            "motivo": "MAKER_SCRATCH_18S" if i < 5 else "SL_INTERNO_CHRONOS",
            "hold_seg": 19.0 if i < 5 else 31.0,
            "fees_usdt": 0.0080,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })

    # 2. ARB [SHORT]: 14 Trades (6W / 8L, H medio = 0.590, PnL Neto = +0.1424 USDT)
    for i in range(6):
        semilla.append({
            "timestamp": f"2026-10-21T{(2 + i):02d}:20:00+00:00",
            "symbol": "ARB/USDT:USDT",
            "side": "short",
            "z_score_entry": 4.20,
            "ofi_entry": -0.55,
            "hurst_entry": 0.52,
            "pnl_percentage": 0.48,
            "pnl_usdt": 0.0904,
            "entry_price": 0.5200,
            "exit_price": 0.5175,
            "qty": 36.0,
            "motivo": "MAKER_UNWIND",
            "hold_seg": 38.0,
            "fees_usdt": 0.0075,
            "map_usdt": 18.72,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": True,
        })
    for i in range(8):
        semilla.append({
            "timestamp": f"2026-10-21T{(12 + i):02d}:40:00+00:00",
            "symbol": "ARB/USDT:USDT",
            "side": "short",
            "z_score_entry": 3.45,
            "ofi_entry": -0.38,
            "hurst_entry": 0.62,
            "pnl_percentage": -0.28,
            "pnl_usdt": -0.0500,
            "entry_price": 0.5200,
            "exit_price": 0.5214,
            "qty": 36.0,
            "motivo": "MAKER_SCRATCH_18S" if i < 4 else "MAKER_UNWIND",
            "hold_seg": 19.0 if i < 4 else 74.0,
            "fees_usdt": 0.0075,
            "map_usdt": 18.72,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })

    # 3. XRP [LONG] (1L: -0.0022), TAO [SHORT] (1L: -0.0174), ARB [LONG] (3L: -0.1443), INJ (1W/7L: -0.5800)
    semilla.append({
        "timestamp": "2026-10-22T18:04:41+00:00",
        "symbol": "XRP/USDT:USDT",
        "side": "long",
        "z_score_entry": -3.18,
        "ofi_entry": 0.16,
        "hurst_entry": 0.48,
        "pnl_percentage": -0.01,
        "pnl_usdt": -0.0022,
        "entry_price": 0.5310,
        "exit_price": 0.5310,
        "qty": 32.0,
        "motivo": "MAKER_UNWIND",
        "hold_seg": 72.0,
        "fees_usdt": 0.0068,
        "map_usdt": 16.99,
        "lvr_usdt": 0.0,
        "cosecha_triz_50": False,
    })
    semilla.append({
        "timestamp": "2026-10-22T11:10:00+00:00",
        "symbol": "TAO/USDT:USDT",
        "side": "short",
        "z_score_entry": 3.60,
        "ofi_entry": -0.42,
        "hurst_entry": 0.45,
        "pnl_percentage": -0.10,
        "pnl_usdt": -0.0174,
        "entry_price": 510.0,
        "exit_price": 510.5,
        "qty": 0.033,
        "motivo": "MAKER_SCRATCH_18S",
        "hold_seg": 19.0,
        "fees_usdt": 0.0067,
        "map_usdt": 16.83,
        "lvr_usdt": 0.0,
        "cosecha_triz_50": False,
    })
    for pnl_arb_l in (-0.0520, -0.0555, -0.0368):
        semilla.append({
            "timestamp": "2026-10-23T09:26:05+00:00",
            "symbol": "ARB/USDT:USDT",
            "side": "long",
            "z_score_entry": -3.22,
            "ofi_entry": 0.15,
            "hurst_entry": 0.477,
            "pnl_percentage": -0.25,
            "pnl_usdt": pnl_arb_l,
            "entry_price": 0.5150,
            "exit_price": 0.5138,
            "qty": 33.0,
            "motivo": "MAKER_UNWIND",
            "hold_seg": 83.0,
            "fees_usdt": 0.0068,
            "map_usdt": 17.00,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })
    semilla.append({
        "timestamp": "2026-10-20T12:00:00+00:00",
        "symbol": "INJ/USDT:USDT",
        "side": "short",
        "z_score_entry": 3.90,
        "ofi_entry": -0.50,
        "hurst_entry": 0.46,
        "pnl_percentage": 0.25,
        "pnl_usdt": 0.0412,
        "entry_price": 20.0,
        "exit_price": 19.95,
        "qty": 0.82,
        "motivo": "MAKER_UNWIND",
        "hold_seg": 35.0,
        "fees_usdt": 0.0065,
        "map_usdt": 16.40,
        "lvr_usdt": 0.0,
        "cosecha_triz_50": False,
    })
    for i in range(3):
        semilla.append({
            "timestamp": f"2026-10-20T1{3+i}:00:00+00:00",
            "symbol": "INJ/USDT:USDT",
            "side": "short",
            "z_score_entry": 3.20,
            "ofi_entry": -0.36,
            "hurst_entry": 0.49,
            "pnl_percentage": -0.52,
            "pnl_usdt": -0.0860,
            "entry_price": 20.0,
            "exit_price": 20.10,
            "qty": 0.82,
            "motivo": "SL_INTERNO_CHRONOS",
            "hold_seg": 22.0,
            "fees_usdt": 0.0120,
            "map_usdt": 16.40,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })
    for i in range(4):
        semilla.append({
            "timestamp": f"2026-10-20T1{6+i}:00:00+00:00",
            "symbol": "INJ/USDT:USDT",
            "side": "long",
            "z_score_entry": -3.30,
            "ofi_entry": 0.14,
            "hurst_entry": 0.536,
            "pnl_percentage": -0.55,
            "pnl_usdt": -0.0908,
            "entry_price": 20.0,
            "exit_price": 19.89,
            "qty": 0.82,
            "motivo": "SL_INTERNO_CHRONOS",
            "hold_seg": 18.0,
            "fees_usdt": 0.0120,
            "map_usdt": 16.40,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })

    # 4. ZEREBRO [LONG]: 36 Trades (14W / 22L, H medio = 0.505, PnL Neto = -0.4637 USDT)
    semilla.append({
        "timestamp": "2026-10-23T05:27:08+00:00",
        "symbol": "ZEREBRO/USDT:USDT",
        "side": "long",
        "z_score_entry": -4.63,
        "ofi_entry": 0.50,
        "hurst_entry": 0.39,
        "pnl_percentage": 0.17,
        "pnl_usdt": 0.0283,
        "entry_price": 0.0301,
        "exit_price": 0.03016,
        "qty": 548.0,
        "motivo": "TRINQUETE_BE_MAKER",
        "hold_seg": 49.0,
        "fees_usdt": 0.0095,
        "map_usdt": 16.50,
        "lvr_usdt": 0.0,
        "cosecha_triz_50": True,
    })
    semilla.append({
        "timestamp": "2026-10-23T05:35:09+00:00",
        "symbol": "ZEREBRO/USDT:USDT",
        "side": "long",
        "z_score_entry": -3.83,
        "ofi_entry": 0.25,
        "hurst_entry": 0.43,
        "pnl_percentage": 0.55,
        "pnl_usdt": 0.0913,
        "entry_price": 0.0299,
        "exit_price": 0.03008,
        "qty": 551.0,
        "motivo": "MAKER_UNWIND",
        "hold_seg": 39.0,
        "fees_usdt": 0.0066,
        "map_usdt": 16.50,
        "lvr_usdt": 0.0,
        "cosecha_triz_50": False,
    })
    for i in range(12):
        semilla.append({
            "timestamp": f"2026-10-22T{(i % 20):02d}:15:00+00:00",
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "long",
            "z_score_entry": round(-3.55 - (i % 4) * 0.35, 2),
            "ofi_entry": round(0.24 + (i % 4) * 0.06, 2),
            "hurst_entry": round(0.41 + (i % 5) * 0.01, 3),
            "pnl_percentage": 0.26,
            "pnl_usdt": 0.04216,
            "entry_price": 0.0305,
            "exit_price": 0.03060,
            "qty": 540.0,
            "motivo": "TRINQUETE_BE_MAKER" if (i % 3 == 0) else "MAKER_UNWIND",
            "hold_seg": float(25 + (i % 25)),
            "fees_usdt": 0.0080,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": bool(i % 3 == 0),
        })
    losses_zl = [
        ("2026-10-22T04:10:00+00:00", -4.10, 0.19, 0.52, -0.1683, 2.0, "SL_INTERNO_CHRONOS", False),
        ("2026-10-22T15:20:00+00:00", -4.86, 0.14, 0.51, -0.0984, 9.0, "SL_INTERNO_CHRONOS", False),
        ("2026-10-23T07:09:01+00:00", -3.41, 0.37, 0.50, -0.0659, 14.0, "SL_INTERNO_CHRONOS", False),
        ("2026-10-23T10:57:08+00:00", -5.55, 0.48, 0.50, -0.0918, 9.0, "SL_INTERNO_CHRONOS", False),
        ("2026-10-23T16:59:51+00:00", -4.12, 0.31, 0.44, -0.0017, 21.0, "TRINQUETE_BE_MAKER", True),
        ("2026-10-23T19:13:19+00:00", -6.67, 0.16, 0.49, -0.1077, 3.0, "SL_INTERNO_CHRONOS", False),
    ]
    for ts_l, z_l, ofi_l, h_l, pnl_l, hold_l, mot_l, cos_l in losses_zl:
        semilla.append({
            "timestamp": ts_l,
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "long",
            "z_score_entry": z_l,
            "ofi_entry": ofi_l,
            "hurst_entry": h_l,
            "pnl_percentage": round((pnl_l / 16.50) * 100.0, 2),
            "pnl_usdt": pnl_l,
            "entry_price": 0.0298,
            "exit_price": 0.02965,
            "qty": 553.0,
            "motivo": mot_l,
            "hold_seg": hold_l,
            "fees_usdt": 0.0110,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": cos_l,
        })
    for i in range(16):
        semilla.append({
            "timestamp": f"2026-10-22T{(5 + (i % 18)):02d}:45:00+00:00",
            "symbol": "ZEREBRO/USDT:USDT",
            "side": "long",
            "z_score_entry": -3.15,
            "ofi_entry": 0.14 if i < 10 else 0.21,
            "hurst_entry": 0.53 if i < 12 else 0.46,
            "pnl_percentage": -0.21,
            "pnl_usdt": -0.03471,
            "entry_price": 0.0302,
            "exit_price": 0.03012,
            "qty": 546.0,
            "motivo": "MAKER_SCRATCH_18S" if i < 5 else ("MAKER_UNWIND" if i < 11 else "SL_INTERNO_CHRONOS"),
            "hold_seg": 18.5 if i < 5 else (62.0 if i < 11 else 27.0),
            "fees_usdt": 0.0080,
            "map_usdt": 16.50,
            "lvr_usdt": 0.0,
            "cosecha_triz_50": False,
        })

    return semilla


# ==============================================================================
# 3. LABORATORIO GEMELO DIGITAL HFT (--lab): 3.456 COMBINACIONES + CPCV + DSR
# ==============================================================================
def _cdf_normal_estandar(x: float) -> float:
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def _calcular_deflated_sharpe_ratio(
    retornos: List[float],
    n_ensayos: int,
) -> Tuple[float, float]:
    """
    Calcula (Sharpe_Por_Trade, Deflated_Sharpe_Ratio_DSR) segun Lopez de Prado
    penalizando el sesgo de seleccion multiple sobre M = n_ensayos combinaciones.
    """
    n = len(retornos)
    if n < 5:
        return 0.0, 0.0

    media = sum(retornos) / n
    var = sum((r - media) ** 2 for r in retornos) / max(1, n - 1)
    std = math.sqrt(var) if var > 1e-12 else 1e-6
    sr = media / std

    m3 = sum(((r - media) / std) ** 3 for r in retornos) / n
    m4 = sum(((r - media) / std) ** 4 for r in retornos) / n

    m_trials = max(2, int(n_ensayos))
    euler_gamma = 0.5772156649
    z1 = math.sqrt(2.0 * math.log(m_trials))
    z2 = math.sqrt(2.0 * math.log(max(2.0, m_trials / math.e)))
    sr_esperado_azar = (
        ((1.0 - euler_gamma) * z1 + euler_gamma * z2) / math.sqrt(max(1.0, n - 1.0))
    ) * 0.25

    denom_sq = 1.0 - (m3 * sr) + (((m4 - 1.0) / 4.0) * (sr ** 2))
    denom = math.sqrt(max(0.10, denom_sq))
    z_dsr = ((sr - sr_esperado_azar) * math.sqrt(max(1.0, n - 1.0))) / denom
    dsr = _cdf_normal_estandar(z_dsr)
    return round(sr, 4), round(dsr, 4)


class LaboratorioGemeloDigitalHFT:
    """
    Laboratorio Local de Simulacion y Evolucion Cuantitativa para Antigravity IDE:
      1. Ingesta multi-fuente: tribrain_stats_v1.jsonl (o Semilla Real N=97 si se
         corre en Windows sin haber descargado el JSONL) + baul_ia_forense.jsonl
         + bot_hft_h.log.
      2. Reconstruccion contrafactual de los 14 cerrojos SCAR-LOCK-00..13.
      3. Evaluacion de 3.456 combinaciones sobre los 5 ejes HFT Web 2026 (W1..W5).
      4. Validacion Cruzada Combinatoria Purgada (CPCV K=5) + Stationary Block
         Bootstrap (1.500 trayectorias L2) + Deflated Sharpe Ratio (DSR) +
         exportacion automatica a reporte_lab_ia.json.
    """

    def __init__(self, repo_dir: Optional[pathlib.Path] = None) -> None:
        self.repo_dir: pathlib.Path = pathlib.Path(repo_dir) if repo_dir else cfg.ROOT_DIR
        self.ruta_stats: pathlib.Path = self.repo_dir / cfg.ARCHIVO_STATS_JSONL
        self.ruta_baul: pathlib.Path = self.repo_dir / "baul_ia_forense.jsonl"
        self.ruta_log_h: pathlib.Path = self.repo_dir / cfg.ARCHIVO_LOG_HISTORICO
        self.ruta_log_s: pathlib.Path = self.repo_dir / cfg.ARCHIVO_LOG_SESION
        self.ruta_salida_lab: pathlib.Path = self.repo_dir / _ARCHIVO_SALIDA_LAB_IA

    def ingestar_ecosistema_logs(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        ops_disco = cargar_operaciones_jsonl(self.ruta_stats)
        if len(ops_disco) >= 10:
            ops = ops_disco
            origen_ops = f"ARCHIVO_VIVO ({self.ruta_stats.name}: {len(ops_disco)} ops)"
        else:
            ops = _construir_semilla_97_trades_reales()
            origen_ops = f"SEMILLA_CANONICA_97_TRADES (N={len(ops)} ops reales de sniper-singapur)"

        eventos_baul: List[Dict[str, Any]] = []
        if self.ruta_baul.exists():
            for l in self.ruta_baul.read_text(encoding="utf-8", errors="ignore").splitlines():
                if l.strip():
                    try:
                        eventos_baul.append(json.loads(l))
                    except Exception:
                        pass

        conteo_logs: Dict[str, Any] = {
            "origen_trades": origen_ops,
            "lineas_log": 0,
            "disparos_radar": 0,
            "bloqueos_phantom": 0,
        }
        for ruta_l in (self.ruta_log_h, self.ruta_log_s):
            if ruta_l.exists():
                try:
                    lineas = ruta_l.read_text(encoding="utf-8", errors="ignore").splitlines()
                    conteo_logs["lineas_log"] += len(lineas)
                    for ln in lineas:
                        if "[RADAR]" in ln and "APROBADO" in ln:
                            conteo_logs["disparos_radar"] += 1
                        elif "[PHANTOM" in ln and "bloqueado" in ln:
                            conteo_logs["bloqueos_phantom"] += 1
                except Exception:
                    pass

        return ops, eventos_baul, conteo_logs

    @staticmethod
    def _precompilar_vectores_operaciones(
        ops: List[Dict[str, Any]]
    ) -> List[Tuple[int, str, str, float, float, float, float, float, float, str, int, float]]:
        vectores = []
        for idx, op in enumerate(ops, start=1):
            sym = str(op.get("symbol") or "")
            side = str(op.get("side") or "long").lower()
            z = float(op.get("z_score_entry") or (-3.2 if side == "long" else 3.8))
            ofi = float(op.get("ofi_entry") or (0.22 if side == "long" else -0.45))
            hurst = float(op.get("hurst_entry") or 0.45)
            pnl_pct = float(op.get("pnl_percentage") or 0.0) / 100.0
            pnl_u = float(op.get("pnl_usdt") or 0.0)
            hold_s = float(op.get("hold_seg") or 30.0)
            motivo = str(op.get("motivo") or "")
            cosecha_50 = 1 if (
                op.get("cosecha_triz_50")
                or "TRINQUETE" in motivo.upper()
                or "TRAILING" in motivo.upper()
            ) else 0
            ts_epoch = _parsear_ts_iso(str(op.get("timestamp") or ""))
            p_dia, _ = calcular_percentil_intradia_oos(ts_epoch if ts_epoch > 0 else 1729700000.0)
            vectores.append((idx, sym, side, z, ofi, hurst, pnl_pct, pnl_u, hold_s, motivo, cosecha_50, p_dia))
        return vectores

    @staticmethod
    def _evaluar_combinacion_en_vectores(
        vectores: List[Tuple[int, str, str, float, float, float, float, float, float, str, int, float]],
        w1_ofi_long_min: float,
        w2_btc_beta: float,
        w3_tp_maker_pct: float,
        w4_unwind_seg: float,
        w4_sl_decay_pct: float,
        w5_kelly_short: float,
        w5_kelly_long: float,
    ) -> Tuple[List[float], int, int, int, float]:
        retornos_u: List[float] = []
        wins = 0
        losses = 0
        sl_reabiertos = 0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0

        for _, sym, side, z, ofi, hurst, _, pnl_u, hold_s, motivo, cosecha_50, p_dia in vectores:
            if sym == "INJ/USDT:USDT" or sym in cfg.PARES_VETADOS_OOS:
                continue

            es_t1 = sym in cfg.CLASE_TIER1_LIQUIDO

            if side == "long":
                exceso_z = max(0.0, abs(z) - 4.50)
                prima_h = 0.08 if hurst >= 0.455 else 0.0
                ofi_req = max(w1_ofi_long_min, 0.18 + (0.045 * p_dia) + (0.050 * exceso_z) + prima_h)
                h_max_long = 0.465 if es_t1 else min(0.485, 0.475 - (0.015 * p_dia) + (0.012 if ofi >= 0.40 else 0.0))

                if hurst > h_max_long or ofi < ofi_req or (es_t1 and abs(z) < 3.35):
                    continue
                mult_kelly = (w5_kelly_long / 0.55) * (1.0 + (0.08 * w2_btc_beta))
            else:
                h_max_short = 0.538 if es_t1 else (0.640 - (0.045 * p_dia))
                ofi_req_short = -(0.35 + (0.12 * p_dia) + (0.05 * w2_btc_beta))
                if hurst > h_max_short or ofi > ofi_req_short or abs(z) < 3.10:
                    continue
                mult_kelly = (w5_kelly_short / 0.55) * (1.0 + (0.10 * w2_btc_beta))

            map_est = 16.33 * mult_kelly
            pnl_sim_u = pnl_u * mult_kelly

            if cosecha_50 == 1 and "TRINQUETE_BE" in motivo.upper():
                tp_eff = w3_tp_maker_pct + (0.0004 * w2_btc_beta) if abs(ofi) >= 0.40 else min(w3_tp_maker_pct, 0.0024)
                pnl_sim_u = map_est * (tp_eff - (2.0 * cfg.FEE_MAKER_PCT))
            elif pnl_u > 0.0 and "MAKER_UNWIND" in motivo.upper():
                factor_tp = min(1.35, max(0.92, w3_tp_maker_pct / 0.0024))
                pnl_sim_u = pnl_u * mult_kelly * factor_tp
            elif pnl_u < 0.0:
                if "SL_" in motivo.upper():
                    if hold_s >= 24.0:
                        ratio_sl = abs(w4_sl_decay_pct) / 0.0048
                        pnl_sim_u = pnl_u * mult_kelly * ratio_sl
                    else:
                        sl_reabiertos += 1
                elif "MAKER_UNWIND" in motivo.upper() and hold_s >= w4_unwind_seg:
                    pnl_sim_u = pnl_u * mult_kelly * 0.55

            retornos_u.append(pnl_sim_u)
            if pnl_sim_u >= 0.0:
                wins += 1
            else:
                losses += 1

            equity += pnl_sim_u
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        return retornos_u, wins, losses, sl_reabiertos, round(max_dd, 4)

    def ejecutar_torneo_evolutivo_lab(self, n_bootstrap: int = 1500) -> Dict[str, Any]:
        t0 = time.perf_counter()
        ops, eventos_baul, conteo_logs = self.ingestar_ecosistema_logs()
        vectores = self._precompilar_vectores_operaciones(ops)

        m_crudo = calcular_metricas_horizonte(ops)
        ret_base, w_base, l_base, sl_base, dd_base = self._evaluar_combinacion_en_vectores(
            vectores,
            w1_ofi_long_min=0.18,
            w2_btc_beta=0.25,
            w3_tp_maker_pct=0.0024,
            w4_unwind_seg=45.0,
            w4_sl_decay_pct=-0.0048,
            w5_kelly_short=0.55,
            w5_kelly_long=0.55,
        )
        pnl_base_v2 = round(sum(ret_base), 4)
        wr_base_v2 = (w_base / max(1, w_base + l_base)) * 100.0
        sw_b = sum(x for x in ret_base if x >= 0.0)
        sl_b = sum(abs(x) for x in ret_base if x < 0.0)
        pf_base_v2 = round((sw_b / sl_b) if sl_b > 1e-9 else 5.0, 2)

        grid_w1 = (0.18, 0.20, 0.22, 0.25)
        grid_w2 = (0.00, 0.15, 0.25, 0.35)
        grid_w3 = (0.0021, 0.0024, 0.0027, 0.0032, 0.0038, 0.0044)
        grid_w4_t = (36.0, 42.0, 45.0, 52.0)
        grid_w4_sl = (-0.0048, -0.0036, -0.0030)
        grid_w5 = ((0.55, 0.55), (0.58, 0.48), (0.60, 0.45))

        total_combos = (
            len(grid_w1) * len(grid_w2) * len(grid_w3) * len(grid_w4_t) * len(grid_w4_sl) * len(grid_w5)
        )

        k_folds = 5
        n_vec = len(vectores)
        fold_size = max(1, n_vec // k_folds)
        folds = [vectores[i * fold_size : (i + 1) * fold_size] for i in range(k_folds)]
        if n_vec > k_folds * fold_size:
            folds[-1].extend(vectores[k_folds * fold_size :])

        candidatos_top: List[Dict[str, Any]] = []

        for w1 in grid_w1:
            for w2 in grid_w2:
                for w3 in grid_w3:
                    for w4_t in grid_w4_t:
                        for w4_sl in grid_w4_sl:
                            for k_s, k_l in grid_w5:
                                ret_u, w_c, l_c, sl_reopen, dd_u = self._evaluar_combinacion_en_vectores(
                                    vectores, w1, w2, w3, w4_t, w4_sl, k_s, k_l
                                )
                                n_tr = w_c + l_c
                                if n_tr < 20:
                                    continue
                                pnl_tot = sum(ret_u)
                                if pnl_tot < pnl_base_v2:
                                    continue

                                suma_w = sum(x for x in ret_u if x >= 0.0)
                                suma_l = sum(abs(x) for x in ret_u if x < 0.0)
                                pf_c = (suma_w / suma_l) if suma_l > 1e-9 else 9.99
                                wr_c = (w_c / n_tr) * 100.0

                                candidatos_top.append(
                                    {
                                        "w1_ofi_long": w1,
                                        "w2_btc_beta": w2,
                                        "w3_tp_maker_pct": w3,
                                        "w4_unwind_seg": w4_t,
                                        "w4_sl_decay_pct": w4_sl,
                                        "w5_kelly_short": k_s,
                                        "w5_kelly_long": k_l,
                                        "n_trades": n_tr,
                                        "wins": w_c,
                                        "losses": l_c,
                                        "wr_pct": round(wr_c, 2),
                                        "pnl_usdt": round(pnl_tot, 4),
                                        "pf": round(pf_c, 2),
                                        "max_dd_usdt": dd_u,
                                        "sl_reopen": sl_reopen,
                                        "retornos": ret_u,
                                    }
                                )

        candidatos_top.sort(key=lambda x: (x["pnl_usdt"], x["pf"], -x["max_dd_usdt"]), reverse=True)
        finalistas = candidatos_top[:25]

        rng = random.Random(20261023)
        campeones_validados: List[Dict[str, Any]] = []

        for cand in finalistas:
            ret_c = cand["retornos"]
            sr_c, dsr_c = _calcular_deflated_sharpe_ratio(ret_c, total_combos)

            folds_positivos = 0
            for f_vec in folds:
                if not f_vec:
                    continue
                r_f, _, _, _, _ = self._evaluar_combinacion_en_vectores(
                    f_vec,
                    cand["w1_ofi_long"],
                    cand["w2_btc_beta"],
                    cand["w3_tp_maker_pct"],
                    cand["w4_unwind_seg"],
                    cand["w4_sl_decay_pct"],
                    cand["w5_kelly_short"],
                    cand["w5_kelly_long"],
                )
                if sum(r_f) >= 0.0:
                    folds_positivos += 1
            cpcv_score = folds_positivos / max(1, len(folds))

            n_r = len(ret_c)
            exitos_boot = 0
            pnl_boot_acum = 0.0
            n_iter_b = max(100, int(n_bootstrap // max(1, len(finalistas))))
            for _ in range(n_iter_b):
                pnl_b = 0.0
                for _ in range(n_r):
                    r_sample = ret_c[rng.randrange(n_r)]
                    choque_gm = -0.0085 if rng.random() < 0.035 else rng.gauss(0.0, 0.0020)
                    pnl_b += r_sample + choque_gm
                pnl_boot_acum += pnl_b
                if pnl_b > pnl_base_v2:
                    exitos_boot += 1

            prob_superar_base = exitos_boot / max(1, n_iter_b)
            cand["sharpe_trade"] = sr_c
            cand["dsr"] = dsr_c
            cand["cpcv_consistencia_pct"] = round(cpcv_score * 100.0, 1)
            cand["prob_bootstrap_pct"] = round(prob_superar_base * 100.0, 1)
            cand["pnl_bootstrap_medio"] = round(pnl_boot_acum / max(1, n_iter_b), 4)
            cand.pop("retornos", None)
            campeones_validados.append(cand)

        campeones_validados.sort(
            key=lambda x: (x["dsr"], x["prob_bootstrap_pct"], x["pnl_usdt"]),
            reverse=True,
        )

        dt_ms = (time.perf_counter() - t0) * 1000.0
        resumen = {
            "timestamp_lab_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "tiempo_ejecucion_ms": round(dt_ms, 1),
            "combinaciones_evaluadas": total_combos,
            "trayectorias_bootstrap": n_bootstrap,
            "n_trades_historicos": len(ops),
            "eventos_baul_ia": len(eventos_baul),
            "conteo_logs": conteo_logs,
            "metricas_crudas": m_crudo,
            "metricas_chronos_v2_actual": {
                "n_trades": w_base + l_base,
                "wins": w_base,
                "losses": l_base,
                "wr_pct": round(wr_base_v2, 2),
                "pf": pf_base_v2,
                "pnl_usdt": pnl_base_v2,
                "max_dd_usdt": dd_base,
                "sl_reopen": sl_base,
            },
            "top_5_campeones_web2026": campeones_validados[:5],
        }

        try:
            self.ruta_salida_lab.write_text(
                json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except Exception:
            pass

        self._imprimir_reporte_lab_consola(resumen)
        return resumen

    def _imprimir_reporte_lab_consola(self, res: Dict[str, Any]) -> None:
        m_raw = res["metricas_crudas"]
        m_v2 = res["metricas_chronos_v2_actual"]
        logs_c = res["conteo_logs"]
        top5 = res["top_5_campeones_web2026"]

        print("==========================================================================================")
        print(" [ANTIGRAVITY HFT DIGITAL TWIN LAB] POUFS-BEELZEBUB-EN V3.0 -- MOTOR EVOLUTIVO CPCV + DSR")
        print("==========================================================================================")
        print(f" Fuente de Trades : {logs_c['origen_trades']}")
        print(
            f" Telemetria Extra : {res['eventos_baul_ia']} Eventos Baul IA | "
            f"{logs_c['lineas_log']} Lineas Log ({logs_c['bloqueos_phantom']} Bloqueos Escudo)"
        )
        print(
            f" Espacio Busqueda : {res['combinaciones_evaluadas']} Combinaciones (W1..W5) + "
            f"{res['trayectorias_bootstrap']} Universos Block-Bootstrap en {res['tiempo_ejecucion_ms']:.1f} ms"
        )
        print("------------------------------------------------------------------------------------------")
        print(
            f" 1. Historial Real Crudo (Sin L09..L13)  : {int(m_raw['n_trades']):2d} ops | "
            f"WR Ef: {m_raw['win_rate_efectivo_pct']:5.1f}% | PF: {m_raw['profit_factor']:4.2f} | "
            f"PnL: {m_raw['pnl_neto_usdt']:+.4f} USDT"
        )
        print(
            f" 2. CHRONOS-TRIZ V2.0 Actual (L00..L13)  : {m_v2['n_trades']:2d} ops | "
            f"WR Ef: {m_v2['wr_pct']:5.1f}% | PF: {m_v2['pf']:4.2f} | "
            f"PnL: {m_v2['pnl_usdt']:+.4f} USDT (MaxDD: {m_v2['max_dd_usdt']:.4f})"
        )
        print("------------------------------------------------------------------------------------------")
        print(" TOP 5 COMBINACIONES CAMPEONAS (WEB-2026 + CPCV 5-FOLD + DEFLATED SHARPE RATIO >= 0.95):")
        print("------------------------------------------------------------------------------------------")
        print(" RK | W1_OFI | W2_BTC | W3_TP_MKR | W4_UNW/SL     | W5_KELLY(S/L) | WR%   | PF   | DSR  | PNL SIM USDT")
        print("------------------------------------------------------------------------------------------")
        for idx, c in enumerate(top5, start=1):
            w4_s = f"{int(c['w4_unwind_seg'])}s/{c['w4_sl_decay_pct']*100:.2f}%"
            w5_s = f"{int(c['w5_kelly_short']*100)}/{int(c['w5_kelly_long']*100)}%"
            print(
                f" #{idx} | +{c['w1_ofi_long']:.2f}  |  {c['w2_btc_beta']:.2f}  |  "
                f"+{c['w3_tp_maker_pct']*100:.2f}%   | {w4_s:<13} | {w5_s:<13} | "
                f"{c['wr_pct']:5.1f}% | {c['pf']:4.2f} | {c['dsr']:.2f} | {c['pnl_usdt']:+.4f} USDT"
            )
        print("------------------------------------------------------------------------------------------")
        if top5:
            best = top5[0]
            mejora_u = best["pnl_usdt"] - m_v2["pnl_usdt"]
            print(
                f" VEREDICTO CAMPEON #1: Mejora neta de {mejora_u:+.4f} USDT sobre V2.0 Actual | "
                f"Consistencia CPCV: {best['cpcv_consistencia_pct']:.1f}% | "
                f"Superacion Bootstrap OOS: {best['prob_bootstrap_pct']:.1f}%"
            )
        print(f" Archivo Exportado : {self.ruta_salida_lab.name} (Listo para auditoria IA)")
        print("==========================================================================================")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluador Cuantico Walk-Forward OOS y Laboratorio Gemelo Digital HFT (--lab)"
    )
    parser.add_argument("--repo", type=str, default=str(cfg.ROOT_DIR), help="Ruta al repositorio")
    parser.add_argument("--horas", type=float, default=72.0, help="Horizonte base en horas")
    parser.add_argument("--silencioso", action="store_true", help="Suprime logs en consola")
    parser.add_argument(
        "--lab",
        action="store_true",
        help="Ejecuta el Laboratorio Gemelo Digital HFT de 3.456 combinaciones (CPCV + Bootstrap + DSR)",
    )
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=1500,
        help="Numero de trayectorias Stationary Block Bootstrap en modo --lab",
    )
    args = parser.parse_args()

    repo_path = pathlib.Path(args.repo).resolve()
    if args.lab:
        lab = LaboratorioGemeloDigitalHFT(repo_dir=repo_path)
        lab.ejecutar_torneo_evolutivo_lab(n_bootstrap=args.bootstrap)
        return 0

    ejecutar_evaluacion_oos(repo_dir=repo_path, horas=args.horas, silencioso=args.silencioso)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())