# Development Log (Backend + Frontend Replay Stack)

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

→ Generalize the pipeline to support **arbitrary tick data files**
(passed as arguments).

---

## ✅ Stage 1‑A: Backend Loader Unit Test

```bash
pytest backend/tests/test_loader.py
```

---

## ✅ Stage 1‑B: FastAPI Live Test

```bash
uvicorn backend.app:app --reload
```

Verify in browser or via curl:

[`http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17`](http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17)

---

## ✅ Stage 2‑A: Frontend Scaffolding

```bash
npm create vite@latest frontend -- --template vanilla-ts
cd frontend
npm install
npm install lightweight-charts@4.1.1 --save
```

---

## ✅ Stage 2‑B: Connect Chart to API

* Overwrite:
  `frontend/index.html` and `frontend/src/main.ts`

* Start backend:

```bash
uvicorn backend.app:app --reload
```

→ FastAPI runs at:
[`http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17`](http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17)

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
  The frontend--via `Date(time * 1000)`--handles local-time conversion for rendering.

* **Duplicate timestamps (ms)** (`backend/loader.py`):
  If multiple entries share the same timestamp,
  aggregate buy and sell volumes separately, then subtract:
  `volume = abs(buy - sell)`, `side = direction of the net flow`.
  This filters out zero-sum scenarios and emphasizes net price actions.

---

## ✅ Stage 2‑C: Enhanced Chart UX (2025-05-21)

Today’s enhancements complete the local-time rendering overhaul and introduce
interactive features for better price navigation:

### ✅ Completed:

* All timestamps are now rendered in **local time (browser-based)**.

* **tickMarkFormatter** on x-axis dynamically switches between:

  * `"YYYY-MM-DD"` at daybreak
  * `"hh:mm:ss"` otherwise

* Implemented **hover tooltip** with:

  * Local timestamp (`YYYY-MM-DD hh:mm:ss.fff`)
  * price, volume, side

* Implemented **click-to-lock time\_cursor**:

  * Clicking the chart sets `time_cursor` at the selected tick
  * `time_cursor` shows:

    * a **fixed-position tooltip** (same format as hover)
    * a **red circle marker** on the line chart

---

## 🧭 TODO (2025-05-21): Dual Chart-Based DOM Visualization Plan

Dual chart-based one-way time-synchronized order book rendering will be 
implemented by independently creating two `createChart()` instances: 
the left for the time-series trade chart, and the right for the order book 
depth chart. These two charts will be arranged side-by-side using CSS Flexbox.

Mouse interaction will be handled exclusively by the left chart. The event 
`subscribeCrosshairMove()` will be used to obtain `param.time` and 
`param.point.x`, which are then used to one-way synchronize the right chart by 
calling `timeScale().setVisibleLogicalRange(...)` and 
`chart.setCrosshairPosition(...)`. Simultaneously, the frontend will request 
a DOM snapshot via `/api/orderbook?time=...`, and the response will be 
converted into a depth visualization using `HistogramSeries` or 
`LineSeries` with `setData()`.

Both charts must share identical options such as `timeVisible: true` and 
`timeZone: 'local'` to maintain visual consistency. To minimize latency, 
the order book responses should be cached on the client side to avoid 
redundant API fetches for already visited timestamps.

This architecture is fully feasible under Lightweight Charts v4.1.1. 
The implementation approach aligns closely with the official tutorial 
["Set crosshair position"](https://tradingview.github.io/lightweight-charts/tutorials/how_to/set-crosshair-position), 
which serves as the most reliable reference for this feature.

---


Last updated: 2025-05-21
Prepared in alignment with `Plan01.md` and folder structure `REPO_STRUCT.html`

---
