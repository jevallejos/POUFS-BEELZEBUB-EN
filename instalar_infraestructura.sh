#!/usr/bin/env bash
# ==============================================================================
# FILE #13: instalar_infraestructura.sh
# SYSTEM: POUFS-BEELZEBUB-EN (Spiritual Message) V5.0 -- CHRONOS-TRIZ STRATEGY
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BIN="${REPO_DIR}/venv/bin/python"
SERVICE_NAME="tribrain-eval-oos"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
USER_NAME="$(whoami)"

echo "=================================================================="
echo " [SETUP] INSTALLING INFRASTRUCTURE: POUFS-BEELZEBUB-EN (Spiritual Message) V5.0"
echo "   Repository  : ${REPO_DIR}"
echo "   Python VENV : ${PY_BIN}"
echo "=================================================================="

if [ ! -x "${PY_BIN}" ]; then
    echo " [ERROR] Python executable not found at ${PY_BIN}"
    exit 1
fi

git -C "${REPO_DIR}" config core.fileMode false || true
chmod +x "${REPO_DIR}/instalar_infraestructura.sh" "${REPO_DIR}/main.py" "${REPO_DIR}/evaluador_cuantico_oos.py" 2>/dev/null || true

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Quantum Walk-Forward OOS Evaluator POUFS-BEELZEBUB-EN (Spiritual Message) V5.0
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
ExecStart=${PY_BIN} ${REPO_DIR}/evaluador_cuantico_oos.py --repo ${REPO_DIR} --horas 8
StandardOutput=journal
StandardError=journal
EOF

sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Tri-Session Timer (00:00, 08:00, 16:00 UTC) for POUFS-BEELZEBUB-EN (Spiritual Message) V5.0

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

echo " [SYSTEMD OK] Timer ${SERVICE_NAME}.timer enabled and active:"
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
txt = re.sub(
    r"# === TRIBRAIN-SNIPER HUD START ===.*?# === TRIBRAIN-SNIPER HUD END ===\n?",
    "",
    txt,
    flags=re.DOTALL,
)

raw_template = r"""# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===
set +e 2>/dev/null || true

tmuxro() {
    set +e
    echo " [READ-ONLY] Attaching to tmux in READ-ONLY MODE (-r). To detach without stopping the bot press: Ctrl+B then d"
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
    local MODE="${1:-live}"
    local SUBMODE="${2:-status}"

    echo "=========================================================================================="
    echo -e " \033[1;38;2;255;255;255;48;2;105;48;195m  PHANTOM 3D  \033[0m \033[1;38;2;0;240;255mREAL-TIME FORENSIC HUD -- POUFS-BEELZEBUB-EN (Spiritual Message) V5.0\033[0m"
    echo "=========================================================================================="

    if [ -f "${LOCK}" ]; then
        local PID
        PID=$(cat "${LOCK}" 2>/dev/null | tr -d '[:space:]' || true)
        if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
            local PS_INFO
            PS_INFO=$(ps -p "${PID}" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}' || true)
            echo -e " \033[1;38;2;10;25;15;48;2;0;230;118m  ONLINE  \033[0m \033[1;38;2;0;255;135mLIVE ENGINE -> ${PS_INFO}\033[0m"
        else
            echo " [ALERT] Lockfile .tribrain.lock present (PID ${PID}), but process is not responding."
        fi
    else
        echo " [STOP] ENGINE STOPPED: No active .tribrain.lock file found."
    fi

    case "${MODE}" in
        -s|--status)
            "${PY}" -c "import sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; gp.imprimir_status_cli_verbot()" || true
            ;;
        -x|--xray)
            "${PY}" -c "import asyncio, sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; asyncio.run(gp.ejecutar_radar_xray_cli('${SUBMODE}'))" || true
            ;;
        -h|--history)
            local HIST_FILE="${LOG}"
            if [ -f "${LOG_H}" ] && [ -s "${LOG_H}" ]; then
                HIST_FILE="${LOG_H}"
            fi
            if [ ! -f "${HIST_FILE}" ]; then
                echo "No historical log file found yet."
            elif [ "${SUBMODE}" = "trades" ]; then
                echo " [TRADES] ACTIVE FILTER: DISPLAYING EXCLUSIVELY SHOTS, HARVESTS, RATCHETS, AND CLOSES"
                echo "------------------------------------------------------------------------------------------"
                grep -h -E "STARTING CENTRAL CORE|INICIANDO CEREBRO|\[RADAR\].*(APPROVED|APROBADO)|Order |Orden |Active.*position|Posicion|Ratchet|Trinquete|Harvest|Cosecha|PHANTOM 50/25/25|Trailing|MAKER-SCRATCH|MAKER_UNWIND|CLOSE|CIERRE|unfilled|no llenada" "${LOG_H}" "${LOG}" 2>/dev/null | awk '!seen[$0]++' | tail -n 60 || true
                echo "=========================================================================================="
            else
                tail -n 60 "${HIST_FILE}" || true
                echo "=========================================================================================="
            fi
            ;;
        -q|--quantum)
            "${PY}" "${REPO}/evaluador_cuantico_oos.py" --repo "${REPO}" --horas 8 || true
            [ -f "${REPO}/reporte_cuantico_oos.md" ] && cat "${REPO}/reporte_cuantico_oos.md" || true
            ;;
        -l|--lab)
            "${PY}" "${REPO}/evaluador_cuantico_oos.py" --repo "${REPO}" --lab || true
            ;;
        -t|--telegram-last)
            "${PY}" -c "import asyncio, sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; asyncio.run(gp.reenviar_ultimo_cierre_cli())" || true
            ;;
        *)
            "${PY}" -c "import sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; gp.imprimir_status_cli_verbot()" || true
            echo " [SAFE MODE] ISOLATED VIEW ACTIVE: Press [Ctrl + C] to exit the live log stream"
            echo "    and return to the SSH prompt without stopping the bot or closing your terminal."
            echo "=========================================================================================="
            if [ -f "${LOG}" ]; then
                (trap 'exit 0' INT TERM; tail -n 35 -f "${LOG}" | "${PY}" -u -c "import sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; [print(gp.colorear_linea_log_mobaxterm(line), flush=True) for line in sys.stdin]" || true) || true
            else
                echo "Log file ${LOG} does not exist yet."
            fi
            echo ""
            echo " [OK] Live view safely closed (POUFS-BEELZEBUB-EN V5.0 daemon continues running in background)."
            ;;
    esac
    return 0
}
# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===
"""

verbot_block = raw_template.replace("__REPO_DIR__", repo_dir)
rc_path.write_text(txt.rstrip() + "\n\n" + verbot_block, encoding="utf-8")
print(" [VERBOT V5.0 OK] Commands installed in ~/.bashrc: verbot, verbot -s, verbot -x, verbot -x close, verbot -h trades, verbot -q, verbot -l, verbot -t")
PYEOF

echo "=================================================================="
echo " [OK] POUFS-BEELZEBUB-EN (Spiritual Message) V5.0 INFRASTRUCTURE INSTALLED"
echo "=================================================================="