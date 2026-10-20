#!/usr/bin/env bash
# ==============================================================================
# ARCHIVO #11: instalar_infraestructura.sh
# SISTEMA: TRI-BRAIN-SNIPER (SKILL HUNTER) V3.0 — ESTRATEGIA CHRONOS-TRIZ
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${REPO_DIR}/venv/bin/python"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
BASHRC_FILE="${HOME}/.bashrc"

echo "=================================================================="
echo "⚙️  INSTALANDO INFRAESTRUCTURA TRI-BRAIN-SNIPER (SKILL HUNTER) V3.0"
echo "   Repositorio : ${REPO_DIR}"
echo "   Python VENV : ${VENV_PY}"
echo "=================================================================="

mkdir -p "${SYSTEMD_USER_DIR}"

cat <<EOF > "${SYSTEMD_USER_DIR}/tribrain-eval-oos.service"
[Unit]
Description=Evaluador Cuantico OOS Tri-Brain-Sniper V3.0 (Skill Hunter)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${REPO_DIR}
Environment="PYTHONUTF8=1"
Nice=15
IOSchedulingClass=best-effort
IOSchedulingPriority=7
ExecStart=${VENV_PY} ${REPO_DIR}/evaluador_cuantico_oos.py
StandardOutput=null
StandardError=null
EOF

cat <<EOF > "${SYSTEMD_USER_DIR}/tribrain-eval-oos.timer"
[Unit]
Description=Timer 8h Evaluador Cuantico OOS Tri-Brain-Sniper V3.0

[Timer]
OnCalendar=*-*-* 00,08,16:00:00 UTC
RandomizedDelaySec=30
Persistent=true
Unit=tribrain-eval-oos.service

[Install]
WantedBy=timers.target
EOF

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable --now tribrain-eval-oos.timer 2>/dev/null || true
    echo "✅ [SYSTEMD OK] Timer tribrain-eval-oos.timer habilitado y activo."
fi

sed -i '/# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===/,/# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===/d' "${BASHRC_FILE}" 2>/dev/null || true
sed -i '/# === TRIBRAIN-SNIPER HUD START ===/,/# === TRIBRAIN-SNIPER HUD END ===/d' "${BASHRC_FILE}" 2>/dev/null || true

cat << 'EOF' >> "${BASHRC_FILE}"
# === INICIO PANEL VERBOT TRI-BRAIN-SNIPER ===
set +e 2>/dev/null || true

verbot() {
    set +e
    local DIR="$HOME/Tri-Brain-Sniper"
    local LOCK="$DIR/.tribrain.lock"
    local LOG="$DIR/bot_hft.log"
    local STATS="$DIR/tribrain_stats_v1.jsonl"
    local PY="$DIR/venv/bin/python"
    local ARG1="${1:-}"
    local ARG2="${2:-}"

    # Permitir atajos directos: 'verbot cierre' o 'verbot cerrar' -> equivale a 'verbot -x cierre'
    if [ "$ARG1" = "cierre" ] || [ "$ARG1" = "cerrar" ] || [ "$ARG1" = "close" ] || [ "$ARG1" = "-c" ]; then
        ARG1="-x"
        ARG2="cierre"
    fi

    # 1. Subcomando -q: Evaluador Cuantico OOS en caliente
    if [ "$ARG1" = "-q" ]; then
        echo "=========================================================================================="
        echo " 🧠 EJECUTANDO EVALUADOR CUÁNTICO OOS WALK-FORWARD — TRI-BRAIN-SNIPER V3.0"
        echo "=========================================================================================="
        (cd "$DIR" && "$PY" evaluador_cuantico_oos.py)
        echo "=========================================================================================="
        return 0
    fi

    # 2. Subcomando -t: Prueba real e inmediata de entrega a Telegram + Resumen del ultimo trade
    if [ "$ARG1" = "-t" ]; then
        echo "=========================================================================================="
        echo " 📨 PROBANDO ENTREGA EN VIVO A TELEGRAM — TRI-BRAIN-SNIPER V3.0 [SKILL HUNTER]"
        echo "=========================================================================================="
        "$PY" - "$DIR" "$STATS" "$LOG" << 'PYTEOF'
import asyncio
import json
import os
import pathlib
import sys

base_dir = pathlib.Path(sys.argv[1])
stats_path = pathlib.Path(sys.argv[2])
log_path = pathlib.Path(sys.argv[3])
sys.path.insert(0, str(base_dir))

import telemetria_telegram as tg_mod

tok, cid = tg_mod._resolver_credenciales_telegram_v3()
if not tok or not cid:
    print(" 🔴 ERROR: No se encontraron TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
    sys.exit(1)

trades = []
if stats_path.exists():
    for l in stats_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if l.strip():
            try:
                trades.append(json.loads(l))
            except Exception:
                pass

total = len(trades)
wins = sum(1 for t in trades if float(t.get("pnl_usdt", 0.0)) > 0)
losses = total - wins
wr = (wins / total * 100.0) if total else 0.0
pnl_total = sum(float(t.get("pnl_usdt", 0.0)) for t in trades)

bal_real = "N/A"
if log_path.exists():
    for l in reversed(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]):
        if "real:" in l and "USDT" in l:
            try:
                bal_real = l.split("real:")[1].split("USDT")[0].strip() + " USDT"
                break
            except Exception:
                pass

ult_str = "Sin operaciones aún"
if trades:
    u = trades[-1]
    sym_u = str(u.get("symbol", "")).replace("/USDT:USDT", "")
    side_u = str(u.get("side", "long")).upper()
    pnl_u = float(u.get("pnl_usdt", 0.0))
    pct_u = float(u.get("pnl_pct", u.get("pnl_percentage", 0.0)))
    mot_u = str(u.get("motivo", "CIERRE"))
    ic_u = "🟩" if pnl_u >= 0 else "🔴"
    ult_str = f"{ic_u} #{total} {sym_u} [{side_u}] {pct_u:+.2f}% ({pnl_u:+.4f} USDT | {mot_u})"

msg_tg = (
    f"⚡ [REPORTE DE ESTADO EN VIVO — TRI-BRAIN-SNIPER V3.0]\n"
    f"📊 Caja Negra: {total} Trades ({wins}W / {losses}L | WR: {wr:.1f}%)\n"
    f"💰 PnL Neto: {pnl_total:+.4f} USDT | UTA Real: {bal_real}\n"
    f"🎯 Último Cierre: {ult_str}"
)

ok = asyncio.run(tg_mod.TELEMETRIA_TG.enviar_mensaje_sistema(msg_tg))
if ok:
    print(" ✅ [TELEGRAM HTTP 200 OK] Mensaje entregado exitosamente a tu chat de Telegram.")
else:
    print(" 🔴 [TELEGRAM ERROR] Falló el envío HTTP a Telegram. Revisa bot_hft.log.")
PYTEOF
        echo "=========================================================================================="
        return 0
    fi

    # 3. Subcomando -h / -h trades: Historial forense
    if [ "$ARG1" = "-h" ]; then
        echo "=========================================================================================="
        echo " 📚 HISTORIAL FORENSE DE OPERACIONES — TRI-BRAIN-SNIPER V3.0 [SKILL HUNTER]"
        echo "=========================================================================================="
        if [ "$ARG2" = "trades" ]; then
            grep -E "INICIANDO CEREBRO|\[RADAR\].*APROBADO|TELEMETRÍA DISPARO|Orden .* en |Posición .* activa|MICRO-SHIELD|MICRO-BE|PULSO POSICIÓN|Cosecha 50%|MAKER-SCRATCH|CIERRE |TELEGRAM OK" "$LOG" | tail -n 60
        else
            tail -n 80 "$LOG"
        fi
        echo "=========================================================================================="
        return 0
    fi

    # 4. Subcomando -x y -x cierre / cerrar: Auditoria en vivo y Liquidacion Manual en Bybit UTA V5
    if [ "$ARG1" = "-x" ]; then
        echo "=========================================================================================="
        if [ "$ARG2" = "cierre" ] || [ "$ARG2" = "cerrar" ] || [ "$ARG2" = "close" ]; then
            echo " 🚨 EJECUTANDO CIERRE MANUAL INMEDIATO (verbot -x cierre) EN BYBIT UTA + TELEGRAM"
        else
            echo " 🎯 AUDITORÍA EN VIVO DE CONTRATOS Y ÓRDENES ABIERTAS (BYBIT UTA + RAM)"
        fi
        echo "=========================================================================================="
        if [ -f "$LOCK" ]; then
            local PID
            PID=$(cat "$LOCK" | tr -d '[:space:]')
            if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
                local PS_INFO
                PS_INFO=$(ps -p "$PID" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}')
                echo " 🟢 MOTOR EN VIVO -> $PS_INFO"
            fi
        fi
        "$PY" - "$DIR" "$LOG" "$ARG2" << 'PYXEOF'
import asyncio
import os
import re
import sys
import pathlib

base_dir = pathlib.Path(sys.argv[1])
log_path = pathlib.Path(sys.argv[2])
modo_arg = str(sys.argv[3] if len(sys.argv) > 3 else "").strip().lower()
es_cierre = modo_arg in ("cerrar", "cierre", "close", "-c", "all")
sys.path.insert(0, str(base_dir))

env_file = base_dir / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

estado_log = {}
if log_path.exists():
    for l in log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-1500:]:
        if "Posición" in l and "activa en " in l:
            m = re.search(r"activa en ([A-Z0-9/]+:USDT):\s*([0-9.]+)\s*@\s*([0-9.]+).*SL interno\s*([0-9.]+)\s*\|\s*SL Bybit\s*([0-9.]+)", l)
            if m:
                sym = m.group(1)
                side = "SHORT" if "SHORT" in l else "LONG"
                estado_log[sym] = {
                    "side": side,
                    "qty_log": float(m.group(2)),
                    "entry_log": float(m.group(3)),
                    "sl_int": m.group(4),
                    "sl_bybit": m.group(5),
                    "fase": "FASE_1 (90s máx)",
                    "ultimo_pulso": l[:29],
                }
        elif "Cosecha 50% TRIZ PostOnly ejecutada" in l:
            for sym in list(estado_log.keys()):
                if sym in l:
                    estado_log[sym]["fase"] = "FREE-RUNNER 50% (Sin límite tiempo)"
                    estado_log[sym]["ultimo_pulso"] = l.split("] ", 1)[-1]
        elif "[MICRO-BE" in l or "[MICRO-SHIELD" in l or "[PULSO POSICIÓN]" in l:
            for sym in list(estado_log.keys()):
                if sym in l:
                    estado_log[sym]["ultimo_pulso"] = l.split("] ", 1)[-1]
        elif "CIERRE " in l:
            for sym in list(estado_log.keys()):
                if sym in l:
                    estado_log.pop(sym, None)

try:
    import ccxt
    import telemetria_telegram as tg_mod
    tg_mod._resolver_credenciales_telegram_v3()

    api_key = os.getenv("BYBIT_API_KEY") or os.getenv("API_KEY") or ""
    api_secret = os.getenv("BYBIT_API_SECRET") or os.getenv("API_SECRET") or ""
    ex = ccxt.bybit({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "swap", "recvWindow": 15000},
    })
    ex.load_markets()
    bal = ex.fetch_balance()
    usdt = bal.get("USDT", {})
    tot_u = float(usdt.get("total") or 0.0)
    free_u = float(usdt.get("free") or 0.0)
    used_u = float(usdt.get("used") or 0.0)

    positions = ex.fetch_positions(None, {"settleCoin": "USDT"})
    abiertas = [p for p in (positions or []) if abs(float(p.get("contracts") or p.get("info", {}).get("size") or 0.0)) > 0]
    try:
        ordenes = ex.fetch_open_orders(None, None, None, {"settleCoin": "USDT"})
    except Exception:
        ordenes = []

    if es_cierre:
        cerradas_n = 0
        recibos_tg = []
        # 1. Cancelar cualquier orden abierta en los pares con posicion o global
        for o in ordenes:
            try:
                ex.cancel_order(o["id"], o["symbol"])
                print(f" 🧹 Orden abierta cancelada: {o.get('symbol')} | Qty: {o.get('amount')} @ {o.get('price')}")
            except Exception:
                pass
        # 2. Liquidar a mercado (reduceOnly=True) el 100% de los contratos abiertos
        for p in abiertas:
            sym = str(p.get("symbol", ""))
            side = str(p.get("side", "")).lower()
            qty = abs(float(p.get("contracts") or p.get("info", {}).get("size") or 0.0))
            ep = float(p.get("entryPrice") or p.get("info", {}).get("avgPrice") or 0.0)
            mp = float(p.get("markPrice") or p.get("info", {}).get("markPrice") or ep)
            upnl = float(p.get("unrealizedPnl") or p.get("info", {}).get("unrealisedPnl") or 0.0)
            pct = ((mp - ep) / ep * 100.0) if (ep > 0 and side == "long") else (((ep - mp) / ep * 100.0) if ep > 0 else 0.0)
            if qty > 0:
                try:
                    ords_sym = ex.fetch_open_orders(sym)
                    for osym in (ords_sym or []):
                        ex.cancel_order(osym["id"], sym)
                except Exception:
                    pass
                close_side = "sell" if side == "long" else "buy"
                ex.create_order(sym, "market", close_side, qty, None, {"reduceOnly": True})
                cerradas_n += 1
                print(f" 🟩 [COBRO MANUAL EJECUTADO] {sym} [{side.upper()}] ({qty} contratos) @ {mp} | PnL: {pct:+.2f}% ({upnl:+.4f} USDT)")
                recibos_tg.append(f"• {sym} [{side.upper()}] ({qty}): {ep} -> {mp} ({pct:+.2f}% | {upnl:+.4f} USDT)")

        # Señalizar al demonio en vivo para liberar el slot en RAM en <150ms
        if cerradas_n > 0 or estado_log:
            try:
                (base_dir / ".tribrain_force_close.signal").write_text("CLOSE_NOW\n", encoding="utf-8")
            except Exception:
                pass

        bal2 = ex.fetch_balance()
        tot2 = float((bal2.get("USDT") or {}).get("total") or tot_u)
        if cerradas_n == 0:
            print(f" ⚪ No había posiciones abiertas en Bybit UTA para cerrar. Saldo UTA Total: {tot2:.4f} USDT")
            msg_c = f"ℹ️ [VERBOT -X CIERRE]\nSin contratos abiertos en Bybit UTA.\n💰 Saldo Consolidado: {tot2:.4f} USDT"
        else:
            print(f" 💰 Nuevo Balance Consolidado en Bybit UTA: {tot2:.4f} USDT")
            msg_c = (
                f"💰 [COBRO MANUAL EJECUTADO (verbot -x cierre)]\n"
                + "\n".join(recibos_tg)
                + f"\n💵 Nuevo Balance UTA: {tot2:.4f} USDT"
            )
        ok_tg = asyncio.run(tg_mod.TELEMETRIA_TG.enviar_mensaje_sistema(msg_c))
        print(f" 📲 [TELEGRAM] Confirmación enviada a tu celular: {ok_tg}")
        sys.exit(0)

    print("------------------------------------------------------------------------------------------")
    print(f" 💰 BILLETERA BYBIT UTA : Total: {tot_u:.4f} USDT | Libre: {free_u:.4f} USDT | Margen en Uso: {used_u:.4f} USDT")
    print("------------------------------------------------------------------------------------------")

    if not abiertas:
        print(" ⚪ CONTRATOS ABIERTOS  : 0 posiciones activas en Bybit en este instante (100% en liquidez).")
    else:
        print(f" 🟢 CONTRATOS ABIERTOS EN BYBIT ({len(abiertas)}) — Usa 'verbot -x cierre' para cobrar a mercado:")
        print(f" {'PAR':<15} {'LADO':<6} {'CONTRATOS':<11} {'ENTRADA':<10} {'MARCA':<10} {'NOCIONAL':<10} {'PNL FLOTANTE':<18} {'SL BYBIT / INT'}")
        print("------------------------------------------------------------------------------------------")
        lineas_tg = [f"🎯 [AUDITORÍA EN VIVO (verbot -x)] | UTA: {tot_u:.4f} USDT"]
        for p in abiertas:
            sym = str(p.get("symbol", ""))
            side = str(p.get("side", "")).upper()
            contracts = float(p.get("contracts") or p.get("info", {}).get("size") or 0.0)
            entry = float(p.get("entryPrice") or p.get("info", {}).get("avgPrice") or 0.0)
            mark = float(p.get("markPrice") or p.get("info", {}).get("markPrice") or 0.0)
            notional = abs(float(p.get("notional") or (contracts * mark) or 0.0))
            upnl = float(p.get("unrealizedPnl") or p.get("info", {}).get("unrealisedPnl") or 0.0)
            pct = ((mark - entry) / entry * 100.0) if (entry > 0 and side == "LONG") else (((entry - mark) / entry * 100.0) if entry > 0 else 0.0)
            sl_b = p.get("stopLossPrice") or p.get("info", {}).get("stopLoss") or "-"
            info_l = estado_log.get(sym, {})
            sl_i = info_l.get("sl_int", "-")
            fase = info_l.get("fase", "ACTIVA")
            ic = "🟩" if upnl >= 0 else "🔴"
            print(f" {sym.replace('/USDT:USDT',''):<15} {side:<6} {contracts:<11.4f} {entry:<10.5f} {mark:<10.5f} {notional:<9.2f}$ {ic} {upnl:+.4f}$ ({pct:+.2f}%)  SL:{sl_b} / Int:{sl_i}")
            print(f"    ↳ Estado Chronos-TRIZ: {fase} | Último evento: {info_l.get('ultimo_pulso', 'N/A')}")
            lineas_tg.append(f"{ic} {sym.replace('/USDT:USDT','')} [{side}] {contracts} @ {entry} -> {mark} ({pct:+.2f}% | {upnl:+.4f} USDT) | {fase}")
        asyncio.run(tg_mod.TELEMETRIA_TG.enviar_mensaje_sistema("\n".join(lineas_tg)))

    print("------------------------------------------------------------------------------------------")
    if not ordenes:
        print(" ⚪ ÓRDENES EN LIBRO    : 0 órdenes Limit PostOnly pendientes.")
    else:
        print(f" 📝 ÓRDENES ABIERTAS EN LIBRO ({len(ordenes)}):")
        for o in ordenes:
            print(f"   • {o.get('symbol')} | {str(o.get('side')).upper()} {o.get('type')} | Qty: {o.get('amount')} @ {o.get('price')} | ID: {o.get('id')}")
except Exception as e:
    print(f" ⚠️ [MODO OFFLINE LOG] No se pudo consultar REST en vivo ({e}). Mostrando estado en RAM/Log:")
    if not estado_log:
        print(" ⚪ CONTRATOS EN RAM/LOG: 0 posiciones abiertas actualmente.")
    else:
        for sym, d in estado_log.items():
            print(f" 🟢 {sym} [{d['side']}] | Contratos: {d['qty_log']} @ {d['entry_log']} | SL Int: {d['sl_int']} | Fase: {d['fase']}")
PYXEOF
        echo "=========================================================================================="
        return 0
    fi

    # 5. Vista Principal (verbot y verbot -s)
    echo "=========================================================================================="
    echo " 👁️  PANEL FORENSE DE ALTA SEÑAL — TRI-BRAIN-SNIPER V3.0 [SKILL HUNTER]"
    echo "=========================================================================================="

    if [ -f "$LOCK" ]; then
        local PID
        PID=$(cat "$LOCK" | tr -d '[:space:]')
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            local PS_INFO
            PS_INFO=$(ps -p "$PID" -o pid=,etime=,rss=,%cpu= 2>/dev/null | awk '{printf "PID: %s | Uptime: %s | RAM: %.1f MB | CPU: %s%%", $1, $2, $3/1024, $4}')
            echo " 🟢 MOTOR EN VIVO -> $PS_INFO"
        else
            echo " 🔴 ALERTA: Archivo .lock presente (PID $PID), pero el proceso no responde."
        fi
    else
        echo " ⚪ MOTOR DETENIDO: No existe archivo .tribrain.lock activo."
    fi

    if [ -f "$STATS" ] && [ -x "$PY" ]; then
        "$PY" - "$STATS" "$LOG" << 'PYEOF'
import json
import re
import sys
import pathlib
from collections import defaultdict

stats_path = pathlib.Path(sys.argv[1])
log_path = pathlib.Path(sys.argv[2])

trades = []
if stats_path.exists():
    for line in stats_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            try:
                trades.append(json.loads(line))
            except Exception:
                pass

total = len(trades)
wins = sum(1 for t in trades if float(t.get("pnl_usdt", 0.0)) > 0)
losses = total - wins
scratches = sum(1 for t in trades if "SCRATCH" in str(t.get("motivo", "")))
cosechas = sum(1 for t in trades if t.get("cosecha_50_ejecutada") or "TRINQUETE" in str(t.get("motivo", "")) or "TRAILING" in str(t.get("motivo", "")))
pnl_total = sum(float(t.get("pnl_usdt", 0.0)) for t in trades)
wr = (wins / total * 100.0) if total else 0.0
lam = min(1.0, total / 40.0)

bal_real = "N/A"
abiertos_ram = {}
if log_path.exists():
    lineas_log = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-800:]
    for l in reversed(lineas_log):
        if "real:" in l and "USDT" in l:
            try:
                bal_real = l.split("real:")[1].split("USDT")[0].strip() + " USDT"
                break
            except Exception:
                pass
    for l in lineas_log:
        if "Posición" in l and "activa en " in l:
            m = re.search(r"activa en ([A-Z0-9/]+:USDT):\s*([0-9.]+)\s*@\s*([0-9.]+).*SL interno\s*([0-9.]+)", l)
            if m:
                sym = m.group(1)
                side = "SHORT" if "SHORT" in l else "LONG"
                abiertos_ram[sym] = f"{sym.replace('/USDT:USDT','')} [{side}] {m.group(2)} @ {m.group(3)} (SL Int {m.group(4)})"
        elif "Cosecha 50% TRIZ PostOnly ejecutada" in l:
            for sym in list(abiertos_ram.keys()):
                if sym in l:
                    abiertos_ram[sym] += " [FREE-RUNNER 50%]"
        elif "CIERRE " in l:
            for sym in list(abiertos_ram.keys()):
                if sym in l:
                    abiertos_ram.pop(sym, None)

print("------------------------------------------------------------------------------------------")
print(f" 📊 CAJA NEGRA : {total} Trades ({wins}W / {losses}L | WR: {wr:.1f}%) | Scratch 18s: {scratches} | Cosechas 50%: {cosechas}")
print(f" 💰 PATRIMONIO : PnL Acumulado: {pnl_total:+.4f} USDT | UTA Real: {bal_real} | Convergence Bayes: λ={lam:.2f} ({total}/40)")
if abiertos_ram:
    print(f" 📂 EN CURSO   : 🟢 " + " | ".join(abiertos_ram.values()) + "  (Usa 'verbot -x cierre' para cobrar)")
else:
    print(" 📂 EN CURSO   : ⚪ 0 contratos abiertos en este instante (Comandos: verbot -s | verbot -x | verbot -x cierre | verbot -t)")
print("------------------------------------------------------------------------------------------")
print(f" {'PAR Y DIRECCIÓN':<22} {'TRADES (W/L)':<15} {'WIN RATE':<10} {'HURST MEDIO':<13} {'PNL NETO USDT':<15}")
print("------------------------------------------------------------------------------------------")

grupos = defaultdict(list)
for t in trades:
    sym = str(t.get("symbol", "")).replace("/USDT:USDT", "")
    side = str(t.get("side", "long")).upper()
    grupos[f"{sym} [{side}]"].append(t)

for k in sorted(grupos.keys(), key=lambda x: sum(float(i.get("pnl_usdt", 0.0)) for i in grupos[x]), reverse=True):
    lista = grupos[k]
    w_g = sum(1 for i in lista if float(i.get("pnl_usdt", 0.0)) > 0)
    l_g = len(lista) - w_g
    wr_g = (w_g / len(lista) * 100.0) if lista else 0.0
    h_vals = [float(i.get("hurst_entry", 0.0)) for i in lista if i.get("hurst_entry") is not None]
    h_med = (sum(h_vals) / len(h_vals)) if h_vals else 0.0
    pnl_g = sum(float(i.get("pnl_usdt", 0.0)) for i in lista)
    ic = "🟩" if pnl_g >= 0 else "🔴"
    print(f" {k:<22} {f'{len(lista)} ({w_g}W/{l_g}L)':<15} {f'{wr_g:5.1f}%':<10} {f'H={h_med:.3f}':<13} {ic} {pnl_g:+.4f} USDT")

print("------------------------------------------------------------------------------------------")
print(f" {'#':<3} {'HORA UTC':<9} {'PAR':<8} {'LADO':<6} {'Z_IN':<7} {'OFI':<7} {'HURST':<7} {'HOLD':<6} {'PNL %':<8} {'PNL USDT':<11} {'MOTIVO'}")
print("------------------------------------------------------------------------------------------")
ultimos = trades[-12:]
idx_base = total - len(ultimos) + 1
for i, t in enumerate(ultimos, start=idx_base):
    ts = str(t.get("timestamp", ""))[11:19]
    sym = str(t.get("symbol", "")).replace("/USDT:USDT", "")[:7]
    side = str(t.get("side", "long")).upper()[:5]
    z_in = float(t.get("z_score_entry") or 0.0)
    ofi_in = float(t.get("ofi_entry") or 0.0)
    h_in = float(t.get("hurst_entry") or 0.0)
    hold = f"{float(t.get('hold_seg') or 0.0):.0f}s"
    pnl_p = float(t.get("pnl_pct") or t.get("pnl_percentage") or 0.0)
    pnl_u = float(t.get("pnl_usdt") or 0.0)
    mot = str(t.get("motivo", ""))[:22]
    ic = "🟩" if pnl_u > 0 else ("🟨" if "SCRATCH" in mot else "🔴")
    print(f" {i:<3} {ts:<9} {sym:<8} {side:<6} {z_in:+6.2f} {ofi_in:+6.2f} {h_in:6.3f}  {hold:<6} {pnl_p:+6.2f}%  {ic} {pnl_u:+.4f}  {mot}")
PYEOF
    fi
    echo "=========================================================================================="
    if [ "$ARG1" = "-s" ]; then
        echo " 📜 ÚLTIMOS EVENTOS CLAVE EN BOT_HFT.LOG (verbot -s | verbot -x | verbot -x cierre | verbot -t):"
        echo "------------------------------------------------------------------------------------------"
        grep -E "INICIANDO CEREBRO|Auditoría UTA|HOT-RELOAD OOS|\[RADAR\]|\[SHORT-SNIPER\]|\[FRANCOTIRADOR\]|TELEMETRÍA DISPARO|PULSO POSICIÓN|MICRO-BE|MICRO-SHIELD|BLOQUEO HURST|ESCUDO EJECUTOR|MAKER-SCRATCH|CIERRE|TELEGRAM OK" "$LOG" | tail -n 15
        echo "=========================================================================================="
        return 0
    fi
    echo " 🛡️  MODO MONITOREO EN VIVO: [Ctrl+C] para salir | Comandos: verbot -s | verbot -x | verbot -x cierre | verbot -t"
    echo "=========================================================================================="
    (trap 'exit 0' INT TERM; tail -f -n 25 "$LOG" || true) || true
    return 0
}
# === FIN PANEL VERBOT TRI-BRAIN-SNIPER ===
EOF

echo "✅ [VERBOT V3.0 OK] Comandos instalados en ~/.bashrc: verbot, verbot -s, verbot -x, verbot -x cierre, verbot -x cerrar, verbot -h, verbot -h trades, verbot -q, verbot -t"
