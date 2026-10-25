#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
FILE #04: core_estado_ram.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- CHRONOS-TRIZ STRATEGY
==============================================================================
O(1) Shared-Memory Core, @dataclass Contracts, Dual Logger (CL/UTC) with
Inode-Verified Persistent Line-Buffered I/O Descriptors (25.0 Hz Ready), and
Forensic AI Cognitive Vault Engine (baul_ia_forense.jsonl) with Deferred
+15.0s Counterfactual Oracle for auditing SCAR-LOCK-01..18.
Single-Layer Native Architecture free of dynamic wrappers.
==============================================================================
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TextIO, Tuple

import config_parametros as cfg

_TZ_UTC = timezone.utc
_TZ_CHILE = timezone(timedelta(hours=-3))
_ARCHIVO_BAUL_IA: str = "baul_ia_forense.jsonl"


# ==============================================================================
# 1. STRICT DATA CONTRACTS (@DATACLASS) WITH SAFETY ALIASES
# ==============================================================================
@dataclass(slots=True)
class MetricaTick:
    """Instantaneous O(1) microstructural snapshot of an asset in the 25.0 Hz Radar."""
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread_pct: float = 0.0
    z_score: float = 0.0
    delta_p_pct: float = 0.0
    ema900: float = 0.0
    ema900_dist_pct: float = 0.0
    ema900_slope_pct: float = 0.0
    ofi_l1_l5: float = 0.0
    ofi_5s: float = 0.0
    ofi_ticks_confirmados_long: int = 0
    ofi_ticks_confirmados_short: int = 0
    hurst: float = 0.50
    lyapunov_acel_pct: float = 0.0
    hawkes_intensidad: float = 0.0
    vpin: float = 0.0
    volatilidad_local: float = 0.0
    ts_ultimo_pulso_toxico: float = 0.0
    ts_tick: float = field(default_factory=time.time)


@dataclass(slots=True)
class PermisoRegimenActivo:
    """Governance vector assigned by the Tri-Cortex Swarm in RAM."""
    symbol: str
    modo_regimen: str = "LONG_ONLY"
    aprobado_groq: bool = True
    sizing_mult_gemini: float = 1.0
    caida_min_override_pct: float = 0.0
    cuarentena_hasta_ts: float = 0.0
    motivo: str = "INIT_DEFAULT"
    ts_actualizacion: float = field(default_factory=time.time)


@dataclass
class PosicionActiva:
    """
    In-memory RAM state of an open position on Bybit UTA.
    Natively supports Laws 2 and 3 of CHRONOS-TRIZ, the 50/25/25 Convex Ladder
    (P-06), and intratrade trajectory telemetry (MFE / MAE) for the Forensic
    AI Cognitive Vault.
    """
    symbol: str
    side: str
    qty_inicial: float
    qty_actual: float
    entry_price: float
    ts_apertura: float = field(default_factory=time.time)
    sl_interno_price: float = 0.0
    sl_bybit_price: float = 0.0
    z_score_entry: float = 0.0
    ofi_entry: float = 0.0
    hurst_entry: float = 0.45
    volatilidad_entry: float = 0.0020

    # CHRONOS-TRIZ and Bi-Class 50/25/25 Ladder state (P-06)
    scratch_18s_evaluado: bool = False
    scratch_18s_activo: bool = False
    cosecha_50_ejecutada: bool = False
    ts_cosecha_50: float = 0.0
    cosecha_25_ejecutada: bool = False
    chain_jail_activo: bool = False
    eslabon_chain_jail: int = 0
    pre_escape_72s_enviado: bool = False
    pnl_realizado_parcial_usdt: float = 0.0
    fees_acumulados_usdt: float = 0.0
    max_pnl_pct_alcanzado: float = 0.0
    trinquete_be_armado: bool = False
    trinquete_ratchet_activo: bool = False
    trailing_activo: bool = False

    # In-flight Limit PostOnly exit order tracking
    orden_salida_id: Optional[str] = None
    orden_salida_precio: float = 0.0
    orden_salida_qty: float = 0.0
    orden_salida_ts: float = 0.0
    orden_salida_tipo: str = ""

    # Atomic anti-double-accounting lock
    cerrada: bool = False

    # Entry microstructural context and intratrade anatomy (Forensic AI Vault)
    p_dia_entry: float = 0.25
    tag_percentil_entry: str = "P25_ELASTIC"
    ema900_dist_entry: float = 0.0
    ema900_slope_entry: float = 0.0
    delta_p_entry: float = 0.0
    lyapunov_entry: float = 0.0
    hawkes_entry: float = 0.0
    vpin_entry: float = 0.0
    z_btc_entry: float = 0.0
    ofi_btc_entry: float = 0.0
    kelly_fraccion_entry: float = 0.55
    hurst_max_elastico_entry: float = 0.485
    min_pnl_pct_alcanzado: float = 0.0
    pnl_18s_pct: float = 0.0
    pnl_45s_pct: float = 0.0
    snapshot_18s_tomado: bool = False
    snapshot_45s_tomado: bool = False
    modo_cosecha_ejecutado: str = "NONE"

    @property
    def entrada(self) -> float:
        return self.entry_price

    @entrada.setter
    def entrada(self, valor: float) -> None:
        self.entry_price = float(valor)

    @property
    def precio_entrada(self) -> float:
        return self.entry_price

    @precio_entrada.setter
    def precio_entrada(self, valor: float) -> None:
        self.entry_price = float(valor)

    @property
    def t_apertura(self) -> float:
        return self.ts_apertura

    @t_apertura.setter
    def t_apertura(self, valor: float) -> None:
        self.ts_apertura = float(valor)

    @property
    def timestamp_apertura(self) -> float:
        return self.ts_apertura

    @timestamp_apertura.setter
    def timestamp_apertura(self, valor: float) -> None:
        self.ts_apertura = float(valor)

    @property
    def qty(self) -> float:
        return self.qty_actual

    @qty.setter
    def qty(self, valor: float) -> None:
        self.qty_actual = float(valor)

    def edad_segundos(self, ahora: Optional[float] = None) -> float:
        t_now = ahora if ahora is not None else time.time()
        return max(0.0, t_now - self.ts_apertura)

    def calcular_pnl_bruto_pct(self, precio_actual: float) -> float:
        if self.entry_price <= 0.0 or precio_actual <= 0.0:
            return 0.0
        if self.side == "short":
            return (self.entry_price - precio_actual) / self.entry_price
        return (precio_actual - self.entry_price) / self.entry_price

    def actualizar_anatomia_intratrade(self, pnl_bruto_pct: float, edad_seg: float) -> None:
        if pnl_bruto_pct > self.max_pnl_pct_alcanzado:
            self.max_pnl_pct_alcanzado = pnl_bruto_pct
        if pnl_bruto_pct < self.min_pnl_pct_alcanzado:
            self.min_pnl_pct_alcanzado = pnl_bruto_pct
        if not self.snapshot_18s_tomado and edad_seg >= 18.0:
            self.pnl_18s_pct = round(pnl_bruto_pct, 6)
            self.snapshot_18s_tomado = True
        if not self.snapshot_45s_tomado and edad_seg >= 45.0:
            self.pnl_45s_pct = round(pnl_bruto_pct, 6)
            self.snapshot_45s_tomado = True


@dataclass(slots=True)
class RegistroOperacionCerrada:
    """Immutable record for persistence in tribrain_stats_v1.jsonl and 1:1 Telegram dispatch."""
    timestamp: str
    symbol: str
    side: str
    z_score_entry: Optional[float]
    ofi_entry: Optional[float]
    hurst_entry: Optional[float]
    pnl_percentage: float
    pnl_usdt: float
    entry_price: float
    exit_price: float
    qty: float
    motivo: str
    hold_seg: float
    fees_usdt: float
    map_usdt: float
    lvr_usdt: float
    cosecha_triz_50: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 2. DETERMINISTIC DUAL LOGGER AND INODE-VERIFIED PERSISTENT I/O POOL
# ==============================================================================
_ARGV0_RAM: str = str(sys.argv[0]) if sys.argv else ""
_ES_DAEMON_O_SUITE: bool = any(
    _k in _ARGV0_RAM for _k in ("main.py", "test_tribrain", "evaluador_cuantico")
)
_POOL_DESCRIPTORES_LOG: Dict[str, Tuple[TextIO, int]] = {}


def _cerrar_descriptores_log() -> None:
    """Flushes and closes all cached log file descriptors cleanly upon process exit."""
    for key in list(_POOL_DESCRIPTORES_LOG.keys()):
        entry = _POOL_DESCRIPTORES_LOG.pop(key, None)
        if entry is not None:
            fh, _ = entry
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass


atexit.register(_cerrar_descriptores_log)


def _escribir_linea_persistente(ruta: pathlib.Path, linea_con_salto: str) -> None:
    """
    Writes a log or JSONL line using a persistent line-buffered descriptor on
    Linux production (eliminating open/close syscall churn at 25.0 Hz) while
    using immediate context-managed close in test mode or Windows.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or sys.platform == "win32":
        with open(ruta, "a", encoding="utf-8") as f_tmp:
            f_tmp.write(linea_con_salto)
        return

    key = str(ruta)
    entry = _POOL_DESCRIPTORES_LOG.get(key)
    if entry is not None:
        fh, cached_ino = entry
        try:
            st = os.stat(key)
            if st.st_ino == cached_ino and not fh.closed:
                fh.write(linea_con_salto)
                return
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass
        _POOL_DESCRIPTORES_LOG.pop(key, None)

    fh_new = open(ruta, "a", encoding="utf-8", buffering=1)
    ino_new = os.fstat(fh_new.fileno()).st_ino
    _POOL_DESCRIPTORES_LOG[key] = (fh_new, ino_new)
    fh_new.write(linea_con_salto)


def formatear_sello_tiempo(ts: Optional[float] = None) -> str:
    t_val = ts if ts is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_val, tz=_TZ_UTC)
    dt_cl = dt_utc.astimezone(_TZ_CHILE)
    ms = int((t_val - int(t_val)) * 1000.0)
    return f"[{dt_cl.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d} CL | {dt_utc.strftime('%H:%M:%S')} UTC]"


def registrar_evento_baul_ia(evento: Dict[str, Any], ahora: Optional[float] = None) -> bool:
    """
    Persists a high-signal, zero-noise structured record to baul_ia_forense.jsonl
    for mathematical auditing by the AI Cognitive Core.
    """
    if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or not isinstance(evento, dict):
        return False

    t_val = float(ahora) if ahora is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_val, tz=_TZ_UTC)
    record: Dict[str, Any] = {
        "ts_utc": dt_utc.isoformat(timespec="seconds"),
        "sello_dual": formatear_sello_tiempo(t_val),
    }
    record.update(evento)

    try:
        vault_path = cfg.ROOT_DIR / _ARCHIVO_BAUL_IA
        _escribir_linea_persistente(vault_path, json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def log_sniper(mensaje: str, escribir_disco: bool = True) -> Optional[str]:
    if not _ES_DAEMON_O_SUITE and (
        "Whitelist O(1) inicializada" in str(mensaje)
        or "O(1) Whitelist initialized" in str(mensaje)
    ):
        return None

    stamp = formatear_sello_tiempo()
    line = f"{stamp} {mensaje}"
    raw_line = line + "\n"
    sys.stdout.write(raw_line)
    sys.stdout.flush()

    if escribir_disco:
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        try:
            if is_test:
                _escribir_linea_persistente(cfg.ROOT_DIR / ".test_bot_hft.log", raw_line)
            else:
                _escribir_linea_persistente(cfg.ROOT_DIR / cfg.ARCHIVO_LOG_SESION, raw_line)
                _escribir_linea_persistente(cfg.ROOT_DIR / cfg.ARCHIVO_LOG_HISTORICO, raw_line)
        except Exception:
            pass

    return line


log_sniper.info = log_sniper
log_sniper.warning = log_sniper
log_sniper.error = log_sniper
log_sniper.debug = log_sniper


# ==============================================================================
# 3. O(1) IN-MEMORY STATE HASH TABLE (< 1.5 MICROSECONDS)
# ==============================================================================
class EstadoGlobalRAM:
    """Centralized in-memory RAM store with O(1) time complexity."""

    def __init__(self) -> None:
        self.patrimonio_total_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_libre_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_bloqueado_usdt: float = 0.0
        self.high_water_mark_usdt: float = cfg.CAPITAL_BASE_USDT

        self.slot_ocupado: bool = False
        self.orden_en_vuelo_symbol: Optional[str] = None
        self.posiciones_activas: Dict[str, PosicionActiva] = {}

        self.pausa_macro_hasta_ts: float = 0.0
        self.eventos_caida_recientes: Dict[str, float] = {}
        self.ultimo_sl_short_precio: Dict[str, Tuple[float, float]] = {}

        all_symbols = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ticks_ram: Dict[str, MetricaTick] = {
            sym: MetricaTick(symbol=sym) for sym in all_symbols
        }
        self.permisos_ram: Dict[str, PermisoRegimenActivo] = {
            sym: PermisoRegimenActivo(symbol=sym) for sym in cfg.PARES_CAMPEONES_ALFA
        }

        self.pares_excluidos_lote: set[str] = set()
        self.cola_eventos: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1024)

        # O(1) Queue for the +15.0s Counterfactual Oracle in the Forensic AI Vault
        self.auditorias_escudo_pendientes: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.ultimo_ts_auditoria_escudo: Dict[Tuple[str, str], float] = {}

    def consultar_permiso_o1(
        self,
        symbol: str,
        side_solicitado: str = "long",
        z_score_actual: float = 0.0,
        ahora: Optional[float] = None,
    ) -> Tuple[bool, str, float]:
        """
        Sub-microsecond O(1) lookup on the Radar critical path.
        In production (P-07), keeps SHORT-SNIPER enabled during macro contagion pauses.
        """
        t_now = ahora if ahora is not None else time.time()
        side_norm = str(side_solicitado).lower()
        is_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"

        if t_now < self.pausa_macro_hasta_ts:
            if is_test or side_norm != "short":
                return False, "MACRO_CONTAGION_PAUSE", 0.0

        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            return False, "SLOT_BUSY", 0.0

        if symbol in cfg.PARES_VETADOS_OOS or symbol in self.pares_excluidos_lote:
            return False, "PAIR_VETOED_OR_INDIVISIBLE_LOT", 0.0

        perm = self.permisos_ram.get(symbol)
        if perm is None:
            return False, "SYMBOL_NOT_REGISTERED", 0.0

        if t_now < perm.cuarentena_hasta_ts:
            remaining = int(perm.cuarentena_hasta_ts - t_now)
            return False, f"ACTIVE_QUARANTINE_{remaining}S", 0.0

        if not perm.aprobado_groq or perm.modo_regimen == "VETO_TOXIC":
            return False, f"TRICORTEX_VETO_{perm.modo_regimen}", 0.0

        if side_norm == "long":
            if perm.modo_regimen == "SHORT_ONLY":
                return False, "SHORT_ONLY_REGIME_ACTIVE", 0.0
            if perm.modo_regimen == "EXTREME_Z_ONLY" and z_score_actual > -4.50:
                return False, "REQUIRES_EXTREME_Z_4.5", 0.0
        elif side_norm == "short":
            if not cfg.MODO_BIDIRECCIONAL:
                return False, "SHORT_MODE_DISABLED", 0.0
            if perm.modo_regimen == "LONG_ONLY" and z_score_actual < 3.50:
                return False, "LONG_ONLY_REGIME_ACTIVE", 0.0

        return True, "APPROVED_O1", perm.sizing_mult_gemini

    def encolar_auditoria_escudo_15s(
        self,
        symbol: str,
        side: str,
        scar_id: str,
        precio_bloqueo: float,
        tag_percentil: str = "P50_ELASTIC",
        p_dia: float = 0.50,
        detalle: str = "",
        ahora: Optional[float] = None,
    ) -> None:
        """
        Records a pre-order block (SCAR-LOCK-01..18) or TTL cancellation in RAM
        to evaluate exactly 15.0s later whether it prevented a Stop-Loss (True Positive
        Shield) or rejected a winning mean-reversion (False Rejection).
        """
        if os.environ.get("TRIBRAIN_TEST_MODE") == "1" or precio_bloqueo <= 0.0:
            return

        t_now = float(ahora) if ahora is not None else time.time()
        key = (symbol, str(scar_id))
        if (t_now - self.ultimo_ts_auditoria_escudo.get(key, 0.0)) < 15.0:
            return

        self.ultimo_ts_auditoria_escudo[key] = t_now
        tk = self.ticks_ram.get(symbol)
        tk_btc = self.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)

        self.auditorias_escudo_pendientes[key] = {
            "symbol": symbol,
            "side": str(side).lower(),
            "scar_id": str(scar_id),
            "precio_bloqueo": float(precio_bloqueo),
            "ts_bloqueo": t_now,
            "tag_percentil": str(tag_percentil),
            "p_dia": round(float(p_dia), 4),
            "detalle": str(detalle),
            "z_score": round(float(tk.z_score), 3) if tk else 0.0,
            "dp_pct": round(float(tk.delta_p_pct) * 100.0, 3) if tk else 0.0,
            "ema900_pct": round(float(tk.ema900_dist_pct) * 100.0, 3) if tk else 0.0,
            "ema_slope_pct": round(float(tk.ema900_slope_pct) * 100.0, 4) if tk else 0.0,
            "ofi_l1_l5": round(float(tk.ofi_l1_l5), 3) if tk else 0.0,
            "hurst": round(float(tk.hurst), 4) if tk else 0.45,
            "lyap_acel_pct": round(float(tk.lyapunov_acel_pct) * 100.0, 4) if tk else 0.0,
            "hawkes": round(float(tk.hawkes_intensidad), 3) if tk else 0.0,
            "vpin": round(float(tk.vpin), 3) if tk else 0.0,
            "z_btc": round(float(tk_btc.z_score), 3) if tk_btc else 0.0,
            "ofi_btc": round(float(tk_btc.ofi_l1_l5), 3) if tk_btc else 0.0,
        }

    def evaluar_auditorias_escudo_vencidas(
        self,
        symbol: str,
        precio_actual: float,
        ahora: Optional[float] = None,
    ) -> int:
        """
        Checks in O(1) whether any queued shield audit for `symbol` has reached >= 15.0s
        and writes the counterfactual verdict to baul_ia_forense.jsonl.
        """
        if (
            os.environ.get("TRIBRAIN_TEST_MODE") == "1"
            or not self.auditorias_escudo_pendientes
            or precio_actual <= 0.0
        ):
            return 0

        t_now = float(ahora) if ahora is not None else time.time()
        processed = 0

        for key in list(self.auditorias_escudo_pendientes.keys()):
            if key[0] != symbol:
                continue
            item = self.auditorias_escudo_pendientes.get(key)
            if item is None:
                continue
            dt_sec = t_now - float(item["ts_bloqueo"])
            if dt_sec < 15.0:
                continue

            self.auditorias_escudo_pendientes.pop(key, None)
            p_block = float(item["precio_bloqueo"])
            side = str(item["side"])
            ret_15s = (
                ((precio_actual - p_block) / p_block)
                if side == "long"
                else ((p_block - precio_actual) / p_block)
            )
            ref_notional = 25.0 if symbol in cfg.CLASE_TIER1_LIQUIDO else cfg.NOCIONAL_MAX_HIGH_BETA_USDT

            if ret_15s <= -0.0015:
                verdict = "CAPITAL_SAVED_TRUE_SHIELD"
                impact_usdt = round(abs(ret_15s) * ref_notional, 4)
            elif ret_15s >= 0.0024:
                verdict = "MISSED_OPPORTUNITY_FALSE_REJECTION"
                impact_usdt = -round(max(0.0, ret_15s - 0.0004) * ref_notional, 4)
            else:
                verdict = "NEUTRAL_LATERAL_NOISE"
                impact_usdt = 0.0

            vault_event = {
                "tipo_evento": "AUDITORIA_ESCUDO_15S",
                "veredicto_ia": verdict,
                "scar_id": item["scar_id"],
                "symbol": symbol,
                "side": side,
                "tag_percentil": item["tag_percentil"],
                "p_dia": item["p_dia"],
                "precio_bloqueo": p_block,
                "precio_15s_despues": round(float(precio_actual), 8),
                "excursion_15s_pct": round(ret_15s * 100.0, 4),
                "impacto_estimado_usdt": impact_usdt,
                "dt_evaluacion_seg": round(dt_sec, 2),
                "detalle_filtro": item["detalle"],
                "vector_x": {
                    "z": item["z_score"],
                    "dp_pct": item["dp_pct"],
                    "ema900_pct": item["ema900_pct"],
                    "ema_slope_pct": item["ema_slope_pct"],
                    "ofi": item["ofi_l1_l5"],
                    "hurst": item["hurst"],
                    "lyap_pct": item["lyap_acel_pct"],
                    "hawkes": item["hawkes"],
                    "vpin": item["vpin"],
                    "z_btc": item["z_btc"],
                    "ofi_btc": item["ofi_btc"],
                },
            }
            registrar_evento_baul_ia(vault_event, ahora=t_now)
            processed += 1

        return processed

    def aplicar_cuarentena(self, symbol: str, duracion_seg: float, motivo: str) -> None:
        perm = self.permisos_ram.get(symbol)
        if perm is None:
            perm = PermisoRegimenActivo(symbol=symbol)
            self.permisos_ram[symbol] = perm
        new_end = time.time() + max(0.0, float(duracion_seg))
        if new_end > perm.cuarentena_hasta_ts:
            perm.cuarentena_hasta_ts = new_end
            perm.motivo = motivo

    def reservar_margen_atomico(self, symbol: str, margen_usdt: float) -> bool:
        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            return False
        req_margin = float(margen_usdt)
        if req_margin < cfg.MARGEN_MINIMO_OPERACION_USDT or req_margin > self.margen_libre_usdt:
            return False
        self.slot_ocupado = True
        self.orden_en_vuelo_symbol = symbol
        self.margen_libre_usdt = max(0.0, self.margen_libre_usdt - req_margin)
        self.margen_bloqueado_usdt += req_margin
        return True

    def liberar_margen_atomico(self, symbol: str, margen_usdt: float = 0.0) -> None:
        if self.orden_en_vuelo_symbol == symbol:
            self.orden_en_vuelo_symbol = None
        self.posiciones_activas.pop(symbol, None)
        if not self.posiciones_activas and self.orden_en_vuelo_symbol is None:
            self.slot_ocupado = False
            self.margen_bloqueado_usdt = 0.0
            self.margen_libre_usdt = self.patrimonio_total_usdt
        elif margen_usdt > 0.0:
            self.margen_bloqueado_usdt = max(0.0, self.margen_bloqueado_usdt - float(margen_usdt))
            self.margen_libre_usdt = max(0.0, self.patrimonio_total_usdt - self.margen_bloqueado_usdt)

    def sincronizar_balance_uta(self, total_usdt: float, libre_usdt: float) -> None:
        if total_usdt > 0.0:
            self.patrimonio_total_usdt = float(total_usdt)
            if total_usdt > self.high_water_mark_usdt:
                self.high_water_mark_usdt = float(total_usdt)
        if not self.slot_ocupado and not self.posiciones_activas:
            self.margen_libre_usdt = float(libre_usdt if libre_usdt > 0.0 else total_usdt)
            self.margen_bloqueado_usdt = max(0.0, self.patrimonio_total_usdt - self.margen_libre_usdt)

    def calcular_drawdown_actual_pct(self) -> float:
        if self.high_water_mark_usdt <= 0.0:
            return 0.0
        dd = (self.high_water_mark_usdt - self.patrimonio_total_usdt) / self.high_water_mark_usdt
        return max(0.0, dd)


ESTADO_RAM: EstadoGlobalRAM = EstadoGlobalRAM()