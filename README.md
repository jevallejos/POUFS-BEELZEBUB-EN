# ⚡ Tri-Brain-Sniper (Emperor Time) v1.0 — Estrategia `CHRONOS-TRIZ` + `FREE-RUNNER 50%`

Arquitectura de Trading Algorítmico de Alta Frecuencia (HFT) a **6.6 Hz (150 ms)** para **Bybit UTA (USDT Perpetual)** desplegada en Tokio (`asia-northeast1`), gobernada por las **4 Leyes Matemáticas de Dominancia Estocástica `CHRONOS-TRIZ`** y un enjambre asíncrono de tres inteligencias artificiales (**Groq LPU + Google Gemini + NVIDIA NIM**) fuera de la ruta crítica.

---

## 1. Las 4 Leyes Matemáticas del Protocolo `CHRONOS-TRIZ`

1. **Ley 1 — Invariante de Impulso Biescala y Abolición Física del `Re-Quote`**:
   - **Túnel Biclase**: Exige dislocación mínima de `-0.85%` (`EMA900 <= -1.15%`, `Z <= -3.20`) en activos *High-Beta* (`ZEREBRO`, `WAL`) y `-0.45%` (`EMA900 <= -0.55%`, `Z <= -2.85`) en activos *Tier-1* (`INJ`, `XRP`, `AVAX`, `TAO`, `ARB`).
   - **Confirmación de 3 Ticks (`450 ms`)**: Prohibido entrar por un pico aislado de 1 tick de flujo. Se exigen 3 ciclos consecutivos de absorción en `ML-OFI` L1–L5 con Exponente de Hurst antipersistente (`H <= 0.49`) y frenado físico de Lyapunov (`a >= -0.020%`).
   - **Ley de Cola de Moallemi-Yuan (`TTL = 2.20s`, `PERMITIR_REQUOTE = False`)**: Cotización pasiva `Limit PostOnly` con *Penny-Jump* (`0.020%` tarifa Maker). Si no se llena en `2.20s`, se cancela de inmediato sin perseguir el precio.

2. **Ley 2 — Desplazamiento del Precio de Reserva a los 18 Segundos (*Maker-Scratch* de Avellaneda-Stoikov)**:
   - Si al cumplir `t = 18.0s` la posición nunca superó `+0.05%` bruto y el flujo acumulado de 5 segundos es adverso (`OFI_5s <= -0.15`), el gestor evacúa la posición mediante orden pasiva `Limit PostOnly` entre `-0.04%` y `-0.14%`, evitando que se convierta en un Stop-Loss Taker.

3. **Ley 3 — Cosecha Fraccionada 50/50 TRIZ + Protocolo `FREE-RUNNER 50%` (Sin Limite de Tiempo)**:
   - **Modo Free-Runner 50%**: Una vez cobrado el primer 50% en `+0.26%`, el segundo 50% apaga los cierres por tiempo (`32s` y `90s`), fija holgura anti-ruido (`+0.05%` interno / `+0.03%` Bybit) y persigue corridas largas con Trailing Stop escalonado sincronizado en Bybit.
   - En **`+0.26%` bruto**: Vende el **50% de los contratos** vía `Limit PostOnly` (cubriendo el 100% de las comisiones de toda la operación) y sube el Stop-Loss del 50% restante al **Piso Invariante Break-Even (`+0.12%` neto)**.
   - En **`+0.38%+` y `+0.65%+`**: Activa el *Trinquete Continuo Maker* y el *Trailing Stop* sin techo artificial.
   - **Stop-Loss Quirúrgico Acotado**: `-0.48%` interno / `-0.70%` en servidor Bybit, con tiempo máximo impostergable de `90.0s`.

4. **Ley 4 — Bimodalidad Simétrica (`Long` / `Short`) y Reingeniería Funcional del Tri-Cortex**:
   - **Córtex 1 (Groq LPU — `qwen/qwen3.8-27b`)**: Clasifica cada activo cada 45s en `LONG_ONLY`, `SHORT_ONLY`, `EXTREME_Z_ONLY` o `VETO_TOXIC`.
   - **Córtex 2 (Google Gemini — `gemini-3.5-flash-lite`)**: Dimensionamiento de Kelly Convexo (Busseti-Ryu-Boyd) proporcional a la calidad física de la señal (`|Z|`, Hurst, L2) con freno Anti-Euforia y penalización por *Drawdown*.
   - **Córtex 3 (NVIDIA NIM — `deepseek-ai/deepseek-v3.2`)**: Auditoría forense Post-Loss (cuarentena de `300s`) y endurecimiento preventivo del umbral de caída en RAM.

---

## 2. Topología de Archivos del Repositorio (15 Archivos)

| # | Archivo | Rol Arquitectónico |
| :---: | :--- | :--- |
| **01** | `.gitignore` | Blindaje estricto de `.env`, `venv/`, `*.lock`, `*.log` y `*.jsonl`. |
| **02** | `requirements.txt` | Dependencias oficiales (`ccxt`, `aiohttp`, `groq`, `python-dotenv`, `uvloop`). |
| **03** | `config_parametros.py` | Fuente única de verdad (100 constantes únicas verificadas por AST + Hot-Reload OOS). |
| **04** | `core_estado_ram.py` | Memoria compartida `O(1)` (`~0.60 µs`), `@dataclass` con alias y Logger Dual (CL/UTC). |
| **05** | `telemetria_telegram.py` | Apareamiento transaccional 1:1 y garantía total de cierres (`🟩`, `��`, `🔴`, `💎`). |
| **06** | `stats_tracker.py` | Caja Negra `tribrain_stats_v1.jsonl`, paridad 1:1 Bybit UTA, `MAP`, `LVR` y velocidad `g*`. |
| **07** | `escudo_tricortex.py` | Orquestador asíncrono Tri-Cortex (Groq Régimen + Gemini Sizing + NVIDIA Forense). |
| **08** | `radar_volatilidad.py` | Radar WebSocket L2 a `6.6 Hz` (`VentanaZ` Bipower, 3 Ticks `ML-OFI`, Hurst, Lyapunov, Hawkes). |
| **09** | `ejecutor_sniper.py` | Disparo `Zero-REST` `Limit PostOnly` con *Penny-Jump*, `TTL = 2.2s` y cero `Re-Quote`. |
| **10** | `gestor_posiciones.py` | Guardián `CHRONOS-TRIZ`: *Maker-Scratch* `18s`, Cosecha 50/50 TRIZ y captura `110017`. |
| **11** | `main.py` | Cerebro Central `uvloop`, cerrojo `.tribrain.lock` y Reconciliador Automático de Arranque. |
| **12** | `evaluador_cuantico_oos.py` | Calibrador Walk-Forward (`8h/24h/72h`), Contracción Bayesiana y Dinámica del Replicador. |
| **13** | `instalar_infraestructura.sh` | Instalador `systemd` (`Nice=15`, `00:00/08:00/16:00 UTC`) y panel CLI seguro `verbot`. |
| **14** | `test_tribrain_v1_suite.py` | Suite Maestra de Certificación Integral (`18/18` pruebas deterministas). |
| **15** | `README.md` | Documentación técnica y operativa del sistema. |

---

## 3. Comandos Operativos en `sniper-tokio`

- `verbot` : Monitoreo en tiempo real de `bot_hft.log` (protegido contra `Ctrl+C`).
- `verbot -s` : Resumen contable instantáneo (`W / L / Scratch 18s / Cosechas 50% TRIZ`).
- `verbot -h` : Últimas 60 líneas del historial perpetuo `bot_hft_h.log`.
- `verbot -q` : Ejecuta bajo demanda el Evaluador Cuántico OOS y envía reporte a Telegram.
- `verbot -t` : Reenvía manualmente a Telegram el último cierre registrado en la Caja Negra.