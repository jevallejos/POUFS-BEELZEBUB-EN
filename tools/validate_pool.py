#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
HERRAMIENTA DE AUDITORIA Y SANITIZACION ESTATICA: tools/validate_pool.py
SISTEMA: TRI-BRAIN-PHANTOM (GOD'S ACCOMPLICE) V1.0 -- COMPUERTA 0
==============================================================================
Audita y sanitiza deterministicamente todos los archivos del repositorio:
  a) Codificacion estricta UTF-8 sin BOM (Byte Order Mark \xef\xbb\xbf).
  b) Saltos de linea exclusivos Unix (LF \n), corrigiendo o rechazando CRLF.
  c) Ausencia total de iconos, emojis, espacios invisibles (\u00A0, \u200B),
     comillas curvas tipograficas o secuencias Mojibake corruptas.
  d) Validacion de sintaxis y compilacion estatica AST para Python (incluyendo
     el contrato de 100 constantes unicas en config_parametros.py).
==============================================================================
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Dict, List, Tuple

ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent

ARCHIVOS_CANONICOS: Tuple[str, ...] = (
    ".gitignore",
    "README.md",
    "requirements.txt",
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
    "instalar_infraestructura.sh",
    "test_tribrain_v1_suite.py",
    "tools/validate_pool.py",
)

MAPA_REEMPLAZO_LIMPIO: Dict[str, str] = {
    "\u00a0": " ",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "--",
    "\u2192": "->",
    "\u2194": "<->",
    "\ufffd": "",
    "\u00f0\u0178\u2019\u017e": "[DIAMOND]",
    "\u00f0\u0178\u203a\u00a1\u00ef\u00b8\u008f": "[SHIELD]",
    "\u00f0\u0178\u017d\u00af": "[TARGET]",
    "\u00f0\u0178\u0178\u00a2": "[ONLINE]",
    "\u00f0\u0178\u0178\u00a5": "[LOSS]",
    "\u00f0\u0178\u0178\u00a8": "[SCRATCH]",
    "\u00f0\u0178\u0178\u00a9": "[WIN]",
    "\u00e2\u0161\u00a0\u00ef\u00b8\u008f": "[WARN]",
    "\u00e2\u0153\u2026": "[OK]",
    "\u00e2\u009d\u0152": "[ERROR]",
}


def _es_caracter_permitido(ch: str) -> bool:
    code = ord(ch)
    if ch in ("\n", "\t"):
        return True
    if 32 <= code <= 126:
        return True
    if 0x00A1 <= code <= 0x00FF:
        return True
    if code in (
        0x03BB,
        0x03BC,
        0x03C3,
        0x03C4,
        0x2022,
        0x2500,
        0x2502,
        0x2550,
        0x2551,
        0x2554,
        0x2557,
        0x255A,
        0x255D,
    ):
        return True
    return False


def sanitizar_texto(texto: str) -> Tuple[str, List[str]]:
    correcciones: List[str] = []
    if "\r\n" in texto or "\r" in texto:
        texto = texto.replace("\r\n", "\n").replace("\r", "\n")
        correcciones.append("CRLF->LF")

    for sucio, limpio in MAPA_REEMPLAZO_LIMPIO.items():
        if sucio in texto:
            texto = texto.replace(sucio, limpio)
            correcciones.append("TOKEN_CORRUPTO_REEMPLAZADO")

    chars_out: List[str] = []
    removidos = 0
    for ch in texto:
        if _es_caracter_permitido(ch):
            chars_out.append(ch)
        else:
            removidos += 1

    if removidos > 0:
        correcciones.append(f"EMOJI_O_ICONO_REMOVIDO({removidos})")

    texto_final = "".join(chars_out)
    return texto_final, correcciones


def validar_archivo(ruta: pathlib.Path, modo_sanitize: bool) -> Tuple[bool, List[str]]:
    mensajes: List[str] = []
    if not ruta.exists():
        return False, ["ARCHIVO_NO_EXISTE"]

    raw = ruta.read_bytes()
    tenia_bom = raw.startswith(b"\xef\xbb\xbf")
    if tenia_bom:
        raw = raw[3:]
        mensajes.append("BOM_DETECTADO")

    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        if not modo_sanitize:
            return False, [f"UTF8_INVALIDO: {exc}"]
        texto = raw.decode("utf-8", errors="ignore")
        mensajes.append("UTF8_REPARADO")

    texto_limpio, cambios = sanitizar_texto(texto)
    mensajes.extend(cambios)

    if modo_sanitize and (tenia_bom or cambios):
        ruta.write_bytes(texto_limpio.encode("utf-8"))
        mensajes = [f"SANITIZADO({','.join(mensajes)})"]
    elif not modo_sanitize and (tenia_bom or cambios):
        return False, mensajes

    if ruta.suffix == ".py":
        try:
            tree = ast.parse(texto_limpio, filename=ruta.name)
            compile(tree, filename=ruta.name, mode="exec")
        except SyntaxError as exc:
            return False, [f"AST_SYNTAX_ERROR(linea {exc.lineno}: {exc.msg})"]

        if ruta.name == "config_parametros.py":
            asignaciones = [
                (n.targets[0].id if isinstance(n, ast.Assign) else n.target.id)
                for n in tree.body
                if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper())
                or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id.isupper())
            ]
            duplicadas = [k for k in set(asignaciones) if asignaciones.count(k) > 1]
            if duplicadas:
                return False, [f"CONSTANTES_DUPLICADAS({duplicadas})"]
            if len(asignaciones) != 100:
                return False, [f"CONTRATO_AST_100_VIOLADO(encontradas={len(asignaciones)})"]
            mensajes.append("AST_100_CONSTANTES_OK")
        else:
            mensajes.append("AST_OK")

    elif ruta.suffix == ".json":
        try:
            json.loads(texto_limpio)
            mensajes.append("JSON_OK")
        except Exception as exc:
            return False, [f"JSON_INVALIDO({exc})"]

    elif ruta.suffix == ".sh":
        if "\r" in texto_limpio:
            return False, ["SH_CONTIENE_CR"]
        mensajes.append("SH_LF_OK")

    return True, mensajes or ["LIMPIO_UTF8_LF"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validador y Sanitizador del Pool TRI-BRAIN-PHANTOM V1.0")
    parser.add_argument("--sanitize", action="store_true", help="Sanitiza automaticamente BOM, CRLF, emojis y caracteres corruptos.")
    args = parser.parse_args()

    print("==========================================================================================")
    print(" [COMPUERTA 0] AUDITORIA ESTATICA DE INTEGRIDAD UTF-8 / LF / AST -- TRI-BRAIN-PHANTOM V1.0")
    print("==========================================================================================")

    errores_totales = 0
    objetivos = list(ARCHIVOS_CANONICOS)
    if (ROOT_DIR / "calibracion_oos.json").exists() and "calibracion_oos.json" not in objetivos:
        objetivos.append("calibracion_oos.json")

    for rel_path in objetivos:
        ruta_f = ROOT_DIR / rel_path
        ok, detalles = validar_archivo(ruta_f, modo_sanitize=bool(args.sanitize))
        estado_str = "[OK]" if ok else "[ERROR]"
        if not ok:
            errores_totales += 1
        print(f" {estado_str:<8} {rel_path:<32} -> {', '.join(detalles)}")

    print("==========================================================================================")
    if errores_totales == 0:
        print(" RESULTADO FINAL: 0 ERRORES DETECTADOS | POOL 100% CERTIFICADO (UTF-8 SIN BOM / LF / AST)")
        print("==========================================================================================")
        return 0

    print(f" RESULTADO FINAL: {errores_totales} ARCHIVO(S) CON ERRORES DE VALIDACION")
    print("==========================================================================================")
    return 1


if __name__ == "__main__":
    sys.exit(main())