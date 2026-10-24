# POUFS-BEELZEBUB-EN (Spiritual Message) V5.0

**Maker-First HFT Microstructural Quantitative Execution System (`VERSION_SISTEMA = "5.0.0"`)**
Core Strategy: **CHRONOS-TRIZ** + **3-Tranche Convex Exit Ladder (50% / 25% / 25% -- Bi-Class Chain-Jail V5.0)** + **Asynchronous $\mathcal{O}(1)$ Tri-Cortex Cognitive Swarm**.

---

## 1. Architectural Upgrades & Structural Innovations in V5.0

### 1.1. 3-Tranche Convex Exit Architecture (50% / 25% / 25% -- Bi-Class Chain-Jail V5.0)
Calibrated across the 3 empirical microstructural waves ($Q_{50}, Q_{80}, Q_{95}$) to maximize the Kelly-Shannon geometric growth rate ($g^*$):

| Stage / Chain Link | Activation Condition | Automated Position Manager Action | Protection & SL Floor |
| :--- | :--- | :--- | :--- |
| **Full-Maker Harvest (Moderate Flow)** | $\text{PnL} \ge +0.24\%$ (`+0.26%` in Test mode) with $\|\text{OFI}\| < 0.65$ or $\text{age} \ge 25\text{s}$ | Executes 100% `Limit PostOnly` exit (`reduceOnly=True`), locking in pure Maker fee (`0.020%`). | Arms Break-Even floor at **`+0.085%`** internal (`+0.060%` on Bybit server) prior to quoting. |
| **1st Tranche (50% Lot)** | $\text{PnL} \ge +0.24\%$ (`+0.26%` in Test mode) on explosive impulse ($\|\text{OFI}\| \ge 0.65, \text{age} < 25\text{s}$) | Sells 50% via `Limit PostOnly` (`reduceOnly=True`), funds 100% of round-trip fees, and disables the 90s hard timer. | Raises SL on Bybit to positive Break-Even (**`+0.085%`** internal / **`+0.060%`** Bybit) with breathing room. |
| **2nd Tranche (25% Lot)** | $\text{PnL} \ge +0.48\%$ | Sells half of the remaining position (25% of initial lot) after validating 4x lot divisibility (`min_qty` and `min_notional`). Consolidates 75% in cash. | Activates time-unlimited `CHAIN-JAIL` (`GHOST-RUNNER`) custody on the final 25% tranche. |
| **Link 0/5 (Breathing Room)** | $+0.48\% \le \text{Max PnL} < +0.72\%$ (or $\ge 12\text{s}$ post-1st harvest) | Absorbs technical micro-pullbacks between Wave 1 and Wave 2 without choking the trade. | Guaranteed SL floor at **`+0.18%`**. |
| **Link 1/5 (Wave 2 Lock)** | $\text{Max PnL} \ge +0.72\%$ | Locks the final 25% tranche at the 2nd tranche execution level. | Minimum SL floor at **`+0.48%`** (trailing distance `0.24%`). |
| **Link 2/5 (Wave 3 Shield)** | $\text{Max PnL} \ge +1.25\%$ | Secures nearly $+1.00\%$ net on the final runner. | Minimum SL floor at **`+0.95%`** (trailing distance `0.30%`). |
| **Link 3/5 (Tier-1 Ceiling)** | $\text{Max PnL} \ge +1.85\%$ | **Automatic TP Guillotine for `CLASE_TIER1_LIQUIDO` assets** (`INJ`, `XRP`, `AVAX`, `TAO`, `ARB`). Continues scaling in `CLASE_HIGH_BETA`. | Minimum SL floor at **`+1.55%`** (`+1.65%` Tier-1 TP, trailing distance `0.30%`). |
| **Link 4/5 (HB Compression)** | $\text{Max PnL} \ge +2.80\%$ | Captures parabolic runs in `CLASE_HIGH_BETA` (`ZEREBRO`, `WAL`). | Minimum SL floor at **`+2.45%`** (trailing distance `0.35%`). |
| **Link 5/5 (HB Guillotine)** | $\text{Max PnL} \ge +5.50\%$ (`+8.00%` in Test mode) | Immediate full liquidation at euphoria climax (`CHAIN_JAIL_TP_MAX`). | Position 100% consolidated in USDT on Bybit UTA. |

---

### 1.2. Production Forensic Hardening Incorporated in V5.0
1. **`Zero-Orphan` Guard & `retCode: 110017` Break-Even Protection (`gestor_posiciones.py`):** Verifies partial `PostOnly` fills before deducting contracts in RAM, reconciles against `fetch_positions` upon closing to guarantee **0 orphan remainder contracts** on Bybit UTA, and enforces `SCAR-LOCK-14` so `retCode: 110017` never overwrites an armed Break-Even or Maker exit as a false `SL_EXCHANGE`.
2. **Startup Age Normalization & 1:1 UTA Parity (`main.py` & `stats_tracker.py`):** Normalizes historical `createdTime` readings on Bybit One-Way accounts, auto-sanitizes any `hold_seg > 86400s` in `tribrain_stats_v1.jsonl`, and enforces 1:1 accounting parity to $10^{-4}\text{ USDT}$ against real Bybit UTA equity.
3. **Hurst De-Saturation & Elastic Band Pre-Order Gate (`radar_volatilidad.py` & `ejecutor_sniper.py`):** Eliminates false `H=0.800` lockouts after monotonic sweeps once the 2nd Lyapunov derivative ($a_{\text{Lyap}} \ge -0.005\%$) confirms physical braking, and enforces the P-02 Elastic Hurst gate prior to order dispatch.
4. **Forensic AI Cognitive Vault (`baul_ia_forense.jsonl`):** Records every pre-order shield interception (`SCAR-LOCK-01..18`) and evaluates the exact price excursion **+15.0 seconds later** in $\mathcal{O}(1)$ RAM (`CAPITAL_SAVED_TRUE_SHIELD`, `NEUTRAL_LATERAL_NOISE`, or `MISSED_OPPORTUNITY_FALSE_REJECTION`), alongside full intratrade MFE/MAE anatomy (`pnl_18s_pct`, `pnl_45s_pct`).
5. **3,456-Combination HFT Digital Twin Laboratory (`evaluador_cuantico_oos.py --lab`):** Evaluates 3,456 strategy parameter combinations across 5-Fold CPCV, 1,500 Stationary Block-Bootstrap stress trajectories, and López de Prado's Deflated Sharpe Ratio (DSR).

---

## 2. Tactical & Operational CLI Command Suite (`verbot` V5.0)

| Command | Operational Function on Production Node & Telegram |
| :--- | :--- |
| **`verbot`** | Live ANSI TrueColor stream of `bot_hft.log` (isolated with safe `Ctrl+C` via `trap 'exit 0' INT TERM`). |
| **`verbot -s`** | Black Box accounting summary (Classic & Effective Win Rate, Net PnL, 18s Scratch count, per-pair breakdown, last 10 trades, and the **+15s Forensic AI Vault** panel). |
| **`verbot -x`** | Live 3D Tactical Radar: displays current unrealized profit, ROE, and Chain-Jail link in console and dispatches a live report to Telegram without closing the position. |
| **`verbot -x close`** | Instant Manual Harvest (`verbot -x cerrar` / `close`): cancels open orders, market-closes (`reduceOnly=True`) active contracts, and sends a receipt to Telegram. |
| **`verbot -h trades`** | Filters historical logs showing exclusively shots, harvests, ratchets, and trade closes. |
| **`verbot -q`** | Runs the Quantum Walk-Forward OOS Evaluator and displays the Markdown report (`reporte_cuantico_oos.md`). |
| **`python3 evaluador_cuantico_oos.py --lab`** | Executes the 3,456-combination HFT Digital Twin Simulator (CPCV + Block-Bootstrap + DSR) and exports `reporte_lab_ia.json`. |
| **`verbot -t`** | Manually resends the last closed trade recorded in the Black Box (`tribrain_stats_v1.jsonl`) to Telegram. |

---

## 3. Immutable File Topology & Quality Certification (18/18)
* **15 Canonical Files:** 11 Python modules structured as a strict Directed Acyclic Graph (DAG) + 4 infrastructure artifacts (`.gitignore`, `requirements.txt`, `instalar_infraestructura.sh`, `README.md`).
* **AST Contract:** Strictly **100 unique top-level uppercase constants** in `config_parametros.py` (`AST_100_CONSTANTES_OK`), pure **UTF-8 without BOM**, and Unix (**LF**) line endings certified by the deterministic `[18/18]` test suite.