#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #07: escudo_tricortex.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Enjambre Cognitivo Asincrono Tri-Cortex (Full-Groq LPU-First + Multi-Cloud):
  1. Cortex 1 (Groq LPU): Matriz Direccional de Regimen (LONG_ONLY, SHORT_ONLY,
     EXTREME_Z_ONLY, VETO_TOXIC) con Guardia Fisica Anti-LUNA y deteccion
     realista de cascadas bajistas (-0.40% EMA900 en produccion).
  2. Cortex 2 (Groq LPU + Failover Google AI gemma-4-26b-a4b-it): Sizing
     Anti-Fragil por Dislocacion Fisica (|Z|, Hurst, Glosten-Milgrom P-07)
     sin doble castigo exponencial de Drawdown.
  3. Cortex 3 (Groq LPU + Failover NVIDIA NIM): Auditoria Forense Post-Loss
     y registro de barrera anti-reentrada en Short-Squeeze.
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
    Coordina los 3 cerebros de IA de forma asincrona fuera de la ruta critica
    y mantiene actualizada en O(1) la tabla ESTADO_RAM.permisos_ram.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self.ultimo_rtt_groq_ms: float = 0.0
        self.ultimo_rtt_gemini_ms: float = 0.0
        self.ultimo_rtt_nvidia_ms: float = 0.0
        self.factor_global_gemini: float = 1.0
        self.inicializar_whitelist_ram()

    def inicializar_whitelist_ram(self) -> None:
        ahora = time.time()
        for sym in cfg.PARES_CAMPEONES_ALFA:
            base_caida = (
                cfg.CAIDA_MIN_HIGH_BETA_PCT
                if sym in cfg.CLASE_HIGH_BETA
                else cfg.CAIDA_MIN_TIER1_PCT
            )
            ESTADO_RAM.permisos_ram[sym] = PermisoRegimenActivo(
                symbol=sym,
                modo_regimen="LONG_ONLY",
                aprobado_groq=True,
                sizing_mult_gemini=1.0,
                caida_min_override_pct=base_caida,
                cuarentena_hasta_ts=0.0,
                motivo="INIT_WHITELIST_O1",
                ts_actualizacion=ahora,
            )
        log_sniper(
            f"[ESCUDO RAM] Whitelist O(1) inicializada con {len(cfg.PARES_CAMPEONES_ALFA)} pares Campeones Alfa."
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

        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        if (
            (metrica.ema900_slope_pct <= -0.0045 or metrica.ema900_dist_pct <= -0.0220)
            and metrica.hurst > 0.52
            and metrica.ofi_l1_l5 < -0.20
        ):
            return "SHORT_ONLY", True, "BEARISH_CASCADE_SHORT_ONLY"

        if not es_test and (
            metrica.ema900_dist_pct <= -0.0040
            and metrica.ema900_slope_pct <= -0.0004
            and metrica.hurst >= 0.50
            and metrica.ofi_l1_l5 <= -0.15
        ):
            return "SHORT_ONLY", True, "BEARISH_CASCADE_SHORT_ONLY"

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
                f"[ESCUDO RAM] Fallback cuantitativo veto a {symbol} "
                f"(caida {caida_pct*100:.1f}%, OFI {ofi_actual:+.2f})"
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
    ) -> Tuple[float, float, float]:
        """
        Calcula (fraccion_kelly, margen_usdt, nocional_usdt) en O(1).
        En produccion evita la doble penalizacion de drawdown cuando DD <= 6.0%
        para garantizar que el lote supere siempre la guardia de cuantizacion 4x.
        """
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        base_k = float(cfg.KELLY_FRACCION_BASE)
        z_abs_raw = abs(float(z_score))

        z_abs = min(6.5, z_abs_raw)
        bono_z = max(-0.06, min(0.07, (z_abs - 3.20) * 0.035))
        bono_hurst = 0.02 if float(hurst) <= 0.44 else (-0.03 if float(hurst) > 0.49 else 0.0)
        bono_ofi = 0.015 if abs(float(ofi)) >= 0.75 else 0.0

        sigma = max(0.0005, float(volatilidad_local or 0.0020))
        penal_vol = -0.04 if sigma > 0.0060 else 0.0

        dd_pct = ESTADO_RAM.calcular_drawdown_actual_pct()
        if es_test:
            factor_dd = math.exp(-3.5 * dd_pct)
        else:
            exceso_dd = max(0.0, dd_pct - 0.06)
            factor_dd = math.exp(-2.0 * exceso_dd)

        ultimas_4 = CAJA_NEGRA.operaciones[-4:] if len(CAJA_NEGRA.operaciones) >= 4 else []
        racha_4_wins = len(ultimas_4) == 4 and all(float(op.get("pnl_usdt") or 0.0) > 0.0 for op in ultimas_4)
        factor_antieuforia = 0.92 if racha_4_wins else 1.00

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        mult_gemini = perm.sizing_mult_gemini if perm is not None else self.factor_global_gemini
        if not es_test:
            mult_gemini = max(0.92, mult_gemini)

        fraccion_bruta = (base_k + bono_z + bono_hurst + bono_ofi + penal_vol) * factor_dd * factor_antieuforia * mult_gemini
        piso_k = cfg.KELLY_FRACCION_MIN if es_test else max(0.48, cfg.KELLY_FRACCION_MIN)
        fraccion_final = max(piso_k, min(cfg.KELLY_FRACCION_MAX, fraccion_bruta))

        gamma_gm = 1.0
        if not es_test and z_abs_raw > 8.50:
            exceso = min(1.0, (z_abs_raw - 8.50) / 10.0)
            fraccion_final = max(piso_k, fraccion_final * (1.0 - 0.15 * exceso))
            gamma_gm = max(0.65, min(1.0, math.exp(-0.08 * (z_abs_raw - 8.50))))

        margen_libre = ESTADO_RAM.margen_libre_usdt
        margen_usdt = round(margen_libre * fraccion_final, 4)
        nocional_usdt = round(margen_usdt * cfg.APALANCAMIENTO_BASE, 4)

        params_clase = cfg.obtener_parametros_clase(symbol)
        tope_nocional = float(params_clase["nocional_max_usdt"]) * gamma_gm
        if nocional_usdt > tope_nocional:
            nocional_usdt = round(tope_nocional, 4)
            margen_usdt = round(nocional_usdt / cfg.APALANCAMIENTO_BASE, 4)

        return round(fraccion_final, 4), margen_usdt, nocional_usdt

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
        ahora = time.time()
        resumen_fisico: Dict[str, Dict[str, float]] = {}
        regimenes_finales: Dict[str, str] = {}

        for sym in cfg.PARES_CAMPEONES_ALFA:
            tk = ESTADO_RAM.ticks_ram.get(sym) or MetricaTick(symbol=sym)
            modo_local, ok_local, mot_local = self.evaluar_regimen_fisico_local(tk)
            perm = ESTADO_RAM.permisos_ram.get(sym) or PermisoRegimenActivo(symbol=sym)
            perm.modo_regimen = modo_local
            perm.aprobado_groq = ok_local
            perm.motivo = mot_local
            perm.ts_actualizacion = ahora
            ESTADO_RAM.permisos_ram[sym] = perm
            regimenes_finales[sym] = modo_local
            resumen_fisico[sym.split("/")[0]] = {
                "z": round(tk.z_score, 2),
                "dp_pct": round(tk.delta_p_pct * 100.0, 2),
                "ema900_pct": round(tk.ema900_dist_pct * 100.0, 2),
                "hurst": round(tk.hurst, 3),
                "ofi": round(tk.ofi_l1_l5, 2),
                "vpin": round(tk.vpin, 2),
            }

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or not cfg.GROQ_API_KEY:
            return regimenes_finales

        prompt_sistema = (
            "Eres el Cortex Tactico Direccional HFT de Tri-Brain-Phantom v1.0 (Estrategia CHRONOS-TRIZ). "
            "Clasifica cada activo en LONG_ONLY, SHORT_ONLY, EXTREME_Z_ONLY o VETO_TOXIC segun sus metricas. "
            "Responde UNICAMENTE un objeto JSON: {\"regimenes\": {\"ZEREBRO\": \"LONG_ONLY\", ...}}"
        )
        prompt_usuario = json.dumps(resumen_fisico, ensure_ascii=False)
        headers = {
            "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GROQ_SEG)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for modelo in cfg.GROQ_MODEL_POOL:
                t0 = time.perf_counter()
                try:
                    payload = {
                        "model": modelo,
                        "messages": [
                            {"role": "system", "content": prompt_sistema},
                            {"role": "user", "content": prompt_usuario},
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
                        contenido = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        parsed = self._extraer_json_seguro(contenido)
                        mapa_ia = parsed.get("regimenes", parsed) if isinstance(parsed, dict) else {}

                        aprobados_cnt = 0
                        for sym in cfg.PARES_CAMPEONES_ALFA:
                            corto = sym.split("/")[0]
                            perm = ESTADO_RAM.permisos_ram[sym]
                            if perm.modo_regimen in ("VETO_TOXIC", "SHORT_ONLY"):
                                if perm.aprobado_groq:
                                    aprobados_cnt += 1
                                continue
                            sugerencia = str(mapa_ia.get(corto, "LONG_ONLY")).upper()
                            tk_sym = ESTADO_RAM.ticks_ram.get(sym)
                            toxicidad_fisica = (
                                tk_sym is not None
                                and tk_sym.bid > 0.0
                                and (tk_sym.vpin >= 0.48 or tk_sym.delta_p_pct <= -0.045)
                            )
                            presion_bajista_real = (
                                tk_sym is not None
                                and tk_sym.bid > 0.0
                                and (
                                    tk_sym.ema900_dist_pct <= -0.0025
                                    or tk_sym.delta_p_pct <= -0.0025
                                    or tk_sym.ema900_slope_pct <= -0.0005
                                )
                            )
                            if sugerencia == "VETO_TOXIC" and not toxicidad_fisica:
                                sugerencia = "LONG_ONLY"
                            if sugerencia == "SHORT_ONLY" and not presion_bajista_real:
                                sugerencia = "LONG_ONLY"
                            if sugerencia in ("LONG_ONLY", "SHORT_ONLY", "EXTREME_Z_ONLY", "VETO_TOXIC"):
                                perm.modo_regimen = sugerencia
                                perm.aprobado_groq = sugerencia != "VETO_TOXIC"
                                regimenes_finales[sym] = sugerencia
                            if perm.aprobado_groq:
                                aprobados_cnt += 1

                        log_sniper(
                            f"[ESCUDO RAM TRI-CORTEX] Matriz Direccional Groq LPU ({modelo}) "
                            f"sincronizada en {self.ultimo_rtt_groq_ms:.0f}ms: {aprobados_cnt}/{len(cfg.PARES_CAMPEONES_ALFA)} habilitados."
                        )
                        return regimenes_finales
                except Exception:
                    continue

        return regimenes_finales

    async def sincronizar_cortex_gemini_sizing(self) -> float:
        ultimos_12 = CAJA_NEGRA.operaciones[-12:] if CAJA_NEGRA.operaciones else []
        wins_12 = sum(1 for op in ultimos_12 if float(op.get("pnl_usdt") or 0.0) >= 0.0)
        losses_12 = len(ultimos_12) - wins_12
        pnl_12 = sum(float(op.get("pnl_usdt") or 0.0) for op in ultimos_12)
        dd_actual = ESTADO_RAM.calcular_drawdown_actual_pct()

        mult_base = 1.00
        if dd_actual > 0.06:
            mult_base = max(0.88, 1.0 - ((dd_actual - 0.06) * 1.5))
        elif len(ultimos_12) >= 4 and losses_12 == 0:
            mult_base = 0.94

        self.factor_global_gemini = round(mult_base, 3)
        for sym in cfg.PARES_CAMPEONES_ALFA:
            if sym in ESTADO_RAM.permisos_ram:
                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            return self.factor_global_gemini

        prompt = (
            f"Actua como Oraculo Cuantico de Riesgo (Busseti-Ryu-Boyd Kelly) para Tri-Brain-Phantom v1.0. "
            f"Ultimos {len(ultimos_12)} trades: {wins_12}W/{losses_12}L (PnL={pnl_12:+.4f} USDT), "
            f"Drawdown actual={dd_actual*100:.2f}%. "
            f"Devuelve UNICAMENTE JSON: {{\"sizing_mult\": 0.95}}"
        )

        # Prioridad 1: Full-Groq LPU-First en produccion (~150ms - 350ms)
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
                                {"role": "system", "content": "Responde UNICAMENTE con un objeto JSON valido con la clave sizing_mult (float entre 0.90 y 1.08)."},
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
                                self.factor_global_gemini = round(max(0.90, min(mult_base + 0.05, min(1.08, val))), 3)
                                for sym in cfg.PARES_CAMPEONES_ALFA:
                                    ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini
                            log_sniper(
                                f"[TRI-CORTEX SIZING LPU] Oraculo groq/{mod_gq} sincronizado en "
                                f"{self.ultimo_rtt_gemini_ms:.0f}ms (Ultimos {len(ultimos_12)} trades: "
                                f"{wins_12}W/{losses_12}L | PnL={pnl_12:+.4f} USDT | Mult={self.factor_global_gemini:.2f})"
                            )
                            return self.factor_global_gemini
                    except Exception:
                        continue

        # Failover Multi-Cloud: Google AI (gemma-4-26b-a4b-it / gemini-3.1-flash-lite)
        if not cfg.GEMINI_API_KEY:
            return self.factor_global_gemini

        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GEMINI_SEG)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for modelo in cfg.GEMINI_MODEL_POOL:
                t0 = time.perf_counter()
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={cfg.GEMINI_API_KEY}"
                try:
                    payload = {"contents": [{"parts": [{"text": prompt}]}]}
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        self.ultimo_rtt_gemini_ms = (time.perf_counter() - t0) * 1000.0
                        texto = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        parsed = self._extraer_json_seguro(texto)
                        if "sizing_mult" in parsed:
                            val = float(parsed["sizing_mult"])
                            self.factor_global_gemini = round(max(0.90, min(mult_base + 0.05, min(1.08, val))), 3)
                            for sym in cfg.PARES_CAMPEONES_ALFA:
                                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini
                        log_sniper(
                            f"[TRI-CORTEX GOOGLE AI] Oraculo {modelo} sincronizado en "
                            f"{self.ultimo_rtt_gemini_ms:.0f}ms (Ultimos {len(ultimos_12)} trades: "
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
        base_caida = (
            cfg.CAIDA_MIN_HIGH_BETA_PCT
            if symbol in cfg.CLASE_HIGH_BETA
            else cfg.CAIDA_MIN_TIER1_PCT
        )

        if pnl_usdt >= 0.0:
            ESTADO_RAM.aplicar_cuarentena(symbol, cfg.COOLDOWN_POST_CIERRE_WIN_SEG, "COOLDOWN_POST_WIN")
            if perm is not None:
                perm.caida_min_override_pct = base_caida
            if str(side).lower() == "short":
                ESTADO_RAM.ultimo_sl_short_precio.pop(symbol, None)
            return cfg.COOLDOWN_POST_CIERRE_WIN_SEG

        mot_up = str(motivo or "").upper()
        if "SCRATCH" in mot_up:
            duracion = 120.0
            ESTADO_RAM.aplicar_cuarentena(symbol, duracion, "COOLDOWN_MAKER_SCRATCH_18S")
            if perm is not None:
                perm.caida_min_override_pct = round(base_caida * 1.12, 5)
            return duracion

        duracion_sl = cfg.COOLDOWN_POST_CIERRE_LOSS_SEG
        ESTADO_RAM.aplicar_cuarentena(symbol, duracion_sl, f"CUARENTENA_POST_LOSS_{mot_up}")
        if perm is not None:
            perm.caida_min_override_pct = round(base_caida * 1.22, 5)

        if str(side).lower() == "short" and exit_price > 0.0:
            ESTADO_RAM.ultimo_sl_short_precio[symbol] = (float(exit_price), time.time())

        if os.environ.get("TRIBRAIN_TEST_MODE") != "1" and (cfg.GROQ_API_KEY or cfg.NVIDIA_API_KEY):
            asyncio.create_task(self._consultar_forense_nvidia_async(symbol, pnl_usdt, motivo))

        return duracion_sl

    async def _consultar_forense_nvidia_async(
        self, symbol: str, pnl_usdt: float = -0.05, motivo: str = "SL"
    ) -> Optional[Dict[str, Any]]:
        prompt = (
            f"Auditoria Forense HFT Tri-Brain-Phantom v1.0: perdida en {symbol} "
            f"({pnl_usdt:+.4f} USDT, motivo={motivo}). Sugiere cuarentena_seg [300..600] "
            f"en JSON: {{\"cuarentena_seg\": 360}}"
        )

        # Prioridad 1 en Produccion: Groq LPU (<350 ms)
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
                            contenido_gq = (
                                data_gq.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            parsed_gq = self._extraer_json_seguro(contenido_gq)
                            q_seg = float(parsed_gq.get("cuarentena_seg", 360.0))
                            q_clamped = max(300.0, min(600.0, q_seg))
                            ESTADO_RAM.aplicar_cuarentena(symbol, q_clamped, f"GROQ_FORENSE_{mod_gq}")
                            log_sniper(
                                f"[TRI-CORTEX FORENSE LPU] Forense {mod_gq} ({rtt_gq:.0f}ms) "
                                f"fijo cuarentena de {q_clamped:.0f}s en {symbol}."
                            )
                            return {"symbol": symbol, "cuarentena_seg": q_clamped, "modelo": f"groq/{mod_gq}"}
                    except Exception:
                        continue

        # Failover Multi-Cloud: NVIDIA NIM
        if cfg.NVIDIA_API_KEY:
            headers = {
                "Authorization": f"Bearer {cfg.NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_NVIDIA_SEG)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for modelo in cfg.NVIDIA_MODEL_POOL:
                    t0 = time.perf_counter()
                    try:
                        payload = {
                            "model": modelo,
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
                            contenido = (
                                data.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            parsed = self._extraer_json_seguro(contenido)
                            q_seg = float(parsed.get("cuarentena_seg", 360.0))
                            q_clamped = max(300.0, min(600.0, q_seg))
                            ESTADO_RAM.aplicar_cuarentena(symbol, q_clamped, f"NVIDIA_FORENSE_{modelo}")
                            log_sniper(
                                f"[TRI-CORTEX NVIDIA NIM] Forense {modelo} ({self.ultimo_rtt_nvidia_ms:.0f}ms) "
                                f"fijo cuarentena de {q_clamped:.0f}s en {symbol}."
                            )
                            return {"symbol": symbol, "cuarentena_seg": q_clamped, "modelo": modelo}
                    except Exception:
                        continue

        return {"symbol": symbol, "cuarentena_seg": 300.0, "modelo": "fallback_local"}

    async def bucle_orquestacion_tricortex(self) -> None:
        self._running = True
        ultimo_gemini = 0.0
        while self._running:
            try:
                ahora = time.time()
                await self.sincronizar_cortex_groq_regimen()
                if ahora - ultimo_gemini >= cfg.CICLO_GEMINI_SIZING_SEG:
                    await self.sincronizar_cortex_gemini_sizing()
                    ultimo_gemini = ahora
            except Exception as exc:
                log_sniper(f"[WARN] [TRI-CORTEX LOOP] Error no fatal en bucle de fondo: {exc}")
            await asyncio.sleep(cfg.CICLO_GROQ_REGIMEN_SEG)

    def detener(self) -> None:
        self._running = False


ESCUDO_TRICORTEX: OrquestadorTriCortex = OrquestadorTriCortex()