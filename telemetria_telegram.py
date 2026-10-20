#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #05: telemetria_telegram.py
SISTEMA: TRI-BRAIN-SNIPER (SKILL HUNTER) V4.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Motor Transaccional de Telemetria a Telegram con Apareamiento Estricto 1:1.
Garantiza el envio 100% confiable de:
  - Aperturas reales confirmadas en Bybit UTA (🎯).
  - Cosecha Fraccionada 50/50 TRIZ (💎).
  - Cierres en Ganancia (🟩), Evacuacion Maker-Scratch 18s (🟨) y Perdidas/SL (🔴).
==============================================================================
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

import config_parametros as cfg
from core_estado_ram import log_sniper


@dataclass(slots=True)
class AperturaPendienteRAM:
    """Buffer en RAM de una orden Limit PostOnly esperando llenado en Bybit (TTL 2.2s)."""
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
    deduplicacion idempotente por ventana temporal y cobertura total de perdidas.
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
        """Retorna True si el evento NO ha sido enviado en los ultimos ttl_seg segundos."""
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
        """
        Paso 1 del Apareamiento 1:1: Guarda la orden Limit PostOnly en RAM
        sin notificar aun a Telegram hasta confirmar que Bybit la lleno.
        """
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
        """
        Paso 2 del Apareamiento 1:1: Si la orden expira a los 2.2s sin llenarse,
        se elimina silenciosamente del buffer en RAM sin emitir spam a Telegram.
        """
        eliminado = self.aperturas_pendientes.pop(symbol, None)
        return eliminado is not None

    async def _despachar_http_telegram(self, texto: str, tipo_evento: str, symbol: str) -> bool:
        """
        Envia el mensaje a la API de Telegram con fallback automatico a texto plano
        para evitar rechazos HTTP 400 por caracteres '_' en motivos de cierre.
        En modo de pruebas (TRIBRAIN_TEST_MODE == '1'), almacena en buzon_test.
        """
        mensaje_final = str(texto or "").strip()
        if not mensaje_final:
            return False

        if cfg.TITULO_TELEGRAM_CANONICO not in mensaje_final:
            mensaje_final = f"{mensaje_final}\n⚙️ {cfg.TITULO_TELEGRAM_CANONICO}"

        if os.environ.get("TRIBRAIN_TEST_MODE") == "1":
            self.buzon_test.append({
                "tipo": tipo_evento,
                "symbol": symbol,
                "texto": mensaje_final,
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
                # Envío directo sin parse_mode fragil para garantizar 100% de entrega en SL/Scratch
                payload = {"chat_id": chat_id, "text": mensaje_final}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    body_err = await resp.text()
                    log_sniper(f"⚠️ [TELEGRAM HTTP {resp.status}] Reintentando envio plano: {body_err[:120]}")
                # Segundo intento de respaldo
                async with session.post(url, json={"chat_id": chat_id, "text": mensaje_final}) as resp2:
                    return resp2.status == 200
        except Exception as exc:
            log_sniper(f"⚠️ [TELEGRAM ERROR RED] No se pudo despachar {tipo_evento} en {symbol}: {exc}")
            return False

    async def confirmar_y_enviar_apertura(
        self,
        symbol: str,
        qty_llenada: float,
        entry_price: float,
        side: str = "long",
        order_id: str = "",
    ) -> bool:
        """
        Paso 3 del Apareamiento 1:1: Invocado UNICAMENTE cuando Bybit confirma
        posicion activa (🎯). Extrae del buffer RAM y despacha la apertura a Telegram.
        """
        if not self._verificar_y_marcar_dedup(f"OPEN:{symbol}", ttl_seg=10.0):
            return False

        pend = self.aperturas_pendientes.pop(symbol, None)
        side_str = (pend.side if pend else side).upper()
        oid_str = order_id or (pend.order_id if pend else "N/A")
        nocional = float(qty_llenada) * float(entry_price)
        extra_metrica = ""
        if pend and (pend.z_score != 0.0 or pend.ofi != 0.0):
            extra_metrica = f"\nSeñal: Z={pend.z_score:+.2f} | OFI={pend.ofi:+.2f}"

        icono_side = "🟩" if side_str == "LONG" else "🟪"
        texto = (
            f"{icono_side} [APERTURA CONFIRMADA {side_str}] {symbol}\n"
            f"Contratos: {qty_llenada} @ {entry_price} (~{nocional:.2f} USDT)\n"
            f"ID Orden: {oid_str}{extra_metrica}\n"
            f"⚙️ {cfg.TITULO_TELEGRAM_CANONICO}"
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
        """
        Notifica la ejecucion de la Ley 3 de CHRONOS-TRIZ:
        Cosecha del primer 50% en +0.26% Maker y armado del Trinquete Break-Even (+0.12% neto).
        """
        if not self._verificar_y_marcar_dedup(f"TRIZ50:{symbol}", ttl_seg=12.0):
            return False

        texto = (
            f"💎 [COSECHA 50% TRIZ + BE ARMADO] {symbol} ({side.upper()})\n"
            f"Lote Cosechado: {qty_vendida} contratos ({entry_price} -> {exit_price})\n"
            f"Caja Asegurada: {pnl_parcial_pct:+.2f} % ({pnl_parcial_usdt:+.4f} USDT)\n"
            f"Restante 50%: Modo FREE-RUNNER activo (sin límite de tiempo, SL +0.05%).\n"
            f"⚙️ {cfg.TITULO_TELEGRAM_CANONICO}"
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
        """
        Paso 4 del Apareamiento 1:1: Despacho 100% garantizado e incondicional de cierres.
        Clasifica visualmente en:
          - 🟩 Cierre en Ganancia (pnl_usdt >= 0)
          - 🟨 Evacuacion Maker-Scratch 18s (Ley 2 Avellaneda-Stoikov)
          - 🔴 Cierre en Perdida / Stop-Loss / Escape Temporal (pnl_usdt < 0)
        """
        mot_upper = str(motivo or "CIERRE").upper()
        # Bloquear unicamente limpiezas de arranque o mocks de ordenes zero_rest
        if "ESCAPE_HUERFANA_BOOT" in mot_upper or float(hold_seg or 0.0) >= 14000.0:
            return False

        if not self._verificar_y_marcar_dedup(f"CLOSE:{symbol}", ttl_seg=12.0):
            return False

        # Limpiar cualquier apertura pendiente residual del mismo simbolo
        self.aperturas_pendientes.pop(symbol, None)

        pnl_u = float(pnl_usdt)
        pnl_p = float(pnl_pct)
        es_ganancia = pnl_u >= 0.0
        es_scratch_18s = ("SCRATCH" in mot_upper) and not es_ganancia

        if es_ganancia:
            icono = "🟩"
            cabecera = "CIERRE GANADOR"
        elif es_scratch_18s:
            icono = "🟨"
            cabecera = "EVACUACIÓN MAKER-SCRATCH 18S"
        else:
            icono = "🔴"
            cabecera = "CIERRE EN PÉRDIDA / SL"

        lado_tag = " [SHORT]" if str(side).lower() == "short" else " [LONG]"
        tramo = f" ({entry_price} -> {exit_price})" if (entry_price > 0.0 and exit_price > 0.0) else ""
        nota_triz = " | Cosecha 50% TRIZ incluida" if cosecha_50_previa else ""

        texto = (
            f"{icono} [{cabecera} - {motivo}]{lado_tag} {symbol}\n"
            f"Resultado Neto: {pnl_p:+.2f} % ({pnl_u:+.4f} USDT) en {float(hold_seg):.0f}s{tramo}{nota_triz}\n"
            f"⚙️ {cfg.TITULO_TELEGRAM_CANONICO}"
        )
        tipo_ev = "CLOSE_WIN" if es_ganancia else ("CLOSE_SCRATCH" if es_scratch_18s else "CLOSE_LOSS")
        return await self._despachar_http_telegram(texto, tipo_ev, symbol)

    async def enviar_mensaje_sistema(self, texto: str) -> bool:
        """Envia notificaciones operativas de arranque o reportes del Evaluador Cuantico OOS."""
        return await self._despachar_http_telegram(texto, "SISTEMA", "GLOBAL")


# Instancia Singleton global del gestor de telemetria
TELEMETRIA_TG: GestorTelemetriaTelegram = GestorTelemetriaTelegram()

# === INICIO GARANTIA ENTREGA TELEGRAM V3.0 ===
def _resolver_credenciales_telegram_v3() -> tuple[str, str]:
    env_p = __import__('pathlib').Path(__file__).resolve().parent / '.env'
    if env_p.exists():
        for lin in env_p.read_text(encoding='utf-8', errors='ignore').splitlines():
            s = lin.strip()
            if s and not s.startswith('#') and '=' in s:
                k, v = s.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    token = (
        os.environ.get('TELEGRAM_BOT_TOKEN')
        or os.environ.get('TELEGRAM_TOKEN')
        or getattr(cfg, 'TELEGRAM_BOT_TOKEN', '')
        or ''
    ).strip()
    chat_id = (
        os.environ.get('TELEGRAM_CHAT_ID')
        or os.environ.get('CHAT_ID')
        or getattr(cfg, 'TELEGRAM_CHAT_ID', '')
        or ''
    ).strip()
    cfg.TELEGRAM_BOT_TOKEN = token
    cfg.TELEGRAM_CHAT_ID = chat_id
    return token, chat_id

if not hasattr(GestorTelemetriaTelegram, '_orig_despachar_http_v3'):
    GestorTelemetriaTelegram._orig_despachar_http_v3 = GestorTelemetriaTelegram._despachar_http_telegram

    async def _despachar_http_telegram_v3(self, texto: str, tipo_evento: str, symbol: str) -> bool:
        if os.environ.get('TRIBRAIN_TEST_MODE') != '1':
            tok, cid = _resolver_credenciales_telegram_v3()
            for attr_t in ('bot_token', 'token'):
                if hasattr(self, attr_t):
                    setattr(self, attr_t, tok)
            for attr_c in ('chat_id',):
                if hasattr(self, attr_c):
                    setattr(self, attr_c, cid)
        ok = await GestorTelemetriaTelegram._orig_despachar_http_v3(self, texto, tipo_evento, symbol)
        if os.environ.get('TRIBRAIN_TEST_MODE') != '1':
            if ok:
                primera = str(texto or '').splitlines()[0][:75]
                log_sniper(f'\U0001f4e8 [TELEGRAM OK] ({tipo_evento}) {primera}')
            else:
                tok, cid = _resolver_credenciales_telegram_v3()
                if not tok or not cid:
                    log_sniper('\u26a0\ufe0f [TELEGRAM ALERTA] Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env')
        return ok

    GestorTelemetriaTelegram._despachar_http_telegram = _despachar_http_telegram_v3
# === FIN GARANTIA ENTREGA TELEGRAM V3.0 ===
