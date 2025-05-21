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

	Output:
		Dual-chart GUI with event-synced depth chart placeholder

................................................................................

TODO (DO NOT DELETE, ChatGPT):

	Dynamic caching for the tooltip data according to the current viewport.

................................................................................
*/

import {
	createChart,
	CrosshairMode,
} from 'lightweight-charts'

/**
 * Helper: zero-pads number to at least `w` width (default: 2)
 */
const pad = (n: number, w = 2) => String(n).padStart(w, '0')

/**
 * Converts UNIX timestamp (sec) to local Date object
 */
const toLocalDate = (ts: number): Date => new Date(ts * 1000)

/**
 * Formats a Date to "YYYY-MM-DD hh:mm:ss.fff (UTC ±X)" format
 */
const formatFullTimestamp = (d: Date): string => {
	const tzOffset = -d.getTimezoneOffset() / 60
	const sign     = tzOffset >= 0 ? '+' : '-'

	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
		`${pad(d.getMilliseconds(), 3)} (UTC ${sign}${Math.abs(tzOffset)})`
	)
}

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
	}
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
	}
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
			}
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
 * Hover handler → update floating tooltip + mirror to right chart
 */
leftChart.subscribeCrosshairMove(param => {
	if (!param.time || !param.seriesData.has(leftSeries)) {
		tooltip.style.display   = 'none'
		rightText.textContent   = ''
		return
	}

	const ts = param.time as number
	const d  = tooltipCache.get(ts)
	if (!d || !param.point) return

	const r = leftEl.getBoundingClientRect()
	tooltip.innerText =
		`${formatFullTimestamp(d.timeObj)}\n` +
		`price:   ${d.value}\n` +
		`volume:  ${d.volume}\n` +
		`side:    ${d.side}`
	tooltip.style.left    = `${r.left + param.point.x + 10}px`
	tooltip.style.top     = `${r.top  + param.point.y + 10}px`
	tooltip.style.display = 'block'

	// Sync crosshair and display text in right chart
	rightChart.setCrosshairPosition(param.point)
	rightText.textContent = tooltip.innerText
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
		`${formatFullTimestamp(d.timeObj)}\n` +
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
