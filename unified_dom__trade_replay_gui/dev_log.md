# 📜 Developer Log – RT-Data Frontend/Backend Sync Project

## 📁 Attached Files & Reference Links

```text
AI-RnD-Kit/
└── RULESET.md

unified_dom__trade_replay_gui/
├── dev_log.md
├── REPO_STRUCT.html
├── dump_tick.json
├── dump_dom.json
├── plan/
│   ├── Plan02 – Order Book Normalization and Backend API Integration.md
│   └── Plan03 – Dual Chart Frontend with Synchronized DOM Snapshot.md
├── backend/
│   ├── app.py
│   └── loader.py
├── frontend/
│   ├── index.html
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       └── main.ts
└── data/
    ├── UNIUSDC_2025-05-17.csv
    └── 2025-05-17_UNIUSDC_ob200.data
````

🔗 References:

* [`dev_log.md`](https://github.com/fordicus/RT-Data/blob/main/unified_dom__trade_replay_gui/dev_log.md)
* [`bybit_execution_format.md`](https://github.com/fordicus/RT-Data/blob/main/bybit_execution_format.md)
* [`bybit_orderbook_format.md`](https://github.com/fordicus/RT-Data/blob/main/bybit_orderbook_format.md)

---
## 🐍 Python (Backend)

```bash
pip install fastapi==0.115.12
pip install "uvicorn[standard]==0.34.2"
pip install pandas==2.2.2
pip install pytest==7.4.4
pip install httpx==0.27.0
````

## 🧩 Node (Frontend)

```bash
npm create vite@latest frontend -- --template vanilla-ts
cd frontend
npm install
npm install lightweight-charts@4.1.1 --save
# vite@6.3.5 is installed via `npm create vite`
```

---

## 🔧 Future TODO

Currently tested only with a specific file:
`UNIUSDC_2025-05-17.csv`

→ Generalize the pipeline to support **arbitrary tick data files** (passed as arguments).

---

## ✅ Connect Chart to API

* Overwrite:
  `frontend/index.html` and `frontend/src/main.ts`

* Start backend:

```bash
uvicorn backend.app:app --reload
```

→ FastAPI runs at:
[`http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17`](http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17)
[`http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747524319.016`](http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747524319.016)

* Start frontend:

```bash
cd frontend && npm run dev
```

→ Frontend runs at:
[`http://localhost:5173`](http://localhost:5173)

---

## ⚠️ Caution

* **Timestamp Handling** (`backend/loader.py`):
  Convert raw CSV `timestamp` values from milliseconds to seconds via:
  `df["time"] = df["time"] / 1000`
  This preserves millisecond-level precision in `float` format,
  as required by Lightweight Charts™.
  Note that **no timezone or localtime conversion** occurs in the backend.
  The frontend--via `Date(ts * 1000)`--handles local-time conversion for rendering.

* **Duplicate timestamps (ms)** (`backend/loader.py`):
  If multiple entries share the same timestamp,
  aggregate buy and sell volumes separately, then subtract:
  `volume = abs(buy - sell)`, `side = direction of the net flow`.
  This filters out zero-sum scenarios and emphasizes net price actions.

---

## 🧠 Current Phase: Plan03

Plan03 focuses on frontend expansion: a dual-chart system where the right pane visualizes DOM (order book) data in sync with the left-side execution chart.

### ✅ So far completed (2025-05-22 기준):

* Hover-based DOM fetching is implemented using `subscribeCrosshairMove()`
* DOM fetch is suppressed on click (via `isClickSuppressed` mechanism)
* Right-side pane correctly mirrors DOM tooltips on hover
* DOM snapshot fetches only on hover (not click), following Plan03 policy
* `vite.config.ts` and `tsconfig.json` are now minimal but correctly functional
* Sub-1s API response confirmed for both `/api/tick` and `/api/orderbook`

---

## 🧱 Plan03 Breakdown & Status

| Phase | Component                                  | Goal                              | Status  |
| ----- | ------------------------------------------ | --------------------------------- | ------- |
| P1    | Hover-based DOM fetch                      | DOM loads via hover event         | ✅ Done  |
| P2    | Tooltip duplication on right pane          | Textual DOM info shown right      | ✅ Done  |
| P3    | DOM depth chart rendering                  | Histogram or LineSeries           | 🟨 TODO |
| P4    | Time axis alignment                        | Dual chart `timeZone + crosshair` | 🟨 TODO |
| P5    | `"N/A"` handling                           | Show graceful empty state         | 🟨 TODO |
| P6    | Optional toggle UI (hover ↔ click control) | Checkbox state modifies behavior  | 🟨 TODO |
| P7    | RULESET cleanup + modularization           | Final polish                      | 🟨 TODO |

---

## 🚧 Next Task: Plan03-P3 (Depth Chart Visualization)

1. Define how the DOM data structure (`{ a: [...], b: [...] }`) maps to visual series:

   * `a` (asks) → Red histogram
   * `b` (bids) → Green histogram or mirror series
2. Ensure rendering occurs only on `hover` if in `hover mode`
3. Optimize layout constraints in `index.html` and `main.ts`
4. Gracefully handle `"DOM": "N/A"` snapshot values

---

## 📆 Previous Milestones Summary

### 🧩 Plan02 Completion Recap

* `loader.py` loads both tick and DOM NDJSON
* DOM is normalized per tick using most recent snapshot ≤ tick timestamp
* Preloading with `aligned_cache` ensures fast lookup in FastAPI
* Backend `/api/orderbook` returns subsecond results

### 🔬 Verified Behavior (2025-05-20\~21)

* `curl` confirms JSON dump consistency and response time, as also mentioned in the docstring of `unified_dom__trade_replay_gui\backend\app.py`:

```bash
curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" -o dump_tick.json
curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747442146.179" -o dump_dom.json
  ```
* `"N/A"` fallback returns as expected for unmatched tick timestamps

---

## 🛠 Notes on Tooling

* `vite.config.ts`: explicitly resolves `/src/` and ensures live reload
* `tsconfig.json`: strictly scoped to `frontend/src`, stripped to minimum
* All frontend logic lives in `main.ts`, loaded via `index.html`
* FastAPI and Vite dev servers must be launched in parallel for full stack

---

## 🔚 Summary

Plan03 is progressing with stable hover-based snapshot syncing.
Next step is depth visualization on the right pane.

→ *DO NOT proceed to depth rendering without testing Plan03-P3 in isolation.*

---
