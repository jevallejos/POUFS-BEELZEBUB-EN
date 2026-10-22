#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #05: telemetria_telegram.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor Transaccional de Telemetria a Telegram con Apareamiento Estricto 1:1.
Formato clasico limpio con iconos simples de colores:
  - Apertura confirmada : \U0001f7e9 ALERTA VERDE (PROD)
  - Cosecha 50% TRIZ    : \U0001f48e [COSECHA 50% TRIZ]
  - Cierre en Ganancia  : \U0001f7e9 [CIERRE ...]
  - Cierre Scratch 18s  : \U0001f7e8 [CIERRE MAKER_SCRATCH_18S]
  - Cierre en Perdida   : \U0001f534 [CIERRE ...]
==============================================================================
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import aiohttp

import config_parametros as cfg
from core_estado_ram import log_sniper

ICONO_VERDE: str = "\U0001f7e9"
ICONO_ROJO: str = "\U0001f534"
ICONO_AMARILLO: str = "\U0001f7e8"
ICONO_DIAMANTE: str = "\U0001f48e"


@dataclass(slots=True)
class AperturaPendienteRAM:
    """Buffer en RAM de una orden Limit PostOnly esperando llenado en Bybit."""
    symbol: str
    side: str
    qty: float
    price: float
    order_id: str
    z_score: float = 0.0
    ofi: float = 0.0
    ts_creacion: float = field(default_factory=time.time)


class GestorTelemetriaTelegram:
    """
    Cliente asincrono de notificaciones con protocolo de apareamiento 1:1,
    deduplicacion idempotente por ventana temporal y formato clasico con iconos simples.
    """

    def __init__(self) -> None:
        self.aperturas_pendientes: Dict[str, AperturaPendienteRAM] = {}
        self.cache_dedup: Dict[str, float] = {}
        self.buzon_test: List[Dict[str, Any]] = []

    def _limpiar_expirados(self, ahora: float, ttl_dedup: float = 12.0) -> None:
        for k in list(self.cache_dedup.keys()):
            if ahora - self.cache_dedup[k] > ttl_dedup:
                self.cache_dedup.pop(k, None)
        for sym in list(self.aperturas_pendientes.keys()):
            if ahora - self.aperturas_pendientes[sym].ts_creacion > 30.0:
                self.aperturas_pendientes.pop(sym, None)

    def _verificar_y_marcar_dedup(self, clave: str, ttl_seg: float = 12.0) -> bool:
        ahora = time.time()
        self._limpiar_expirados(ahora, ttl_seg)
        if clave in self.cache_dedup:
            return False
        self.cache_dedup[clave] = ahora
        return True

    def retener_apertura_pendiente(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_id: str,
        z_score: float = 0.0,
        ofi: float = 0.0,
    ) -> None:
        self.aperturas_pendientes[symbol] = AperturaPendienteRAM(
            symbol=symbol,
            side=side.lower(),
            qty=float(qty),
            price=float(price),
            order_id=str(order_id),
            z_score=float(z_score),
            ofi=float(ofi),
            ts_creacion=time.time(),
        )

    def descartar_apertura_no_llenada(self, symbol: str) -> bool:
        eliminado = self.aperturas_pendientes.pop(symbol, None)
        return eliminado is not None

    async def _despachar_http_telegram(self, texto: str, tipo_evento: str, symbol: str) -> bool:
        mensaje_final = str(texto or "").strip()
        if not mensaje_final:
            return False

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            texto_test = mensaje_final
            if cfg.TITULO_TELEGRAM_CANONICO not in texto_test:
                texto_test = f"{texto_test}\n{cfg.TITULO_TELEGRAM_CANONICO}"
            self.buzon_test.append({
                "tipo": tipo_evento,
                "symbol": symbol,
                "texto": texto_test,
                "ts": time.time(),
            })
            return True

        token = cfg.TELEGRAM_BOT_TOKEN
        chat_id = cfg.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        timeout = aiohttp.ClientTimeout(total=8.0)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {"chat_id": chat_id, "text": mensaje_final}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body_err = await resp.text()
                    log_sniper(f"[WARN] [TELEGRAM HTTP {resp.status}] Reintentando envio: {body_err[:120]}")
                async with session.post(url, json={"chat_id": chat_id, "text": mensaje_final}) as resp2:
                    return resp2.status == 200
        except Exception as exc:
            log_sniper(f"[WARN] [TELEGRAM ERROR RED] No se pudo despachar {tipo_evento} en {symbol}: {exc}")
            return False

    async def confirmar_y_enviar_apertura(
        self,
        symbol: str,
        qty_llenada: float,
        entry_price: float,
        side: str = "long",
        order_id: str = "",
    ) -> bool:
        if not self._verificar_y_marcar_dedup(f"OPEN:{symbol}", ttl_seg=10.0):
            return False

        pend = self.aperturas_pendientes.pop(symbol, None)
        side_str = (pend.side if pend else side).upper()
        oid_str = order_id or (pend.order_id if pend else "N/A")
        lado_tag = f" [{side_str}]" if side_str == "SHORT" else ""

        texto = (
            f"{ICONO_VERDE} ALERTA VERDE (PROD):\n"
            f"Orden Limit PostOnly en {symbol}{lado_tag}\n"
            f"Precio: {entry_price}\n"
            f"ID: {oid_str}"
        )
        return await self._despachar_http_telegram(texto, "OPEN_CONFIRMED", symbol)

    async def notificar_cosecha_parcial_triz(
        self,
        symbol: str,
        side: str,
        qty_vendida: float,
        entry_price: float,
        exit_price: float,
        pnl_parcial_pct: float,
        pnl_parcial_usdt: float,
    ) -> bool:
        if not self._verificar_y_marcar_dedup(f"TRIZ50:{symbol}", ttl_seg=12.0):
            return False

        lado_tag = " [SHORT]" if str(side).lower() == "short" else ""
        texto = (
            f"{ICONO_DIAMANTE} [COSECHA 50% TRIZ]{lado_tag} {symbol}\n"
            f"{pnl_parcial_pct:+.2f} % ({pnl_parcial_usdt:+.4f} USDT) | {qty_vendida} @ {exit_price}"
        )
        return await self._despachar_http_telegram(texto, "COSECHA_50_TRIZ", symbol)

    async def enviar_cierre_garantizado(
        self,
        symbol: str,
        side: str,
        pnl_pct: float,
        pnl_usdt: float,
        hold_seg: float,
        motivo: str,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        cosecha_50_previa: bool = False,
    ) -> bool:
        mot_upper = str(motivo or "CIERRE").upper()
        if "ESCAPE_HUERFANA_BOOT" in mot_upper or float(hold_seg or 0.0) >= 14000.0:
            return False

        if not self._verificar_y_marcar_dedup(f"CLOSE:{symbol}", ttl_seg=12.0):
            return False

        self.aperturas_pendientes.pop(symbol, None)

        pnl_u = float(pnl_usdt)
        pnl_p = float(pnl_pct)
        es_ganancia = pnl_u >= 0.0
        es_scratch_18s = ("SCRATCH" in mot_upper) and not es_ganancia

        if es_ganancia:
            icono = ICONO_VERDE
        elif es_scratch_18s:
            icono = ICONO_AMARILLO
        else:
            icono = ICONO_ROJO

        lado_tag = " [SHORT]" if str(side).lower() == "short" else ""
        texto = (
            f"{icono} [CIERRE {motivo}]{lado_tag} {symbol}\n"
            f"{pnl_p:+.2f} % ({pnl_u:+.4f} USDT) en {float(hold_seg):.0f}s"
        )
        tipo_ev = "CLOSE_WIN" if es_ganancia else ("CLOSE_SCRATCH" if es_scratch_18s else "CLOSE_LOSS")
        return await self._despachar_http_telegram(texto, tipo_ev, symbol)

    async def enviar_mensaje_sistema(self, texto: str) -> bool:
        return await self._despachar_http_telegram(texto, "SISTEMA", "GLOBAL")


TELEMETRIA_TG: GestorTelemetriaTelegram = GestorTelemetriaTelegram()