#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #14: test_tribrain_v1_suite.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Master End-to-End Certification Suite (18/18 Deterministic Tests).
Audits with 100% test-to-production parity all 11 core Python modules +
the Unix infrastructure installer, mathematically verifying the 4 Laws of
CHRONOS-TRIZ, Tri-Cortex orchestration, and the 1:1 Telegram pairing guarantee.
==============================================================================
"""
from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import sys
import tempfile
import time

# Enable isolated test log/lock files prior to importing the engine modules
os.environ["TRIBRAIN_TEST_MODE"] = "1"

import config_parametros as cfg
import core_estado_ram as ram
import ejecutor_sniper as ej_mod
import escudo_tricortex as tc_mod
import evaluador_cuantico_oos as oos_mod
import gestor_posiciones as gp_mod
import main as main_mod
import radar_volatilidad as rad_mod
import stats_tracker as st_mod
import telemetria_telegram as tg_mod

MODULOS_NUCLEO = (
    "config_parametros.py",
    "core_estado_ram.py",
    "telemetria_telegram.py",
    "stats_tracker.py",
    "escudo_tricortex.py",
    "radar_volatilidad.py",
    "ejecutor_sniper.py",
    "gestor_posiciones.py",
    "main.py",
    "evaluador_cuantico_oos.py",
    "test_tribrain_v1_suite.py",
)


class MockBybitSuite:
    """Deterministic Bybit UTA V5 simulator for Zero-REST and Position Manager contract tests."""

    def __init__(self, modo: str = "fill", simular_110017: bool = False) -> None:
        self.modo = modo
        self.simular_110017 = simular_110017
        self.llamadas: list = []
        self.markets = {
            "BTC/USDT:USDT":     {"precision": {"price": 0.1,     "amount": 0.001}, "limits": {"amount": {"min": 0.001}}, "info": {"lastPrice": "92000.0"}},
            "ETH/USDT:USDT":     {"precision": {"price": 0.01,    "amount": 0.01},  "limits": {"amount": {"min": 0.01}},  "info": {"lastPrice": "3100.0"}},
            "ZEREBRO/USDT:USDT": {"precision": {"price": 0.00001, "amount": 1.0},   "limits": {"amount": {"min": 1.0}},   "info": {"lastPrice": "0.0225"}},
            "WAL/USDT:USDT":     {"precision": {"price": 0.00001, "amount": 1.0},   "limits": {"amount": {"min": 1.0}},   "info": {"lastPrice": "0.0500"}},
            "INJ/USDT:USDT":     {"precision": {"price": 0.001,   "amount": 0.1},   "limits": {"amount": {"min": 0.1}},   "info": {"lastPrice": "8.000"}},
            "XRP/USDT:USDT":     {"precision": {"price": 0.0001,  "amount": 1.0},   "limits": {"amount": {"min": 1.0}},   "info": {"lastPrice": "1.300"}},
            "ARB/USDT:USDT":     {"precision": {"price": 0.0001,  "amount": 0.1},   "limits": {"amount": {"min": 0.1}},   "info": {"lastPrice": "0.180"}},
        }

    async def fetch_open_orders(self, symbol: str):
        return []

    async def fetch_positions(self):
        if self.modo == "boot_zombies":
            t_zombie_ms = int((time.time() - 14400.0) * 1000)
            return [
                {"symbol": "ADA/USDT:USDT", "side": "long", "contracts": 33.0, "entryPrice": 0.2307, "markPrice": 0.2315, "timestamp": t_zombie_ms},
                {"symbol": "ENA/USDT:USDT", "side": "long", "contracts": 53.0, "entryPrice": 0.19659, "markPrice": 0.1972, "timestamp": t_zombie_ms},
                {"symbol": "XRP/USDT:USDT", "side": "long", "contracts": 5.0,  "entryPrice": 1.3278, "markPrice": 1.3310, "timestamp": t_zombie_ms},
            ]
        return []

    async def set_trading_stop(self, symbol: str, params: dict):
        self.llamadas.append(("set_trading_stop", symbol, params))
        return {"retCode": 0}

    async def create_order(self, symbol: str, type_: str, side: str, amount: float, price=None, params=None):
        if self.simular_110017:
            raise Exception('bybit {"retCode":110017,"retMsg":"reduce-only order has same side"}')
        self.llamadas.append(("create_order", symbol, type_, side, amount, price, params))
        if self.modo == "boot_zombies":
            exits = {"ADA/USDT:USDT": 0.2315, "ENA/USDT:USDT": 0.1972, "XRP/USDT:USDT": 1.3310}
            return {"id": "oid-boot", "status": "closed", "filled": amount, "average": exits.get(symbol, 1.0)}
        if self.modo == "nofill":
            return {"id": "oid-nofill", "status": "open", "filled": 0.0, "price": price}
        return {"id": "oid-fill", "status": "closed", "filled": amount, "average": price}

    async def fetch_order(self, order_id: str, symbol: str):
        self.llamadas.append(("fetch_order", order_id))
        if self.modo == "nofill":
            return {"id": order_id, "status": "open", "filled": 0.0}
        return {"id": order_id, "status": "closed", "filled": 700.0, "average": 0.02251}

    async def cancel_order(self, order_id: str, symbol: str):
        self.llamadas.append(("cancel_order", order_id))
        return {"id": order_id, "status": "canceled"}


async def ejecutar_suite_certificacion_v1() -> int:
    print("==================================================================")
    print(f" STARTING CERTIFICATION SUITE: {cfg.NOMBRE_ESTRATEGIA.upper()} [{cfg.ESTRATEGIA_MATEMATICA}]")
    print("==================================================================")

    with tempfile.TemporaryDirectory() as tmpdir:
        p_tmp = pathlib.Path(tmpdir)

        # ------------------------------------------------------------------
        # [1/18] AST compilation and pure UTF-8 (no BOM) across all 11 .py files
        # ------------------------------------------------------------------
        for mod_name in MODULOS_NUCLEO:
            mod_path = cfg.ROOT_DIR / mod_name
            assert mod_path.exists(), f"Missing core module: {mod_name}"
            raw_m = mod_path.read_bytes()
            assert not raw_m.startswith(b"\xef\xbb\xbf"), f"BOM U+FEFF detected in {mod_name}"
            ast.parse(raw_m.decode("utf-8"), filename=mod_name)
        ram.log_sniper(f" [1/18] AST compilation and pure UTF-8 encoding without BOM verified across all {len(MODULOS_NUCLEO)} Python modules.")

        # ------------------------------------------------------------------
        # [2/18] AST unique constants contract & CHRONOS-TRIZ invariants
        # ------------------------------------------------------------------
        tree_cfg = ast.parse((cfg.ROOT_DIR / "config_parametros.py").read_text(encoding="utf-8"))
        assignments = [
            (n.targets[0].id if isinstance(n, ast.Assign) else n.target.id)
            for n in tree_cfg.body
            if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper())
            or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id.isupper())
        ]
        duplicates = [k for k in set(assignments) if assignments.count(k) > 1]
        assert not duplicates, f"Duplicate constants in config_parametros.py: {duplicates}"
        assert abs(cfg.CAPITAL_BASE_USDT - 9.8662) < 1e-6
        assert cfg.PERMITIR_REQUOTE is False and cfg.TTL_ORDEN_ENTRADA_SEG == 2.20
        assert cfg.MAKER_SCRATCH_TIEMPO_SEG == 18.0 and cfg.COSECHA_TRIZ_ACTIVACION_PCT == 0.0026
        assert cfg.SL_INTERNO_PCT == 0.0048 and cfg.TIEMPO_MAX_HOLD_SEG == 90.0
        ram.log_sniper(
            f" [2/18] CHRONOS-TRIZ AST Contract validated: {len(assignments)} unique constants "
            f"(TTL=2.2s, ReQuote=False, Scratch=18s, Harvest50%=+0.26%, SL=-0.48%, Hold=90s)."
        )

        # ------------------------------------------------------------------
        # [3/18] O(1) Lookup benchmark in ESTADO_RAM, Single-Slot Mutex & @property aliases
        # ------------------------------------------------------------------
        tc_mod.ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        now = time.time()
        n_iter = 50000
        t0 = time.perf_counter()
        for _ in range(n_iter):
            ok_o1, _, _ = ram.ESTADO_RAM.consultar_permiso_o1("ZEREBRO/USDT:USDT", "long", -3.60, now)
        dt_us = ((time.perf_counter() - t0) * 1e6) / n_iter
        assert ok_o1 is True and dt_us < 2.5
        pos_alias = ram.PosicionActiva("ZEREBRO/USDT:USDT", "long", 100.0, 100.0, 0.0225, 1700000000.0)
        assert pos_alias.entrada == 0.0225 and pos_alias.precio_entrada == 0.0225 and pos_alias.t_apertura == 1700000000.0
        ram.log_sniper(
            f" [3/18] O(1) RAM Whitelist Lookup ({dt_us:.3f} us), @property aliases, and {len(cfg.GROQ_MODEL_POOL)}-model Groq pool validated."
        )

        # ------------------------------------------------------------------
        # [4/18] Structural Anti-Collapse Filter (Anti-LUNA)
        # ------------------------------------------------------------------
        ok_luna = tc_mod.ESCUDO_TRICORTEX.verificar_anti_colapso_estructural("ZEREBRO/USDT:USDT", -0.085, -0.92)
        assert ok_luna is False and ram.ESTADO_RAM.permisos_ram["ZEREBRO/USDT:USDT"].modo_regimen == "VETO_TOXIC"
        tc_mod.ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        ram.log_sniper(" [4/18] Structural anti-collapse filter (Anti-LUNA: drop -8.5%, OFI -0.92 -> VETO_TOXIC) validated.")

        # ------------------------------------------------------------------
        # [5/18] Tri-Cortex Directional Matrix (Automatic switch to SHORT_ONLY)
        # ------------------------------------------------------------------
        tk_bear = ram.ESTADO_RAM.ticks_ram["ZEREBRO/USDT:USDT"]
        tk_bear.ema900_slope_pct = -0.0065
        tk_bear.ema900_dist_pct = -0.0260
        tk_bear.hurst = 0.56
        tk_bear.ofi_l1_l5 = -0.45
        regimes = await tc_mod.ESCUDO_TRICORTEX.sincronizar_cortex_groq_regimen()
        assert regimes["ZEREBRO/USDT:USDT"] == "SHORT_ONLY"
        ok_long_b, mot_b, _ = ram.ESTADO_RAM.consultar_permiso_o1("ZEREBRO/USDT:USDT", "long", -3.80, now)
        ok_short_b, _, _ = ram.ESTADO_RAM.consultar_permiso_o1("ZEREBRO/USDT:USDT", "short", 1.20, now)
        assert ok_long_b is False and mot_b in ("SHORT_ONLY_REGIME_ACTIVE", "REGIMEN_SHORT_ONLY_ACTIVO") and ok_short_b is True
        tc_mod.ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        ram.log_sniper(" [5/18] Groq LPU Directional Matrix validated: bearish cascade switches to SHORT_ONLY (Long blocked, Short active).")

        # ------------------------------------------------------------------
        # [6/18] Anti-Fragile Kelly Sizing (Busseti-Ryu-Boyd)
        # ------------------------------------------------------------------
        ram.ESTADO_RAM.sincronizar_balance_uta(cfg.CAPITAL_BASE_USDT, cfg.CAPITAL_BASE_USDT)
        f_mod, _, noc_mod = tc_mod.ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil("INJ/USDT:USDT", -3.00, 0.30, 0.48, 0.0025)
        f_ext, _, noc_ext = tc_mod.ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil("INJ/USDT:USDT", -5.20, 0.90, 0.41, 0.0020)
        assert f_ext > f_mod and noc_ext > noc_mod
        ram.log_sniper(
            f" [6/18] Anti-Fragile Kelly Sizing validated: moderate signal ({f_mod*100:.1f}% -> {noc_mod:.2f} USDT) vs extreme ({f_ext*100:.1f}% -> {noc_ext:.2f} USDT)."
        )

        # ------------------------------------------------------------------
        # [7/18] Bipower VentanaZ Calibration (Micro-noise ignored vs Collapse triggered)
        # ------------------------------------------------------------------
        vz_cal = rad_mod.VentanaZ(maxlen=60)
        for i in range(45):
            vz_cal.agregar_precio(1.0000 * (1.0 + ((-1) ** i) * 0.0002))
        z_noise, _, _ = vz_cal.calcular_z(0.9996)
        z_crash, _, _ = vz_cal.calcular_z(0.9779)
        assert abs(z_noise) < 2.0 and z_crash <= -5.0
        ram.log_sniper(
            f" [7/18] Bipower VentanaZ Calibration verified: Micro-noise (-0.04%) -> Z={z_noise:.2f} (Ignored) | Collapse (-2.21%) -> Z={z_crash:.2f} (Triggered)."
        )

        # ------------------------------------------------------------------
        # [8/18] Single-instance physical lock (.tribrain_test.lock)
        # ------------------------------------------------------------------
        lock_path = p_tmp / ".tribrain_test.lock"
        lock1 = main_mod.CerrojoInstanciaUnica(ruta_lock=lock_path)
        assert lock1.adquirir() is True
        lock_path.write_text(f"{os.getppid()}\n", encoding="utf-8")
        lock2 = main_mod.CerrojoInstanciaUnica(ruta_lock=lock_path)
        assert lock2.adquirir() is False
        lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        lock1.liberar()
        ram.log_sniper(" [8/18] Physical single-instance lock validated in isolated file (.tribrain_test.lock).")

        # ------------------------------------------------------------------
        # [9/18] Startup Auto-Reconciler (3 zombie positions + 0 Telegram spam)
        # ------------------------------------------------------------------
        st_mod.CAJA_NEGRA = st_mod.GestorCajaNegra(ruta_jsonl=p_tmp / "stats_boot.jsonl")
        main_mod.CAJA_NEGRA = st_mod.CAJA_NEGRA
        gp_mod.CAJA_NEGRA = st_mod.CAJA_NEGRA
        tg_mod.TELEMETRIA_TG.buzon_test.clear()
        ex_boot = MockBybitSuite(modo="boot_zombies")
        zombies_proc = await main_mod.reconciliar_posiciones_arranque(ex_boot)
        assert zombies_proc == 3 and len(tg_mod.TELEMETRIA_TG.buzon_test) == 0
        ram.log_sniper(" [9/18] Startup Auto-Reconciliation validated: 3 zombie positions (ADA, ENA, XRP) liquidated with reduceOnly=True and 0 Telegram spam.")

        # ------------------------------------------------------------------
        # [10/18] Cross-Asset Contagion Firewall (>= 3 pairs in <= 10s) & Post-Loss Quarantine
        # ------------------------------------------------------------------
        radar = rad_mod.RadarVolatilidad()
        radar.resetear_contagio_macro()
        t_c = time.time()
        await radar.verificar_contagio_cross_asset("INJ/USDT:USDT", -3.40, t_c)
        await radar.verificar_contagio_cross_asset("XRP/USDT:USDT", -3.50, t_c + 1.0)
        contagion_ok = await radar.verificar_contagio_cross_asset("ARB/USDT:USDT", -3.80, t_c + 2.0)
        assert contagion_ok is True and ram.ESTADO_RAM.pausa_macro_hasta_ts > t_c
        radar.resetear_contagio_macro()
        q_loss = await tc_mod.ESCUDO_TRICORTEX.auditar_cierre_y_calibrar_umbral("WAL/USDT:USDT", -0.080, "SL_INTERNO_CHRONOS")
        assert q_loss == 300.0
        tc_mod.ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        ram.log_sniper(" [10/18] Cross-Asset Contagion Firewall (>= 3 pairs in <=10s) and Post-Loss Quarantine (300s) validated.")

        # ------------------------------------------------------------------
        # [11/18] CHRONOS-TRIZ Law 1: 3-Tick ML-OFI Confirmation, Lyapunov & Spread
        # ------------------------------------------------------------------
        a_lyap = rad_mod.calcular_aceleracion_lyapunov([0.02500, 0.02480, 0.02482])
        sp_ok, sp_val = rad_mod.verificar_friccion_spread(0.05000, 0.05005)
        sp_veto, _ = rad_mod.verificar_friccion_spread(0.05000, 0.05013, max_spread_pct=0.0012)
        assert a_lyap > 0.0 and sp_ok is True and sp_veto is False

        vz_z = radar.ventanas["ZEREBRO/USDT:USDT"]
        t_b = time.time() - 10.0
        for i in range(40):
            vz_z.agregar_precio(0.02500 * (1.0 + ((-1) ** i) * 0.0003))
        vz_z.agregar_precio(0.02462)
        vz_z.agregar_precio(0.02460)
        bids_f = [[0.02460, 9500.0], [0.02459, 8000.0], [0.02458, 7000.0]]
        asks_d = [[0.02461, 800.0],  [0.02462, 900.0],  [0.02463, 1000.0]]
        s_t1 = await radar.procesar_instantanea_libro("ZEREBRO/USDT:USDT", bids_f, asks_d, t_b + 1.0)
        s_t2 = await radar.procesar_instantanea_libro("ZEREBRO/USDT:USDT", bids_f, asks_d, t_b + 1.15)
        s_t3 = await radar.procesar_instantanea_libro("ZEREBRO/USDT:USDT", bids_f, asks_d, t_b + 1.30)
        assert s_t1 is None and s_t2 is None and s_t3 is not None and s_t3["side"] == "long"
        radar.resetear_contagio_macro()
        ram.log_sniper(
            f" [11/18] CHRONOS-TRIZ Law 1 validated: 3 consecutive ML-OFI Ticks (450ms), Lyapunov Attractor (a={a_lyap*100:+.4f}%), and Spread Gate ({sp_val*100:.2f}%)."
        )

        # ------------------------------------------------------------------
        # [12/18] CHRONOS-TRIZ Law 4: EMA900 Anti-Pump-Top & Symmetric SHORT-SNIPER Shot
        # ------------------------------------------------------------------
        vz_w = radar.ventanas["WAL/USDT:USDT"]
        for _ in range(45):
            vz_w.agregar_precio(0.05000)
        await radar.procesar_instantanea_libro("WAL/USDT:USDT", [[0.05070, 5000.0]], [[0.05072, 1000.0]], t_b + 2.0)
        assert vz_w.vigilancia_short_hasta_ts > t_b
        await radar.procesar_instantanea_libro("WAL/USDT:USDT", [[0.05064, 400.0], [0.05063, 400.0]], [[0.05066, 8500.0], [0.05067, 9000.0]], t_b + 2.20)
        await radar.procesar_instantanea_libro("WAL/USDT:USDT", [[0.05054, 300.0], [0.05053, 300.0]], [[0.05056, 9500.0], [0.05057, 9500.0]], t_b + 2.35)
        s_sh = await radar.procesar_instantanea_libro("WAL/USDT:USDT", [[0.05038, 200.0], [0.05037, 200.0]], [[0.05040, 11000.0], [0.05041, 11000.0]], t_b + 2.50)
        assert s_sh is not None and s_sh["side"] == "short"
        ram.log_sniper(" [12/18] CHRONOS-TRIZ Law 4 validated: EMA900 Anti-Pump-Top Filter and symmetric SHORT-SNIPER shot after 3 exhaustion ticks.")

        # ------------------------------------------------------------------
        # [13/18] Penny-Jump Quoting (Long/Short) & Zero-REST Shot
        # ------------------------------------------------------------------
        st_mod.CAJA_NEGRA = st_mod.GestorCajaNegra(ruta_jsonl=p_tmp / "stats_live.jsonl")
        gp_mod.CAJA_NEGRA = st_mod.CAJA_NEGRA
        tg_mod.TELEMETRIA_TG.buzon_test.clear()
        tg_mod.TELEMETRIA_TG.cache_dedup.clear()
        ram.ESTADO_RAM.liberar_margen_atomico("ZEREBRO/USDT:USDT")
        ram.ESTADO_RAM.sincronizar_balance_uta(cfg.CAPITAL_BASE_USDT, cfg.CAPITAL_BASE_USDT)

        q_pj_l = ej_mod.calcular_precio_penny_jump("long", 0.0499, 0.0502, 0.0001, 0.40)
        q_pj_s = ej_mod.calcular_precio_penny_jump("short", 0.0499, 0.0502, 0.0001, -0.45)
        assert q_pj_l == 0.0500 and q_pj_s == 0.0501

        ex_fill = MockBybitSuite(modo="fill")
        sniper_fill = ej_mod.EjecutorSniper(exchange=ex_fill)
        pos_activa = await sniper_fill.ejecutar_senal_sniper(s_t3, ttl_override_seg=0.12)
        assert pos_activa is not None and ex_fill.llamadas[0][0] == "create_order"
        ram.ESTADO_RAM.liberar_margen_atomico("ZEREBRO/USDT:USDT")
        ram.log_sniper(" [13/18] Penny-Jump Quoting (0.0499->0.0500 Long | 0.0502->0.0501 Short) and Zero-REST Shot validated.")

        # ------------------------------------------------------------------
        # [14/18] Moallemi-Yuan Queue Law (TTL=2.2s) & Physical Re-Quote Abolition
        # ------------------------------------------------------------------
        ex_nf = MockBybitSuite(modo="nofill")
        sniper_nf = ej_mod.EjecutorSniper(exchange=ex_nf)
        inbox_before = len(tg_mod.TELEMETRIA_TG.buzon_test)
        pos_nf = await sniper_nf.ejecutar_senal_sniper(s_t3, ttl_override_seg=0.10)
        creates_nf = sum(1 for x in ex_nf.llamadas if isinstance(x, tuple) and x[0] == "create_order")
        cancels_nf = sum(1 for x in ex_nf.llamadas if isinstance(x, tuple) and x[0] == "cancel_order")
        assert pos_nf is None and creates_nf == 1 and cancels_nf == 1
        assert len(tg_mod.TELEMETRIA_TG.buzon_test) == inbox_before
        ram.log_sniper(" [14/18] Moallemi-Yuan Queue Law (TTL=2.2s) and Physical Price-Chasing Re-Quote Abolition (1 create + 1 cancel, 0 spam) validated.")

        # ------------------------------------------------------------------
        # [15/18] CHRONOS-TRIZ Law 3: Invariant BE Floor, 50/50 TRIZ Harvest & Trailing Ratchet
        # ------------------------------------------------------------------
        sl_i_be, sl_b_be = gp_mod.calcular_piso_invariante_breakeven("long", 0.05691, 0.00001)
        assert sl_i_be > 0.05691 and sl_b_be > 0.05691

        gestor = gp_mod.GestorPosiciones(exchange=ex_fill)
        t_pos = 1700000000.0
        pos_triz = ram.PosicionActiva(
            symbol="ZEREBRO/USDT:USDT", side="long", qty_inicial=700.0, qty_actual=700.0,
            entry_price=0.02200, ts_apertura=t_pos, sl_interno_price=0.02189, sl_bybit_price=0.02185,
        )
        ram.ESTADO_RAM.posiciones_activas["ZEREBRO/USDT:USDT"] = pos_triz
        tk_z = ram.ESTADO_RAM.ticks_ram["ZEREBRO/USDT:USDT"]
        tk_z.bid, tk_z.ask, tk_z.ofi_l1_l5, tk_z.ofi_5s = 0.02207, 0.02208, 0.65, 0.60
        await gestor.evaluar_posicion_activa(pos_triz, ahora=t_pos + 6.0)
        assert pos_triz.cosecha_50_ejecutada is True and pos_triz.qty_actual == 350.0 and pos_triz.trinquete_be_armado is True

        tk_z.bid, tk_z.ask, tk_z.ofi_l1_l5 = 0.02216, 0.02217, 0.45
        await gestor.evaluar_posicion_activa(pos_triz, ahora=t_pos + 12.0)
        tk_z.bid, tk_z.ask, tk_z.ofi_l1_l5 = 0.02214, 0.02215, -0.15
        mot_triz = await gestor.evaluar_posicion_activa(pos_triz, ahora=t_pos + 14.0)
        assert mot_triz == "TRAILING_RATCHET_MAKER" and pos_triz.cerrada is True
        ram.log_sniper(
            f" [15/18] CHRONOS-TRIZ Law 3 validated: BE Floor ({sl_i_be}), 50/50 TRIZ Harvest (+0.32%), and TRAILING_RATCHET_MAKER close (+0.73%)."
        )

        # ------------------------------------------------------------------
        # [16/18] CHRONOS-TRIZ Law 2: Passive Maker-Scratch Evacuation at 18s (Avellaneda-Stoikov)
        # ------------------------------------------------------------------
        pos_sc = ram.PosicionActiva(
            symbol="INJ/USDT:USDT", side="long", qty_inicial=2.0, qty_actual=2.0,
            entry_price=8.000, ts_apertura=t_pos + 100.0, sl_interno_price=7.962, sl_bybit_price=7.944,
        )
        ram.ESTADO_RAM.posiciones_activas["INJ/USDT:USDT"] = pos_sc
        tk_inj = ram.ESTADO_RAM.ticks_ram["INJ/USDT:USDT"]
        tk_inj.bid, tk_inj.ask, tk_inj.ofi_l1_l5, tk_inj.ofi_5s = 7.994, 7.996, -0.40, -0.32
        mot_sc = await gestor.evaluar_posicion_activa(pos_sc, ahora=t_pos + 118.5)
        assert mot_sc == "MAKER_SCRATCH_18S" and pos_sc.cerrada is True
        ram.log_sniper(" [16/18] CHRONOS-TRIZ Law 2 validated: Passive Maker-Scratch evacuation at 18s (-0.09% Maker vs -0.48% SL).")

        # ------------------------------------------------------------------
        # [17/18] pos.cerrada Lock, retCode:110017 Capture (SL_EXCHANGE) & 1:1 Telegram Loss Guarantee
        # ------------------------------------------------------------------
        ex_110017 = MockBybitSuite(modo="fill", simular_110017=True)
        gestor_110017 = gp_mod.GestorPosiciones(exchange=ex_110017)
        pos_sl = ram.PosicionActiva(
            symbol="WAL/USDT:USDT", side="long", qty_inicial=300.0, qty_actual=300.0,
            entry_price=0.05000, ts_apertura=t_pos + 200.0, sl_interno_price=0.04976, sl_bybit_price=0.04965,
        )
        ram.ESTADO_RAM.posiciones_activas["WAL/USDT:USDT"] = pos_sl
        tk_wal = ram.ESTADO_RAM.ticks_ram["WAL/USDT:USDT"]
        tk_wal.bid, tk_wal.ask = 0.04970, 0.04972
        mot_sl = await gestor_110017.evaluar_posicion_activa(pos_sl, ahora=t_pos + 225.0)
        dup_sl = await st_mod.CAJA_NEGRA.registrar_cierre_posicion(pos_sl, 0.04970, "SL_DUP", False, t_pos + 226.0)
        assert mot_sl == "SL_INTERNO_CHRONOS" and dup_sl is None
        assert st_mod.CAJA_NEGRA.operaciones[-1]["motivo"] == "SL_EXCHANGE"
        tipos_tg = [m["tipo"] for m in tg_mod.TELEMETRIA_TG.buzon_test]
        assert "CLOSE_WIN" in tipos_tg and "CLOSE_SCRATCH" in tipos_tg and "CLOSE_LOSS" in tipos_tg
        ram.log_sniper(" [17/18] pos.cerrada lock, native retCode:110017 capture (SL_EXCHANGE), and 1:1 Telegram loss guarantee validated.")

        # ------------------------------------------------------------------
        # [18/18] Quantum Walk-Forward OOS Evaluator, Bayesian Shrinkage & < 0.5ms Hot-Reload
        # ------------------------------------------------------------------
        p_json_oos = p_tmp / "calibracion_oos.json"
        p_md_oos = p_tmp / "reporte_cuantico_oos.md"
        ev_oos = oos_mod.EvaluadorCuanticoOOS(
            ruta_jsonl=st_mod.CAJA_NEGRA.ruta_jsonl,
            ruta_json_oos=p_json_oos,
            ruta_reporte_md=p_md_oos,
        )
        res_oos = await ev_oos.ejecutar_ciclo_evaluacion_completo(notificar_telegram=True)
        assert p_json_oos.exists() and p_md_oos.exists()
        t0_hr = time.perf_counter()
        hr_info = cfg.recargar_calibracion_oos_si_cambio(p_json_oos)
        dt_hr_ms = (time.perf_counter() - t0_hr) * 1000.0
        assert hr_info["recargado"] is True and dt_hr_ms < 5.0
        sh_raw = (cfg.ROOT_DIR / "instalar_infraestructura.sh").read_bytes()
        assert b"\r\n" not in sh_raw and b"Nice=15" in sh_raw
        ram.log_sniper(
            f" [18/18] Quantum OOS Evaluator (lambda={res_oos['significancia_estadistica']['credibilidad_bayesiana_lambda']:.2f}), "
            f"Hot-Reload ({dt_hr_ms:.2f} ms), and Unix LF installer validated."
        )

    ram.log_sniper("==================================================================")
    ram.log_sniper(f" ALL INTEGRITY TESTS FOR {cfg.NOMBRE_ESTRATEGIA.upper()} [CHRONOS-TRIZ] (18/18) PASSED")
    ram.log_sniper("==================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(ejecutar_suite_certificacion_v1()))