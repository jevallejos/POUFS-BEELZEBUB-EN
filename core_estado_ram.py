#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #04: core_estado_ram.py
SISTEMA: TRI-BRAIN-SNIPER (EMPEROR TIME) V1.0 — ESTRATEGIA CHRONOS-TRIZ
==============================================================================
Nucleo de Memoria Compartida O(1), Contratos @dataclass y Logger Dual (CL/UTC).
Erradica al 100% el uso de builtins.print hooks y expresiones regulares
para comunicar modulos internos.
==============================================================================
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import config_parametros as cfg

# Zona horaria canonica de Chile Continental (UTC-3) y UTC
_TZ_UTC = timezone.utc
_TZ_CHILE = timezone(timedelta(hours=-3))


# ==============================================================================
# 1. CONTRATOS DE DATOS ESTRICTOS (@DATACLASS) CON ALIAS DE SEGURIDAD
# ==============================================================================
@dataclass(slots=True)
class MetricaTick:
    """Fotografia microestructural instantanea O(1) de un activo en el Radar 6.6 Hz."""
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
    """Vector de gobernanza asignado por el Enjambre Tri-Cortex en memoria RAM."""
    symbol: str
    modo_regimen: str = "LONG_ONLY"         # LONG_ONLY | SHORT_ONLY | EXTREME_Z_ONLY | VETO_TOXIC
    aprobado_groq: bool = True
    sizing_mult_gemini: float = 1.0         # Multiplicador anti-fragil [0.70 .. 1.15]
    caida_min_override_pct: float = 0.0     # Ajuste pre-vuelo de NVIDIA NIM
    cuarentena_hasta_ts: float = 0.0        # Timestamp de fin de cuarentena post-loss o post-pump
    motivo: str = "INIT_DEFAULT"
    ts_actualizacion: float = field(default_factory=time.time)


@dataclass
class PosicionActiva:
    """
    Estado en memoria RAM de una posicion abierta en Bybit UTA.
    Soporta nativamente las Leyes 2 y 3 de CHRONOS-TRIZ:
      - Evaluacion Maker-Scratch a los 18s (Avellaneda-Stoikov).
      - Cosecha Fraccionada 50/50 TRIZ (+0.26%) + Trinquete Continuo Maker.
    """
    symbol: str
    side: str                               # "long" | "short"
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

    # Estado CHRONOS-TRIZ (Ley 2: Scratch 18s | Ley 3: Cosecha 50/50 + Trinquete)
    scratch_18s_evaluado: bool = False
    scratch_18s_activo: bool = False
    cosecha_50_ejecutada: bool = False
    pnl_realizado_parcial_usdt: float = 0.0
    fees_acumulados_usdt: float = 0.0
    max_pnl_pct_alcanzado: float = 0.0
    trinquete_be_armado: bool = False
    trinquete_ratchet_activo: bool = False
    trailing_activo: bool = False

    # Control de orden Limit PostOnly de salida en vuelo (PFQI)
    orden_salida_id: Optional[str] = None
    orden_salida_precio: float = 0.0
    orden_salida_qty: float = 0.0
    orden_salida_ts: float = 0.0
    orden_salida_tipo: str = ""             # "COSECHA_50" | "RATCHET" | "SCRATCH_18S" | "ESCUDO_FASE2"

    # Cerrojo atomico anti-doble-contabilizacion
    cerrada: bool = False

    # Propiedades alias para compatibilidad total entre modulos (0 riesgo de AttributeError)
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


@dataclass(slots=True)
class RegistroOperacionCerrada:
    """Registro inmutable para persistencia en tribrain_stats_v1.jsonl y despacho 1:1 a Telegram."""
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
# 2. TABLA HASH DE ESTADO EN MEMORIA RAM O(1) (< 1.0 MICROSEGUNDO)
# ==============================================================================
class EstadoGlobalRAM:
    """
    Almacen centralizado en memoria RAM con complejidad O(1).
    Coordina Radar, Escudo Tri-Cortex, Ejecutor Sniper, Gestor de Posiciones y Telemetria.
    """

    def __init__(self) -> None:
        self.patrimonio_total_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_libre_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_bloqueado_usdt: float = 0.0
        self.high_water_mark_usdt: float = cfg.CAPITAL_BASE_USDT

        # Cerrojo de posicion unica (Single-Slot Mutex)
        self.slot_ocupado: bool = False
        self.orden_en_vuelo_symbol: Optional[str] = None
        self.posiciones_activas: Dict[str, PosicionActiva] = {}

        # Cortafuegos macro de contagio sistemico
        self.pausa_macro_hasta_ts: float = 0.0
        self.eventos_caida_recientes: Dict[str, float] = {}

        # Tablas hash pre-alojadas O(1) para los 7 Campeones + Centinela BTC
        todos_simbolos = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ticks_ram: Dict[str, MetricaTick] = {
            sym: MetricaTick(symbol=sym) for sym in todos_simbolos
        }
        self.permisos_ram: Dict[str, PermisoRegimenActivo] = {
            sym: PermisoRegimenActivo(symbol=sym) for sym in cfg.PARES_CAMPEONES_ALFA
        }

        # Pares excluidos dinamicamente por filtro de lote minimo indivisible
        self.pares_excluidos_lote: set[str] = set()

        # Cola asincrona de eventos para desacoplar modulos sin tocar print()
        self.cola_eventos: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1024)

    def consultar_permiso_o1(
        self,
        symbol: str,
        side_solicitado: str,
        z_score_actual: float,
        ahora: float,
    ) -> Tuple[bool, str, float]:
        """
        Lookup O(1) sub-microsegundo en la ruta critica del Radar.
        Retorna: (permitido: bool, motivo: str, sizing_mult: float)
        """
        if ahora < self.pausa_macro_hasta_ts:
            return False, "PAUSA_CONTAGIO_MACRO", 0.0

        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            return False, "SLOT_OCUPADO", 0.0

        if symbol in cfg.PARES_VETADOS_OOS or symbol in self.pares_excluidos_lote:
            return False, "PAR_VETADO_O_LOTE_INDIVISIBLE", 0.0

        perm = self.permisos_ram.get(symbol)
        if perm is None:
            return False, "SIMBOLO_NO_REGISTRADO", 0.0

        if ahora < perm.cuarentena_hasta_ts:
            restante = int(perm.cuarentena_hasta_ts - ahora)
            return False, f"CUARENTENA_ACTIVA_{restante}S", 0.0

        if not perm.aprobado_groq or perm.modo_regimen == "VETO_TOXIC":
            return False, f"VETO_TRICORTEX_{perm.modo_regimen}", 0.0

        side_norm = side_solicitado.lower()
        if side_norm == "long":
            if perm.modo_regimen == "SHORT_ONLY":
                return False, "REGIMEN_SHORT_ONLY_ACTIVO", 0.0
            if perm.modo_regimen == "EXTREME_Z_ONLY" and z_score_actual > -4.50:
                return False, "EXIGE_EXTREME_Z_4.5", 0.0
        elif side_norm == "short":
            if not cfg.MODO_BIDIRECCIONAL:
                return False, "MODO_SHORT_DESACTIVADO", 0.0
            if perm.modo_regimen == "LONG_ONLY" and z_score_actual < 3.50:
                return False, "REGIMEN_LONG_ONLY_ACTIVO", 0.0

        return True, "APROBADO_O1", perm.sizing_mult_gemini

    def aplicar_cuarentena(self, symbol: str, duracion_seg: float, motivo: str) -> None:
        """Aplica cuarentena temporal O(1) en RAM sobre un activo."""
        perm = self.permisos_ram.get(symbol)
        if perm is None:
            perm = PermisoRegimenActivo(symbol=symbol)
            self.permisos_ram[symbol] = perm
        nuevo_fin = time.time() + max(0.0, float(duracion_seg))
        if nuevo_fin > perm.cuarentena_hasta_ts:
            perm.cuarentena_hasta_ts = nuevo_fin
            perm.motivo = motivo

    def reservar_margen_atomico(self, symbol: str, margen_usdt: float) -> bool:
        """Deduce margen en RAM en O(1) y bloquea el Single-Slot Mutex antes de create_order."""
        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            return False
        margen_req = float(margen_usdt)
        if margen_req < cfg.MARGEN_MINIMO_OPERACION_USDT or margen_req > self.margen_libre_usdt:
            return False
        self.slot_ocupado = True
        self.orden_en_vuelo_symbol = symbol
        self.margen_libre_usdt = max(0.0, self.margen_libre_usdt - margen_req)
        self.margen_bloqueado_usdt += margen_req
        return True

    def liberar_margen_atomico(self, symbol: str, margen_usdt: float = 0.0) -> None:
        """Libera el Single-Slot Mutex y restituye el margen en RAM tras cancelacion o cierre."""
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
        """Actualiza el patrimonio real de Bybit UTA y el High-Water Mark en RAM."""
        if total_usdt > 0.0:
            self.patrimonio_total_usdt = float(total_usdt)
            if total_usdt > self.high_water_mark_usdt:
                self.high_water_mark_usdt = float(total_usdt)
        if not self.slot_ocupado and not self.posiciones_activas:
            self.margen_libre_usdt = float(libre_usdt if libre_usdt > 0.0 else total_usdt)
            self.margen_bloqueado_usdt = max(0.0, self.patrimonio_total_usdt - self.margen_libre_usdt)

    def calcular_drawdown_actual_pct(self) -> float:
        """Retorna el drawdown porcentual respecto al High-Water Mark [0.0 .. 1.0]."""
        if self.high_water_mark_usdt <= 0.0:
            return 0.0
        dd = (self.high_water_mark_usdt - self.patrimonio_total_usdt) / self.high_water_mark_usdt
        return max(0.0, dd)


# Instancia Singleton global en memoria RAM
ESTADO_RAM: EstadoGlobalRAM = EstadoGlobalRAM()


# ==============================================================================
# 3. LOGGER DUAL DETERMINISTA (CHILE CONTINENTAL / UTC)
# ==============================================================================
def formatear_sello_tiempo(ts: Optional[float] = None) -> str:
    """Genera el sello [YYYY-MM-DD HH:MM:SS.mmm CL | HH:MM:SS UTC]."""
    t_val = ts if ts is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_val, tz=_TZ_UTC)
    dt_cl = dt_utc.astimezone(_TZ_CHILE)
    ms = int((t_val - int(t_val)) * 1000.0)
    return f"[{dt_cl.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d} CL | {dt_utc.strftime('%H:%M:%S')} UTC]"


def log_sniper(mensaje: str, escribir_disco: bool = True) -> str:
    """
    Imprime en consola con sello dual (CL | UTC) y persiste en bot_hft.log y bot_hft_h.log.
    Si TRIBRAIN_TEST_MODE == '1', aisla la escritura en .test_bot_hft.log sin tocar bot_hft_h.log.
    """
    sello = formatear_sello_tiempo()
    linea = f"{sello} {mensaje}"
    sys.stdout.write(linea + "\n")
    sys.stdout.flush()

    if escribir_disco:
        es_test = os.environ.get("TRIBRAIN_TEST_MODE") == "1"
        try:
            if es_test:
                ruta_test = cfg.ROOT_DIR / ".test_bot_hft.log"
                with open(ruta_test, "a", encoding="utf-8") as f_test:
                    f_test.write(linea + "\n")
            else:
                ruta_sesion = cfg.ROOT_DIR / cfg.ARCHIVO_LOG_SESION
                ruta_hist = cfg.ROOT_DIR / cfg.ARCHIVO_LOG_HISTORICO
                with open(ruta_sesion, "a", encoding="utf-8") as f_ses:
                    f_ses.write(linea + "\n")
                with open(ruta_hist, "a", encoding="utf-8") as f_hist:
                    f_hist.write(linea + "\n")
        except Exception:
            pass

    return linea