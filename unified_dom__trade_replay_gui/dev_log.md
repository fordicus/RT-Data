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

→ Generalize the pipeline to support **arbitrary tick data files** (passed as arguments).

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
./uvicorn backend.app:app --reload
```

→ FastAPI runs at:
[`http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17`](http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17)

* Start frontend:

```bash
./frontend/npm run dev
```

→ Frontend runs at:
[`http://localhost:5173`](http://localhost:5173)

---

## ⚠️ Caution

- **Timestamp Handling** (`backend/loader.py`):  
  Convert raw CSV `timestamp` values from milliseconds to seconds via:  
  `df["time"] = df["time"] / 1000`  
  This preserves millisecond-level precision in `float` format,  
  as required by Lightweight Charts™.  
  Note that **no timezone or localtime conversion** occurs in the backend.  
  All `time` values are passed as raw UNIX timestamps in seconds.  
  The frontend--via `Date(time * 1000)`--handles local-time conversion for rendering.


- **Duplicate timestamps (ms)** (`backend/loader.py`):  
  If multiple entries share the same timestamp,  
  aggregate buy and sell volumes separately, then subtract:  
  `volume = abs(buy - sell)`, `side = direction of the net flow`.  
  This filters out zero-sum scenarios and emphasizes net price actions.


---

Last updated: 2025-05-20
Prepared in alignment with `Plan01.md` and folder structure `REPO_STRUCT.html`


---
