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

- **Date:**  2025-05-20  
- **Range:** 2025-05-07 to 2025-05-19  
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

## 📚 Data Format Reference

- 📘 [OrderBook Format](bybit_orderbook_format.md)  
  (Tick-level DOM snapshots and deltas — `.data` files)

- 📙 [Execution Format](bybit_execution_format.md)  
  (Trade history CSV with RPI flags — `.csv` files)

See also 🔗 [ByBit Data Explanation](https://bybit-exchange.github.io/docs/tax/explain?utm_source=chatgpt.com).

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

## 🛡️ License

This project is licensed under the  
✍️ [Creative Commons Attribution-NonCommercial 4.0 International License – Legal Code](https://creativecommons.org/licenses/by-nc/4.0/legalcode).  
🚫💰 Commercial use is prohibited.  
✨🛠️ Adaptation is permitted with attribution.  
⚠️ No warranty is provided.

[![License: CC BY-NC 4.0](https://licensebuttons.net/l/by-nc/4.0/88x31.png)](https://creativecommons.org/licenses/by-nc/4.0/legalcode)
