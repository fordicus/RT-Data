# High-Frequency Spot OrderBook Dataset

This repository manages high-frequency Level 2 (DOM) data 
from a major cryptocurrency spot exchange. The goal is to structure 
this data for use in Reinforcement Learning (RL) and Transformer-based models 
to extract alpha signals from market microstructure dynamics.

---

## 🧭 Mission Summary

- Automate the download and organization of spot OrderBook tick data.
- Visualize snapshots and deltas via GUI.
- Generate datasets at fine timestamp resolutions (e.g., 10s or true tick).
- Build infrastructure for training RL and Transformer models:
  - Focus exclusively on order book data (exclude chart-based history).
  - Normalize time series to eliminate symbol dependency.
  - Use recent time frames to predict future movement likelihood.

---

## 📅 Latest Data Acquisition

- **Date:** 2025-05-12  
- **Range:** 2025-04-29 to 2025-05-11  
- **Symbols (45):**

['PEPEUSDT', 'UNIUSDT', 'ADAUSDT', 'AAVEUSDT', 'XRPUSDC', 'SHIBUSDT',
'SOLUSDT', 'PEPEUSDC', 'ETHUSDT', 'SUIUSDC', 'BCHUSDC', 'SUIUSDT',
'ONDOUSDT', 'NEARUSDC', 'BTCUSDT', 'DOTUSDC', 'AVAXUSDT', 'TONUSDT',
'SOLUSDC', 'TONUSDC', 'LTCUSDC', 'DOTUSDT', 'ETHUSDC', 'BTCUSDC',
'WLDUSDC', 'ADAUSDC', 'XLMUSDC', 'BNBUSDT', 'WBTCUSDT', 'AVAXUSDC',
'UNIUSDC', 'BCHUSDT', 'LTCUSDT', 'BNBUSDC', 'ONDOUSDC', 'HBARUSDT',
'SHIBUSDC', 'XRPUSDT', 'WLDUSDT', 'DOGEUSDC', 'XLMUSDT', 'LINKUSDT',
'DOGEUSDT', 'NEARUSDT', 'LINKUSDC']


---

## 📊 OrderBook Field Structure

| Field      | Description |
|------------|-------------|
| `data`     | Root object with order book info. |
| `data.a`   | Asks (ascending price). |
| `data.a[0]`| Ask price. |
| `data.a[1]`| Ask size (0 = removed in delta). |
| `data.b`   | Bids (descending price). |
| `data.b[0]`| Bid price. |
| `data.b[1]`| Bid size (0 = removed in delta). |
| `data.s`   | Symbol (e.g., `BTCUSDT`). |
| `data.seq` | Cross-sequence ID (lower = older). |
| `data.u`   | Update ID (`u = 1` = snapshot after restart). |
| `topic`    | Topic name (e.g., `orderbook.500.BTCUSDT`). |
| `ts`       | Timestamp (ms). |
| `type`     | `"snapshot"` or `"delta"`. |

---

## 📝 TODO

- [ ] Summarize the features, pros, and cons of Spot OrderBook data.
- [ ] Fully understand the field structure and data schema.
- [ ] Add a few papers.

---

## 🔧 Code Structure

### `get_hist_ob.py` (🔒 Private)

This script automates the download of historical spot order book data.  
**It is private and intentionally excluded from version control (`.gitignore`)**  
to protect the data collection mechanism from overexposure.

> Please note: This script involves rate-sensitive infrastructure.  
> Public sharing is deliberately restricted.

---

### `vis_dom.py` (🟢 Public)

A GUI-based order book player that replays downloaded DOM stream snapshots and deltas —  
mimicking real-time trading environments for visual inspection and debugging.

---

## 🚀 Final Goal

Deliver a normalized, high-resolution dataset 
for training RL and Transformer models capable of 
predicting future market behavior from raw order book streams.
