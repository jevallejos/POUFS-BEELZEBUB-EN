#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #11: main.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Asynchronous Central Orchestrator Core (uvloop + Bybit UTA WebSocket L2):
  - Physical single-instance kernel lock (.tribrain.lock / .tribrain_test.lock).
  - Pre-flight atomic sanitizer for calibracion_oos.json (P-08) aligned with
    Bi-Class Z-Score bounds and intelligent boot position reconciler.
  - Non-blocking parallel orchestration:
      1. 25.0 Hz (40 ms) L2 WebSocket streaming (7 Alpha Champions + BTC Sentinel).
      2. CHRONOS-TRIZ position monitoring (P-04, P-05, P-06).
      3. Tri-Cortex Swarm (Full-Groq LPU + Multi-Cloud Failover).
      4. Sub-0.5ms OOS Hot-Reload watcher and periodic Black Box telemetry.
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import signal
import sys
import time
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
from typing import Any, List, Optional

import config_parametros as cfg
from core_estado_ram import ESTADO_RAM, PosicionActiva, log_sniper
from ejecutor_sniper import (
    EjecutorSniper,
    calcular_barreras_sl_iniciales,
    extraer_precision_y_minimos,
)
from escudo_tricortex import ESCUDO_TRICORTEX
from gestor_posiciones import GestorPosiciones
from radar_volatilidad import RadarVolatilidad
from stats_tracker import CAJA_NEGRA
from telemetria_telegram import TELEMETRIA_TG

if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass


class CerrojoInstanciaUnica:
    """Cross-platform OS-level PID lockfile preventing concurrent bot instances."""

    def __init__(self, ruta_lock: Optional[pathlib.Path] = None) -> None:
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        lock_name = cfg.ARCHIVO_LOCK_TEST if is_test else cfg.ARCHIVO_LOCK_PRODUCCION
        self.ruta_lock: pathlib.Path = ruta_lock or (cfg.ROOT_DIR / lock_name)
        self.adquirido: bool = False
        self.pid: int = os.getpid()

    @staticmethod
    def _pid_sigue_vivo(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return False
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False

    def adquirir(self) -> bool:
        if self.ruta_lock.exists():
            try:
                content = self.ruta_lock.read_text(encoding="utf-8").strip()
                existing_pid = int(content) if content.isdigit() else -1
                if existing_pid == self.pid:
                    self.adquirido = True
                    return True
                if self._pid_sigue_vivo(existing_pid):
                    return False
            except Exception:
                pass
            try:
                self.ruta_lock.unlink(missing_ok=True)
            except Exception:
                return False

        try:
            self.ruta_lock.write_text(f"{self.pid}\n", encoding="utf-8")
            self.adquirido = True
            return True
        except Exception:
            return False

    def liberar(self) -> None:
        if not self.adquirido:
            return
        try:
            if self.ruta_lock.exists():
                content = self.ruta_lock.read_text(encoding="utf-8").strip()
                if content == str(self.pid):
                    self.ruta_lock.unlink(missing_ok=True)
        except Exception:
            pass
        self.adquirido = False


def _sanear_json_oos_disco_phantom() -> None:
    """
    Sanitizes calibracion_oos.json on disk prior to boot in production mode,
    enforcing Bi-Class Z-Score coherence (z_t1 > z_hb) and atomic writes only
    when adjustments are required.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
        return
    json_path = cfg.ROOT_DIR / cfg.ARCHIVO_CALIBRACION_OOS
    if not json_path.exists():
        return
    try:
        raw_text = json_path.read_text(encoding="utf-8-sig")
        d = json.loads(raw_text)
        if not isinstance(d, dict):
            return

        modified = False
        for root_key in (
            "COSECHA_TRIZ_ACTIVACION_PCT",
            "OFI_MIN_ENTRADA",
            "Z_SCORE_UMBRAL_HIGH_BETA",
            "Z_SCORE_UMBRAL_TIER1",
        ):
            if root_key in d:
                d.pop(root_key, None)
                modified = True

        prms = d.get("parametros")
        if isinstance(prms, dict):
            kelly_san = round(
                max(0.52, min(0.58, float(prms.get("KELLY_FRACCION_BASE", 0.55)))), 4
            )
            z_hb_san = round(
                max(-3.15, min(-2.80, float(prms.get("Z_SCORE_UMBRAL_HIGH_BETA", -2.85)))), 4
            )
            z_t1_raw = float(prms.get("Z_SCORE_UMBRAL_TIER1", z_hb_san + 0.25))
            if z_t1_raw <= z_hb_san:
                z_t1_raw = z_hb_san + 0.25
            z_t1_san = round(max(-2.85, min(-2.45, z_t1_raw)), 4)

            expected_updates = {
                "KELLY_FRACCION_BASE": kelly_san,
                "Z_SCORE_UMBRAL_HIGH_BETA": z_hb_san,
                "Z_UMBRAL_HIGH_BETA": z_hb_san,
                "Z_SCORE_UMBRAL_TIER1": z_t1_san,
                "Z_UMBRAL_TIER1": z_t1_san,
            }
            for k_u, v_u in expected_updates.items():
                if prms.get(k_u) != v_u:
                    prms[k_u] = v_u
                    modified = True

            if isinstance(d.get("parametros_calibrados"), dict):
                d["parametros_calibrados"] = dict(prms)

        if modified:
            tmp_path = json_path.with_suffix(".json.tmp")
            tmp_path.write_bytes((json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            tmp_path.replace(json_path)
    except Exception as exc:
        log_sniper(f"[WARN] [MAIN] Could not sanitize {json_path.name}: {exc}")


async def reconciliar_posiciones_arranque(exchange: Any) -> int:
    """
    Cancels dangling open orders and reconciles any existing Bybit UTA positions on startup:
    - Positions older than TIEMPO_MAX_HOLD_SEG are liquidated as ESCAPE_HUERFANA_BOOT.
    - Recent positions (< TIEMPO_MAX_HOLD_SEG) are adopted into RAM with full SL protection.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE") != "1":
        _sanear_json_oos_disco_phantom()
        cfg._aplicar_parametros_produccion_phantom()

    if exchange is None:
        return 0

    processed = 0
    now = time.time()

    for sym in cfg.PARES_CAMPEONES_ALFA:
        try:
            orders = await exchange.fetch_open_orders(sym)
            if orders:
                await exchange.cancel_all_orders(sym)
                log_sniper(f"[RECONCILER] {len(orders)} dangling order(s) canceled on {sym}.")
        except Exception:
            pass

    try:
        positions = await exchange.fetch_positions()
    except Exception as exc:
        log_sniper(f"[WARN] [RECONCILER] Could not query positions on startup: {exc}")
        return 0

    open_positions = [p for p in (positions or []) if float(p.get("contracts") or 0.0) > 0.0]
    if not open_positions:
        log_sniper("[RECONCILER] No orphan positions open on Bybit. Margin 100% clear.")
        return 0

    for p in open_positions:
        sym = str(p.get("symbol") or "")
        side = str(p.get("side") or "long").lower()
        qty = float(p.get("contracts") or 0.0)
        ep = float(p.get("entryPrice") or p.get("info", {}).get("avgPrice") or 0.0)
        mark_p = float(p.get("markPrice") or ep)

        ts_ms = p.get("timestamp") or p.get("info", {}).get("updatedTime") or p.get("info", {}).get("createdTime")
        if ts_ms is not None and float(ts_ms) > 0:
            t_open = float(ts_ms) / 1000.0 if float(ts_ms) > 1e11 else float(ts_ms)
            age_sec = max(0.0, now - t_open)
        else:
            age_sec = 14400.0
            t_open = now - age_sec

        age_min = age_sec / 60.0
        if age_sec >= cfg.TIEMPO_MAX_HOLD_SEG:
            log_sniper(
                f"[RECONCILER] Zombie orphan position detected on {sym}: "
                f"{qty} contracts @ {ep} (age {age_min:.1f} min >= {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s). "
                f"Liquidating at market to release margin..."
            )
            side_close = "sell" if side == "long" else "buy"
            exit_p = mark_p
            try:
                close_ord = await exchange.create_order(
                    sym, "market", side_close, qty, None, {"reduceOnly": True}
                )
                if isinstance(close_ord, dict):
                    p_avg = float(close_ord.get("average") or close_ord.get("price") or 0.0)
                    if p_avg > 0.0:
                        exit_p = p_avg
            except Exception as exc:
                log_sniper(f"[WARN] [RECONCILER] Error closing zombie position on {sym}: {exc}")
                continue

            zombie_pos = PosicionActiva(
                symbol=sym,
                side=side,
                qty_inicial=qty,
                qty_actual=qty,
                entry_price=ep,
                ts_apertura=t_open,
            )
            await CAJA_NEGRA.registrar_cierre_posicion(
                pos=zombie_pos,
                exit_price=exit_p,
                motivo="ESCAPE_HUERFANA_BOOT",
                es_salida_maker=False,
                ahora=now,
            )
            processed += 1
        else:
            tick_s, _, _ = extraer_precision_y_minimos(exchange, sym, ep)
            sl_i, sl_b = calcular_barreras_sl_iniciales(side, ep, tick_s)
            ts_norm = now if (age_sec > 3600.0 or age_sec < 0.0) else t_open
            live_pos = PosicionActiva(
                symbol=sym,
                side=side,
                qty_inicial=qty,
                qty_actual=qty,
                entry_price=ep,
                ts_apertura=ts_norm,
                sl_interno_price=sl_i,
                sl_bybit_price=sl_b,
            )
            ESTADO_RAM.slot_ocupado = True
            ESTADO_RAM.posiciones_activas[sym] = live_pos
            log_sniper(
                f"[RECONCILER] Recent position adopted on {sym}: {qty} @ {ep} (age {age_sec:.0f}s)."
            )
            processed += 1

    log_sniper(f"[RECONCILER] Startup reconciliation completed: {processed} position(s) processed.")
    return processed


def auditar_y_filtrar_lotes_minimos(exchange: Any, nocional_kelly_usdt: float) -> List[str]:
    """Filters out symbols whose minimum exchange lot notional exceeds 1.35x the Kelly notional."""
    excluded: List[str] = []
    markets = getattr(exchange, "markets", None) or {}
    for sym, mkt in markets.items():
        if not str(sym).endswith("/USDT:USDT"):
            continue
        lims = (mkt.get("limits") or {}).get("amount") or {}
        min_q = float(lims.get("min") or 0.0)
        info = mkt.get("info") or {}
        approx_price = float(info.get("lastPrice") or info.get("markPrice") or 0.0)
        if min_q > 0.0 and approx_price > 0.0:
            min_cost = min_q * approx_price
            if min_cost > (nocional_kelly_usdt * 1.35):
                ESTADO_RAM.pares_excluidos_lote.add(sym)
                excluded.append(sym)
    return sorted(excluded)


class MotorTriBrainSniper:
    """Central asynchronous HFT engine orchestrating Radar, Sniper, Position Manager, and Tri-Cortex."""

    def __init__(self, exchange: Any = None) -> None:
        self.exchange: Any = exchange
        self.gestor: GestorPosiciones = GestorPosiciones(exchange=exchange)
        self.ejecutor: EjecutorSniper = EjecutorSniper(
            exchange=exchange,
            callback_posicion_abierta=self.gestor.armar_proteccion_inicial_bybit,
        )
        self.radar: RadarVolatilidad = RadarVolatilidad(
            callback_disparo=self.ejecutor.ejecutar_senal_sniper,
            callback_evacuacion_macro=self._evacuar_por_contagio_macro,
        )
        self._running: bool = False
        self._last_maint_err_ts: float = 0.0

    async def _evacuar_por_contagio_macro(self, motivo: str) -> None:
        await self.gestor.evacuar_todas_por_emergencia(motivo=motivo)

    async def sincronizar_patrimonio_bybit(self) -> None:
        if self.exchange is None:
            return
        try:
            bal = await self.exchange.fetch_balance()
            usdt = (bal or {}).get("USDT") or {}
            total = float(usdt.get("total") or 0.0)
            free = float(usdt.get("free") or total)
            if total > 0.0:
                ESTADO_RAM.sincronizar_balance_uta(total, free)
                if hasattr(CAJA_NEGRA, "sincronizar_paridad_patrimonio_real"):
                    CAJA_NEGRA.sincronizar_paridad_patrimonio_real(total)
        except Exception as exc:
            log_sniper(f"[WARN] [MAIN] Could not synchronize UTA balance: {exc}")

    async def _vigilar_stream_simbolo(self, symbol: str) -> None:
        while self._running and self.exchange is not None:
            try:
                ob = await self.exchange.watch_order_book(symbol, limit=50)
                bids = (ob or {}).get("bids") or []
                asks = (ob or {}).get("asks") or []
                if bids and asks:
                    await self.radar.procesar_instantanea_libro(symbol, bids, asks)
                await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[RADAR] Stream error on {symbol}: {type(exc).__name__}: {exc}")
                await asyncio.sleep(2.5)

    async def _bucle_mantenimiento_y_hot_reload(self) -> None:
        last_panel = time.time()
        last_trades_cnt = CAJA_NEGRA.trades_totales
        last_vault_cnt = getattr(ESTADO_RAM, "contador_auditorias_baul", 0)
        last_auto_cal_ts = time.time()
        watched_py = [
            cfg.ROOT_DIR / fn
            for fn in (
                "config_parametros.py",
                "core_estado_ram.py",
                "radar_volatilidad.py",
                "ejecutor_sniper.py",
                "gestor_posiciones.py",
                "escudo_tricortex.py",
                "stats_tracker.py",
                "evaluador_cuantico_oos.py",
                "main.py",
            )
            if (cfg.ROOT_DIR / fn).exists()
        ]
        boot_code_mtime = max((f.stat().st_mtime for f in watched_py), default=0.0)
        while self._running:
            await asyncio.sleep(30.0)
            try:
                if os.environ.get("TRIBRAIN_TEST_MODE") != "1":
                    disk_code_mtime = max((f.stat().st_mtime for f in watched_py if f.exists()), default=0.0)
                    if (
                        disk_code_mtime > (boot_code_mtime + 1.0)
                        and not ESTADO_RAM.slot_ocupado
                        and not ESTADO_RAM.posiciones_activas
                        and ESTADO_RAM.orden_en_vuelo_symbol is None
                    ):
                        log_sniper(
                            "[AUTO-RESPAWN] Updated Python bytecode detected on disk with 0 open positions: "
                            "executing atomic os.execv reload..."
                        )
                        await self.detener()
                        try:
                            (cfg.ROOT_DIR / cfg.ARCHIVO_LOCK_PRODUCCION).unlink(missing_ok=True)
                        except Exception:
                            pass
                        os.execv(sys.executable, [sys.executable, "-W", "ignore::DeprecationWarning"] + sys.argv)
                now_m = time.time()
                cur_trades = CAJA_NEGRA.trades_totales
                cur_vault = getattr(ESTADO_RAM, "contador_auditorias_baul", 0)
                if (
                    cur_trades != last_trades_cnt
                    or (cur_vault - last_vault_cnt) >= 4
                    or (now_m - last_auto_cal_ts) >= 900.0
                ):
                    last_trades_cnt = cur_trades
                    last_vault_cnt = cur_vault
                    last_auto_cal_ts = now_m
                    from evaluador_cuantico_oos import EvaluadorCuanticoOOS
                    ev_auto = EvaluadorCuanticoOOS(repo_dir=cfg.ROOT_DIR)
                    await asyncio.to_thread(ev_auto.calibrar_parametros_walk_forward, None, 72.0, True)
                res_oos = cfg.recargar_calibracion_oos_si_cambio()
                if res_oos.get("recargado"):
                    log_sniper(
                        f"[HOT-RELOAD OOS] Autonomous parameters synchronized from {cfg.ARCHIVO_CALIBRACION_OOS}: "
                        f"{res_oos.get('aplicados')} | Ctrl={getattr(ESTADO_RAM, 'controlador_autonomo', {})}"
                    )
                now = time.time()
                if now - last_panel >= 300.0:
                    await self.sincronizar_patrimonio_bybit()
                    CAJA_NEGRA.imprimir_panel_caja_negra()
                    last_panel = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                now_err = time.time()
                if (now_err - self._last_maint_err_ts) >= 60.0:
                    self._last_maint_err_ts = now_err
                    log_sniper(f"[WARN] [MAINTENANCE] Error in maintenance/hot-reload loop: {exc}")

    async def iniciar_produccion(self) -> None:
        self._running = True
        loop_name = type(asyncio.get_running_loop()).__name__
        log_sniper("==================================================================")
        log_sniper(f"STARTING CENTRAL CORE {cfg.NOMBRE_ESTRATEGIA.upper()} [{cfg.ESTRATEGIA_MATEMATICA}]")
        log_sniper("==================================================================")
        log_sniper(f"[MAIN] Physical single-instance lock acquired successfully (PID {os.getpid()} | Loop: {loop_name}).")
        log_sniper(f"[MAIN] Local timestamped telemetry active in: {cfg.ARCHIVO_LOG_SESION}")

        if self.exchange is None:
            import ccxt.pro as ccxtpro
            self.exchange = ccxtpro.bybit({
                "apiKey": cfg.BYBIT_API_KEY,
                "secret": cfg.BYBIT_API_SECRET,
                "timeout": 20000,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                    "recvWindow": 15000,
                    "adjustForTimeDifference": True,
                },
            })
            self.gestor.exchange = self.exchange
            self.ejecutor.exchange = self.exchange

        await self.exchange.load_markets()
        await reconciliar_posiciones_arranque(self.exchange)
        await self.sincronizar_patrimonio_bybit()

        total_u = ESTADO_RAM.patrimonio_total_usdt
        free_u = ESTADO_RAM.margen_libre_usdt
        locked_u = ESTADO_RAM.margen_bloqueado_usdt
        kelly_margin = round(free_u * cfg.KELLY_FRACCION_BASE, 2)
        kelly_notional = round(kelly_margin * cfg.APALANCAMIENTO_BASE, 2)

        log_sniper(
            f"[MAIN] UTA USDT Audit -> Total: {total_u:.4f} | Free RAM: {free_u:.4f} | "
            f"Locked: {locked_u:.4f} | Kelly Margin ({cfg.KELLY_FRACCION_BASE*100:.0f}%): "
            f"{kelly_margin:.2f} USDT (Notional {cfg.APALANCAMIENTO_BASE}x: {kelly_notional:.2f} USDT) [READY TO FIRE]"
        )

        excluded = auditar_y_filtrar_lotes_minimos(self.exchange, kelly_notional)
        if excluded:
            log_sniper(f"[MAIN] Minimum lot filter excluded indivisible pairs: {', '.join(excluded[:8])}")

        cad_ms = int(round(float(cfg.CADENCIA_RADAR_SEG) * 1000.0))
        freq_hz = round(1.0 / max(0.010, float(cfg.CADENCIA_RADAR_SEG)), 1)
        log_sniper(
            f"[MAIN] Paper Mode: {cfg.MODO_PAPER} | Radar: {freq_hz:.1f}Hz ({cad_ms}ms) | "
            f"Entry TTL: {cfg.TTL_ORDEN_ENTRADA_SEG}s (ReQuote={cfg.PERMITIR_REQUOTE}) | "
            f"Scratch: {cfg.MAKER_SCRATCH_TIEMPO_SEG:.0f}s | 50% TRIZ Harvest: +{cfg.COSECHA_TRIZ_ACTIVACION_PCT*100:.2f}% | "
            f"Internal SL: -{cfg.SL_INTERNO_PCT*100:.2f}% | Max Hold: {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s"
        )
        log_sniper(f"[MAIN] Active targets ({len(cfg.PARES_CAMPEONES_ALFA)} Alpha Champions): {', '.join(cfg.PARES_CAMPEONES_ALFA)}")

        ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        CAJA_NEGRA.imprimir_panel_caja_negra()

        await TELEMETRIA_TG.enviar_mensaje_sistema(
            f"[BOOT] {cfg.NOMBRE_ESTRATEGIA}\n"
            f"- Strategy: {cfg.ESTRATEGIA_MATEMATICA}\n"
            f"- UTA Equity: {total_u:.4f} USDT (Free: {free_u:.4f} USDT)\n"
            f"- Active Champions: {', '.join(p.split('/')[0] for p in cfg.PARES_CAMPEONES_ALFA)}\n"
            f"- Geometry: Radar={freq_hz:.1f}Hz ({cad_ms}ms) | TTL={cfg.TTL_ORDEN_ENTRADA_SEG}s | "
            f"Scratch={cfg.MAKER_SCRATCH_TIEMPO_SEG:.0f}s | 50% Harvest=+{cfg.COSECHA_TRIZ_ACTIVACION_PCT*100:.2f}% | SL=-{cfg.SL_INTERNO_PCT*100:.2f}%"
        )

        ws_symbols = list(cfg.PARES_CAMPEONES_ALFA) + [cfg.SIMBOLO_CENTINELA_MACRO]
        tasks = [asyncio.create_task(self._vigilar_stream_simbolo(s)) for s in ws_symbols]
        tasks.append(asyncio.create_task(self.gestor.bucle_vigilancia_posiciones()))
        tasks.append(asyncio.create_task(ESCUDO_TRICORTEX.bucle_orquestacion_tricortex()))
        tasks.append(asyncio.create_task(self._bucle_mantenimiento_y_hot_reload()))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.detener()

    async def detener(self) -> None:
        self._running = False
        self.gestor.detener()
        ESCUDO_TRICORTEX.detener()
        if self.exchange is not None:
            try:
                await self.exchange.close()
            except Exception:
                pass


async def main_async() -> int:
    lock = CerrojoInstanciaUnica()
    if not lock.adquirir():
        log_sniper("[ERROR] [ABORTED] Another instance of POUFS-BEELZEBUB-EN is already running (.tribrain.lock active).")
        return 1

    engine = MotorTriBrainSniper()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        log_sniper("[STOP] [MAIN] Shutdown signal received. Closing connections cleanly...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_shutdown)
            except Exception:
                pass

    try:
        await engine.iniciar_produccion()
        return 0
    finally:
        lock.liberar()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main_async()))
    except KeyboardInterrupt:
        sys.exit(0)