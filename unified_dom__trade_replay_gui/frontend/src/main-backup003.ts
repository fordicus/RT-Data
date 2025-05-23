/**
................................................................................

How to Use:

	Start backend (from project root):

		uvicorn backend.app:app --reload

	→ FastAPI runs at:
		http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17

	Start frontend (from ./frontend):

		cd frontend && npm run dev

	→ Frontend runs at:
		http://localhost:5173

................................................................................

Dependency:

	npm install lightweight-charts@4.1.1

................................................................................

Functionality:

	- Left chart: tick chart with tooltip (hover + fixed), red marker
	- Right chart: blank chart with synced crosshair, tooltip text output
	- Crosshair from left chart controls right chart (1-way sync)
	- Full local timestamp formatting applied in both charts

................................................................................

IO Structure:

	Input:
		GET http://localhost:8000/api/tick?symbol=...&date=...
		GET http://localhost:8000/api/orderbook?symbol=...&date=...&time=...

	Output:
		Dual-chart GUI with synchronized event-linked rendering

................................................................................

Project Structure & Build Tool:

	This file:
		frontend/src/main.ts

	Related files:
		frontend/vite.config.ts
		frontend/index.html

	Vite configuration is essential for:
		- Module aliasing (e.g., "@/utils/...")
		- TypeScript support
		- Hot Module Replacement during `npm run dev`

	NOTE: Without vite.config.ts, dev server will fail to resolve
	      module paths correctly, especially when importing from ./src.

	IMPORTANT:
		Vite must be run from the `frontend/` directory for alias paths
		and entry resolution to work as expected. Ensure consistency with
		REPO_STRUCT.html and fast refresh pipeline.

................................................................................

Limitation:

	2025-05-22:
		There are four sources of time information displayed in the charts:
		[1]. The x-axis' time labels.
		[2]. The custom crosshair hover tooltip (on the left pane).
		[3]. The mirrored text of the custom hover tooltip (on the right pane).
		[4]. The default tooltip on the bottom of the left pane's crosshair.

		While sources [1-3] correctly apply the local timezone,
		source [4] consistently displays the original UNIX Timestamp,
		which is UTC+0. This specific behavior for the default crosshair
		tooltip [4] could not be modified or overridden within
		lightweight-charts@4.1.1.
		
................................................................................

TODO (DO NOT DELETE, ChatGPT):

	Dynamic caching for the tooltip data according to the current viewport.

................................................................................
*/

import {
	createChart,
	CrosshairMode,
} from 'lightweight-charts'

const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
console.log('Detected Local TimeZone ID:', localTimeZone); 

/**
 * Helper: zero-pads number to at least `w` width (default: 2)
 */
const pad = (n: number, w = 2) => String(n).padStart(w, '0')

/**
 * Converts UNIX timestamp (sec) to local Date object
 */
const toLocalDate = (ts: number): Date => new Date(ts * 1000)

/**
 * Tick label: if day starts (00:00:00) → YYYY-MM-DD else → hh:mm:ss
 */
const formatTickLabel = (d: Date): string => {
	if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	}

	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// Chart container bindings (chart-left / chart-right are in HTML)
const leftEl  = document.getElementById('chart-left') as HTMLElement
const rightEl = document.getElementById('chart-right') as HTMLElement
rightEl.style.position = 'relative'

/**
 * Creates the primary (left) chart for trade price series
 */
const leftChart = createChart(leftEl, {
	width       : leftEl.clientWidth,
	height      : leftEl.clientHeight,
	layout      : {
		background: { color: '#111' },
		textColor : '#DDD'
	},
	grid        : {
		vertLines: { color: '#222' },
		horzLines: { color: '#222' }
	},
	crosshair   : {
		mode: CrosshairMode.Normal
	},
	timeScale   : {
		timeVisible       : true,
		secondsVisible    : true,
		tickMarkFormatter : () => ''
	},
	timeZone: localTimeZone
})

/**
 * Creates the secondary (right) chart to mirror crosshair and render text
 */
const rightChart = createChart(rightEl, {
	width       : rightEl.clientWidth,
	height      : rightEl.clientHeight,
	layout      : {
		background: { color: '#181818' },
		textColor : '#AAA'
	},
	grid        : {
		vertLines: { color: '#222' },
		horzLines: { color: '#222' }
	},
	crosshair   : {
		mode: CrosshairMode.Normal
	},
	timeScale   : {
		timeVisible    : true,
		secondsVisible : true
	},
	timeZone: localTimeZone
})

const leftSeries = leftChart.addLineSeries()

/**
 * Tooltip that follows mouse hover (floating)
 */
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

/**
 * === Canvas overlay for Order‑Book depth (Plan03‑P3.5) ===
 */
const domCanvas = document.createElement('canvas')
domCanvas.width  = rightEl.clientWidth
domCanvas.height = rightEl.clientHeight
domCanvas.style.position = 'absolute'
domCanvas.style.top      = '0'
domCanvas.style.left     = '0'
rightEl.appendChild(domCanvas)
domCanvas.style.zIndex = '9999'

const domCtx = domCanvas.getContext('2d')!

/**
 * drawDOMSnapshot – render bid/ask depth bars into canvas
 *
 * 🧠 Adaptivity is crucial when rendering order book data because:
 * - Different markets and timeframes have drastically different price ranges.
 * - Volume (size) values vary across assets and change over time.
 * - The canvas should render correctly regardless of resolution or data scale.
 *
 * ✅ This implementation adapts to:
 * - canvas size → adjusts bar height and horizontal width
 * - data range  → computes dynamic price-to-y mapping
 * - volume scale → normalizes widths based on max size per snapshot
 * - font spacing → calculates label spacing with midpoint adjustment
 */

function drawDOMSnapshot(dom: { a: [string, string][], b: [string, string][] }): void {
	domCtx.clearRect(0, 0, domCanvas.width, domCanvas.height)

	const margin     = 20
	const fontSize   = 10
	const fontPad    = 4
	const fontGap    = fontSize + fontPad
	const TEXT_X     = domCanvas.width * 0.02
	const barOffset  = domCanvas.width * 0.12
	const barH       = Math.max(1, domCanvas.height / (dom.b.length + dom.a.length) / 2)

	const bids = dom.b.slice().sort((a, b) => +a[0] - +b[0])  // low → high
	const asks = dom.a.slice().sort((a, b) => +a[0] - +b[0])  // low → high

	const prices = bids.concat(asks).map(([p]) => +p)
	const minP   = Math.min(...prices)
	const maxP   = Math.max(...prices)

	const priceToY = (p: number): number => {
		const t = (p - minP) / (maxP - minP)
		return margin + (1 - t) * (domCanvas.height - 2 * margin)
	}

	const maxSize = Math.max(
		...bids.map(([_, s]) => +s),
		...asks.map(([_, s]) => +s),
		1
	)

	// === Draw BID bars (green) ===
	for (const [p, s] of bids) {
		const price = +p
		const size  = +s
		const y     = priceToY(price)
		const w     = (size / maxSize) * (domCanvas.width - barOffset - 1)

		domCtx.fillStyle = 'rgba( 80,255, 80,.6)'
		domCtx.fillRect(barOffset, y, w, barH)
	}

	// === Draw ASK bars (red) ===
	for (const [p, s] of asks) {
		const price = +p
		const size  = +s
		const y     = priceToY(price)
		const w     = (size / maxSize) * (domCanvas.width - barOffset - 1)

		domCtx.fillStyle = 'rgba(255, 80, 80,.6)'
		domCtx.fillRect(barOffset, y, w, barH)
	}

	// === Draw only top bid and lowest ask prices with fixed spacing ===
	if (bids.length > 0 && asks.length > 0) {
		const topBid = bids[bids.length - 1]
		const lowAsk = asks[0]

		const yBid = priceToY(+topBid[0])
		const yAsk = priceToY(+lowAsk[0])
		const yMid = (yBid + yAsk) / 2

		domCtx.font         = `${fontSize}px monospace`
		domCtx.textAlign    = 'left'
		domCtx.textBaseline = 'middle'

		// Ask → upper
		domCtx.fillStyle = '#f88'
		domCtx.fillText(`${+lowAsk[0]}`, TEXT_X, yMid - fontGap / 2)

		// Bid → lower
		domCtx.fillStyle = '#8f8'
		domCtx.fillText(`${+topBid[0]}`, TEXT_X, yMid + fontGap / 2)
	}
}

/**
 * Tooltip that shows fixed info after click
 */
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

/**
 * Right chart mirror text box for debugging (absolute positioned)
 * DO NOT DELETE THIS BLOCK: USEFUL for DEBUGGING
 */
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

const tooltipCache = new Map<number, any>()
let time_cursor: number | null = null
let currentMarker: { time: number, position: string, color: string, shape: string }[] = []

/**
 * Fetch tick data from API and populate left chart and tooltipCache
 */
fetch('http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17')
	.then(res => res.json())
	.then(data => {
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

		leftChart.applyOptions({
			timeScale: {
				tickMarkFormatter: (ts: number) =>
					formatTickLabel(toLocalDate(ts))
			},
			timeZone: localTimeZone
		})

		leftSeries.setData(points)
		leftChart.timeScale().fitContent()

		// Initially sync right chart's range
		rightChart.timeScale().setVisibleLogicalRange(
			leftChart.timeScale().getVisibleLogicalRange()!
		)
	})
	.catch(err => {
		console.error('Tick data fetch failed:', err)
	})

/**
 * Global flag for DOM fetch interaction mode
 *
 * default = 'hover' → DOM snapshots are fetched only during hover
 * other mode (to be used in Plan03-P6) = 'click'
 */
let domFetchMode: 'hover' | 'click' = 'hover'

/**
 * Flag for suppressing fetch caused by click-induced crosshair moves.
 *
 * Activated on mousedown (capture phase),
 * cleared on mouseup (next tick), covers entire click lifecycle.
 */
let isClickSuppressed = false

/**
 * Activate fetch suppression for full click duration.
 *
 * Capture phase ensures we suppress before crosshairMove triggers.
 */
leftEl.addEventListener(
	'mousedown',
	() => {
		isClickSuppressed = true
	},
	true  // capture phase
)

/**
 * Clear suppression after full click-release finishes.
 *
 * Use next tick to ensure clean separation of event phases.
 */
leftEl.addEventListener(
	'mouseup',
	() => {
		setTimeout(() => {
			isClickSuppressed = false
		}, 0)
	},
	true
)

const formatFullTimestamp = (d: Date): string => {
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
		`${pad(d.getMilliseconds(), 3)}`
	)
}

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

/**
 * Hover handler → update floating tooltip + mirror to right chart
 */
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
	
	const r = leftEl.getBoundingClientRect()
	tooltip.innerText =
		`${formatDualTimestamp(ts)}\n` +
		`price:   ${d.value}\n` +
		`volume:  ${d.volume}\n` +
		`side:    ${d.side}`
	tooltip.style.left    = `${r.left + param.point.x + 10}px`
	tooltip.style.top     = `${r.top  + param.point.y + 10}px`
	tooltip.style.display = 'block'

	// Sync crosshair and display text in right chart
	rightChart.setCrosshairPosition(param.point)
	
	// DO NOT DELETE (DEBUGGING PURPOSE)
	rightText.textContent = tooltip.innerText

	/**
	 * 🧠 DOM snapshot fetch (Plan03-P1 final)
	 *
	 * Only fetch if:
	 * - in 'hover' mode
	 * - NOT during click (mousedown ~ mouseup)
	 */
	if (domFetchMode === 'hover' && !isClickSuppressed) {
		const url =
			`/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=${ts}`

		fetch(url)
			.then(res => res.json())
			.then(data => {
				console.log("DOM Snapshot", data.DOM)
				// Canvas depth draw (Plan03‑P3.5)
				if (data.DOM !== 'N/A') drawDOMSnapshot(data.DOM);
			})
			.catch(err => {
				console.error("DOM fetch error:", err)
			})
	}
})

/**
 * Click handler → fix tooltip and show red marker
 */
leftChart.subscribeClick(param => {
	if (!param.time || !param.point) return

	time_cursor = param.time as number
	const d     = tooltipCache.get(time_cursor)
	if (!d) return
	
	const r = leftEl.getBoundingClientRect()
	fixedTooltip.innerText =
		`${formatDualTimestamp(ts)}\n` +
		`price:   ${d.value}\n` +
		`volume:  ${d.volume}\n` +
		`side:    ${d.side}`
	fixedTooltip.style.left    = `${r.left + param.point.x + 10}px`
	fixedTooltip.style.top     = `${r.top  + param.point.y + 40}px`
	fixedTooltip.style.display = 'block'

	currentMarker = [{
		time    : time_cursor,
		position: 'inBar',
		color   : '#ff0000',
		shape   : 'circle'
	}]
	leftSeries.setMarkers(currentMarker)
})