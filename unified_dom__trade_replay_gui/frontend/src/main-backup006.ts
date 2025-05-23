/**
 * ============================================================================
 * Project Overview:
 *
 *   Dual-panel GUI for tick-level replay and DOM snapshot visualization.
 *   Visualizes (historical) ByBit spot execution trace and order book flow.
 *   Left chart: price line, crosshair, floating & fixed tooltips.
 *   Right chart: canvas overlay for DOM bars and mirrored text debug.
 *
 * ============================================================================
 * Frontend Technology:
 *
 *   ▸ Language         :   TypeScript 5.8.3 (compiled via Vite/ESBuild)
 *   ▸ Build Tool       :   Vite 6.3.5 (dev server, ESM bundler)
 *   ▸ Charting Library :   lightweight-charts@4.1.1 (TradingView)
 *   ▸ Tooltip Layering :   DOM overlay (<div>, absolute-positioned)
 *   ▸ Depth Visualization: HTML5 <canvas> overlay on right pane
 *
 *   ▸ Runtime:
 *       • Node.js : v20.17.0
 *       • npm     : 10.8.2
 *
 *   ▸ Referenced Files:
 *       • tsconfig.json   → compiler options (strict mode, module)
 *       • vite.config.ts  → dev server config, module aliasing
 *       • index.html      → root layout, chart container anchors
 *
 * ============================================================================
 *
 * Backend Integration:
 *
 *   - Language     : Python 3.11 (FastAPI + pandas)
 *   - Components   : 
 *       • app.py       → FastAPI endpoints
 *       • loader.py    → tick and DOM file parser
 *   - Input files  :
 *       • CSV: tick stream (timestamp, price, side, volume)
 *       • NDJSON: DOM updates (ByBit ob200.data)
 *   - Example API Calls:
 *       curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" \
 *            -o dump_tick.json
 *       curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17\
 *            &time=1747525846.066" -o dump_dom.json
 *
 * ============================================================================
 * How to Run (Dev Only):
 *
 *   # Start backend server
 *   uvicorn backend.app:app --reload
 *
 *   # Start frontend dev server via Vite
 *   cd frontend && npm run dev
 *
 *   ➤ Runtime URLs:
 *     FastAPI tick data  :
 *       http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17
 *     FastAPI order book :
 *       http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747524319.016
 *     Frontend (Vite dev server):
 *       http://localhost:5173
 *
 *   ➤ Utility Files (in project root):
 *     • local_frontend.url – shortcut that opens frontend in browser
 *     • test_cmd.bat        – unified launcher for backend + frontend
 *
 * ============================================================================
 * Limitation:
 *
 *   2025-05-22:
 *     There are four sources of time information displayed in the charts:
 *       [1]. The x-axis' time labels.
 *       [2]. The custom crosshair hover tooltip (on the left pane).
 *       [3]. The mirrored text of the custom hover tooltip (on the right pane).
 *       [4]. The default tooltip on the bottom of the left pane's crosshair.
 *
 *     While sources [1-3] correctly apply the local timezone,
 *     source [4] consistently displays the original UNIX Timestamp,
 *     which is UTC+0. This specific behavior for the default crosshair
 *     tooltip [4] could not be modified or overridden within
 *     lightweight-charts@4.1.1.
 *
 * ============================================================================
 * TODO (DO NOT DELETE, ChatGPT):
 *
 *   Dynamic caching for the tooltip data according to the current viewport.
 *
 * ============================================================================
 */

import {
	createChart,
	CrosshairMode,
} from 'lightweight-charts'

/* ----------------------------------------------------------------------
   🔎 Detect the user's local time zone ID (e.g., "Europe/Berlin")

   This is important for converting timestamps into human-readable,
   locale-specific datetime strings when rendering charts.
---------------------------------------------------------------------- */
const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
console.log('Detected Local TimeZone ID:', localTimeZone)

/* ----------------------------------------------------------------------
   📌 pad(n, w)

   Pads a number `n` with leading zeros to ensure it is at least `w`
   characters wide. Used to maintain uniform formatting like "05:09:03".
   Default width is 2 (e.g., pad(9) → "09").
---------------------------------------------------------------------- */
const pad = (n: number, w = 2): string => String(n).padStart(w, '0')

/* ----------------------------------------------------------------------
   🕒 toLocalDate(ts)

   Converts a UNIX timestamp (in seconds) to a local Date object.
   Timestamps from the backend are in UNIX epoch time (e.g., 1716559200),
   so this ensures we render them in the user's local timezone context.
---------------------------------------------------------------------- */
const toLocalDate = (ts: number): Date => new Date(ts * 1000)

/* ----------------------------------------------------------------------
   🏷️ formatTickLabel(d)

   Used to label X-axis tick marks on the chart based on Date `d`.

   - If the time is exactly midnight (00:00:00), it returns a full date:
       → "2025-05-23"
   - Otherwise, it returns time only:
       → "13:45:21"

   This improves visual clarity: we emphasize new days explicitly,
   but use compact time format for intraday points.
---------------------------------------------------------------------- */
const formatTickLabel = (d: Date): string => {
	if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	}

	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/* ----------------------------------------------------------------------
   📦 Bind HTML elements for dual chart layout

   The HTML file should contain two `<div>` elements with the IDs:
   - `chart-left`  → main price chart (e.g., line series of trades)
   - `chart-right` → overlay chart for DOM snapshot & tooltip sync

   These DOM elements will serve as chart containers.
---------------------------------------------------------------------- */
const leftEl  = document.getElementById('chart-left')  as HTMLElement
const rightEl = document.getElementById('chart-right') as HTMLElement

/* Position is required to be 'relative' for absolutely-positioned 
   children (e.g., canvas overlays, tooltips) to anchor correctly */
rightEl.style.position = 'relative'

/* ----------------------------------------------------------------------
   📈 Create the primary (left) chart

   This chart visualizes the main time-series data (price over time).
   - Uses dark background for contrast
   - Enables second-level granularity on the X-axis
   - Tick labels are customized later after data load
   - Chart respects the local timezone for rendering timestamps
---------------------------------------------------------------------- */
const leftChart = createChart(leftEl, {
	width       : leftEl.clientWidth,
	height      : leftEl.clientHeight,
	layout      : {
		background: { color: '#111' },  // dark gray background
		textColor : '#DDD',             // soft white text
	},
	grid        : {
		vertLines: { color: '#222' },   // muted grid
		horzLines: { color: '#222' },
	},
	crosshair   : {
		mode: CrosshairMode.Normal      // free movement on both axes
	},
	timeScale   : {
		timeVisible       : true,       // show X-axis time labels
		secondsVisible    : true,       // show seconds
		tickMarkFormatter : () => '',   // placeholder, overwritten later
	},
	timeZone: localTimeZone            // apply client-local timezone
})

/* ----------------------------------------------------------------------
   🪞 Create the secondary (right) chart

   This chart is visually muted and used for:
   - Crosshair synchronization (mirrors the left chart)
   - DOM overlays (rendered via canvas)
   - Textual outputs (e.g., tooltips)
---------------------------------------------------------------------- */
const rightChart = createChart(rightEl, {
	width       : rightEl.clientWidth,
	height      : rightEl.clientHeight,
	layout      : {
		background: { color: '#181818' }, // slightly lighter dark background
		textColor : '#AAA',               // gray text
	},
	grid        : {
		vertLines: { color: '#222' },
		horzLines: { color: '#222' },
	},
	crosshair   : {
		mode: CrosshairMode.Normal,
	},
	timeScale   : {
		timeVisible    : true,
		secondsVisible : true,
	},
	timeZone: localTimeZone
})

/* Add the primary line series (e.g., price series) to the left chart */
const leftSeries = leftChart.addLineSeries()

/* ----------------------------------------------------------------------
   🖱️ Floating tooltip for mouse hover (left chart only)

   - Created as a DOM element positioned absolutely over the chart
   - Hidden by default (`display: none`) and only shown on hover
   - Styled with monospace font and translucent background
   - `white-space: pre` preserves newlines in text content
   - `pointer-events: none` ensures it does not block mouse interaction
---------------------------------------------------------------------- */
const tooltip = document.createElement('div')
tooltip.className = 'hover-tooltip'
tooltip.style = `
	position        : absolute;
	display         : none;
	background-color: rgba(0, 0, 0, 0.7);
	color           : white;
	padding         : 8px;
	border-radius   : 4px;
	white-space     : pre;
	pointer-events  : none;
	font-family     : monospace;
	font-size       : 12px;
	z-index         : 1000;
`
document.body.appendChild(tooltip)

/* ----------------------------------------------------------------------
   📊 Canvas overlay: order-book depth bars (Plan03‑P3.5)

   This canvas will render bid/ask volume bars aligned with price levels.
   - Anchored over `rightEl` (chart-right)
   - High `z-index` ensures it appears above chart elements
   - Canvas context (`domCtx`) is used for drawing rectangles and text
---------------------------------------------------------------------- */
const domCanvas = document.createElement('canvas')
domCanvas.width  = rightEl.clientWidth
domCanvas.height = rightEl.clientHeight
domCanvas.style.position = 'absolute'
domCanvas.style.top      = '0'
domCanvas.style.left     = '0'
domCanvas.style.zIndex   = '9999'
rightEl.appendChild(domCanvas)

/* Get 2D drawing context for DOM rendering */
const domCtx = domCanvas.getContext('2d')!

/* ----------------------------------------------------------------------
   🎨 drawDOMSnapshot()

   Render bid/ask depth bars onto the right-side canvas overlay.

   🧠 Why adaptive rendering is important:
   - Price ranges vary widely across markets and symbols.
   - Volume sizes differ drastically between snapshots.
   - Display must adjust dynamically to canvas resolution.

   ✅ This implementation adapts to:
   - canvas size → bar height, spacing
   - data range  → dynamic y-axis scaling
   - volume scale → normalized bar width
   - price labels → positioned at mid-gap between best bid/ask
---------------------------------------------------------------------- */
function drawDOMSnapshot(dom: { a: [string, string][], b: [string, string][] }): void {
	/* ---------------------------------------------------------------
	   🔄 Clear canvas before drawing new snapshot
	   Ensures no overlap or artifacts from previous draw calls
	--------------------------------------------------------------- */
	domCtx.clearRect(0, 0, domCanvas.width, domCanvas.height)

	/* ---------------------------------------------------------------
	   📐 Layout constants for rendering
	   - `margin`        : vertical padding from top/bottom
	   - `fontSize`/`Pad`: text size and vertical spacing
	   - `TEXT_X`        : horizontal starting point for text labels
	   - `barOffset`     : X-coordinate where bars begin
	   - `barH`          : vertical height per bar, dynamic based on data count
	--------------------------------------------------------------- */
	const margin     = 20
	const fontSize   = 10
	const fontPad    = 4
	const fontGap    = fontSize + fontPad
	const TEXT_X     = domCanvas.width * 0.02
	const barOffset  = domCanvas.width * 0.12
	const barH       = Math.max(1,
		domCanvas.height / (dom.b.length + dom.a.length) / 2)

	/* ---------------------------------------------------------------
	   📊 Sort bid/ask orders numerically by price (low → high)
	   - Bids are often unordered, so we must sort them to draw correctly.
	   - Asks too must be sorted for consistent rendering.
	--------------------------------------------------------------- */
	const bids = dom.b.slice().sort((a, b) => +a[0] - +b[0])
	const asks = dom.a.slice().sort((a, b) => +a[0] - +b[0])

	/* ---------------------------------------------------------------
	   📈 Determine price range for vertical mapping
	   - `minP`, `maxP`: global min/max across both sides
	   - priceToY(): maps any price to a vertical position on canvas
	--------------------------------------------------------------- */
	const prices = bids.concat(asks).map(([p]) => +p)
	const minP   = Math.min(...prices)
	const maxP   = Math.max(...prices)

	const priceToY = (p: number): number => {
		const t = (p - minP) / (maxP - minP)
		return margin + (1 - t) * (domCanvas.height - 2 * margin)
	}

	/* ---------------------------------------------------------------
	   📏 Compute the maximum size among all bid/ask levels
	   - This is used to normalize each bar's width.
	   - We include fallback to 1 to avoid division by zero.
	--------------------------------------------------------------- */
	const maxSize = Math.max(
		...bids.map(([_, s]) => +s),
		...asks.map(([_, s]) => +s),
		1
	)

	/* ---------------------------------------------------------------
	   ✅ Draw BID bars (green, left-to-right)
	--------------------------------------------------------------- */
	for (const [p, s] of bids) {
		const price = +p
		const size  = +s
		const y     = priceToY(price)
		const w     = (size / maxSize) * (domCanvas.width - barOffset - 1)

		domCtx.fillStyle = 'rgba( 80,255, 80,.6)'
		domCtx.fillRect(barOffset, y, w, barH)
	}

	/* ---------------------------------------------------------------
	   ✅ Draw ASK bars (red, left-to-right)
	--------------------------------------------------------------- */
	for (const [p, s] of asks) {
		const price = +p
		const size  = +s
		const y     = priceToY(price)
		const w     = (size / maxSize) * (domCanvas.width - barOffset - 1)

		domCtx.fillStyle = 'rgba(255, 80, 80,.6)'
		domCtx.fillRect(barOffset, y, w, barH)
	}

	/* ---------------------------------------------------------------
	   🧾 Display best bid and lowest ask prices
	   - Only these two are shown to reduce visual clutter.
	   - They are rendered near the vertical midpoint.
	--------------------------------------------------------------- */
	if (bids.length > 0 && asks.length > 0) {
		const topBid = bids[bids.length - 1]  // highest bid
		const lowAsk = asks[0]                // lowest ask

		const yBid = priceToY(+topBid[0])
		const yAsk = priceToY(+lowAsk[0])
		const yMid = (yBid + yAsk) / 2

		domCtx.font         = `${fontSize}px monospace`
		domCtx.textAlign    = 'left'
		domCtx.textBaseline = 'middle'

		// Ask label (upper)
		domCtx.fillStyle = '#f88'
		domCtx.fillText(`${+lowAsk[0]}`, TEXT_X, yMid - fontGap / 2)

		// Bid label (lower)
		domCtx.fillStyle = '#8f8'
		domCtx.fillText(`${+topBid[0]}`, TEXT_X, yMid + fontGap / 2)
	}
}

/* ----------------------------------------------------------------------
   📌 Fixed Tooltip: remains visible after user clicks on chart

   - Unlike the floating tooltip shown on hover, this one appears
     only after a click event on the left chart.
   - It remains anchored in place and displays:
     timestamp, price, volume, and side.
   - Styled similarly to the hover tooltip but with higher opacity
     and higher z-index (appears above other overlays).
---------------------------------------------------------------------- */
const fixedTooltip = document.createElement('div')
fixedTooltip.className = 'fixed-tooltip'
fixedTooltip.style = `
	position        : absolute;
	display         : none;
	background-color: rgba(0, 0, 0, 0.85);
	color           : white;
	padding         : 8px;
	border-radius   : 4px;
	white-space     : pre;
	pointer-events  : none;
	font-family     : monospace;
	font-size       : 12px;
	z-index         : 1001;
`
document.body.appendChild(fixedTooltip)

/* ----------------------------------------------------------------------
   🐞 Debugging Overlay (top-right)

   - This text box displays mirrored tooltip data from the right chart.
   - It can help verify whether crosshair sync and data rendering
     are working correctly.
   - DO NOT DELETE: this block is essential for development-time
     diagnostics and alignment testing.
---------------------------------------------------------------------- */
const rightText = document.createElement('div')
rightText.className = 'mirrored-tooltip'
rightText.style = `
	position        : absolute;
	top             : 10px;
	right           : 10px;
	z-index         : 9999;
	color           : #ccc;
	font-family     : monospace;
	font-size       : 13px;
	padding         : 10px;
	white-space     : pre;
	pointer-events  : none;
`
document.body.appendChild(rightText)

/* ----------------------------------------------------------------------
   🧠 Runtime State

   - tooltipCache: stores all parsed tick info indexed by timestamp.
     Used during hover/click to retrieve display text quickly.
   - time_cursor: current timestamp "pinned" via click
   - currentMarker: red circular marker placed at clicked timestamp
     and rendered on the main line chart
---------------------------------------------------------------------- */
const tooltipCache = new Map<number, any>()

let time_cursor: number | null = null

let currentMarker: {
	time    : number,
	position: string,
	color   : string,
	shape   : string
}[] = []

/* ----------------------------------------------------------------------
   📡 Fetch Tick Data

   Call backend API to retrieve tick-by-tick trade data for a specific
   symbol and date. The response contains:
   - time   (UNIX seconds)
   - value  (price)
   - volume (trade size)
   - side   (buy/sell)

   The following actions are performed:
   - Convert to local Date
   - Store in `tooltipCache` for quick access during hover/click
   - Populate `leftSeries` chart
   - Format tick labels on X-axis
   - Sync visible range to right chart
---------------------------------------------------------------------- */
fetch('http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17')
	.then(res => res.json())
	.then(data => {
		/* -----------------------------------------------------------
		   🧮 Transform API data → chart points + tooltip cache
		----------------------------------------------------------- */
		const points = data.map((pt: any) => {
			const local = toLocalDate(pt.time)

			tooltipCache.set(pt.time, {
				timeObj: local,
				value  : pt.value,
				volume : pt.volume,
				side   : pt.side
			})

			return {
				time : pt.time,
				value: pt.value
			}
		})

		points.sort((a, b) => a.time - b.time)

		/* -----------------------------------------------------------
		   📊 Update chart appearance
		   - Configure tick label formatter with localized date
		   - Apply local time zone (redundant but explicit)
		----------------------------------------------------------- */
		leftChart.applyOptions({
			timeScale: {
				tickMarkFormatter: (ts: number) =>
					formatTickLabel(toLocalDate(ts))
			},
			timeZone: localTimeZone
		})

		leftSeries.setData(points)
		leftChart.timeScale().fitContent()

		/* -----------------------------------------------------------
		   🧭 Sync right chart range with left chart on load
		----------------------------------------------------------- */
		rightChart.timeScale().setVisibleLogicalRange(
			leftChart.timeScale().getVisibleLogicalRange()!
		)
	})
	.catch(err => {
		console.error('Tick data fetch failed:', err)
	})

/* ----------------------------------------------------------------------
   ⚙️ Interaction Flags
---------------------------------------------------------------------- */

/* Mode for DOM fetch trigger:
   - 'hover' = default; fetch DOM only when hovering over price
   - 'click' = alternate; fetch DOM only on click (for future plan) */
let domFetchMode: 'hover' | 'click' = 'hover'

/* Suppresses hover-based fetches during click lifecycle
   - Enabled at mousedown (capture phase)
   - Cleared on next tick after mouseup
   - Prevents hover fetch triggered by crosshair jump on click */
let isClickSuppressed = false

/* ----------------------------------------------------------------------
   🖱️ Crosshair Fetch Suppression (Click Safety)

   These listeners prevent unwanted DOM fetches when a user clicks
   on the chart (crosshair triggers a hover immediately).
---------------------------------------------------------------------- */

/* Activate suppression on mouse down (capture phase ensures early fire) */
leftEl.addEventListener(
	'mousedown',
	() => {
		isClickSuppressed = true
	},
	true
)

/* Deactivate suppression after full click cycle (next tick ensures phase separation) */
leftEl.addEventListener(
	'mouseup',
	() => {
		setTimeout(() => {
			isClickSuppressed = false
		}, 0)
	},
	true
)

/* ----------------------------------------------------------------------
   🧾 formatFullTimestamp(d)
   Formats a Date object into full datetime with milliseconds:

   → "YYYY-MM-DD hh:mm:ss.mmm"

   Used as the core formatting helper inside `formatDualTimestamp`.
---------------------------------------------------------------------- */
const formatFullTimestamp = (d: Date): string => {
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
		`${pad(d.getMilliseconds(), 3)}`
	)
}

/* ----------------------------------------------------------------------
   🌍 formatDualTimestamp(ts)

   Converts a UNIX timestamp into two aligned datetime strings:
   - Local time → with timezone offset
   - UTC time   → raw global timestamp

   Example:
   2025-05-23 10:05:23.123 (UTC +2, Local)
   2025-05-23 08:05:23.123 (UTC +0, Global)
---------------------------------------------------------------------- */
function formatDualTimestamp(ts: number): string {
	const localDate  = new Date(ts * 1000)
	const globalDate = new Date(ts * 1000 + localDate.getTimezoneOffset() * 60000)

	const tzOffset = -localDate.getTimezoneOffset() / 60
	const sign     = tzOffset >= 0 ? '+' : '-'

	return (
		`${formatFullTimestamp(localDate)} (UTC ${sign}${Math.abs(tzOffset)}, Local)\n` +
		`${formatFullTimestamp(globalDate)} (UTC +0, Global)`
	)
}

/* ----------------------------------------------------------------------
   🧾 formatTooltipText(ts, d)

   Generate a unified tooltip text block for:
   - floating tooltip (hover)
   - fixed tooltip (click)
   - mirrored debug box (rightText)

   Contains:
   - dual-format timestamp
   - price, volume, side
---------------------------------------------------------------------- */
function formatTooltipText(ts: number, d: {
	timeObj: Date,
	value  : number,
	volume : number,
	side   : string
}): string {
	return (
		`${formatDualTimestamp(ts)}\n` +
		`price:   ${d.value}\n` +
		`volume:  ${d.volume}\n` +
		`side:    ${d.side}`
	)
}

/* ----------------------------------------------------------------------
   🖱️ Hover Handler → floating tooltip + right chart sync

   Triggered whenever user hovers over the left chart.

   ✅ Actions:
   - If not inside price series → hide tooltip
   - Otherwise:
     • fetch from tooltipCache
     • display floating tooltip
     • update right chart crosshair
     • optionally trigger DOM snapshot fetch (Plan03-P1)

   NOTE: snapshot fetch only occurs if:
   - mode is 'hover'
   - not during click cycle (mousedown ~ mouseup)
---------------------------------------------------------------------- */
leftChart.subscribeCrosshairMove(param => {
	if (!param.time || !param.seriesData.has(leftSeries)) {
		tooltip.style.display   = 'none'

		// DO NOT DELETE (DEBUGGING PURPOSE)
		rightText.textContent   = ''
		return
	}

	const ts = param.time as number
	const d  = tooltipCache.get(ts)
	if (!d || !param.point) return

	const text = formatTooltipText(ts, d)

	const r = leftEl.getBoundingClientRect()
	tooltip.innerText       = text
	tooltip.style.left      = `${r.left + param.point.x + 10}px`
	tooltip.style.top       = `${r.top  + param.point.y + 10}px`
	tooltip.style.display   = 'block'

	rightChart.setCrosshairPosition(param.point)

	// DO NOT DELETE (DEBUGGING PURPOSE)
	rightText.textContent = text

	/* ---------------------------------------------------------------
	   🧠 Optional DOM snapshot fetch (Plan03-P3.5)

	   - fetches orderbook state for timestamp `ts`
	   - result is visualized as a canvas overlay
	--------------------------------------------------------------- */
	if (domFetchMode === 'hover' && !isClickSuppressed) {
		const url =
			`/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=${ts}`

		fetch(url)
			.then(res => res.json())
			.then(data => {
				console.log("DOM Snapshot", data.DOM)

				if (data.DOM !== 'N/A') {
					drawDOMSnapshot(data.DOM)
				}
			})
			.catch(err => {
				console.error("DOM fetch error:", err)
			})
	}
})

/* ----------------------------------------------------------------------
   🖱️ Click Handler → fix tooltip + red marker

   When user clicks on left chart:
   - Tooltip becomes fixed in position
   - Crosshair stays at that time
   - A red circular marker is placed on the line chart
---------------------------------------------------------------------- */
leftChart.subscribeClick(param => {
	if (!param.time || !param.point) return

	time_cursor = param.time as number
	const d     = tooltipCache.get(time_cursor)
	if (!d) return

	const text = formatTooltipText(time_cursor, d)

	const r = leftEl.getBoundingClientRect()
	fixedTooltip.innerText       = text
	fixedTooltip.style.left      = `${r.left + param.point.x + 10}px`
	fixedTooltip.style.top       = `${r.top  + param.point.y + 40}px`
	fixedTooltip.style.display   = 'block'

	currentMarker = [{
		time    : time_cursor,
		position: 'inBar',
		color   : '#ff0000',
		shape   : 'circle'
	}]
	leftSeries.setMarkers(currentMarker)
})

