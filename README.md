# ⚡ TRI-BRAIN-SNIPER (Skill Hunter) V4.0

**Sistema Cuantitativo de Ejecución Microestructural HFT Maker-First (`VERSION_SISTEMA = "4.0.0"`)**
Estrategia Base: **CHRONOS-TRIZ** + **Escalera Convexa de 3 Tiradas (50% / 25% / 25% — Chain-Jail Biclase V4.0)** + **Enjambre Cognitivo Asíncrono Tri-Córtex $\mathcal{O}(1)$**.

---

## 1. Novedades y Mejoras Estructurales en V4.0

### 1.1. Arquitectura de Salida Convexa en 3 Tiradas (50% / 25% / 25% — Chain-Jail Biclase V4.0)
Calibrada sobre las 3 Olas Microestructurales empíricas ($Q_{50}, Q_{80}, Q_{95}$) para maximizar la tasa de crecimiento geométrico de Kelly-Shannon ($g^*$):

| Etapa / Eslabón | Condición de Activación | Acción Automática del Gestor | Protección y Piso SL |
| :--- | :--- | :--- | :--- |
| **1ra Tirada (50% Lote)** | $\text{PnL} \ge +0.24\%$ (`+0.26%` en modo Test) | Vende el 50% en `Limit PostOnly` (`reduceOnly=True`), financia el 100% de las comisiones y apaga el reloj límite de 90s. | Sube el SL en Bybit a Break-Even positivo (`+0.02%`) con colchón de oxígeno. |
| **2da Tirada (25% Lote)** | $\text{PnL} \ge +0.48\%$ | Vende la mitad del remanente (25% del total) tras validar divisibilidad 4x (`min_qty` y `min_notional`). Consolida el 75% en efectivo. | Activa el modo `CHAIN-JAIL` sin límite de tiempo sobre el último 25%. |
| **Eslabón 0/5 (Oxígeno)** | $+0.48\% \le \text{Max PnL} < +0.72\%$ | Absorbe el micro-rebote técnico entre la Ola 1 y la Ola 2 sin estrangular la posición. | Piso SL asegurado en **`+0.18%`**. |
| **Eslabón 1/5 (Candado Ola 2)** | $\text{Max PnL} \ge +0.72\%$ | Traba el candado sobre el último 25% en el precio de la 2da tirada. | Piso SL mínimo en **`+0.48%`** (distancia `0.24%`). |
| **Eslabón 2/5 (Escudo Ola 3)** | $\text{Max PnL} \ge +1.25\%$ | Asegura casi $+1.00\%$ neto sobre el tramo final. | Piso SL mínimo en **`+0.95%`** (distancia `0.30%`). |
| **Eslabón 3/5 (Techo Tier-1)** | $\text{Max PnL} \ge +1.85\%$ | **Guillotina TP automática para activos `CLASE_TIER1_LIQUIDO`** (`INJ`, `XRP`, `AVAX`, `TAO`, `ARB`). En `HIGH_BETA` continúa escalando. | Piso SL mínimo en **`+1.55%`** (distancia `0.30%`). |
| **Eslabón 4/5 (Compresión HB)** | $\text{Max PnL} \ge +2.80\%$ | Captura corridas parabólicas en `CLASE_HIGH_BETA` (`ZEREBRO`, `WAL`). | Piso SL mínimo en **`+2.45%`** (distancia `0.35%`). |
| **Eslabón 5/5 (Guillotina HB)** | $\text{Max PnL} \ge +5.50\%$ (`+8.00%` en Test) | Liquidación total inmediata en el clímax de euforia (`CHAIN_JAIL_TP_8PCT`). | Posición 100% consolidada en USDT en Bybit UTA. |

### 1.2. Las 5 Correcciones Forenses de Producción Incorporadas en V4.0
1. **Guardia `Zero-Orphan` en Cosechas y Cierres (`gestor_posiciones.py`):** Verifica el estado de las órdenes `PostOnly` parciales antes de descontar contratos en RAM y concilia contra `fetch_positions` al cerrar para garantizar **0 contratos remanentes huérfanos** en Bybit UTA.
2. **Normalización de Edad en Reconciliación de Arranque (`main.py` y `stats_tracker.py`):** Corrige la lectura de `createdTime` histórico en cuentas One-Way de Bybit y sanea automáticamente cualquier `hold_seg > 86400s` en `tribrain_stats_v1.jsonl`.
3. **Des-saturación de Hurst en Frenos Físicos Confirmados (`radar_volatilidad.py`):** Elimina el falso bloqueo `H=0.800` tras barridos monotónicos cuando la segunda derivada de Lyapunov ($a_{\text{Lyap}} \ge -0.005\%$) certifica que la caída ya frenó, y evalúa Hurst en `SHORT-SNIPER` antes de emitir el log de aprobación del radar.
4. **Enfriamiento Post-Reconexión WebSocket (`radar_volatilidad.py`):** Otorga `3.5s` de enfriamiento tras cualquier `RequestTimeout` de ping-pong para evitar falsas alarmas de `CIRCUIT BREAKER CONTAGIO`.
5. **Sincronización OOS y Contabilidad de Scratch (`evaluador_cuantico_oos.py`):** Mantiene sincronizados los umbrales de producción (`+0.24%` cosecha, `0.10` OFI, `3.8s` TTL) tras cada recarga en caliente.

---

## 2. Suite de Comandos Operativos y Tácticos (`verbot` V4.0)

| Comando | Función Operativa en `sniper-tokio` y Telegram |
| :--- | :--- |
| **`verbot`** | Monitoreo en vivo de `bot_hft.log` (aislado con `Ctrl+C` seguro mediante `trap 'exit 0' INT TERM`). |
| **`verbot -s`** | Resumen contable de la Caja Negra (Win Rate, PnL, Scratch 18s, desglose por par y últimas 10 operaciones). |
| **`verbot -x`** | Radar Chain-Jail en vivo: muestra ganancia actual, ROE y eslabón en consola y envía reporte a Telegram sin cerrar. |
| **`verbot -x cerrar`** | Cobro Manual Instantáneo: cancela órdenes abiertas, cierra a mercado (`reduceOnly=True`) los contratos abiertos y notifica en Telegram. |
| **`verbot -h trades`** | Filtra el historial mostrando únicamente disparos, cosechas, trinquetes y cierres. |
| **`verbot -q`** | Ejecuta el Evaluador Cuántico Walk-Forward OOS y muestra el reporte Markdown (`reporte_cuantico_oos.md`). |
| **`verbot -t`** | Reenvía manualmente a Telegram el último cierre registrado en la Caja Negra (`tribrain_stats_v1.jsonl`). |

---

## 3. Topología Inmutable y Certificación de Calidad (18/18)
* **15 Archivos Canónicos:** 11 módulos Python en Grafo Acíclico Dirigido (DAG) + 4 artefactos de infraestructura (`.gitignore`, `requirements.txt`, `instalar_infraestructura.sh`, `README.md`).
* **Contrato AST:** Exactamente **100 constantes globales únicas** en `config_parametros.py`, codificación **UTF-8 sin BOM** y saltos de línea Unix (**LF**).
