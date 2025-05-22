
# Plan02 – Order Book Normalization and Backend API Integration

---

## ✅ Goal: Normalize Order Book Snapshots for Tick-Based Rendering

To enable synchronized rendering between tick-based execution charts and order
book (DOM) snapshots, we adopt a normalization strategy in which each trade
tick timestamp is matched to the **most recent past order book snapshot**.

This ensures a stable one-to-one time alignment, even though executions and
order book updates are independently triggered. If no suitable DOM snapshot
exists for a tick timestamp, the system returns a placeholder:

```json
{ "time": <tick_ts>, "DOM": "N/A" }
````

---

## 🗂️ File Context

* `backend/loader.py`

  * `load_orderbook()`: parse .data into timestamp → DOM snapshot
  * `align_orderbook_to_ticks()`: map tick timestamp to snapshot
* `backend/app.py`

  * `/api/orderbook`: serve DOM aligned to tick time
  * `/api/tick`: serve trade tick stream
* Input data:

  * `data/UNIUSDC_2025-05-17.csv` – trade tick file
  * `data/2025-05-17_UNIUSDC_ob200.data` – NDJSON DOM log

Format references:

* [bybit\_execution\_format.md](https://github.com/fordicus/RT-Data/blob/main/bybit_execution_format.md)
* [bybit\_orderbook\_format.md](https://github.com/fordicus/RT-Data/blob/main/bybit_orderbook_format.md)

---

## 🚀 Implementation Summary

### `loader.py`

* ✅ `load_orderbook(path: str) -> dict[float, dict]`

  * Parses NDJSON `.data` file
  * Supports both `"snapshot"` and `"delta"`
  * Reconstructs full state `DOM[ts] = { a: [...], b: [...] }`
* ✅ `align_orderbook_to_ticks(tick_df, ob_dict) -> dict`

  * For each `tick_ts`, finds closest past `DOM_ts`
  * Fallbacks to `"N/A"` if no match

### `app.py`

* ✅ `/api/tick?symbol=...&date=...`

  * Loads tick data from cache
  * Returns JSON list of ticks

* ✅ `/api/orderbook?symbol=...&date=...&time=...`

  * On startup, caches:

    * trades → `tick_cache`
    * DOM → `orderbook_cache`
    * aligned snapshots → `aligned_cache`
  * Lookup is constant time (precomputed)
  * Returns:

    ```json
    { "time": 1747442146.179, "DOM": { "a": [...], "b": [...] } }
    ```

    or `"N/A"`

---

## 🧪 Backend Test Strategy

### Manual test via curl

```bash
# Dump all tick data
curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" -o dump_tick.json

# Fetch DOM aligned to specific timestamp
curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747442146.179" -o dump_dom.json
```

### ✅ Expected Output

1. Tick dump:

```json
[
  {
    "time": 1747442146.179,
    "value": 6.0024,
    "side": "sell",
    "volume": -5.05
  },
  ...
]
```

2. DOM snapshot:

```json
{
  "time": 1747442146.179,
  "DOM": {
    "a": [["5.10", "300.0"], ...],
    "b": [["5.09", "500.0"], ...]
  }
}
```

or:

```json
{
  "time": 1747442146.179,
  "DOM": "N/A"
}
```

---

## ⏱ Performance Result

| Endpoint         | Response Time (Before) | After Optimization |
| ---------------- | ---------------------- | ------------------ |
| `/api/tick`      | < 1s                   | ✅ < 1s             |
| `/api/orderbook` | 3.5\~4.0s              | ✅ < 1s      |

---

## 🔚 Conclusion

Plan02 is now complete with:

* 🧠 Efficient memory-cached preprocessing at server startup
* 🧪 Reproducible backend testing without frontend involvement
* 📉 Subsecond DOM delivery at arbitrary tick-aligned timestamps

→ Ready to proceed to **Plan03: Dual Chart Rendering and Frontend Sync**.
