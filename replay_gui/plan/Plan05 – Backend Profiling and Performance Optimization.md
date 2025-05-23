# 📈 Plan05 – Backend Profiling and Performance Optimization

This plan investigates and resolves performance bottlenecks in the backend 
of the DOM replay visualization stack, especially when processing high-frequency 
tick and order book data (e.g., BTCUSDT full-day logs).

---

## 🔍 Motivation

While the system operates correctly for small-scale test cases (e.g., UNIUSDC),
it demonstrates substantial latency when dealing with large symbols such as BTCUSDT.

Empirical observation:
- System resource usage remains low during data ingestion.
- No CPU or memory spikes observed in Windows System Manager.
- Indicates suboptimal computation (e.g., inefficient loops, Python overhead).

---

## 🔬 Suspected Bottlenecks (in ranked order)

| Function                     | Location         | Risk Level | Description |
|-----------------------------|------------------|------------|-------------|
| `align_orderbook_to_ticks()`| `loader.py`      | 🔴 High     | Performs repeated bisection over sorted list; could be replaced with `O(n+m)` scan. |
| `load_orderbook()`          | `loader.py`      | 🟠 Medium   | Involves cumulative parsing, sorting, possibly redundant filtering. |
| Pandas Serialization        | `app.py` (GET)   | 🟡 Low      | Relevant only under heavy concurrent load, less likely root cause. |

---

## 🧪 Step-by-Step Plan

### P1. Insert Timing & Logging Hooks
- ✅ Add `time.perf_counter()` around:
  - `load_trades()`
  - `load_orderbook()`
  - `align_orderbook_to_ticks()`
- ✅ Print duration per function to stdout on `startup`.

### P2. Analyze `align_orderbook_to_ticks()` Complexity
- Consider replacing `bisect_right` loop with **two-pointer scan**.
- Benchmark both approaches on synthetic large-scale data.

### P3. Consider `merge_asof()` (Vectorized Alternative)
- If both tick and DOM snapshots are converted to `pd.DataFrame`,
  try `pd.merge_asof()` with direction='backward'.
- Compare output accuracy and performance.

### P4. Optional: Async Initialization (Low Priority)
- Investigate whether FastAPI startup can offload heavy loading
  to background threads without blocking `/api` endpoints.

---

## 🛠 Profiling Tools

| Tool               | Purpose                       |
|--------------------|-------------------------------|
| `time.perf_counter()` | Inline function timing        |
| Windows Task Manager | System-level CPU/Memory usage |
| `cProfile` + `snakeviz` | Fine-grained function profiling |

---

## 🧪 Future Considerations

- Add CLI option to preload only a subset of data (e.g., time window).
- If `load_orderbook()` proves heavy, switch NDJSON to binary format.
- Enable symbol/date pair switching without full reload (Plan06?).

---

## ✅ Deliverables

- Per-function benchmark output (for different symbols)
- One optimized implementation (bisect vs. scan)
- Profiling summary snapshot (optional)
