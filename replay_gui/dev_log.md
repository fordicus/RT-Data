# 📜 Developer Log – RT-Data Frontend/Backend Sync Project

## 📁 Attached Files & Reference Links

```text
AI-RnD-Kit/
└── RULESET.md

replay_gui/
├── dev_log.md
├── REPO_STRUCT.html
├── dump_tick.json
├── dump_dom.json
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

* [`dev_log.md`](https://github.com/fordicus/RT-Data/blob/main/chart_dom_replay_gui/dev_log.md)
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
```

## 🧩 Node (Frontend)

```bash
npm create vite@latest frontend -- --template vanilla-ts
cd frontend
npm install
npm install lightweight-charts@4.1.1 --save
# vite@6.3.5 is installed via `npm create vite`
```

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

## 📆 Completed Milestones

### 🧩 Plan02 – Backend Alignment (2025-05-21)

* `loader.py` loads both tick and DOM NDJSON
* DOM is normalized per tick using most recent snapshot ≤ tick timestamp
* Preloading with `aligned_cache` ensures fast lookup in FastAPI
* Backend `/api/orderbook` returns subsecond results
* `"N/A"` fallback returns as expected for unmatched tick timestamps
* `curl` confirms JSON dump consistency and latency

```bash
curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" -o dump_tick.json
curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747442146.179" -o dump_dom.json
```

---

### 🎯 Plan03 – Dual-Pane Time-Synchronized Replay (Completed 2025-05-23)

Plan03 focused on frontend expansion: a dual-chart system where the right pane visualizes DOM (order book) data in sync with the left-side execution chart.

✅ Completed Components:

* Hover-based DOM fetching is implemented using `subscribeCrosshairMove()`
* DOM fetch is suppressed on click (via `isClickSuppressed` mechanism)
* Right-side pane mirrors DOM tooltips and shows live canvas-rendered depth
* DOM snapshot fetches only on hover (not click), following Plan03 policy
* Lightweight-charts\@4.1.1 handles rendering; local time correctly shown
* DOM canvas respects tick timestamp alignment with sub-ms resolution
* `main.ts`, `app.py`, `loader.py` are fully documented and aligned
* Execution & DOM replay now scientifically inspectable via canvas & overlay

---

## 🛠 Notes on Tooling

* `vite.config.ts`: explicitly resolves `/src/` and ensures live reload
* `tsconfig.json`: strictly scoped to `frontend/src`, stripped to minimum
* All frontend logic lives in `main.ts`, loaded via `index.html`
* FastAPI and Vite dev servers must be launched in parallel for full stack

---

## 📌 Future TODO

Currently tested only with a specific file:
`UNIUSDC_2025-05-17.csv`

→ Generalize the pipeline to support **arbitrary tick data files** (passed as arguments)

→ Parameterize input to dynamically support symbol and date across all components

→ Allow agent training to feed data back into the canvas in closed loop simulation

---
