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

Ongoing Progress: 2025-05-21

현재 우리는 **호버 시에만 로컬 타임존이 적용된 `YYYY-MM-DD hh:mm:ss.fff` 형식의 타임스탬프**를 렌더링하고 있습니다. 하지만 **차트 하단(x축)에 표시되는 시각은 다음 두 가지 문제가 있습니다**:

1. 로컬 타임존으로 변환되지 않았고,
2. `"YYYY-MM-DD hh:mm:ss.fff"` 형식의 출력 규칙을 따르지 않고 있습니다.

* 차트 하단의 시각 표시를 **"YYYY-MM-DD hh\:mm\:ss.fff" 전체 포맷으로 출력**하고
* 수직 방향(vertical orientation)으로 렌더링되도록 하고 싶습니다.

해당 작업은 프론트엔드의 책임이므로, 다음 파일에 적용하는 것이 적절합니다:

```
RT-Data\unified_dom__trade_replay_gui\frontend\src\main.ts
```
(lightweight-charts\@4.1.1의 공식 문서를 기준으로 검토 바랍니다)

---
