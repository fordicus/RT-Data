**📄 Plan04 – Symbol-Aware Autoloading for Dynamic Chart-DOM Visualization**

---

## 🎯 Goal

Enable the visualization system to dynamically recognize and visualize any pair of
tick (.csv) and DOM (.data) files based solely on their presence and naming structure
within a predefined folder (`./data/`), without requiring hardcoded filenames or CLI input.

This plan eliminates hardcoded assumptions and prepares the pipeline for scalable
multi-symbol replay and future UI-based dataset selection (Plan05).

---

## 🧠 Key Assumptions

* Folder `./data/` exists under project root and contains exactly one `.csv` and one `.data` file.
* Filenames encode both `symbol` and `date` in the following formats:

  * Tick file:   `{SYMBOL}_YYYY-MM-DD.csv`
  * Orderbook file: `YYYY-MM-DD_{SYMBOL}_ob200.data`
* The `SYMBOL` extracted from both filenames must match.

---

## 🛠️ Modified Components

### 🔧 backend/app.py

* `@app.on_event("startup")` scans the `./data/` directory for matching files.
* Validates presence and structural integrity of file pair.
* Automatically loads tick and DOM data into memory.
* Extracted `symbol` and `date` are used by new endpoint:

```python
GET /api/meta
→ { "symbol": "UNIUSDC", "date": "2025-05-17" }
```

* All other API routes (`/api/tick`, `/api/orderbook`) now consume this in-memory context.

---

### 🔧 frontend/main.ts

* Removed all hardcoded `symbol`, `date` references.
* On startup, fetches `/api/meta` to determine symbol/date pair.
* Uses them to dynamically construct:

  * `/api/tick?symbol=...&date=...`
  * `/api/orderbook?symbol=...&date=...&time=...`
* `globalSymbol` is included in the tooltip text.

---

### 🔧 \_run\_reply\_gui.bat

* No longer needs to pass arguments.
* Assumes fixed working directory:
  `C:\workspace\RT-Data\chart_dom_replay_gui`
* Automatically picks up the correct file pair inside `data/`.

---

## 🔚 Outcome

✔ One-line launch via batch script
✔ Symbol and date correctly inferred from filenames
✔ Frontend remains agnostic to underlying filenames
✔ Ready for Plan05: UI-based file selector

---
