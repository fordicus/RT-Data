# High-Frequency Spot OrderBook and Chart Dataset

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

- **Date:**  2025.07.27  
- **Range (78 days):** 2025.05.10 ~ 2025.07.26  
- **Symbols (30):**

ETHUSDT,BTCUSDT,SOLUSDT,ETHUSDC,BTCUSDC,XRPUSDT,PEPEUSDT,DOGEUSDT,SUIUSDT,AAVEUSDT,ONDOUSDT,SOLUSDC,ADAUSDT,XRPUSDC,LTCUSDT,DOGEUSDC,HBARUSDT,UNIUSDT,SUIUSDC,DOTUSDT,ADAUSDC,WLDUSDT,NEARUSDT,AVAXUSDT,TONUSDT,BCHUSDT,PEPEUSDC,LINKUSDT,BNBUSDT,SHIBUSDT

---

## 📅 Next Data Acquisition
Next data acquisition date is +13 days from the latest data acquisition date, e.g.,  
Latest Acq. Date +00: 2025-07-27  
Next Acq.... Date   +13: ***2025-08-09***

---

## 📚 Data Format Reference

- 📘 [OrderBook Format](bybit_orderbook_format.md)  
  (Tick-level DOM snapshots and deltas — `.data` files)

- 📙 [Execution Format](bybit_execution_format.md)  
  (Trade history CSV with RPI flags — `.csv` files)

See also 🔗 [ByBit Data Explanation](https://bybit-exchange.github.io/docs/tax/explain?utm_source=chatgpt.com).

---

## 📝 TODO

- [ ] Summarize the features, advantages, and limitations of Spot Chart and Order Book data, including their intended purpose.
- [ ] Fully understand the field structures and data schemas involved.
- [ ] Add relevant papers and video links that help explain the underlying concepts.


---

## 🔧 Code Structure

### `get_bybit_chart_dom.py` (🔒 Private)

This script automates the download of historical spot **chart data (executions)**
and **DOM snapshots (orderbook)** from ByBit public archives.

**It supports multi-day, multi-symbol batch retrieval via parallel curl executions**
and includes post-download validation to ensure data format integrity.
Configuration parameters (e.g., date range, trading pairs, max parallelism)
are specified in the external file `get_bybit_chart_dom.conf`.

> Please note: This script involves rate-sensitive infrastructure.
> Public sharing is deliberately restricted.

### `get_bybit_chart_dom_validated.py` (✅ Public)

A companion script to validate the integrity of previously downloaded `.csv.gz` and `.data.zip` files.
It performs full-format checks using parallel validation,
ensuring the data is safe to use for RL training or analysis.

This script is intended to be run **after** `get_bybit_chart_dom.py`
and does **not require internet access**.

---

## 🛠️ Development Environment Setup

For detailed instructions on setting up the development environment, including Docker Desktop and VS Code integration for cross-platform workflows, refer to:

📘 [Docker-VS-Code Guide](DOCKER-VS-CODE%20GUIDE.md)

This guide provides step-by-step instructions for configuring Windows-based development environments with Ubuntu deployment targets, ensuring consistency and compatibility across platforms.

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
