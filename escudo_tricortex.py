#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #07: escudo_tricortex.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Reingenieria Funcional 10/10 del Enjambre Tri-Cortex (Fuera de Ruta Critica):
  1. Cortex 1 (Groq LPU): Matriz Direccional de Regimen (LONG_ONLY, SHORT_ONLY,
     EXTREME_Z_ONLY, VETO_TOXIC) con Guardia Fisica Anti-LUNA.
  2. Cortex 2 (Google Gemini): Dimensionamiento Anti-Fragil por Magnitud de
     Dislocacion Fisica (|Z|, Hurst, Volatilidad y Freno Anti-Euforia).
  3. Cortex 3 (NVIDIA NIM / DeepSeek): Calibracion Pre-Vuelo de Umbrales
     Microestructurales + Auditoria Forense Post-Loss.
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
        """Inicializa la tabla hash O(1) en RAM para los 7 Campeones Alfa."""
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

    # ==========================================================================
    # 1. CLASIFICADOR FISICO DETERMINISTA Y FILTRO ANTI-LUNA (0 MS FALLBACK)
    # ==========================================================================
    @staticmethod
    def evaluar_regimen_fisico_local(metrica: MetricaTick) -> Tuple[str, bool, str]:
        """
        Evalua las ecuaciones fisicas del activo en O(1):
          - Filtro Anti-LUNA: caida <= -6.5% con OFI <= -0.80 -> VETO_TOXIC.
          - Toxicidad VPIN extrema: VPIN >= 0.58 con OFI < -0.50 -> VETO_TOXIC.
          - Cascada Bajista Estructural: pendiente EMA900 <= -0.45% o distancia
            EMA900 <= -2.20% con Hurst > 0.52 y OFI < -0.25 -> SHORT_ONLY.
          - Transicion Volatil: Hurst entre 0.49 y 0.52 -> EXTREME_Z_ONLY.
          - Reversion Limpia: Hurst <= 0.49 -> LONG_ONLY.
        """
        # 1. Filtro Anti-Colapso Estructural (Anti-LUNA)
        if (
            metrica.delta_p_pct <= cfg.CAIDA_COLAPSO_ESTRUCTURAL_PCT
            and metrica.ofi_l1_l5 <= -0.80
        ):
            return "VETO_TOXIC", False, "ANTI_LUNA_STRUCTURAL_COLLAPSE"

        # 2. Bloqueo por toxicidad informacional severa (VPIN)
        if metrica.vpin >= cfg.VPIN_TOXICO_MAX and metrica.ofi_l1_l5 <= -0.50:
            return "VETO_TOXIC", False, f"VPIN_TOXIC_{metrica.vpin:.2f}"

        # 3. Deteccion de Tendencia Bajista Persistente -> Conmutar a SHORT_ONLY
        if (
            (metrica.ema900_slope_pct <= -0.0045 or metrica.ema900_dist_pct <= -0.0220)
            and metrica.hurst > 0.52
            and metrica.ofi_l1_l5 < -0.20
        ):
            return "SHORT_ONLY", True, "BEARISH_CASCADE_SHORT_ONLY"

        # 4. Regimen de Transicion -> Exigir dislocacion extrema (|Z| >= 4.50)
        if metrica.hurst > cfg.HURST_MAX_ENTRADA and metrica.ema900_dist_pct < -0.0150:
            return "EXTREME_Z_ONLY", True, "HIGH_HURST_EXTREME_Z_ONLY"

        return "LONG_ONLY", True, "MEAN_REVERSION_CLEAN"

    def verificar_anti_colapso_estructural(
        self, symbol: str, caida_pct: float, ofi_actual: float
    ) -> bool:
        """
        Verifica en tiempo constante si un activo sufre un colapso tipo LUNA.
        Retorna True si el activo es seguro, False si queda vetado en RAM.
        """
        if caida_pct <= cfg.CAIDA_COLAPSO_ESTRUCTURAL_PCT and ofi_actual <= -0.80:
            perm = ESTADO_RAM.permisos_ram.get(symbol)
            if perm is not None:
                perm.modo_regimen = "VETO_TOXIC"
                perm.aprobado_groq = False
                perm.motivo = "ANTI_LUNA_VETO"
            log_sniper(
                f"[ESCUDO RAM] Fallback cuantitativo vetó a {symbol} "
                f"(caída {caida_pct*100:.1f}%, OFI {ofi_actual:+.2f})"
            )
            return False
        return True

    # ==========================================================================
    # 2. DIMENSIONAMIENTO ANTI-FRAGIL DE KELLY (BUSSETI-RYU-BOYD + GEMINI)
    # ==========================================================================
    def calcular_fraccion_kelly_antifragil(
        self,
        symbol: str,
        z_score: float,
        ofi: float,
        hurst: float,
        volatilidad_local: float,
    ) -> Tuple[float, float, float]:
        """
        Calcula (fraccion_kelly, margen_usdt, nocional_usdt) en O(1) eliminando
        el sesgo prociclico. Escala con la fuerza fisica de la sennal (|Z|, OFI, Hurst)
        y aplica contraccion exponencial por Drawdown y freno Anti-Euforia.
        """
        base_k = float(cfg.KELLY_FRACCION_BASE)

        # 1. Conviccion fisica por magnitud de dislocacion |Z| y absorcion OFI
        z_abs = min(6.5, abs(float(z_score)))
        bono_z = max(-0.06, min(0.07, (z_abs - 3.20) * 0.035))
        bono_hurst = 0.02 if float(hurst) <= 0.44 else (-0.03 if float(hurst) > 0.49 else 0.0)
        bono_ofi = 0.015 if abs(float(ofi)) >= 0.75 else 0.0

        # 2. Penalizacion por volatilidad local excesiva
        sigma = max(0.0005, float(volatilidad_local or 0.0020))
        penal_vol = -0.04 if sigma > 0.0060 else 0.0

        # 3. Penalizacion convexa por Drawdown de cuenta (Busseti-Ryu-Boyd)
        dd_pct = ESTADO_RAM.calcular_drawdown_actual_pct()
        factor_dd = math.exp(-3.5 * dd_pct)

        # 4. Freno Anti-Euforia: si las ultimas 4 operaciones fueron victorias seguidas,
        # recortar un 8% la exposicion para proteger la curva de capital antes de una regresion
        ultimas_4 = CAJA_NEGRA.operaciones[-4:] if len(CAJA_NEGRA.operaciones) >= 4 else []
        racha_4_wins = len(ultimas_4) == 4 and all(float(op.get("pnl_usdt") or 0.0) > 0.0 for op in ultimas_4)
        factor_antieuforia = 0.92 if racha_4_wins else 1.00

        perm = ESTADO_RAM.permisos_ram.get(symbol)
        mult_gemini = perm.sizing_mult_gemini if perm is not None else self.factor_global_gemini

        fraccion_bruta = (base_k + bono_z + bono_hurst + bono_ofi + penal_vol) * factor_dd * factor_antieuforia * mult_gemini
        fraccion_final = max(cfg.KELLY_FRACCION_MIN, min(cfg.KELLY_FRACCION_MAX, fraccion_bruta))

        margen_libre = ESTADO_RAM.margen_libre_usdt
        margen_usdt = round(margen_libre * fraccion_final, 4)
        nocional_usdt = round(margen_usdt * cfg.APALANCAMIENTO_BASE, 4)

        # Respetar tope nocional anti-seleccion adversa en High-Beta (ZEREBRO, WAL)
        params_clase = cfg.obtener_parametros_clase(symbol)
        tope_nocional = float(params_clase["nocional_max_usdt"])
        if nocional_usdt > tope_nocional:
            nocional_usdt = tope_nocional
            margen_usdt = round(nocional_usdt / cfg.APALANCAMIENTO_BASE, 4)

        return round(fraccion_final, 4), margen_usdt, nocional_usdt

    # ==========================================================================
    # 3. CORTEX 1: GROQ LPU (MATRIZ DIRECCIONAL DE REGIMEN CADA 45S)
    # ==========================================================================
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
        """
        Consulta el pool de modelos Groq LPU con las metricas fisicas actuales
        y combina la respuesta con la Guardia Fisica Determinista.
        """
        ahora = time.time()
        resumen_fisico: Dict[str, Dict[str, float]] = {}
        regimenes_finales: Dict[str, str] = {}

        # 1. Aplicar primero la evaluacion fisica determinista sobre cada par
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
            "Eres el Cortex Tactico Direccional HFT de Tri-Brain-Sniper v1.0 (Estrategia CHRONOS-TRIZ). "
            "Clasifica cada activo en LONG_ONLY, SHORT_ONLY, EXTREME_Z_ONLY o VETO_TOXIC segun sus metricas. "
            "Responde UNICAMENTE un objeto JSON: {\"regimenes\": {\"ZEREBRO\": \"LONG_ONLY\", ...}}"
        )
        prompt_usuario = json.dumps(resumen_fisico, ensure_ascii=False)

        headers = {
            "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GROQ_SEG)

        for modelo in cfg.GROQ_MODEL_POOL:
            t0 = time.perf_counter()
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
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
                            # La Guardia Fisica local tiene prioridad si ya detecto VETO_TOXIC o SHORT_ONLY
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
                            if sugerencia == "VETO_TOXIC" and not toxicidad_fisica:
                                sugerencia = "LONG_ONLY"
                            presion_bajista_real = (
                                tk_sym is not None
                                and tk_sym.bid > 0.0
                                and (tk_sym.ema900_dist_pct <= -0.0040 or tk_sym.delta_p_pct <= -0.0040)
                            )
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

    # ==========================================================================
    # 4. CORTEX 2: GOOGLE GEMINI (DIMENSIONAMIENTO ANTI-FRAGIL)
    # ==========================================================================
    async def sincronizar_cortex_gemini_sizing(self) -> float:
        """
        Analiza la velocidad de crecimiento geometrico g* y el regimen de volatilidad
        para ajustar el multiplicador anti-fragil en RAM [0.75 .. 1.12].
        """
        ultimos_12 = CAJA_NEGRA.operaciones[-12:] if CAJA_NEGRA.operaciones else []
        wins_12 = sum(1 for op in ultimos_12 if float(op.get("pnl_usdt") or 0.0) >= 0.0)
        losses_12 = len(ultimos_12) - wins_12
        pnl_12 = sum(float(op.get("pnl_usdt") or 0.0) for op in ultimos_12)
        dd_actual = ESTADO_RAM.calcular_drawdown_actual_pct()

        # Calculo determinista anti-fragil base
        mult_base = 1.00
        if dd_actual > 0.05:
            mult_base = max(0.75, 1.0 - (dd_actual * 2.0))
        elif len(ultimos_12) >= 4 and losses_12 == 0:
            # Freno anti-euforia tras racha invicta
            mult_base = 0.94

        self.factor_global_gemini = round(mult_base, 3)
        for sym in cfg.PARES_CAMPEONES_ALFA:
            if sym in ESTADO_RAM.permisos_ram:
                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or not cfg.GEMINI_API_KEY:
            return self.factor_global_gemini

        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_GEMINI_SEG)
        prompt = (
            f"Actua como Oraculo Cuantico de Riesgo (Busseti-Ryu-Boyd Kelly) para Tri-Brain-Sniper v1.0. "
            f"Ultimos {len(ultimos_12)} trades: {wins_12}W/{losses_12}L (PnL={pnl_12:+.4f} USDT), "
            f"Drawdown actual={dd_actual*100:.2f}%. "
            f"Devuelve UNICAMENTE JSON: {{\"sizing_mult\": 0.95}}"
        )

        for modelo in cfg.GEMINI_MODEL_POOL:
            t0 = time.perf_counter()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={cfg.GEMINI_API_KEY}"
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
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
                            # Nunca permitir que el LLM supere el tope anti-euforia local
                            self.factor_global_gemini = round(max(0.75, min(mult_base + 0.05, min(1.10, val))), 3)
                            for sym in cfg.PARES_CAMPEONES_ALFA:
                                ESTADO_RAM.permisos_ram[sym].sizing_mult_gemini = self.factor_global_gemini
                        log_sniper(
                            f"[TRI-CORTEX GOOGLE AI] 🧠 Oráculo {modelo} sincronizado en "
                            f"{self.ultimo_rtt_gemini_ms:.0f}ms (Ultimos {len(ultimos_12)} trades: "
                            f"{wins_12}W/{losses_12}L | PnL={pnl_12:+.4f} USDT | Mult={self.factor_global_gemini:.2f})"
                        )
                        return self.factor_global_gemini
            except Exception:
                continue

        return self.factor_global_gemini

    # ==========================================================================
    # 5. CORTEX 3: NVIDIA NIM / DEEPSEEK (PRE-FLIGHT & AUDITORIA POST-LOSS)
    # ==========================================================================
    async def auditar_cierre_y_calibrar_umbral(
        self,
        symbol: str,
        pnl_usdt: float,
        motivo: str,
    ) -> float:
        """
        Invocado inmediatamente tras cualquier cierre:
          - Si fue ganancia (pnl_usdt >= 0): aplica enfriamiento corto (90s).
          - Si fue Maker-Scratch 18s: aplica enfriamiento de 120s y endurece un 10% el umbral de caida.
          - Si fue Stop-Loss (pnl_usdt < 0): aplica cuarentena de 300s, endurece un 20% el umbral
            de caida en RAM y dispara auditoria forense en NVIDIA NIM fuera de ruta critica.
        """
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
            return cfg.COOLDOWN_POST_CIERRE_WIN_SEG

        mot_up = str(motivo or "").upper()
        if "SCRATCH" in mot_up:
            duracion = 120.0
            ESTADO_RAM.aplicar_cuarentena(symbol, duracion, "COOLDOWN_MAKER_SCRATCH_18S")
            if perm is not None:
                perm.caida_min_override_pct = round(base_caida * 1.12, 5)
            return duracion

        # Caso Stop-Loss o Escape Temporal en perdida
        duracion_sl = cfg.COOLDOWN_POST_CIERRE_LOSS_SEG
        ESTADO_RAM.aplicar_cuarentena(symbol, duracion_sl, f"CUARENTENA_POST_LOSS_{mot_up}")
        if perm is not None:
            perm.caida_min_override_pct = round(base_caida * 1.22, 5)

        if os.environ.get("TRIBRAIN_TEST_MODE") != "1" and cfg.NVIDIA_API_KEY:
            asyncio.create_task(self._consultar_forense_nvidia_async(symbol, pnl_usdt, motivo))

        return duracion_sl

    async def _consultar_forense_nvidia_async(
        self, symbol: str, pnl_usdt: float, motivo: str
    ) -> None:
        headers = {
            "Authorization": f"Bearer {cfg.NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=cfg.TIMEOUT_NVIDIA_SEG)
        prompt = (
            f"Auditoria Forense HFT Tri-Brain-Sniper v1.0: perdida en {symbol} "
            f"({pnl_usdt:+.4f} USDT, motivo={motivo}). Sugiere cuarentena_seg [300..600] "
            f"en JSON: {{\"cuarentena_seg\": 360}}"
        )
        for modelo in cfg.NVIDIA_MODEL_POOL:
            t0 = time.perf_counter()
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
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
                        q_seg = float(parsed.get("cuarentena_seg", 300.0))
                        q_clamped = max(300.0, min(600.0, q_seg))
                        ESTADO_RAM.aplicar_cuarentena(symbol, q_clamped, f"NVIDIA_FORENSE_{modelo}")
                        log_sniper(
                            f"[TRI-CORTEX NVIDIA NIM] 🛡️ Forense {modelo} ({self.ultimo_rtt_nvidia_ms:.0f}ms) "
                            f"fijó cuarentena de {q_clamped:.0f}s en {symbol}."
                        )
                        return
            except Exception:
                continue

    async def bucle_orquestacion_tricortex(self) -> None:
        """Bucle perpetuo de segundo plano fuera de la ruta critica del WebSocket."""
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
                log_sniper(f"⚠️ [TRI-CORTEX LOOP] Error no fatal en bucle de fondo: {exc}")
            await asyncio.sleep(cfg.CICLO_GROQ_REGIMEN_SEG)

    def detener(self) -> None:
        self._running = False


# Instancia Singleton global del Orquestador Tri-Cortex
ESCUDO_TRICORTEX: OrquestadorTriCortex = OrquestadorTriCortex()

# === [PASO 5 SKILL HUNTER V3.0: KELLY GLOSTEN-MILGROM (O(1) PURO SIN INSPECT)] ===
def calcular_atenuacion_glosten_milgrom(f_kelly: float, z_score: float, z_crit: float = 8.50, kappa: float = 0.025) -> float:
    """Contrae de forma no-monotona la fraccion de Kelly cuando |Z| supera el umbral de seleccion adversa z_crit."""
    f_val = float(f_kelly)
    z_abs = abs(float(z_score))
    if z_abs <= z_crit:
        return f_val
    f_min = float(getattr(cfg, "KELLY_FRACCION_MIN", 0.42))
    f_max = float(getattr(cfg, "KELLY_FRACCION_MAX", 0.62))
    return round(max(f_min, min(f_max, f_val * math.exp(-kappa * (z_abs - z_crit)))), 4)


if "calcular_fraccion_kelly_antifragil" in globals() and not hasattr(sys.modules[__name__], "_orig_p5_kelly_fn"):
    _orig_p5_kelly_fn = calcular_fraccion_kelly_antifragil

    def calcular_fraccion_kelly_antifragil(z_score: float, ofi: float, *args, **kwargs):
        res = _orig_p5_kelly_fn(z_score, ofi, *args, **kwargs)
        z_abs = abs(float(z_score))
        if z_abs <= 8.50:
            return res
        if isinstance(res, (int, float)):
            return calcular_atenuacion_glosten_milgrom(float(res), z_abs)
        if isinstance(res, tuple) and len(res) >= 2 and isinstance(res[0], (int, float)):
            f_orig = float(res[0])
            if f_orig <= 1e-9:
                return res
            f_gm = calcular_atenuacion_glosten_milgrom(f_orig, z_abs)
            lista = list(res)
            lista[0] = f_gm
            if isinstance(lista[1], (int, float)):
                lista[1] = round(float(lista[1]) * (f_gm / f_orig), 4)
            return tuple(lista)
        return res

# === INICIO AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===
def calcular_factor_tope_glosten_milgrom(
    z_score: float, z_crit: float = 8.50, kappa: float = 0.12
) -> float:
    z_abs = abs(float(z_score))
    if z_abs <= float(z_crit):
        return 1.0
    factor = math.exp(-float(kappa) * (z_abs - float(z_crit)))
    return float(max(0.55, min(1.0, factor)))
# === FIN AJUSTES QUIRURGICOS V3.0 (SKILL HUNTER) ===



# === [PHANTOM V1.0 SYMBOLIC HIGH-ENTROPY REGIME FILTER (P-07)] ===
if "ESCUDO_TRICORTEX" in globals():
    _ClsEscudoPhantom = type(ESCUDO_TRICORTEX)
    for _m_groq_name in ("sincronizar_matriz_groq", "actualizar_matriz_direccional_groq", "consultar_matriz_groq"):
        if hasattr(_ClsEscudoPhantom, _m_groq_name) and not hasattr(_ClsEscudoPhantom, "_orig_groq_phantom"):
            _ClsEscudoPhantom._orig_groq_phantom = getattr(_ClsEscudoPhantom, _m_groq_name)
            async def _sincronizar_matriz_groq_phantom(self, *args, **kwargs):
                res = await _ClsEscudoPhantom._orig_groq_phantom(self, *args, **kwargs)
                if __import__("os").getenv("TRIBRAIN_TEST_MODE", "0") != "1":
                    tick_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
                    ofi_btc = float(getattr(tick_btc, "ofi_l1", 0.0) or 0.0)
                    for sym in cfg.WHITELIST_CAMPEONES_ALFA:
                        t_s = ESTADO_RAM.ticks_ram.get(sym)
                        p_s = ESTADO_RAM.permisos_ram.get(sym)
                        if t_s is not None and p_s is not None and getattr(p_s, "regimen", "") != "VETO_TOXIC":
                            ofi_s = float(getattr(t_s, "ofi_l1", 0.0) or 0.0)
                            if ofi_btc < -0.28 and ofi_s < -0.25:
                                p_s.regimen = "SHORT_ONLY"
                                p_s.long_permitido = False
                                p_s.short_permitido = True
                return res
            setattr(_ClsEscudoPhantom, _m_groq_name, _sincronizar_matriz_groq_phantom)
            break
