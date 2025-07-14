# Plan01 – Python FastAPI + TypeScript (Lightweight Charts) Replay Stack

> **Test‑Expand workflow** — each stage must compile & pass tests before moving on. Wait for user confirmation ✔️ before proceeding to the next stage.

---

## 0 Scope & Guiding Principles

| Item                   | Decision                                                             |
| ---------------------- | -------------------------------------------------------------------- |
| **Goal**               | Interactive replay of ByBit tick‑trades & (later) order‑book data.   |
| **Backend**            | **Python 3.11 + FastAPI + pandas** (CSV/NDJSON loader)               |
| **Frontend**           | **TypeScript + Vite** bundler + Lightweight Charts v4                |
| **Transport**          | REST (`/api/tick?symbol=UNIUSDC&date=2025‑05‑17`) returns JSON array |
| **Viewport**           | Left = tick price line + marker layer<br>Right = HTML table tape     |
| **Performance target** | ≥ 60 FPS with ≤ 100 k points, initial load ≤ 1 s                     |
| **Testing style**      | Unit (pytest), API (HTTPX), e2e (Playwright)                         |

---

## 1 Milestone Roadmap (High‑Priority only)

| Stage       | Deliverable                                                                                | Tests (expand)                                             |
| ----------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| **1‑A**     | *Backend loader*<br>`load_trades(path)` → `DataFrame` with `time: float`, sorted by `time` | pytest: read sample CSV, assert shape > 0 & monotonic time |
| **1‑B**     | *FastAPI endpoint* `/api/tick` returns list `[{time: float, value, side, volume}]`         | HTTPX: GET returns 200 & len>0                             |
| **2‑A**     | *Frontend scaffold* via Vite + TS + LW Charts                                              | vite build passes; blank chart renders ✔️                  |
| **2‑B**     | *Fetch & render* tick line; markers colored by `side`                                      | Playwright: first point y==price\[0]                       |
| **3‑A**     | *Playback controls* (Play/Pause, Speed 1‑10×)                                              | Unit: timer interval adjusts; UI buttons enabled           |
| **3‑B**     | *Trade tape table* right pane, sync scroll                                                 | Playwright: clicking play increments both views            |
| **4 Smoke** | One‑day UNIUSDC replay at 5×, no drift ≥ 10 min                                            | Manual acceptance ✔️                                       |

---

## 2 Folder Structure Draft

```
backend/
├─ app.py         # FastAPI entry‑point
├─ loader.py      # pandas helpers
└─ tests/
    └─ test_api.py
frontend/
├─ index.html
├─ main.ts        # LW chart + fetch logic
├─ tape.tsx       # React / Preact table (optional)
└─ tests/
    └─ e2e.spec.ts
```

---

## 3 Testing Strategy (Test‑Expand)

1. **Unit** – loader converts ≤1 MB CSV in <200 ms.
2. **API** – `/api/tick` latency <50 ms (localhost).
3. **Integration** – chart renders first 100 ticks without console error.
4. **Performance smoke** – 100 k points draw in <1 s.

---

## 4 Future Enhancements (deferred)

* OrderBook NDJSON sync (`/api/dom`), depth overlay.
* On‑chain Liquidity Flow alignment.
* Export replay to GIF/MP4.

---

*Last updated 2025‑05‑20 – prepared by ChatGPT.*
