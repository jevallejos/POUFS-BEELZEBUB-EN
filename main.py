#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #11: main.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Cerebro Central Orquestador Asincrono (uvloop + Bybit UTA WebSocket L2):
  - Cerrojo fisico de instancia unica (.tribrain.lock / .tribrain_test.lock).
  - Sanitizador pre-vuelo de calibracion_oos.json (P-08) y reconciliador
    inteligente de arranque (ESCAPE_HUERFANA_BOOT / adopcion de posiciones).
  - Orquestacion paralela sin bloqueos:
      1. Streaming WebSocket L2 a 6.6 Hz (limit=25 en 7 Campeones + Centinela BTC).
      2. Vigilancia de posiciones CHRONOS-TRIZ (P-04, P-05, P-06).
      3. Enjambre Tri-Cortex (Groq Regimen + Gemini Sizing + NVIDIA Forense).
      4. Vigilante Hot-Reload OOS (< 0.5 ms) y telemetria periodica Caja Negra.
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
    def __init__(self, ruta_lock: Optional[pathlib.Path] = None) -> None:
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        nombre = cfg.ARCHIVO_LOCK_TEST if es_test else cfg.ARCHIVO_LOCK_PRODUCCION
        self.ruta_lock: pathlib.Path = ruta_lock or (cfg.ROOT_DIR / nombre)
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
                contenido = self.ruta_lock.read_text(encoding="utf-8").strip()
                pid_existente = int(contenido) if contenido.isdigit() else -1
                if pid_existente == self.pid:
                    self.adquirido = True
                    return True
                if self._pid_sigue_vivo(pid_existente):
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
                contenido = self.ruta_lock.read_text(encoding="utf-8").strip()
                if contenido == str(self.pid):
                    self.ruta_lock.unlink(missing_ok=True)
        except Exception:
            pass
        self.adquirido = False


def _sanear_json_oos_disco_phantom() -> None:
    if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
        return
    ruta_j = cfg.ROOT_DIR / cfg.ARCHIVO_CALIBRACION_OOS
    if not ruta_j.exists():
        return
    try:
        d = json.loads(ruta_j.read_text(encoding="utf-8-sig"))
        for sub_k in ("parametros", "parametros_calibrados", "hot_reload"):
            if sub_k in d and isinstance(d[sub_k], dict):
                d[sub_k]["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
                d[sub_k]["OFI_MIN_ENTRADA"] = 0.12
                d[sub_k]["Z_SCORE_UMBRAL_HIGH_BETA"] = max(
                    -3.60, min(float(d[sub_k].get("Z_SCORE_UMBRAL_HIGH_BETA", -3.10)), -3.00)
                )
                d[sub_k]["Z_SCORE_UMBRAL_TIER1"] = max(
                    -3.30, min(float(d[sub_k].get("Z_SCORE_UMBRAL_TIER1", -2.85)), -2.75)
                )
        d["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0024
        d["OFI_MIN_ENTRADA"] = 0.12
        d["Z_SCORE_UMBRAL_HIGH_BETA"] = max(
            -3.60, min(float(d.get("Z_SCORE_UMBRAL_HIGH_BETA", -3.10)), -3.00)
        )
        d["Z_SCORE_UMBRAL_TIER1"] = max(
            -3.30, min(float(d.get("Z_SCORE_UMBRAL_TIER1", -2.85)), -2.75)
        )
        ruta_j.write_bytes((json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        pass


_sanear_json_oos_disco_phantom()


async def reconciliar_posiciones_arranque(exchange: Any) -> int:
    if os.environ.get("TRIBRAIN_TEST_MODE") != "1":
        _sanear_json_oos_disco_phantom()
        cfg._aplicar_parametros_produccion_phantom()

    if exchange is None:
        return 0

    procesadas = 0
    ahora = time.time()

    for sym in cfg.PARES_CAMPEONES_ALFA:
        try:
            ordenes = await exchange.fetch_open_orders(sym)
            if ordenes:
                await exchange.cancel_all_orders(sym)
                log_sniper(f"🧹 [RECONCILIADOR] {len(ordenes)} orden(es) colgada(s) cancelada(s) en {sym}.")
        except Exception:
            pass

    try:
        posiciones = await exchange.fetch_positions()
    except Exception as exc:
        log_sniper(f"⚠️ [RECONCILIADOR] No se pudo consultar posiciones en arranque: {exc}")
        return 0

    abiertas = [p for p in (posiciones or []) if float(p.get("contracts") or 0.0) > 0.0]
    if not abiertas:
        log_sniper("[RECONCILIADOR] Sin posiciones huérfanas abiertas en Bybit. Margen 100% despejado.")
        return 0

    for p in abiertas:
        sym = str(p.get("symbol") or "")
        side = str(p.get("side") or "long").lower()
        qty = float(p.get("contracts") or 0.0)
        ep = float(p.get("entryPrice") or p.get("info", {}).get("avgPrice") or 0.0)
        mark_p = float(p.get("markPrice") or ep)

        ts_ms = p.get("timestamp") or p.get("info", {}).get("updatedTime") or p.get("info", {}).get("createdTime")
        if ts_ms is not None and float(ts_ms) > 0:
            t_apertura = float(ts_ms) / 1000.0 if float(ts_ms) > 1e11 else float(ts_ms)
            edad_seg = max(0.0, ahora - t_apertura)
        else:
            edad_seg = 14400.0
            t_apertura = ahora - edad_seg

        edad_min = edad_seg / 60.0
        if edad_seg >= cfg.TIEMPO_MAX_HOLD_SEG:
            log_sniper(
                f"🧹 [RECONCILIADOR] Posición zombie huérfana detectada en {sym}: "
                f"{qty} contratos @ {ep} (edad {edad_min:.1f} min >= {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s). "
                f"Liquidando a mercado para liberar margen..."
            )
            side_close = "sell" if side == "long" else "buy"
            exit_p = mark_p
            try:
                orden_c = await exchange.create_order(
                    sym, "market", side_close, qty, None, {"reduceOnly": True}
                )
                if isinstance(orden_c, dict):
                    p_avg = float(orden_c.get("average") or orden_c.get("price") or 0.0)
                    if p_avg > 0.0:
                        exit_p = p_avg
            except Exception as exc:
                log_sniper(f"⚠️ [RECONCILIADOR] Error cerrando zombie en {sym}: {exc}")
                continue

            pos_zombie = PosicionActiva(
                symbol=sym,
                side=side,
                qty_inicial=qty,
                qty_actual=qty,
                entry_price=ep,
                ts_apertura=t_apertura,
            )
            await CAJA_NEGRA.registrar_cierre_posicion(
                pos=pos_zombie,
                exit_price=exit_p,
                motivo="ESCAPE_HUERFANA_BOOT",
                es_salida_maker=False,
                ahora=ahora,
            )
            procesadas += 1
        else:
            tick_s, _, _ = extraer_precision_y_minimos(exchange, sym, ep)
            sl_i, sl_b = calcular_barreras_sl_iniciales(side, ep, tick_s)
            ts_norm = ahora if (edad_seg > 3600.0 or edad_seg < 0.0) else t_apertura
            pos_viva = PosicionActiva(
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
            ESTADO_RAM.posiciones_activas[sym] = pos_viva
            log_sniper(
                f"🛡️ [RECONCILIADOR] Posición reciente adoptada en {sym}: {qty} @ {ep} (edad {edad_seg:.0f}s)."
            )
            procesadas += 1

    log_sniper(f"[RECONCILIADOR] Reconciliación de arranque completada: {procesadas} posición(es) procesada(s).")
    return procesadas


def auditar_y_filtrar_lotes_minimos(exchange: Any, nocional_kelly_usdt: float) -> List[str]:
    excluidos: List[str] = []
    mercados = getattr(exchange, "markets", None) or {}
    for sym, mkt in mercados.items():
        if not str(sym).endswith("/USDT:USDT"):
            continue
        lims = (mkt.get("limits") or {}).get("amount") or {}
        min_q = float(lims.get("min") or 0.0)
        info = mkt.get("info") or {}
        precio_aprox = float(info.get("lastPrice") or info.get("markPrice") or 0.0)
        if min_q > 0.0 and precio_aprox > 0.0:
            costo_min = min_q * precio_aprox
            if costo_min > (nocional_kelly_usdt * 1.35):
                ESTADO_RAM.pares_excluidos_lote.add(sym)
                excluidos.append(sym)
    return sorted(excluidos)


class MotorTriBrainSniper:
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

    async def _evacuar_por_contagio_macro(self, motivo: str) -> None:
        await self.gestor.evacuar_todas_por_emergencia(motivo=motivo)

    async def sincronizar_patrimonio_bybit(self) -> None:
        if self.exchange is None:
            return
        try:
            bal = await self.exchange.fetch_balance()
            usdt = (bal or {}).get("USDT") or {}
            total = float(usdt.get("total") or 0.0)
            libre = float(usdt.get("free") or total)
            if total > 0.0:
                ESTADO_RAM.sincronizar_balance_uta(total, libre)
        except Exception as exc:
            log_sniper(f"⚠️ [MAIN] No se pudo sincronizar balance UTA: {exc}")

    async def _vigilar_stream_simbolo(self, symbol: str) -> None:
        while self._running and self.exchange is not None:
            try:
                ob = await self.exchange.watch_order_book(symbol, limit=25)
                bids = (ob or {}).get("bids") or []
                asks = (ob or {}).get("asks") or []
                if bids and asks:
                    await self.radar.procesar_instantanea_libro(symbol, bids, asks)
                await asyncio.sleep(cfg.CADENCIA_RADAR_SEG)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[RADAR] Error en {symbol}: {type(exc).__name__}: {exc}")
                await asyncio.sleep(2.5)

    async def _bucle_mantenimiento_y_hot_reload(self) -> None:
        ultimo_panel = time.time()
        while self._running:
            await asyncio.sleep(30.0)
            try:
                res_oos = cfg.recargar_calibracion_oos_si_cambio()
                if res_oos.get("recargado"):
                    log_sniper(
                        f"🔄 [HOT-RELOAD OOS] Parámetros actualizados en caliente desde {cfg.ARCHIVO_CALIBRACION_OOS}: "
                        f"{res_oos.get('aplicados')}"
                    )
                ahora = time.time()
                if ahora - ultimo_panel >= 300.0:
                    await self.sincronizar_patrimonio_bybit()
                    CAJA_NEGRA.imprimir_panel_caja_negra()
                    ultimo_panel = ahora
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def iniciar_produccion(self) -> None:
        self._running = True
        loop_name = type(asyncio.get_running_loop()).__name__
        log_sniper("==================================================================")
        log_sniper(f"INICIANDO CEREBRO CENTRAL {cfg.NOMBRE_ESTRATEGIA.upper()} [{cfg.ESTRATEGIA_MATEMATICA}]")
        log_sniper("==================================================================")
        log_sniper(f"[MAIN] Bloqueo de instancia física adquirido exitosamente (PID {os.getpid()} | Loop: {loop_name}).")
        log_sniper(f"[MAIN] Telemetría local con sellado de tiempo activa en: {cfg.ARCHIVO_LOG_SESION}")

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
        libre_u = ESTADO_RAM.margen_libre_usdt
        bloq_u = ESTADO_RAM.margen_bloqueado_usdt
        margen_k = round(libre_u * cfg.KELLY_FRACCION_BASE, 2)
        nocional_k = round(margen_k * cfg.APALANCAMIENTO_BASE, 2)

        log_sniper(
            f"[MAIN] Auditoría UTA USDT -> Total: {total_u:.4f} | Libre RAM: {libre_u:.4f} | "
            f"Bloqueado: {bloq_u:.4f} | Margen Kelly ({cfg.KELLY_FRACCION_BASE*100:.0f}%): "
            f"{margen_k:.2f} USDT (Nocional {cfg.APALANCAMIENTO_BASE}x: {nocional_k:.2f} USDT) [LISTO PARA DISPARAR]"
        )

        excluidos = auditar_y_filtrar_lotes_minimos(self.exchange, nocional_k)
        if excluidos:
            log_sniper(f"[MAIN] Filtro de lote mínimo excluyó pares indivisibles: {', '.join(excluidos[:8])}")

        log_sniper(
            f"[MAIN] Modo Paper: {cfg.MODO_PAPER} | Estrategia: {cfg.ESTRATEGIA_MATEMATICA} | "
            f"TTL Entrada: {cfg.TTL_ORDEN_ENTRADA_SEG}s (ReQuote={cfg.PERMITIR_REQUOTE}) | "
            f"Scratch: {cfg.MAKER_SCRATCH_TIEMPO_SEG:.0f}s | Cosecha 50% TRIZ: +{cfg.COSECHA_TRIZ_ACTIVACION_PCT*100:.2f}% | "
            f"SL Interno: -{cfg.SL_INTERNO_PCT*100:.2f}% | Hold Máx: {cfg.TIEMPO_MAX_HOLD_SEG:.0f}s"
        )
        log_sniper(f"[MAIN] Presas activas ({len(cfg.PARES_CAMPEONES_ALFA)} Campeones Alfa): {', '.join(cfg.PARES_CAMPEONES_ALFA)}")

        ESCUDO_TRICORTEX.inicializar_whitelist_ram()
        CAJA_NEGRA.imprimir_panel_caja_negra()

        await TELEMETRIA_TG.enviar_mensaje_sistema(
            f"⚡ {cfg.NOMBRE_ESTRATEGIA}\n"
            f"📐 Estrategia: {cfg.ESTRATEGIA_MATEMATICA}\n"
            f"💰 Patrimonio UTA: {total_u:.4f} USDT (Libre: {libre_u:.4f} USDT)\n"
            f"🎯 Campeones activos: {', '.join(p.split('/')[0] for p in cfg.PARES_CAMPEONES_ALFA)}\n"
            f"🛡️ Geometría: TTL={cfg.TTL_ORDEN_ENTRADA_SEG}s | Scratch={cfg.MAKER_SCRATCH_TIEMPO_SEG:.0f}s | "
            f"Cosecha 50%=+{cfg.COSECHA_TRIZ_ACTIVACION_PCT*100:.2f}% | SL=-{cfg.SL_INTERNO_PCT*100:.2f}%"
        )

        simbolos_ws = list(cfg.PARES_CAMPEONES_ALFA) + [cfg.SIMBOLO_CENTINELA_MACRO]
        tareas = [asyncio.create_task(self._vigilar_stream_simbolo(s)) for s in simbolos_ws]
        tareas.append(asyncio.create_task(self.gestor.bucle_vigilancia_posiciones()))
        tareas.append(asyncio.create_task(ESCUDO_TRICORTEX.bucle_orquestacion_tricortex()))
        tareas.append(asyncio.create_task(self._bucle_mantenimiento_y_hot_reload()))

        try:
            await asyncio.gather(*tareas)
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
    cerrojo = CerrojoInstanciaUnica()
    if not cerrojo.adquirir():
        log_sniper("❌ [ABORTADO] Otra instancia de Tri-Brain-Sniper ya está en ejecución (.tribrain.lock activo).")
        return 1

    motor = MotorTriBrainSniper()
    loop = asyncio.get_running_loop()

    def _solicitar_apagado() -> None:
        log_sniper("🛑 [MAIN] Señal de apagado recibida. Cerrando conexiones limpiamente...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _solicitar_apagado)
            except Exception:
                pass

    try:
        await motor.iniciar_produccion()
        return 0
    finally:
        cerrojo.liberar()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main_async()))
    except KeyboardInterrupt:
        sys.exit(0)
