#!/usr/bin/env bash
# ==============================================================================
# ARCHIVO #13: instalar_infraestructura.sh
# SISTEMA: TRI-BRAIN-PHANTOM (God's Accomplice) V1.0 — ESTRATEGIA CHRONOS-TRIZ
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BIN="${REPO_DIR}/venv/bin/python"
SERVICE_NAME="tribrain-eval-oos"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
USER_NAME="$(whoami)"

echo "=================================================================="
echo "⚙️  INSTALANDO INFRAESTRUCTURA TRI-BRAIN-PHANTOM (God's Accomplice) V1.0"
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
Description=Evaluador Cuantico Walk-Forward OOS TRI-BRAIN-PHANTOM (God's Accomplice) V1.0
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
StandardOutput=journal
StandardError=journal
EOF

sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Timer Tri-Sesion (00:00, 08:00, 16:00 UTC) para TRI-BRAIN-PHANTOM (God's Accomplice) V1.0

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
txt = re.sub(
    r"# === TRIBRAIN-SNIPER HUD START ===.*?# === TRIBRAIN-SNIPER HUD END ===\n?",
    "",
    txt,
    flags=re.DOTALL,
)

plantilla_raw = r"""# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===
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
    local SUBMODO="${2:-status}"

    echo "=========================================================================================="
    echo -e " \033[1;38;2;255;255;255;48;2;105;48;195m 👁️ PHANTOM 3D \033[0m \033[1;38;2;0;240;255mPANEL FORENSE EN TIEMPO REAL — TRI-BRAIN-PHANTOM (God's Accomplice) V1.0\033[0m"
    echo "=========================================================================================="

    if [ -f "${LOCK}" ]; then
        local PID
        PID=$(cat "${LOCK}" 2>/dev/null | tr -d '[:space:]' || true)
        if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
            local PS_INFO
            PS_INFO=$(ps -p "${PID}" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}' || true)
            echo -e " \033[1;38;2;10;25;15;48;2;0;230;118m 🟢 ONLINE \033[0m \033[1;38;2;0;255;135mMOTOR EN VIVO -> ${PS_INFO}\033[0m"
        else
            echo " 🔴 ALERTA: Archivo .tribrain.lock presente (PID ${PID}), pero el proceso no responde."
        fi
    else
        echo " ⚪ MOTOR DETENIDO: No existe archivo .tribrain.lock activo."
    fi

    case "${MODO}" in
        -s|--status)
            "${PY}" -c "import sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; gp.imprimir_status_cli_verbot()" || true
            ;;
        -x|--xray)
            "${PY}" -c "import asyncio, sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; asyncio.run(gp.ejecutar_radar_xray_cli('${SUBMODO}'))" || true
            ;;
        -h|--history)
            local ARCHIVO_HIST="${LOG}"
            if [ -f "${LOG_H}" ] && [ -s "${LOG_H}" ]; then
                ARCHIVO_HIST="${LOG_H}"
            fi
            if [ ! -f "${ARCHIVO_HIST}" ]; then
                echo "Aun no existe bitacora de historial."
            elif [ "${SUBMODO}" = "trades" ]; then
                echo " 🎯 FILTRO ACTIVO: MOSTRANDO UNICAMENTE DISPAROS, COSECHAS, TRINQUETES Y CIERRES"
                echo "------------------------------------------------------------------------------------------"
                grep -h -E "INICIANDO CEREBRO|\[RADAR\].*APROBADO|Orden |Posición|Trinquete|Cosecha|CHAIN-JAIL|Trailing|MAKER-SCRATCH|MAKER_UNWIND|CIERRE|no llenada" "${LOG_H}" "${LOG}" 2>/dev/null | awk '!seen[$0]++' | tail -n 60 || true
                echo "=========================================================================================="
            else
                tail -n 60 "${ARCHIVO_HIST}" || true
                echo "=========================================================================================="
            fi
            ;;
        -q|--quantum)
            "${PY}" "${REPO}/evaluador_cuantico_oos.py" --repo "${REPO}" --horas 8 --telegram || true
            [ -f "${REPO}/reporte_cuantico_oos.md" ] && cat "${REPO}/reporte_cuantico_oos.md" || true
            ;;
        -t|--telegram-last)
            "${PY}" -c "import asyncio, sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; asyncio.run(gp.reenviar_ultimo_cierre_cli())" || true
            ;;
        *)
            "${PY}" -c "import sys; sys.path.insert(0, '${REPO}'); import gestor_posiciones as gp; gp.imprimir_status_cli_verbot()" || true
            echo " 🛡️  MODO AISLADO ACTIVO: Presiona [Ctrl + C] para salir de la vista"
            echo "    y volver al prompt SSH sin apagar el bot ni cerrar tu consola."
            echo "=========================================================================================="
            if [ -f "${LOG}" ]; then
                (trap 'exit 0' INT TERM; tail -n 35 -f "${LOG}" || true) || true
            else
                echo "Aun no existe ${LOG}"
            fi
            echo ""
            echo "✅ Vista en vivo cerrada de forma segura (El demonio V4.0 sigue operando en segundo plano)."
            ;;
    esac
    return 0
}
# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===
"""

bloque_verbot = plantilla_raw.replace("__REPO_DIR__", repo_dir)
rc_path.write_text(txt.rstrip() + "\n\n" + bloque_verbot, encoding="utf-8")
print("✅ [VERBOT PHANTOM V1.0 OK] Comandos instalados en ~/.bashrc: verbot, verbot -s, verbot -x, verbot -x cerrar, verbot -h trades, verbot -q, verbot -t")
PYEOF

echo "=================================================================="
echo "✅ INFRAESTRUCTURA TRI-BRAIN-PHANTOM (God's Accomplice) V1.0 INSTALADA"
echo "=================================================================="
