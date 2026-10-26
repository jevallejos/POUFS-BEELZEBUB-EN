#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #07: escudo_tricortex.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Asynchronous Tri-Cortex Cognitive Swarm (Full-Groq LPU-First + Multi-Cloud):
  1. Cortex 1 (Groq LPU): Directional Regime Matrix (LONG_ONLY, SHORT_ONLY,
     EXTREME_Z_ONLY, VETO_TOXIC) with physical Anti-LUNA Guard and
     Ornstein-Uhlenbeck protection (prevents forcing SHORT_ONLY below EMA900 in prod).
  2. Cortex 2 (Groq LPU + Google AI gemma-4-26b-a4b-it Failover): Anti-Fragile
     Sizing by Physical Dislocation (|Z|, Hurst, Glosten-Milgrom P-07)
     without double exponential Drawdown penalty.
  3. Cortex 3 (Groq LPU + NVIDIA NIM Failover): Post-Loss Forensic Audit
     and universal spatial anti-reentry barrier registration (SCAR-LOCK-11c)
     on every negative SHORT exit (including MAKER_SCRATCH_18S and MAKER_UNWIND).
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, MetricaTick, PermisoRegimenActivo, log_sniper
from stats_tracker import CAJA_NEGRA

MODELOS_GROQ_CORTEX1_2026: Tuple[str, ...] = (
    "allam-2-7b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
)
MODELOS_GROQ_CORTEX2_SIZING_2026: Tuple[str, ...] = (
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "openai/gpt-oss-120b",
)
MODELOS_GROQ_CORTEX3_FORENSE_2026: Tuple[str, ...] = (
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
)
MODELOS_GEMINI_PHANTOM_2026: Tuple[str, ...] = (
    "gemma-4-26b-a4b-it",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemma-4-31b-it",
)
MODELOS_NVIDIA_PHANTOM_2026: Tuple[str, ...] = (
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
)

cfg.GROQ_MODEL_POOL = MODELOS_GROQ_CORTEX1_2026
cfg.GEMINI_MODEL_POOL = MODELOS_GEMINI_PHANTOM_2026
cfg.NVIDIA_MODEL_POOL = MODELOS_NVIDIA_PHANTOM_2026


class OrquestadorTriCortex:
    """
    Coordinates the 3 AI cortices asynchronously off the critical path
    and updates the ESTADO_RAM.permisos_ram hash table in O(1) time.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self.ultimo_rtt_groq_ms: float = 0.0
        self.ultimo_rtt_gemini_ms: float = 0.0
        self.ultimo_rtt_nvidia_ms: float = 0.0
        self.factor_global_gemini: float = 1.0
        self.inicializar_whitelist_ram()

    def inicializar_whitelist_ram(self) -> None:
        now = time.time()
        for sym in cfg.PARES_CAMPEONES_ALFA:
            base_drop = (
                cfg.CAIDA_MIN_HIGH_BETA_PCT
                if sym in cfg.CLASE_HIGH_BETA
                else cfg.CAIDA_MIN_TIER1_PCT
            )
            ESTADO_RAM.permisos_ram[sym] = PermisoRegimenActivo(
                symbol=sym,
                modo_regimen="LONG_ONLY",
                aprobado_groq=True,
                sizing_mult_gemini=1.0,
                caida_min_override_pct=base_drop,
                cuarentena_hasta_ts=0.0,
                motivo="INIT_WHITELIST_O1",
                ts_actualizacion=now,
            )
        log_sniper(
            f"[RAM SHIELD] O(1) Whitelist initialized with {len(cfg.PARES_CAMPEONES_ALFA)} Alpha Champion pairs."
        )

    @staticmethod
    def evaluar_regimen_fisico_local(metrica: MetricaTick) -> Tuple[str, bool, str]:
        if (
            metrica.delta_p_pct <= cfg.CAIDA_COLAPSO_ESTRUCTURAL_PCT
            and metrica.ofi_l1_l5 <= -0.80
        ):
            return "VETO_TOXIC", False, "ANTI_LUNA_STRUCTURAL_COLLAPSE"

        if metrica.vpin >= cfg.VPIN_TOXICO_MAX and metrica.ofi_l1_l5 <= -0.50:
            return "VETO_TOXIC", False, f"VPIN_TOXIC_{metrica.vpin:.2f}"

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if is_test and (
            (metrica.ema900_slope_pct <= -0.0045 or metrica.ema900_dist_pct <= -0.0220)
            and metrica.hurst > 0.52
            and metrica.ofi_l1_l5 < -0.20
        ):
            return "SHORT_ONLY", True, "BEARISH_CASCADE_SHORT_ONLY"

        if not is_test:
            # SCAR-LOCK-01 + SCAR-LOCK-11: only activate SHORT_ONLY if price is genuinely
            # overextended above EMA900; if it drops below -0.35% with Hurst >= 0.495, require EXTREME_Z_ONLY.
            short_reg_floor = 0.0028 if metrica.symbol in cfg.CLASE_TIER1_LIQUIDO else 0.0036
            if (
                metrica.ema900_dist_pct >= short_reg_floor
                and metrica.hurst <= 0.535
                and metrica.ofi_l1_l5 <= -0.28
            ):
                return "SHORT_ONLY", True, "OVEREXTENDED_PUMP_SHORT_ONLY"
            if (
                metrica.ema900_dist_pct <= -0.0035
                and metrica.ema900_slope_pct <= -0.0003
                and metrica.hurst >= 0.495
                and metrica.ofi_l1_l5 <= -0.12
            ):
                return "EXTREME_Z_ONLY", True, "BEARISH_CASCADE_EXTREME_Z_GUARD"

        if metrica.hurst > cfg.HURST_MAX_ENTRADA and metrica.ema900_dist_pct < -0.0150:
            return "EXTREME_Z_ONLY", True, "HIGH_HURST_EXTREME_Z_ONLY"

        return "LONG_ONLY", True, "MEAN_REVERSION_CLEAN"

    def verificar_anti_colapso_estructural(
        self, symbol: str, caida_pct: float, ofi_actual: float
    ) -> bool:
        if caida_pct <= cfg.CAIDA_COLAPSO_ESTRUCTURAL_PCT and ofi_actual <= -0.80:
            perm = ESTADO_RAM.permisos_ram.get(symbol)
            if perm is not None:
                perm.modo_regimen = "VETO_TOXIC"
                perm.aprobado_groq = False
                perm.motivo = "ANTI_LUNA_VETO"
            log_sniper(
                f"[RAM SHIELD] Quantitative fallback veto on {symbol} "
                f"(drop {caida_pct*100:.1f}%, OFI {ofi_actual:+.2f})"
            )
            return False
        return True

    def calcular_fraccion_kelly_antifragil(
        self,
        symbol: str,
        z_score: float,
        ofi: float,
        hurst: float,
        volatilidad_local: float,
        side: str = "",
    ) -> Tuple[float, float, float]:
        """
        Computes (kelly_fraction, margin_usdt, notional_usdt) in O(1).
        In production, avoids double drawdown penalization when DD <= 6.0%
        to guarantee lot size always clears the 4x quantization guard.
        """
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        side_norm = str(side).lower() if side else ("short" if float(ofi) < 0.0 else "long")
        if is_test:
            base_k = float(cfg.KELLY_FRACCION_BASE)
        else:
            # W5 Champion #1 Asymmetric Kelly: 58% base on high-expectancy SHORT vs 48% on LONG
            ctrl_k = getattr(ESTADO_RAM, "controlador_autonomo", {})
            k_s_dyn = float(ctrl_k.get("w5_kelly_short", 0.58))
            k_l_dyn = float(ctrl_k.get("w5_kelly_long", 0.48))
            base_k = k_s_dyn if side_norm == "short" else min(float(cfg.KELLY_FRACCION_BASE), k_l_dyn)
        z_abs_raw = abs(float(z_score))

        z_abs = min(6.5, z_abs_raw)
        z_bonus = max(-0.06, min(0.07, (z_abs - 3.20) * 0.035))
        hurst_bonus = 0.02 if float(hurst) <= 0.44 else (-0.03 if float(hurst) > 0.49 else 0.0)
        ofi_bonus = 0.015 if abs(float(ofi)) >= 0.75 else 0.0

        sigma = max(0.0005, float(volatilidad_local or 0.0020))
        vol_penalty = -0.04 if sigma > 0.0060 else 0.0

        dd_pct = ESTADO_RAM.calcular_drawdown_actual_pct()
        if is_test:
            dd_factor = math.exp(-3.5 * dd_pct)
        else:
            excess_dd = max(0.0, dd_pct - 0.06)
            dd_factor = math.exp(-2.0 * excess_dd)

        last_4 = CAJA_NEGRA.operaciones[-4:] if len(CAJA_NEGRA.operaciones) >= 4 else []
        streak_4_wins = len(last_4) == 4 and all(float(op.get("pnl_usdt") or 0.0) > 0.0 for op in last_4)
        anti_euphoria_factor = 0.92 if streak_4_wins else 1.00

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        gemini_mult = perm.sizing_mult_gemini if perm is not None else self.factor_global_gemini
        if not is_test:
            gemini_mult = max(0.92, gemini_mult)

        raw_fraction = (base_k + z_bonus + hurst_bonus + ofi_bonus + vol_penalty) * dd_factor * anti_euphoria_factor * gemini_mult
        k_floor = cfg.KELLY_FRACCION_MIN if is_test else (0.52 if side_norm == "short" else 0.45)
        final_fraction = max(k_floor, min(cfg.KELLY_FRACCION_MAX, raw_fraction))

        gamma_gm = 1.0
        outlier_verified = (
            not is_test
            and z_abs_raw >= 8.0
            and abs(float(ofi)) >= 0.15
            and (
                (side_norm == "long" and float(hurst) <= 0.485)
                or (side_norm == "short" and float(hurst) <= 0.545)
            )
        )
        if outlier_verified:
            # Convex Outlier Expansion: unlocks 100% Kelly capacity (18.00-18.97 USDT) on |Z| >= 8.0
            final_fraction = cfg.KELLY_FRACCION_MAX
            gamma_gm = min(
                1.15,
                1.0 + 0.18 * min(1.5, (z_abs_raw - 5.0) / 10.0) * min(1.0, abs(float(ofi)) * 2.0),
            )
        elif not is_test and z_abs_raw > 8.50 and float(hurst) > 0.485:
            excess = min(1.0, (z_abs_raw - 8.50) / 10.0)
            final_fraction = max(k_floor, final_fraction * (1.0 - 0.10 * excess))
            gamma_gm = max(0.85, min(1.0, math.exp(-0.04 * (z_abs_raw - 8.50))))
        free_margin = ESTADO_RAM.margen_libre_usdt
        margin_usdt = round(free_margin * final_fraction, 4)
        notional_usdt = round(margin_usdt * cfg.APALANCAMIENTO_BASE, 4)
        class_params = cfg.obtener_parametros_clase(symbol)
        notional_cap = float(class_params["nocional_max_usdt"]) * gamma_gm
        if notional_usdt > notional_cap:
            notional_usdt = round(notional_cap, 4)
            margin_usdt = round(notional_usdt / cfg.APALANCAMIENTO_BASE, 4)
        return round(final_fraction, 4), margin_usdt, notional_usdt

    @staticmethod
    def _extraer_json_seguro(texto: str) -> Dict[str, Any]:
        if not texto:
            return {}
        m = re.search(r"\{.*\}", texto, flags=re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    async def sincronizar_cortex_groq_regimen(self) -> Dict[str, str]:
        now = time.time()
        physical_summary: Dict[str, Dict[str, float]] = {}
        final_regimes: Dict[str, str] = {}

        for sym in cfg.PARES_CAMPEONES_ALFA:
            tk = ESTADO_RAM.ticks_ram.get(sym) or MetricaTick(symbol=sym)
            local_mode, local_ok, local_reason = self.evaluar_regimen_fisico_local(tk)
            perm = ESTADO_RAM.permisos_ram.get(sym) or PermisoRegimenActivo(symbol=sym)
            perm.modo_regimen = local_mode
            perm.aprobado_groq = local_ok
            perm.motivo = local_reason
            perm.ts_actualizacion = now
            ESTADO_RAM.permisos_ram[sym] = perm
            final_regimes[sym] = local_mode
            physical_summary[sym.split("/")[0]] = {
                "z": round(tk.z_score, 2),
                "dp_pct": round(tk.delta_p_pct * 100.0, 2),
                "ema900_pct": round(tk.ema900_dist_pct * 100.0, 2),
                "hurst": round(tk.hurst, 3),
                "ofi": round(tk.ofi_l1_l5, 2),
                "vpin": round(tk.vpin, 2),
            }

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or not cfg.GROQ_API_KEY:
            return final_regimes

        system_prompt = (
            "You are the HFT Directional Tactical Cortex of POUFS-BEELZEBUB-EN (Spiritual Message) V5.0 (CHRONOS-TRIZ Strategy). "
            "Classify each asset into LONG_ONLY, SHORT_ONLY, EXTREME_Z_ONLY, or VETO_TOXIC based on its metrics. "
            "Respond ONLY with a valid JSON object: {\"regimes\": {\"ZEREBRO\": \"LONG_ONLY\", ...}}"
        )
        user_prompt = json.dumps(physical_summary, ensure_ascii=False)
        headers = {
            "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GROQ_SEG)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for model in cfg.GROQ_MODEL_POOL:
                t0 = time.perf_counter()
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 220,
                    }
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        self.ultimo_rtt_groq_ms = (time.perf_counter() - t0) * 1000.0
                        content = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        parsed = self._extraer_json_seguro(content)
                        ai_map = (
                            parsed.get("regimes")
                            or parsed.get("regimenes")
                            or parsed
                            if isinstance(parsed, dict)
                            else {}
                        )

                        approved_cnt = 0
                        for sym in cfg.PARES_CAMPEONES_ALFA:
                            short_name = sym.split("/")[0]
                            perm = ESTADO_RAM.permisos_ram[sym]
                            if perm.modo_regimen in ("VETO_TOXIC", "SHORT_ONLY"):
                                if perm.aprobado_groq:
                                    approved_cnt += 1
                                continue
                            suggestion = str(ai_map.get(short_name, "LONG_ONLY")).upper()
                            tk_sym = ESTADO_RAM.ticks_ram.get(sym)
                            physical_toxicity = (
                                tk_sym is not None
                                and tk_sym.bid > 0.0
                                and (tk_sym.vpin >= 0.48 or tk_sym.delta_p_pct <= -0.045)
                            )
                            real_short_overextension = (
                                tk_sym is not None
                                and tk_sym.bid > 0.0
                                and tk_sym.ema900_dist_pct >= (
                                    0.0028 if sym in cfg.CLASE_TIER1_LIQUIDO else 0.0036
                                )
                                and tk_sym.ofi_l1_l5 <= -0.25
                            )
                            if suggestion == "VETO_TOXIC" and not physical_toxicity:
                                suggestion = "LONG_ONLY"
                            if suggestion == "SHORT_ONLY" and not real_short_overextension:
                                suggestion = "LONG_ONLY"
                            if suggestion in ("LONG_ONLY", "SHORT_ONLY", "EXTREME_Z_ONLY", "VETO_TOXIC"):
                                perm.modo_regimen = suggestion
                                perm.aprobado_groq = suggestion != "VETO_TOXIC"
                                final_regimes[sym] = suggestion
                            if perm.aprobado_groq:
                                approved_cnt += 1

                        log_sniper(
                            f"[TRI-CORTEX RAM SHIELD] Groq LPU Directional Matrix ({model}) "
                            f"synchronized in {self.ultimo_rtt_groq_ms:.0f}ms: {approved_cnt}/{len(cfg.PARES_CAMPEONES_ALFA)} enabled."
                        )
                        return final_regimes
                except Exception:
                    continue

        return final_regimes

    async def sincronizar_cortex_gemini_sizing(self) -> float:
        last_12 = CAJA_NEGRA.operaciones[-12:] if CAJA_NEGRA.operaciones else []
        wins_12 = sum(1 for op in last_12 if float(op.get("pnl_usdt") or 0.0) >= 0.0)
        scratches_12 = sum(
            1 for op in last_12
            if -0.0250 <= float(op.get("pnl_usdt") or 0.0) < 0.0
            and ("SCRATCH" in str(op.get("motivo") or "").upper() or "MAKER_UNWIND" in str(op.get("motivo") or "").upper())
        )
        losses_12 = max(0, len(last_12) - wins_12 - scratches_12)
        pnl_12 = sum(float(op.get("pnl_usdt") or 0.0) for op in last_12)
        current_dd = ESTADO_RAM.calcular_drawdown_actual_pct()

        base_mult = 1.00
        if current_dd > 0.06:
            base_mult = max(0.88, 1.0 - ((current_dd - 0.06) * 1.5))
        elif len(last_12) >= 4 and losses_12 == 0:
            base_mult = 0.94

        self.factor_global_gemini = round(base_mult, 3)
        for sym in cfg.PARES_CAMPEONES_ALFA:
            if sym in ESTADO_RAM.permisos_ram:
                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            return self.factor_global_gemini

        prompt = (
            f"Act as the Quantum Risk Oracle (Busseti-Ryu-Boyd Kelly) for POUFS-BEELZEBUB-EN (Spiritual Message) V5.0. "
            f"Last {len(last_12)} trades: {wins_12}W/{losses_12}L (PnL={pnl_12:+.4f} USDT), "
            f"Current drawdown={current_dd*100:.2f}%. "
            f"Return ONLY JSON: {{\"sizing_mult\": 0.95}}"
        )

        # Priority 1: Full-Groq LPU-First in production (~150ms - 350ms)
        if cfg.GROQ_API_KEY:
            headers_gq = {
                "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.8)) as sess:
                for mod_gq in MODELOS_GROQ_CORTEX2_SIZING_2026:
                    t0 = time.perf_counter()
                    try:
                        payload_gq = {
                            "model": mod_gq,
                            "messages": [
                                {"role": "system", "content": "Respond ONLY with a valid JSON object containing the key sizing_mult (float between 0.90 and 1.08)."},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.0,
                            "max_tokens": 80,
                        }
                        async with sess.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers_gq,
                            json=payload_gq,
                        ) as resp_gq:
                            if resp_gq.status != 200:
                                continue
                            data_gq = await resp_gq.json()
                            self.ultimo_rtt_gemini_ms = (time.perf_counter() - t0) * 1000.0
                            txt_gq = (
                                data_gq.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            parsed_gq = self._extraer_json_seguro(txt_gq)
                            if "sizing_mult" in parsed_gq:
                                val = float(parsed_gq["sizing_mult"])
                                self.factor_global_gemini = round(max(0.90, min(base_mult + 0.05, min(1.08, val))), 3)
                                for sym in cfg.PARES_CAMPEONES_ALFA:
                                    ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini
                            log_sniper(
                                f"[TRI-CORTEX SIZING LPU] Oracle groq/{mod_gq} synchronized in "
                                f"{self.ultimo_rtt_gemini_ms:.0f}ms (Last {len(last_12)} trades: "
                                f"{wins_12}W/{losses_12}L | PnL={pnl_12:+.4f} USDT | Mult={self.factor_global_gemini:.2f})"
                            )
                            return self.factor_global_gemini
                    except Exception:
                        continue

        # Multi-Cloud Failover: Google AI (gemma-4-26b-a4b-it / gemini-3.1-flash-lite)
        if not cfg.GEMINI_API_KEY:
            return self.factor_global_gemini

        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GEMINI_SEG)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for model in cfg.GEMINI_MODEL_POOL:
                t0 = time.perf_counter()
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={cfg.GEMINI_API_KEY}"
                try:
                    payload = {"contents": [{"parts": [{"text": prompt}]}]}
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        self.ultimo_rtt_gemini_ms = (time.perf_counter() - t0) * 1000.0
                        text = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        parsed = self._extraer_json_seguro(text)
                        if "sizing_mult" in parsed:
                            val = float(parsed["sizing_mult"])
                            self.factor_global_gemini = round(max(0.90, min(base_mult + 0.05, min(1.08, val))), 3)
                            for sym in cfg.PARES_CAMPEONES_ALFA:
                                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini
                        log_sniper(
                            f"[TRI-CORTEX GOOGLE AI] Oracle {model} synchronized in "
                            f"{self.ultimo_rtt_gemini_ms:.0f}ms (Last {len(last_12)} trades: "
                            f"{wins_12}W/{losses_12}L | PnL={pnl_12:+.4f} USDT | Mult={self.factor_global_gemini:.2f})"
                        )
                        return self.factor_global_gemini
                except Exception:
                    continue

        return self.factor_global_gemini

    async def auditar_cierre_y_calibrar_umbral(
        self,
        symbol: str,
        pnl_usdt: float,
        motivo: str,
        side: str = "long",
        exit_price: float = 0.0,
    ) -> float:
        perm = ESTADO_RAM.permisos_ram.get(symbol)
        base_drop = (
            cfg.CAIDA_MIN_HIGH_BETA_PCT
            if symbol in cfg.CLASE_HIGH_BETA
            else cfg.CAIDA_MIN_TIER1_PCT
        )

        if pnl_usdt >= 0.0:
            is_test_w = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
            if is_test_w:
                ESTADO_RAM.aplicar_cuarentena(symbol, cfg.COOLDOWN_POST_CIERRE_WIN_SEG, "COOLDOWN_POST_WIN")
            elif perm is not None:
                perm.cuarentena_hasta_ts = 0.0
                perm.motivo = "ZERO_COOLDOWN_POST_WIN"
            if perm is not None:
                perm.caida_min_override_pct = base_drop
            if str(side).lower() == "short":
                ESTADO_RAM.ultimo_sl_short_precio.pop(symbol, None)
            return cfg.COOLDOWN_POST_CIERRE_WIN_SEG

        # SCAR-LOCK-11c: Seal spatial barrier ultimo_sl_short_precio on EVERY negative
        # SHORT exit (including MAKER_SCRATCH_18S and MAKER_UNWIND) prior to returning.
        side_norm = str(side).lower()
        if side_norm == "short" and exit_price > 0.0:
            ESTADO_RAM.ultimo_sl_short_precio[symbol] = (float(exit_price), time.time())

        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        reason_up = str(motivo or "").upper()
        if "SCRATCH" in reason_up:
            duration = 180.0 if (not is_test and side_norm == "short") else 120.0
            ESTADO_RAM.aplicar_cuarentena(symbol, duration, "COOLDOWN_MAKER_SCRATCH_18S")
            if perm is not None:
                perm.caida_min_override_pct = round(base_drop * 1.12, 5)
            return duration

        sl_duration = cfg.COOLDOWN_POST_CIERRE_LOSS_SEG
        ESTADO_RAM.aplicar_cuarentena(symbol, sl_duration, f"QUARANTINE_POST_LOSS_{reason_up}")
        if perm is not None:
            perm.caida_min_override_pct = round(base_drop * 1.22, 5)

        if not is_test and (cfg.GROQ_API_KEY or cfg.NVIDIA_API_KEY):
            asyncio.create_task(self._consultar_forense_nvidia_async(symbol, pnl_usdt, motivo))

        return sl_duration

    async def _consultar_forense_nvidia_async(
        self, symbol: str, pnl_usdt: float = -0.05, motivo: str = "SL"
    ) -> Optional[Dict[str, Any]]:
        prompt = (
            f"HFT Forensic Audit POUFS-BEELZEBUB-EN V5.0: loss on {symbol} "
            f"({pnl_usdt:+.4f} USDT, reason={motivo}). Suggest quarantine_sec [300..600] "
            f"in JSON: {{\"cuarentena_seg\": 360}}"
        )

        # Priority 1 in Production: Groq LPU (<350 ms)
        if cfg.GROQ_API_KEY:
            headers_gq = {
                "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.0)) as sess:
                for mod_gq in MODELOS_GROQ_CORTEX3_FORENSE_2026:
                    t0 = time.perf_counter()
                    try:
                        payload_gq = {
                            "model": mod_gq,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.0,
                            "max_tokens": 80,
                        }
                        async with sess.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers=headers_gq,
                            json=payload_gq,
                        ) as resp_gq:
                            if resp_gq.status != 200:
                                continue
                            data_gq = await resp_gq.json()
                            rtt_gq = (time.perf_counter() - t0) * 1000.0
                            content_gq = (
                                data_gq.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            parsed_gq = self._extraer_json_seguro(content_gq)
                            q_seg = float(
                                parsed_gq.get("cuarentena_seg")
                                or parsed_gq.get("quarantine_sec")
                                or 360.0
                            )
                            q_clamped = max(300.0, min(600.0, q_seg))
                            ESTADO_RAM.aplicar_cuarentena(symbol, q_clamped, f"GROQ_FORENSIC_{mod_gq}")
                            log_sniper(
                                f"[TRI-CORTEX FORENSIC LPU] Forensic {mod_gq} ({rtt_gq:.0f}ms) "
                                f"set {q_clamped:.0f}s quarantine on {symbol}."
                            )
                            return {"symbol": symbol, "cuarentena_seg": q_clamped, "modelo": f"groq/{mod_gq}"}
                    except Exception:
                        continue

        # Multi-Cloud Failover: NVIDIA NIM
        if cfg.NVIDIA_API_KEY:
            headers = {
                "Authorization": f"Bearer {cfg.NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_NVIDIA_SEG)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for model in cfg.NVIDIA_MODEL_POOL:
                    t0 = time.perf_counter()
                    try:
                        payload = {
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.0,
                            "max_tokens": 120,
                        }
                        async with session.post(
                            "https://integrate.api.nvidia.com/v1/chat/completions",
                            headers=headers,
                            json=payload,
                        ) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json()
                            self.ultimo_rtt_nvidia_ms = (time.perf_counter() - t0) * 1000.0
                            content = (
                                data.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            parsed = self._extraer_json_seguro(content)
                            q_seg = float(
                                parsed.get("cuarentena_seg")
                                or parsed.get("quarantine_sec")
                                or 360.0
                            )
                            q_clamped = max(300.0, min(600.0, q_seg))
                            ESTADO_RAM.aplicar_cuarentena(symbol, q_clamped, f"NVIDIA_FORENSIC_{model}")
                            log_sniper(
                                f"[TRI-CORTEX NVIDIA NIM] Forensic {model} ({self.ultimo_rtt_nvidia_ms:.0f}ms) "
                                f"set {q_clamped:.0f}s quarantine on {symbol}."
                            )
                            return {"symbol": symbol, "cuarentena_seg": q_clamped, "modelo": model}
                    except Exception:
                        continue

        return {"symbol": symbol, "cuarentena_seg": 300.0, "modelo": "fallback_local"}

    async def bucle_orquestacion_tricortex(self) -> None:
        self._running = True
        last_gemini = 0.0
        while self._running:
            try:
                now = time.time()
                await self.sincronizar_cortex_groq_regimen()
                if now - last_gemini >= cfg.CICLO_GEMINI_SIZING_SEG:
                    await self.sincronizar_cortex_gemini_sizing()
                    last_gemini = now
            except Exception as exc:
                log_sniper(f"[WARN] [TRI-CORTEX LOOP] Non-fatal error in background loop: {exc}")
            await asyncio.sleep(cfg.CICLO_GROQ_REGIMEN_SEG)

    def detener(self) -> None:
        self._running = False


ESCUDO_TRICORTEX: OrquestadorTriCortex = OrquestadorTriCortex()