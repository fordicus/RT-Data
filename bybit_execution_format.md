# ByBit Trade History Data Explained

## 📄 File Naming Convention

```
SYMBOL_YYYY-MM-DD.csv
```

**Example:**
`BTCUSDT_2025-05-19.csv`

---

## ✅ Format Summary

* Each row represents a **single market trade** (i.e., taker fills).
* Format is **CSV**, with columns consistently structured.
* Can be read via `pandas.read_csv(...)` or any spreadsheet software.

---

## 🧪 Sample Data

```csv
id,timestamp,price,volume,side,rpi
1,1747612800074,106453.8,0.003718,sell,0
2,1747612800150,106456.9,0.000500,buy,0
3,1747612800150,106456.9,0.000500,buy,0
...
```

---

## 📂 Field Definitions

| Field       | Description                                                                             |
| ----------- | ----------------------------------------------------------                              |
| `id`        | Unique trade identifier (within the file)                                               |
| `timestamp` | [UNIX Timestamp](https://en.wikipedia.org/wiki/Unix_time) in ms — `ts` in orderbook     |
| `price`     | Execution price of the trade                                                            |
| `volume`    | Trade size (quantity traded)                                                            |
| `side`      | Taker side: `"buy"` or `"sell"`                                                         |
| `rpi`       | RPI (Retail Price Improvement) flag. WARNING: BROKERAGE DEPENDENT INFO!                 |

---

## 🧩 Use Case Notes

* Trades are **append-only** and reflect **taker-initiated executions**.
* Time-series plots of `price` and `volume` allow for microstructure analysis.
* Can be aligned with **On-chain Liquidity Flow** or **Order Book state** using `timestamp`.

---

## 📎 Reference

Field semantics adapted from
🔗 [ByBit Derivatives Data - History Download Documentation](https://www.bybit.com/derivatives/en/history-data)

See also 🔗 [ByBit Data Explanation](https://bybit-exchange.github.io/docs/tax/explain?utm_source=chatgpt.com)

---