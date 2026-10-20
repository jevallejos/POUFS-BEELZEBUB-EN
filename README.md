# ⛓️ TRI-BRAIN-SNIPER (Skill Hunter) V3.0

Motor autónomo de ejecución microestructural de alta frecuencia (**HFT Maker-First**) sobre **Bybit Unified Trading Account (UTA V5)**, gobernado en tiempo constante $\mathcal{O}(1)$ (`~0.41 µs`) por un enjambre cognitivo asíncrono **Tri-Córtex** (**Groq LPU + Google Gemini + NVIDIA NIM**) y el protocolo de salida convexa asimétrica **`Chain-Jail (50 / 25 / 25)`**.

---

## 🚀 Novedades de la Versión `v2.0 (Chain-Jail)`

1. **Arquitectura de Salida Convexa en 3 Tiradas (`50% / 25% / 25%`)**:
   - **1ra Tirada (`50%` en `+0.26%`)**: Cubre el 100% de las comisiones de ida y vuelta en tarifa *Maker* (`0.020%`) y asegura flujo de caja inmediato.
   - **2da Tirada (`25%` en `+0.55%`)**: Cosecha el segundo cuarto al finalizar el primer impulso de liquidación, consolidando el **`75%`** de la posición en efectivo.
   - **3ra Tirada (`25%` en `CHAIN-JAIL` hasta `+8.00%` sin límite de tiempo)**: El último `25%` de los contratos queda exento del reloj de `90 segundos` y encadenado a una escalera de **6 Eslabones Automáticos** respaldados en el Stop-Loss nativo de los servidores de Bybit (`MarkPrice`):
     - **Eslabón 0 (`+0.55%` a `+0.89%` — Zona de Oxígeno)**: Freno en **`+0.15%`** para absorber el micro-rebote técnico sin asfixiar la posición.
     - **Eslabón 1 (`>= +0.90%` — Candado `+0.55%`)**: El freno sube y se clava en **`+0.55%`** (cero retroceso respecto a la segunda tirada).
     - **Eslabón 2 (`>= +1.60%` — Escudo Tier-1)**: Freno clavado en **`+1.15%`** (persecución dinámica a `0.45%` de distancia).
     - **Eslabón 3 (`>= +2.55%` — Meta +2% Extra)**: Freno clavado en **`+2.20%`** (persecución comprimida a `0.35%` de distancia).
     - **Eslabón 4 (`>= +4.50%` — Hiper-Compresión)**: Persecución ultra-estrecha a **`0.25%`** detrás del máximo alcanzado.
     - **Eslabón 5 (`>= +8.00%` — Guillotina Take-Profit Duro)**: Liquidación total inmediata en el pico de euforia (`+8.00%` puro / `+24.00% ROE` a `3x`).

2. **Nuevos Comandos Tácticos en Consola y Telegram (`verbot -x`)**:
   - `verbot -x`: Inspecciona en vivo las posiciones abiertas en Bybit UTA, calcula el `%` de ganancia actual, el eslabón `Chain-Jail` (`0/5` a `5/5`) y **envía instantáneamente una alerta a Telegram con la fotografía en vivo sin cerrar la operación**.
   - `verbot -x cerrar`: Cancela órdenes abiertas y **cobra a mercado (`reduceOnly=True`) el 100% de los contratos abiertos en menos de 1 segundo**, enviando el recibo de consolidación a Telegram.

3. **Calibración Táctica de Frecuencia (Opción B Cero-Ruido)**:
   - Umbrales $Z\text{-Score}$ Bipower ajustados a **`-2.85`** (`High-Beta`) y **`-2.55`** (`Tier-1`), manteniendo intacta la confirmación de **3 ticks consecutivos de `ML-OFI` (`450 ms`)**, el **Exponente de Hurst ($H \le 0.490$)**, el **Repulsor de Lyapunov**, el **`Maker-Scratch` a los `18s`** y el disparo simétrico **`SHORT-SNIPER`**.

---

## 🛠️ Comandos Operativos en Producción (`sniper-tokio`)

| Comando | Acción |
| :--- | :--- |
| `verbot` | Monitoreo en vivo de `bot_hft.log` (aislado con `Ctrl+C` seguro). |
| `verbot -s` | Resumen contable de la Caja Negra (`Win Rate`, `PnL`, `Scratch 18s`, últimas 10 operaciones). |
| `verbot -x` | **Radar Chain-Jail en vivo**: muestra ganancia actual en consola y **envía reporte a Telegram sin cerrar**. |
| `verbot -x cerrar` | **Cobro Manual Instantáneo**: cierra a mercado (`reduceOnly=True`) los contratos abiertos y notifica en Telegram. |
| `verbot -h trades` | Filtra el historial mostrando únicamente disparos, cosechas, trinquetes y cierres. |
| `verbot -q` | Ejecuta el Evaluador Cuántico Walk-Forward OOS y muestra el reporte Markdown. |
| `verbot -t` | Reenvía manualmente a Telegram el último cierre registrado en la Caja Negra. |
