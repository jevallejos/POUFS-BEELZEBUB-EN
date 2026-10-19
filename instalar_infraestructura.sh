#!/usr/bin/env bash
# ==============================================================================
# ARCHIVO #13: instalar_infraestructura.sh
# SISTEMA: TRI-BRAIN-SNIPER (CHAIN-JAIL) V2.0 — ESTRATEGIA CHRONOS-TRIZ
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BIN="${REPO_DIR}/venv/bin/python"
SERVICE_NAME="tribrain-eval-oos"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
USER_NAME="$(whoami)"

echo "=================================================================="
echo "⚙️  INSTALANDO INFRAESTRUCTURA TRI-BRAIN-SNIPER (CHAIN-JAIL) V2.0"
echo "   Repositorio : ${REPO_DIR}"
echo "   Python VENV : ${PY_BIN}"
echo "=================================================================="

if [ ! -x "${PY_BIN}" ]; then
    echo "❌ [ERROR] No se encontro el ejecutable Python en ${PY_BIN}"
    exit 1
fi

git -C "${REPO_DIR}" config core.fileMode false || true
chmod +x "${REPO_DIR}/instalar_infraestructura.sh" "${REPO_DIR}/main.py" "${REPO_DIR}/evaluador_cuantico_oos.py" 2>/dev/null || true

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

python3 - "${REPO_DIR}" << 'PYEOF'
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

bloque_verbot = f"""# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===
set +e 2>/dev/null || true

tmuxro() {{
    set +e
    echo "🔒 Entrando a tmux en MODO SOLO LECTURA (-r). Para salir sin apagar el bot presiona: Ctrl+B y luego d"
    sleep 1
    command tmux attach -t demonio_hft -r || true
    return 0
}}

verbot() {{
    set +e
    local REPO="{repo_dir}"
    local PY="${{REPO}}/venv/bin/python"
    local LOCK="${{REPO}}/.tribrain.lock"
    local LOG="${{REPO}}/bot_hft.log"
    local LOG_H="${{REPO}}/bot_hft_h.log"
    local MODO="${{1:-live}}"
    local SUBMODO="${{2:-status}}"

    echo "================================================================================"
    echo " 👁️  PANEL FORENSE EN TIEMPO REAL — TRI-BRAIN-SNIPER V2.0 [CHAIN-JAIL]"
    echo "================================================================================"

    if [ -f "${{LOCK}}" ]; then
        local PID
        PID=$(cat "${{LOCK}}" 2>/dev/null | tr -d '[:space:]' || true)
        if [ -n "${{PID}}" ] && kill -0 "${{PID}}" 2>/dev/null; then
            local PS_INFO
            PS_INFO=$(ps -p "${{PID}}" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}}' || true)
            echo " 🟢 MOTOR EN VIVO -> ${{PS_INFO}}"
        else
            echo " 🔴 ALERTA: Archivo .tribrain.lock presente (PID ${{PID}}), pero el proceso no responde."
        fi
    else
        echo " ⚪ MOTOR DETENIDO: No existe archivo .tribrain.lock activo."
    fi

    case "${{MODO}}" in
        -s|--status)
            "${{PY}}" -c "
import json, pathlib
repo = pathlib.Path('${{REPO}}')
stats_f = repo / 'tribrain_stats_v1.jsonl'
ops = [json.loads(l) for l in stats_f.read_text(encoding='utf-8').splitlines() if l.strip()] if stats_f.exists() else []
ops = [x for x in ops if 'ESCAPE_HUERFANA_BOOT' not in str(x.get('motivo', '')).upper()]
w = sum(1 for x in ops if float(x.get('pnl_usdt', 0)) >= 0)
l = len(ops) - w
s = sum(1 for x in ops if 'SCRATCH' in str(x.get('motivo', '')).upper() and float(x.get('pnl_usdt', 0)) < 0)
triz = sum(1 for x in ops if x.get('cosecha_triz_50'))
pnl = sum(float(x.get('pnl_usdt', 0)) for x in ops)
wr = (w / len(ops) * 100.0) if ops else 0.0
wr_ef = (w / max(1, len(ops) - s) * 100.0) if ops else 0.0
print('--------------------------------------------------------------------------------')
print(f' 📊 CAJA NEGRA: {{len(ops)}} Trades (W: {{w}} | L: {{l}} | Scratch 18s: {{s}} | Cosecha 50%: {{triz}})')
print(f' 🎯 Win Rate  : Clasico {{wr:.1f}}% | Efectivo (sin Scratch) {{wr_ef:.1f}}% | PnL Neto: {{pnl:+.4f}} USDT')
print('--------------------------------------------------------------------------------')
if ops:
    for op in ops[-10:]:
        ic = '🟩' if float(op.get('pnl_usdt', 0)) >= 0 else ('🟨' if 'SCRATCH' in str(op.get('motivo', '')).upper() else '🔴')
        print(f\"  {{ic}} {{str(op.get('timestamp',''))[:19]}} | {{str(op.get('symbol','')):<17}} | {{float(op.get('pnl_percentage',0)):+6.2f}}% ({{float(op.get('pnl_usdt',0)):+.4f}} USDT) | {{op.get('motivo','')}}\")
else:
    print('  ⏳ Esperando el primer disparo confirmado...')
print('================================================================================')
" || true
            ;;
        -x|--xray)
            "${{PY}}" -c "import asyncio, sys; sys.path.insert(0, '${{REPO}}'); import gestor_posiciones as gp; asyncio.run(gp.ejecutar_radar_xray_cli('${{SUBMODO}}'))" || true
            ;;
        -h|--history)
            if [ ! -f "${{LOG_H}}" ]; then
                echo "Aun no existe ${{LOG_H}}"
            elif [ "${{SUBMODO}}" = "trades" ]; then
                echo " 🎯 FILTRO ACTIVO: MOSTRANDO SOLO DISPAROS, ÓRDENES, COSECHAS Y CIERRES HISTÓRICOS"
                echo "--------------------------------------------------------------------------------"
                grep -E "INICIANDO CEREBRO|\[RADAR\]|Orden |Posición|Trinquete|Cosecha|CHAIN-JAIL|Trailing|MAKER-SCRATCH|CIERRE|no llenada" "${{LOG_H}}" | tail -n 50 || true
            else
                tail -n 60 "${{LOG_H}}" || true
            fi
            ;;
        -q|--quantum)
            "${{PY}}" "${{REPO}}/evaluador_cuantico_oos.py" --repo "${{REPO}}" --horas 8 --telegram || true
            [ -f "${{REPO}}/reporte_cuantico_oos.md" ] && cat "${{REPO}}/reporte_cuantico_oos.md" || true
            ;;
        -t|--telegram-last)
            "${{PY}}" -c "
import asyncio, json, pathlib, sys
sys.path.insert(0, '${{REPO}}')
from telemetria_telegram import TELEMETRIA_TG
stats_f = pathlib.Path('${{REPO}}/tribrain_stats_v1.jsonl')
if not stats_f.exists():
    print('  ℹ️ Aun no hay cierres registrados en tribrain_stats_v1.jsonl.')
else:
    lineas = [l for l in stats_f.read_text(encoding='utf-8').splitlines() if l.strip()]
    if not lineas:
        print('  ℹ️ Archivo tribrain_stats_v1.jsonl vacio.')
    else:
        u = json.loads(lineas[-1])
        TELEMETRIA_TG.cache_dedup.clear()
        ok = asyncio.run(TELEMETRIA_TG.enviar_cierre_garantizado(
            symbol=u['symbol'], side=u.get('side','long'),
            pnl_pct=float(u['pnl_percentage']), pnl_usdt=float(u['pnl_usdt']),
            hold_seg=float(u['hold_seg']), motivo=str(u['motivo']),
            entry_price=float(u.get('entry_price',0)), exit_price=float(u.get('exit_price',0)),
            cosecha_50_previa=bool(u.get('cosecha_triz_50',False))
        ))
        print(f'  ✅ Reenvio manual a Telegram del ultimo cierre ({{u[\"symbol\"]}}): {{ok}}')
" || true
            ;;
        *)
            echo "--------------------------------------------------------------------------------"
            echo " 🛡️  MODO AISLADO ACTIVO: Presiona [Ctrl + C] para salir de la vista"
            echo "    y volver al prompt SSH sin apagar el bot ni cerrar tu consola."
            echo "================================================================================"
            if [ -f "${{LOG}}" ]; then
                (trap 'exit 0' INT TERM; tail -n 40 -f "${{LOG}}" || true) || true
            else
                echo "Aun no existe ${{LOG}}"
            fi
            echo ""
            echo "✅ Vista en vivo cerrada de forma segura (El demonio sigue operando en segundo plano)."
            ;;
    esac
    return 0
}}
# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===
"""

rc_path.write_text(txt.rstrip() + "\n\n" + bloque_verbot, encoding="utf-8")
print("✅ [VERBOT V2.0 OK] Comandos instalados en ~/.bashrc: verbot, verbot -s, verbot -x, verbot -x cerrar, verbot -h, verbot -q, verbot -t")
PYEOF

echo "=================================================================="
echo "✅ INFRAESTRUCTURA TRI-BRAIN-SNIPER (CHAIN-JAIL) V2.0 INSTALADA"
echo "=================================================================="