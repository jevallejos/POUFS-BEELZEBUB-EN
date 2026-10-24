#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
STATIC AUDIT AND SANITIZATION TOOL: tools/validate_pool.py
SYSTEM: POUFS-BEELZEBUB-EN (SPIRITUAL MESSAGE) V5.0 -- GATE 0
==============================================================================
Deterministically audits and sanitizes all repository files:
  a) Strict UTF-8 encoding without BOM (Byte Order Mark \xef\xbb\xbf).
  b) Exclusive Unix line endings (LF \n), fixing or rejecting CRLF.
  c) Total absence of unescaped icons, emojis, invisible spaces (\u00A0, \u200B),
     typographic smart quotes, or corrupted Mojibake sequences.
  d) Static AST syntax validation and compilation for Python modules (including
     the 100 unique top-level constants contract in config_parametros.py).
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
    fixes: List[str] = []
    if "\r\n" in texto or "\r" in texto:
        texto = texto.replace("\r\n", "\n").replace("\r", "\n")
        fixes.append("CRLF->LF")

    for dirty, clean in MAPA_REEMPLAZO_LIMPIO.items():
        if dirty in texto:
            texto = texto.replace(dirty, clean)
            fixes.append("CORRUPTED_TOKEN_REPLACED")

    chars_out: List[str] = []
    removed = 0
    for ch in texto:
        if _es_caracter_permitido(ch):
            chars_out.append(ch)
        else:
            removed += 1

    if removed > 0:
        fixes.append(f"EMOJI_OR_ICON_REMOVED({removed})")

    final_text = "".join(chars_out)
    return final_text, fixes


def validar_archivo(ruta: pathlib.Path, modo_sanitize: bool) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    if not ruta.exists():
        return False, ["FILE_NOT_FOUND"]

    raw = ruta.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
        messages.append("BOM_DETECTED")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        if not modo_sanitize:
            return False, [f"INVALID_UTF8: {exc}"]
        text = raw.decode("utf-8", errors="ignore")
        messages.append("UTF8_REPAIRED")

    clean_text, changes = sanitizar_texto(text)
    messages.extend(changes)

    if modo_sanitize and (had_bom or changes):
        ruta.write_bytes(clean_text.encode("utf-8"))
        messages = [f"SANITIZED({','.join(messages)})"]
    elif not modo_sanitize and (had_bom or changes):
        return False, messages

    if ruta.suffix == ".py":
        try:
            tree = ast.parse(clean_text, filename=ruta.name)
            compile(tree, filename=ruta.name, mode="exec")
        except SyntaxError as exc:
            return False, [f"AST_SYNTAX_ERROR(line {exc.lineno}: {exc.msg})"]

        if ruta.name == "config_parametros.py":
            assignments = [
                (n.targets[0].id if isinstance(n, ast.Assign) else n.target.id)
                for n in tree.body
                if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id.isupper())
                or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id.isupper())
            ]
            duplicates = [k for k in set(assignments) if assignments.count(k) > 1]
            if duplicates:
                return False, [f"DUPLICATE_CONSTANTS({duplicates})"]
            if len(assignments) != 100:
                return False, [f"AST_100_CONTRACT_VIOLATED(found={len(assignments)})"]
            messages.append("AST_100_CONSTANTES_OK")
        else:
            messages.append("AST_OK")

    elif ruta.suffix == ".json":
        try:
            json.loads(clean_text)
            messages.append("JSON_OK")
        except Exception as exc:
            return False, [f"INVALID_JSON({exc})"]

    elif ruta.suffix == ".sh":
        if "\r" in clean_text:
            return False, ["SH_CONTAINS_CR"]
        messages.append("SH_LF_OK")

    return True, messages or ["CLEAN_UTF8_LF"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gate 0 Pool Validator & Sanitizer for POUFS-BEELZEBUB-EN (Spiritual Message) V5.0"
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Automatically sanitize BOM, CRLF, unescaped emojis, and corrupted tokens.",
    )
    args = parser.parse_args()

    print("==========================================================================================")
    print(" [GATE 0] STATIC UTF-8 / LF / AST INTEGRITY AUDIT -- POUFS-BEELZEBUB-EN V5.0")
    print("==========================================================================================")

    total_errors = 0
    targets = list(ARCHIVOS_CANONICOS)
    if (ROOT_DIR / "calibracion_oos.json").exists() and "calibracion_oos.json" not in targets:
        targets.append("calibracion_oos.json")

    for rel_path in targets:
        file_path = ROOT_DIR / rel_path
        ok, details = validar_archivo(file_path, modo_sanitize=bool(args.sanitize))
        status_str = "[OK]" if ok else "[ERROR]"
        if not ok:
            total_errors += 1
        print(f" {status_str:<8} {rel_path:<32} -> {', '.join(details)}")

    print("==========================================================================================")
    if total_errors == 0:
        print(" FINAL RESULT: 0 ERRORS DETECTED | POOL 100% CERTIFIED (UTF-8 NO BOM / LF / AST)")
        print("==========================================================================================")
        return 0

    print(f" FINAL RESULT: {total_errors} FILE(S) WITH VALIDATION ERRORS")
    print("==========================================================================================")
    return 1


if __name__ == "__main__":
    sys.exit(main())