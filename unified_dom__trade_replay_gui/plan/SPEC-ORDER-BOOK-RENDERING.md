
# SPEC-ORDER-BOOK-RENDERING.md

## 📘 Purpose

This document defines the updated visual and data logic for  
**Order Book rendering in the right pane** of RT-Data's frontend,  
based on **Canvas-based rendering** introduced in Plan03-P3.5.

---

## 🖼️ Visual Layout (Canvas Overlay)

```

────────────── Start ──────────────
Order Book Snapshot View
────────────── Price Scale (Y) ──────────────
ASK (SELL) side
• Sorted in descending price order
• Bars extend → (left to right)
• Labels aligned left, placed before bars
• Color: rgba(255, 80, 80, 0.6)

────────────── Hover Mid Price ──────────────
• Hover timestamp’s market price
• Already shown in right-pane debug label

BID (BUY) side
• Sorted in ascending price order
• Bars extend → (left to right)
• Labels aligned left, placed before bars
• Color: rgba( 80,255, 80, 0.6)
────────────── End ──────────────

```

---

## 📐 Coordinate Mapping

| Axis    | Meaning                     | Source     |
|---------|-----------------------------|------------|
| Y-Axis  | Price                       | Shared across ASK/BID |
| X-Axis  | Volume (size), positive     | Width of bars |

- Bars always grow **left → right**.
- Canvas labels (prices) are drawn on the **left of the bar** using `fillText(...)`.

---

## 🧱 Rendering Rules (Canvas)

### ✅ Bar Drawing
- Both `dom.a` (ASK) and `dom.b` (BID) are drawn as **horizontal bars**
- Width ∝ `parseFloat(size)`
- Bars rendered using `fillRect(...)`

### ✅ Price Label Drawing
- All price labels are rendered **before the bar** (left-aligned)
- Font: `10px monospace`, color depends on side (red/green)
- Text spacing: enforce **minimum vertical gap** between labels
- Shared vertical label spacing via a **unified `lastYLabel` variable**

---

## 🧪 Tooltip Strategy

Tooltips are **not implemented independently**.
The existing **right-pane debug box** is reused to show:
- Hover time
- Market price
- Volume
- Side

---

## 🔁 FastAPI Endpoint

```
GET /api/orderbook?symbol=UNIUSDC\&date=2025-05-17\&time=1747524319.016

````

### ✅ Response JSON

```json
{
  "time": 1747524319.016,
  "DOM": {
    "a": [["5.769", "43.25"], ["5.774", "3.48"], ...],
    "b": [["5.727", "349.22"], ["5.724", "329.74"], ...]
  }
}
````

| Key   | Meaning                                 |
| ----- | --------------------------------------- |
| `"a"` | ASK side (SELL); descending price order |
| `"b"` | BID side (BUY); ascending price order   |

---

## ✅ Sorting Responsibility

| Layer    | Sorting? | Note                           |
| -------- | -------- | ------------------------------ |
| Backend  | ✅        | Guarantees price order by side |
| FastAPI  | ✅        | Emits sorted snapshot          |
| Frontend | ❌        | Consumes as-is, no sorting     |

---

## 🔧 Implementation Notes

* Rendering uses **Canvas 2D API** directly (not Lightweight Charts series)
* Text and bar positioning calculated manually
* Overlay `canvas` is absolutely positioned on top of `rightChart`
* Bar height, spacing, and text alignment are all handled in `main.ts`

---

## 📌 Summary

| Aspect       | Design Choice                      |
| ------------ | ---------------------------------- |
| Rendering    | HTMLCanvasElement                  |
| Direction    | Bars always drawn left → right     |
| Label side   | Price text to left of bars         |
| Spacing      | Vertical spacing enforced globally |
| Axis sharing | Price axis shared ASK ↔ BID        |
| Sorting      | Backend-resolved                   |
| Tooltip      | Reuses rightText debug box         |

---
