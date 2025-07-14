# Plan03 – Dual Chart Frontend with Synchronized DOM Snapshot

---

## 🎯 Goal

To extend the current replay frontend with a second chart pane that displays
depth-of-market (DOM) snapshots, synchronized with user interactions on the
tick execution chart (left pane).

The dual chart interface should ensure:

- DOM snapshots appear in real-time on the right pane
- Alignment to the correct execution time (ms precision)
- User interactions never block or delay the tick rendering

---

## ✅ What We’ve Achieved So Far

| Area                | Status  | Details |
|---------------------|---------|---------|
| Tick Data API       | ✅ Done | `/api/tick` serves MS-precision ticks |
| DOM Snapshot API    | ✅ Done | `/api/orderbook` returns normalized DOM |
| Hover & Click Logic | ✅ Done | Left chart supports `subscribeCrosshairMove()` + `time_cursor` |
| Dual Chart Layout   | ✅ Done | Left: execution / Right: empty (DOM placeholder) |
| Backend Performance | ✅ Done | All data is memory-cached on startup (sub-300ms API) |

All Plan02 components have been verified as stable.

---

## 🔁 Strategy – Test–Expand Flow

We adopt a **Test–Expand** methodology:

1. Start with smallest verifiable interaction unit
2. Confirm observable behavior (console or static DOM)
3. Expand only if correctness + latency goals are met

---

## 🧠 DOM Update Policy – Hover vs. Click

To ensure clarity and future flexibility, the following rules must be strictly enforced:

### 🔹 Present Behavior (default)

- DOM updates **only on hover** (crosshair move).
- This is captured via `subscribeCrosshairMove()` events:
	- `param.time` → `/api/orderbook?...` → right chart update

### 🔹 Forbidden Behavior

- ❌ DOM must **not update** when the user clicks:
	- `time_cursor` is visual-only and decoupled from DOM logic.

### 🔹 Planned Enhancement

- A frontend **toggle UI (checkbox)** will be added:
	- "Hover mode": update DOM on hover (default)
	- "Click mode": update DOM on click (via `time_cursor`)

This enables user-driven control of interaction semantics.

---

## 🧱 Breakdown: Plan03 Subcomponents

| Phase | Component                                      | Goal                                 | Status |
|-------|------------------------------------------------|--------------------------------------|--------|
| P1    | Hover-based DOM fetch                          | DOM loads correctly via hover event | 🟨 TODO |
| P2    | Tooltip duplication on right pane              | Textual DOM info aligned to hover    | 🟨 TODO |
| P3    | DOM depth chart rendering                      | Histogram or LineSeries              | 🟨 TODO |
| P4    | Time axis alignment                            | Dual chart `timeZone + crosshair`    | 🟨 TODO |
| P5    | `"N/A"` handling                               | Show graceful message or empty state | 🟨 TODO |
| P6    | Optional toggle UI (hover ↔ click control)     | Checkbox state modifies behavior     | 🟨 TODO |
| P7    | RULESET cleanup + modularization               | Final polish                         | 🟨 TODO |

---

## 🧪 Phase 1: Hover-Based DOM Fetch (P1)

Minimal working example:

- On `subscribeCrosshairMove()` event:
	- Capture `param.time` if defined
	- Issue GET to:
		```ts
		/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=${param.time}
		```
	- Log DOM snapshot to console (for now)

✅ This verifies:
- Event-to-API wiring
- Time alignment correctness
- Backend readiness and latency

---

## 🔚 Final Deliverable

A fully functional dual chart UI:

- Left chart: shows execution ticks and tooltip/click markers
- Right chart: updates live DOM state (text + visual)
- Toggle mode: hover or click based on user control
- Robust fallback: `"N/A"` is handled gracefully
- No visual blocking under rapid interactions

---