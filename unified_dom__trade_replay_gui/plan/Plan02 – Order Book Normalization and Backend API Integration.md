# Plan02 – Order Book Normalization and Backend API Integration

---

## ✅ Goal: Normalize Order Book Snapshots for Tick-Based Rendering

To enable synchronized rendering between tick-based execution charts and order book (DOM) snapshots, we adopt a normalization strategy in which each trade tick timestamp is matched to the **most recent past order book snapshot**. This ensures a stable one-to-one time alignment, even though executions and order book updates are independently triggered and not necessarily sorted. The resulting structure enables fast API-based retrieval and seamless frontend rendering without requiring on-demand search or interpolation.

If no suitable past snapshot exists for a given tick timestamp, the system falls back to a placeholder format such as:

```json
{ "time": <tick_ts>, "DOM": "N/A" }
```

This preserves downstream consistency and enables pipeline-level filtering or placeholder logic in both frontend and model consumption layers.

---

## 📁 File Context

* `unified_dom__trade_replay_gui/backend/loader.py` – to be extended with `load_orderbook()` and `align_orderbook_to_ticks()`
* `unified_dom__trade_replay_gui/backend/app.py` – to expose `/api/orderbook?time=...` endpoint
* Input source:

  * `data/2025-05-17_UNIUSDC_ob200.data` (NDJSON DOM log)
  * `data/UNIUSDC_2025-05-17.csv` (execution log, already handled)

Reference formats:

* [bybit\_orderbook\_format.md](https://github.com/fordicus/RT-Data/blob/main/bybit_orderbook_format.md)
* [bybit\_execution\_format.md](https://github.com/fordicus/RT-Data/blob/main/bybit_execution_format.md)

---

## 🚀 Implementation Steps

1. **In `loader.py`:**

   * Add `load_orderbook(path: str) -> dict[float, dict]`:

     * Parses NDJSON order book `.data` file.
     * Handles both `"snapshot"` and `"delta"` events.
     * Reconstructs `DOM[ts] = {"a": [...], "b": [...]}` state per snapshot point.

   * Add `align_orderbook_to_ticks(tick_df, ob_dict)`:

     * For each tick timestamp, find the closest past `ts` in `ob_dict`.
     * If none found, assign `"DOM": "N/A"`; otherwise, attach the latest DOM snapshot.
     * Returns a mapping: `tick_ts → DOM`.

2. **In `app.py`:**

   * Add a new endpoint:

     ```python
     @app.get("/api/orderbook")
     def get_orderbook(time: float):
         ...
     ```

   * The handler:

     * Accepts `time` (float in seconds).
     * Uses in-memory dict or on-demand query from preloaded normalized snapshot data.
     * Returns JSON:

       ```json
       { "time": ..., "DOM": { "a": [...], "b": [...] } }
       ```

       or

       ```json
       { "time": ..., "DOM": "N/A" }
       ```

---

## 🧪 Backend-Only Test Strategy

Since frontend is not involved at this stage, we ensure correctness entirely via backend tooling:

### 1. Unit Test Coverage (suggested in `tests/test_loader.py`)

* `test_load_orderbook()`:

  * Validates parsing and reconstruction logic for `.data` file
  * Ensures `"snapshot"` resets and `"delta"` applies correctly

* `test_align_orderbook_to_ticks()`:

  * Confirms that for each tick, the correct (≤ ts) DOM snapshot is used
  * Verifies fallback `"N/A"` behavior when no past snapshot exists

### 2. Manual FastAPI curl test

After `uvicorn backend.app:app --reload`, test:

```bash
curl 'http://localhost:8000/api/orderbook?time=1715883422'
```

Expected responses:

🟢 If DOM is available:

```json
{
  "time": 1715883422,
  "DOM": {
    "b": [["5.09", "720.0"], ...],
    "a": [["5.10", "530.0"], ...]
  }
}
```

⚠️ If no past DOM exists:

```json
{
  "time": 1715883422,
  "DOM": "N/A"
}
```

---

## 🔄 Design Considerations

* **Backend-only focus** enables tight feedback on parsing and normalization logic
* **Frontend delay** is avoided by delivering DOM snapshots via pre-aligned mappings
* **Data structure predictability** supports both realtime rendering and future ML replay

---

✅ This plan finalizes all backend responsibilities for DOM integration and ensures complete testability **without frontend**, paving the way for Plan03 (frontend rendering integration).
