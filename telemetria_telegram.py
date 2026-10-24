#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #05: telemetria_telegram.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
Transactional Telegram Telemetry Engine with Strict 1:1 Pairing.
Clean classic format with color status icons:
  - Confirmed Open       : \U0001f7e9 GREEN ALERT (PROD)
  - 50% TRIZ Harvest     : \U0001f48e [50% TRIZ HARVEST]
  - Profitable Close     : \U0001f7e9 [CLOSE ...]
  - 18s Scratch Close    : \U0001f7e8 [CLOSE MAKER_SCRATCH_18S]
  - Loss Close           : \U0001f534 [CLOSE ...]
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
    """In-memory RAM buffer for a Limit PostOnly order awaiting fill on Bybit."""
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
    Asynchronous notification client with a strict 1:1 pairing protocol,
    idempotent time-window deduplication, and clean classic icon formatting.
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
        now = time.time()
        self._limpiar_expirados(now, ttl_seg)
        if clave in self.cache_dedup:
            return False
        self.cache_dedup[clave] = now
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
        removed = self.aperturas_pendientes.pop(symbol, None)
        return removed is not None

    async def _despachar_http_telegram(self, texto: str, tipo_evento: str, symbol: str) -> bool:
        final_message = str(texto or "").strip()
        if not final_message:
            return False

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            test_text = final_message
            if cfg.TITULO_TELEGRAM_CANONICO not in test_text:
                test_text = f"{test_text}\n{cfg.TITULO_TELEGRAM_CANONICO}"
            self.buzon_test.append({
                "tipo": tipo_evento,
                "symbol": symbol,
                "texto": test_text,
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
                payload = {"chat_id": chat_id, "text": final_message}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body_err = await resp.text()
                    log_sniper(f"[WARN] [TELEGRAM HTTP {resp.status}] Retrying dispatch: {body_err[:120]}")
                async with session.post(url, json={"chat_id": chat_id, "text": final_message}) as resp2:
                    return resp2.status == 200
        except Exception as exc:
            log_sniper(f"[WARN] [TELEGRAM NET ERROR] Could not dispatch {tipo_evento} on {symbol}: {exc}")
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

        pending = self.aperturas_pendientes.pop(symbol, None)
        side_str = (pending.side if pending else side).upper()
        oid_str = order_id or (pending.order_id if pending else "N/A")
        side_tag = f" [{side_str}]" if side_str == "SHORT" else ""

        text = (
            f"{ICONO_VERDE} GREEN ALERT (PROD):\n"
            f"Limit PostOnly Order on {symbol}{side_tag}\n"
            f"Price: {entry_price}\n"
            f"ID: {oid_str}"
        )
        return await self._despachar_http_telegram(text, "OPEN_CONFIRMED", symbol)

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

        side_tag = " [SHORT]" if str(side).lower() == "short" else ""
        text = (
            f"{ICONO_DIAMANTE} [50% TRIZ HARVEST]{side_tag} {symbol}\n"
            f"{pnl_parcial_pct:+.2f} % ({pnl_parcial_usdt:+.4f} USDT) | {qty_vendida} @ {exit_price}"
        )
        return await self._despachar_http_telegram(text, "COSECHA_50_TRIZ", symbol)

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
        reason_upper = str(motivo or "CLOSE").upper()
        if "ESCAPE_HUERFANA_BOOT" in reason_upper or float(hold_seg or 0.0) >= 14000.0:
            return False

        if not self._verificar_y_marcar_dedup(f"CLOSE:{symbol}", ttl_seg=12.0):
            return False

        self.aperturas_pendientes.pop(symbol, None)

        pnl_u = float(pnl_usdt)
        pnl_p = float(pnl_pct)
        is_profit = pnl_u >= 0.0
        is_scratch_18s = ("SCRATCH" in reason_upper) and not is_profit

        if is_profit:
            icon = ICONO_VERDE
        elif is_scratch_18s:
            icon = ICONO_AMARILLO
        else:
            icon = ICONO_ROJO

        side_tag = " [SHORT]" if str(side).lower() == "short" else ""
        text = (
            f"{icon} [CLOSE {motivo}]{side_tag} {symbol}\n"
            f"{pnl_p:+.2f} % ({pnl_u:+.4f} USDT) in {float(hold_seg):.0f}s"
        )
        event_type = "CLOSE_WIN" if is_profit else ("CLOSE_SCRATCH" if is_scratch_18s else "CLOSE_LOSS")
        return await self._despachar_http_telegram(text, event_type, symbol)

    async def enviar_mensaje_sistema(self, texto: str) -> bool:
        return await self._despachar_http_telegram(texto, "SISTEMA", "GLOBAL")


TELEMETRIA_TG: GestorTelemetriaTelegram = GestorTelemetriaTelegram()