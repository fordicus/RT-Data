# ByBit OrderBook Historical Data Explained

## 📄 File Naming Convention

```
YYYY-MM-DD_SYMBOL_ob200.data
```

**Example:**
`2025-05-09_BTCUSDT_ob200.data`

---

## ✅ Format Summary

* Each line of the file is a **complete JSON object**.
* The file is in **NDJSON (newline-delimited JSON)** format.
* Parse line-by-line using `json.loads(line)` in Python.
* This format is ideal for **time-series processing of market microstructure data**.

---

## 🧪 Example Data

### 📌 Snapshot (abridged)

```json
{
  "topic": "orderbook.200.UNIUSDC",
  "ts": 1747440000831,
  "type": "snapshot",
  "data": {
    "s": "UNIUSDC",
    "b": [["6.064", "37.72"], ["6.063", "329.86"], ...],
    "a": [["6.108", "37.64"], ["6.109", "81.63"], ...],
    "u": 735910,
    "seq": 100039231732
  },
  "cts": 1747440000147
}
```

### 📌 Delta (fully shown)

```json
{
  "topic": "orderbook.200.UNIUSDC",
  "ts": 1747440004431,
  "type": "delta",
  "data": {
    "s": "UNIUSDC",
    "b": [["6.057", "0"]],
    "a": [],
    "u": 735911,
    "seq": 100039236102
  },
  "cts": 1747440004299
}
```
Delta messages define how to update the DOM — they act as precise instructions to insert, modify, or remove price levels.


---

## 📂 Field Definitions

| Field     | Description                                                                                |
| --------- | ----------------------------------------------------------------------------------         |
| `topic`   | Topic name (e.g., `orderbook.200.UNIUSDC`)                                                 |
| `ts`      | [UNIX Timestamp](https://en.wikipedia.org/wiki/Unix_time) in ms — `timestamp` in execution |
| `type`    | Type of message: `"snapshot"` or `"delta"`                                                 |
| `data`    | Object that contains the full order book content                                           |
| └─ `s`    | Symbol name (e.g., `UNIUSDC`)                                                              |
| └─ `b`    | Bids. In snapshots, sorted by price descending                                             |
| └─ `b[0]` | Bid price                                                                                  |
| └─ `b[1]` | Bid size. In deltas, size = `0` means full fill or cancel                                  |
| └─ `a`    | Asks. In snapshots, sorted by price ascending                                              |
| └─ `a[0]` | Ask price                                                                                  |
| └─ `a[1]` | Ask size. In deltas, size = `0` means full fill or cancel                                  |
| └─ `u`    | Update ID. Sequential counter. `"u": 1` indicates full snapshot after system reset         |
| └─ `seq`  | Cross-sequence number. Lower `seq` indicates older data                                    |
| `cts`     | Client-side timestamp when data was received                                               |

---

## 📎 Reference

Field semantics adapted from
🔗 [ByBit Derivatives Data - History Download Documentation](https://www.bybit.com/derivatives/en/history-data)

See also 🔗 [ByBit Data Explanation](https://bybit-exchange.github.io/docs/tax/explain?utm_source=chatgpt.com)

---
