#!/usr/bin/env bash
# ==============================================================================
# ARCHIVO #13: instalar_infraestructura.sh
# SISTEMA: TRI-BRAIN-SNIPER (EMPEROR TIME) V1.0 — ESTRATEGIA CHRONOS-TRIZ
# ==============================================================================
# Instalador idempotente para Ubuntu/Debian (sniper-tokio):
#   1. Configura git config core.fileMode false para mantener git status limpio.
#   2. Instala tribrain-eval-oos.service con aislamiento de CPU/IO (Nice=15,
#      IOSchedulingClass=best-effort, IOSchedulingPriority=7).
#   3. Instala y activa tribrain-eval-oos.timer (00:00, 08:00 y 16:00 UTC).
#   4. Instala los comandos blindados 'verbot' (-s, -h, -h trades, -q, -t) y
#      'tmuxro' en ~/.bashrc usando bloques heredoc << 'PYEOF' (cero colision
#      de comillas en Bash y cero SyntaxWarning en Python 3.14).
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BIN="${REPO_DIR}/venv/bin/python"
SERVICE_NAME="tribrain-eval-oos"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
USER_NAME="$(whoami)"

echo "=================================================================="
echo "⚙️  INSTALANDO INFRAESTRUCTURA TRI-BRAIN-SNIPER V2.0 [CHAIN-JAIL]"
echo "   Repositorio : ${REPO_DIR}"
echo "   Python VENV : ${PY_BIN}"
echo "=================================================================="

if [ ! -x "${PY_BIN}" ]; then
    echo "❌ [ERROR] No se encontro el ejecutable Python en ${PY_BIN}"
    exit 1
fi

# 1. Evitar que chmod +x ensucie git status -s
git -C "${REPO_DIR}" config core.fileMode false || true
chmod +x "${REPO_DIR}/instalar_infraestructura.sh" "${REPO_DIR}/main.py" "${REPO_DIR}/evaluador_cuantico_oos.py" 2>/dev/null || true

# 2. Crear unidad systemd con aislamiento estricto de CPU e I/O (Low-Jitter Ops)
sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Evaluador Cuantico Walk-Forward OOS Tri-Brain-Sniper (Chain-Jail) v2.0
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${USER_NAME}
WorkingDirectory=${REPO_DIR}
Environment="PYTHONUTF8=1"
Nice=15
IOSchedulingClass=best-effort
IOSchedulingPriority=7
ExecStart=${PY_BIN} ${REPO_DIR}/evaluador_cuantico_oos.py --repo ${REPO_DIR} --horas 8 --telegram
StandardOutput=append:${REPO_DIR}/bot_hft_h.log
StandardError=append:${REPO_DIR}/bot_hft_h.log
EOF

# 3. Crear timer systemd alineado con los 3 cortes globales de financiacion (00:00, 08:00, 16:00 UTC)
sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Timer Tri-Sesion (00:00, 08:00, 16:00 UTC) para Tri-Brain-Sniper (Chain-Jail) v2.0

[Timer]
OnCalendar=*-*-* 00,08,16:00:00 UTC
Persistent=true
RandomizedDelaySec=25
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.timer"
sudo systemctl restart "${SERVICE_NAME}.timer"

echo "✅ [SYSTEMD OK] Timer ${SERVICE_NAME}.timer habilitado y activo:"
systemctl list-timers "${SERVICE_NAME}.timer" --no-pager || true

# 4. Instalar panel CLI 'verbot' y 'tmuxro' en ~/.bashrc usando raw string y heredoc PYEOF
python3 - "${REPO_DIR}" << 'PYINSTALL'
import pathlib, re, sys

repo_dir = sys.argv[1]
rc_path = pathlib.Path.home() / ".bashrc"
txt = rc_path.read_text(encoding="utf-8", errors="ignore") if rc_path.exists() else ""

txt = re.sub(
    r"# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===.*?# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===\n?",
    "",
    txt,
    flags=re.DOTALL,
)

plantilla_raw = r"""# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===
# Desactivar errexit (set -e) en la consola interactiva SSH para evitar cierres de sesion
set +e 2>/dev/null || true

tmuxro() {
    set +e
    echo "🔒 Entrando a tmux en MODO SOLO LECTURA (-r). Para salir sin apagar el bot presiona: Ctrl+B y luego d"
    sleep 1
    command tmux attach -t demonio_hft -r || true
    return 0
}

verbot() {
    set +e
    local REPO="__REPO_DIR__"
    local PY="${REPO}/venv/bin/python"
    local LOCK="${REPO}/.tribrain.lock"
    local LOG="${REPO}/bot_hft.log"
    local LOG_H="${REPO}/bot_hft_h.log"
    local MODO="${1:-live}"
    local SUBMODO="${2:-all}"

    echo "================================================================================"
    echo " 👁️  PANEL FORENSE EN TIEMPO REAL — TRI-BRAIN-SNIPER V2.0 [CHAIN-JAIL]"
    echo "================================================================================"

    if [ -f "${LOCK}" ]; then
        local PID
        PID=$(cat "${LOCK}" 2>/dev/null | tr -d '[:space:]' || true)
        if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
            local PS_INFO
            PS_INFO=$(ps -p "${PID}" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}' || true)
            echo " 🟢 MOTOR EN VIVO -> ${PS_INFO}"
        else
            echo " 🔴 ALERTA: Archivo .tribrain.lock presente (PID ${PID}), pero el proceso no responde."
        fi
    else
        echo " ⚪ MOTOR DETENIDO: No existe archivo .tribrain.lock activo."
    fi

    case "${MODO}" in
        -s|--status)
            "${PY}" - "${REPO}" << 'PYEOF' || true
import json, pathlib, sys
repo = pathlib.Path(sys.argv[1])
stats_f = repo / "tribrain_stats_v1.jsonl"
ops = [json.loads(l) for l in stats_f.read_text(encoding="utf-8").splitlines() if l.strip()] if stats_f.exists() else []
ops = [x for x in ops if "ESCAPE_HUERFANA_BOOT" not in str(x.get("motivo", "")).upper()]
w = sum(1 for x in ops if float(x.get("pnl_usdt", 0)) >= 0)
l = len(ops) - w
s = sum(1 for x in ops if "SCRATCH" in str(x.get("motivo", "")).upper() and float(x.get("pnl_usdt", 0)) < 0)
triz = sum(1 for x in ops if x.get("cosecha_triz_50"))
pnl = sum(float(x.get("pnl_usdt", 0)) for x in ops)
wr = (w / len(ops) * 100.0) if ops else 0.0
wr_ef = (w / max(1, len(ops) - s) * 100.0) if ops else 0.0
print("--------------------------------------------------------------------------------")
print(f" 📊 CAJA NEGRA: {len(ops)} Trades (W: {w} | L: {l} | Scratch 18s: {s} | Cosecha 50%: {triz})")
print(f" 🎯 Win Rate  : Clasico {wr:.1f}% | Efectivo (sin Scratch) {wr_ef:.1f}% | PnL Neto: {pnl:+.4f} USDT")
print("--------------------------------------------------------------------------------")
if ops:
    for op in ops[-10:]:
        ic = "🟩" if float(op.get("pnl_usdt", 0)) >= 0 else ("🟨" if "SCRATCH" in str(op.get("motivo", "")).upper() else "🔴")
        ts = str(op.get("timestamp", ""))[:19]
        sym = str(op.get("symbol", ""))
        pct = float(op.get("pnl_percentage", 0))
        pu = float(op.get("pnl_usdt", 0))
        mot = str(op.get("motivo", ""))
        print(f"  {ic} {ts} | {sym:<17} | {pct:+6.2f}% ({pu:+.4f} USDT) | {mot}")
else:
    print("  ⏳ Esperando el primer disparo confirmado bajo las 4 Leyes de CHRONOS-TRIZ...")
print("================================================================================")
PYEOF
            ;;
        -h|--history)
            if [ ! -f "${LOG_H}" ]; then
                echo "Aun no existe ${LOG_H}"
            elif [ "${SUBMODO}" = "trades" ]; then
                echo " 🎯 FILTRO ACTIVO: MOSTRANDO SOLO DISPAROS, ÓRDENES, COSECHAS Y CIERRES HISTÓRICOS"
                echo "--------------------------------------------------------------------------------"
                grep -E "INICIANDO CEREBRO|\[RADAR\]|Orden |Posición|Trinquete|Cosecha|Trailing|MAKER-SCRATCH|CIERRE|no llenada" "${LOG_H}" | tail -n 50 || true
            else
                tail -n 60 "${LOG_H}" || true
            fi
            ;;
        -q|--quantum)
            "${PY}" "${REPO}/evaluador_cuantico_oos.py" --repo "${REPO}" --horas 8 --telegram || true
            [ -f "${REPO}/reporte_cuantico_oos.md" ] && cat "${REPO}/reporte_cuantico_oos.md" || true
            ;;
        -x|--xray)
            "${PY}" - "${REPO}" "${SUBMODO}" << 'XRAYEOF'
import asyncio, os, sys, urllib.request, urllib.parse
from pathlib import Path
import ccxt.async_support as ccxt

repo_path = Path(sys.argv[1])
accion = sys.argv[2].lower() if len(sys.argv) > 2 else "status"
sys.path.insert(0, str(repo_path))
import config_parametros as cfg
from gestor_posiciones import calcular_eslabon_chain_jail

def cargar_claves():
    pares = {}
    env_f = repo_path / ".env"
    if env_f.exists():
        for ln in env_f.read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                pares[k.strip()] = v.strip().strip("'").strip('"')
    for k in dir(cfg):
        if k.isupper() and isinstance(getattr(cfg, k), str) and getattr(cfg, k).strip():
            pares[k] = getattr(cfg, k).strip()
    ign = ("GROQ", "GEMINI", "GOOGLE", "NVIDIA", "NIM", "TELEGRAM", "TG_", "DISCORD", "OPENAI")
    ak, asec, tgt, tgc = None, None, pares.get("TELEGRAM_BOT_TOKEN") or pares.get("TELEGRAM_TOKEN"), pares.get("TELEGRAM_CHAT_ID") or pares.get("CHAT_ID")
    for k, v in pares.items():
        ku = k.upper()
        if any(x in ku for x in ign):
            continue
        if ("KEY" in ku or "API" in ku) and "SECRET" not in ku and "PRIV" not in ku and not ak:
            ak = v
        elif ("SECRET" in ku or "PRIV" in ku) and not asec:
            asec = v
    return ak, asec, tgt, tgc

def mandar_tg(token, chat_id, texto):
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": texto}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status == 200:
                print(" 📲 [TELEGRAM] Alerta en vivo enviada a tu celular.")
    except Exception as e:
        print(f" ⚠️ [TELEGRAM] Error: {e}")

async def main_xray():
    ak, asec, tgt, tgc = cargar_claves()
    ex = ccxt.bybit({"apiKey": ak, "secret": asec, "enableRateLimit": True, "options": {"defaultType": "swap"}})
    try:
        posiciones = await ex.fetch_positions(None, {"settleCoin": "USDT"})
        activas = [p for p in posiciones if float(p.get("contracts") or 0) > 0]
        bal = await ex.fetch_balance()
        usdt = bal.get("USDT", {})
        tot = float(usdt.get("total") or 0.0)
        lib = float(usdt.get("free") or 0.0)
        print("--------------------------------------------------------------------------------")
        print(f" ⛓️  RADAR TÁCTICO CHAIN-JAIL (verbot -x) | Balance UTA: {tot:.4f} USDT (Libre: {lib:.4f})")
        print("--------------------------------------------------------------------------------")
        if not activas:
            print(" 🟢 Sin posiciones abiertas en Bybit (0 contratos corriendo).")
            print("================================================================================")
            if accion in ("status", "all"):
                mandar_tg(tgt, tgc, f"⛓️ [RADAR CHAIN-JAIL v2.0]\nEstado: 0 contratos abiertos\nBalance UTA: {tot:.4f} USDT (Libre: {lib:.4f} USDT)\n⚙️ {cfg.TITULO_TELEGRAM_CANONICO}")
            return

        lineas_tg = [f"⛓️ [RADAR CHAIN-JAIL EN VIVO]\n💰 Balance UTA: {tot:.4f} USDT"]
        for p in activas:
            sym = p["symbol"]
            side = p["side"].lower()
            qty = float(p["contracts"])
            ep = float(p.get("entryPrice") or 0.0)
            mp = float(p.get("markPrice") or 0.0)
            pnl_u = float(p.get("unrealizedPnl") or 0.0)
            lev = float(p.get("leverage") or 3.0)
            sl_b = (p.get("info") or {}).get("stopLoss") or "SIN SL"
            pct = ((mp - ep) / ep if side == "long" else (ep - mp) / ep) if ep > 0 else 0.0
            eslabon, piso_sug, _ = calcular_eslabon_chain_jail(max(0.0, pct))

            if accion == "cerrar":
                ords = await ex.fetch_open_orders(sym)
                for o in ords:
                    await ex.cancel_order(o["id"], sym)
                lado_c = "buy" if side == "short" else "sell"
                await ex.create_order(sym, "market", lado_c, qty, None, {"reduceOnly": True})
                bal2 = await ex.fetch_balance()
                tot2 = float((bal2.get("USDT") or {}).get("total") or tot)
                print(f" 🟩 COBRO MANUAL CHAIN-JAIL EJECUTADO: {sym} [{side.upper()}] ({qty} contratos)")
                print(f" 💵 Capturado: {pct*100:+.2f}% puro ({pnl_u:+.4f} USDT) | Nuevo Balance: {tot2:.4f} USDT")
                print("================================================================================")
                mandar_tg(
                    tgt, tgc,
                    f"💰 [COBRO MANUAL CHAIN-JAIL (verbot -x cerrar)]\n"
                    f"Activo: {sym} [{side.upper()}] ({qty} contratos)\n"
                    f"Precio: {ep} -> {mp} ({pct*100:+.2f}% | ROE {pct*lev*100:+.2f}%)\n"
                    f"PnL Cobrado: {pnl_u:+.4f} USDT\n"
                    f"Nuevo Balance UTA: {tot2:.4f} USDT\n"
                    f"⚙️ {cfg.TITULO_TELEGRAM_CANONICO}"
                )
            else:
                print(f" �� {sym} [{side.upper()}] | Contratos: {qty} | Entrada: {ep} -> Actual: {mp}")
                print(f" 🔥 Ganancia Actual : {pct*100:+.2f}% puro ({pct*lev*100:+.2f}% ROE {lev:.0f}x) | {pnl_u:+.4f} USDT")
                print(f" ⛓️ Eslabón Chain-Jail: {eslabon}/5 (Piso Eslabón: +{piso_sug*100:.2f}% | Meta Techo: +8.00%) | SL Bybit: {sl_b}")
                print("================================================================================")
                lineas_tg.append(
                    f"🎯 {sym} [{side.upper()}] ({qty} contratos)\n"
                    f"• Precio: {ep} -> {mp}\n"
                    f"• Ganancia: {pct*100:+.2f}% (ROE {pct*lev*100:+.2f}%) | {pnl_u:+.4f} USDT\n"
                    f"• Eslabón Chain-Jail: {eslabon}/5 (Piso +{piso_sug*100:.2f}% -> Techo +8.00%)\n"
                    f"• SL en Bybit: {sl_b}"
                )
        if accion != "cerrar":
            lineas_tg.append(f"⚙️ {cfg.TITULO_TELEGRAM_CANONICO}")
            mandar_tg(tgt, tgc, "\n".join(lineas_tg))
    finally:
        await ex.close()

asyncio.run(main_xray())
XRAYEOF
            ;;
        -t|--telegram-last)
            "${PY}" - "${REPO}" << 'PYEOF' || true
import asyncio, json, pathlib, sys
repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo))
from telemetria_telegram import TELEMETRIA_TG
stats_f = repo / "tribrain_stats_v1.jsonl"
if not stats_f.exists():
    print("  ℹ️ Aun no hay cierres registrados en tribrain_stats_v1.jsonl.")
else:
    lineas = [l for l in stats_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lineas:
        print("  ℹ️ Archivo tribrain_stats_v1.jsonl vacio.")
    else:
        u = json.loads(lineas[-1])
        TELEMETRIA_TG.cache_dedup.clear()
        ok = asyncio.run(TELEMETRIA_TG.enviar_cierre_garantizado(
            symbol=u["symbol"], side=u.get("side", "long"),
            pnl_pct=float(u["pnl_percentage"]), pnl_usdt=float(u["pnl_usdt"]),
            hold_seg=float(u["hold_seg"]), motivo=str(u["motivo"]),
            entry_price=float(u.get("entry_price", 0)), exit_price=float(u.get("exit_price", 0)),
            cosecha_50_previa=bool(u.get("cosecha_triz_50", False))
        ))
        sym_u = u["symbol"]
        print(f"  ✅ Reenvio manual a Telegram del ultimo cierre ({sym_u}): {ok}")
PYEOF
            ;;
        *)
            echo "--------------------------------------------------------------------------------"
            echo " 🛡️  MODO AISLADO ACTIVO: Presiona [Ctrl + C] para salir de la vista"
            echo "    y volver al prompt SSH sin apagar el bot ni cerrar tu consola."
            echo "================================================================================"
            if [ -f "${LOG}" ]; then
                (trap 'exit 0' INT TERM; tail -n 40 -f "${LOG}" || true) || true
            else
                echo "Aun no existe ${LOG}"
            fi
            echo ""
            echo "✅ Vista en vivo cerrada de forma segura (El demonio sigue operando en segundo plano)."
            ;;
    esac
    return 0
}
# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===
"""

bloque_final = plantilla_raw.replace("__REPO_DIR__", repo_dir)
rc_path.write_text(txt.rstrip() + "\n\n" + bloque_final, encoding="utf-8")
print("✅ [VERBOT & TMUXRO OK] Comandos instalados en ~/.bashrc (0 colisiones de comillas).")
PYINSTALL

echo "=================================================================="
echo "✅ INFRAESTRUCTURA TRI-BRAIN-SNIPER V1.0 INSTALADA EXITOSAMENTE"
echo "=================================================================="