/**................................................................................

How to Use:

	Start backend (in project root):

		uvicorn backend.app:app --reload

	→ FastAPI runs at:
		http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17

	Start frontend (in ./frontend):

		cd frontend && npm run dev

	→ Frontend runs at:
		http://localhost:5173

	→ Then open your browser at:
		http://localhost:5173

................................................................................

Dependency:

	npm install lightweight-charts@4.1.1

................................................................................

Functionality:

	- Renders tick-level trade price chart with local time formatting.
	- Chart x-axis shows day/time with adaptive formatting:
		* At day start: YYYY-MM-DD
		* Otherwise  : hh:mm:ss
	- Hover tooltip shows localtime with ms precision and:
		* price
		* volume
		* side
	- Backend-provided tick data is cached and reused without further fetch.

................................................................................

IO Structure:

	Input:
		GET http://localhost:8000/api/tick?symbol=...&date=...

	Output:
		Line chart rendered with Lightweight Charts.
		Timestamps and tooltips reflect user's local time.

................................................................................

TODO:

	Dynamic caching for the tooltip data according to the current viewport.

................................................................................*/

import {
	createChart,
	CrosshairMode,
} from 'lightweight-charts'

const pad = (n: number, w = 2) => String(n).padStart(w, '0')

const toLocalDate = (ts: number): Date => new Date(ts * 1000)

const formatFullTimestamp = (d: Date): string => {
	const tzOffset = -d.getTimezoneOffset() / 60
	const sign     = tzOffset >= 0 ? '+' : '-'
	const tz       = `UTC ${sign}${Math.abs(tzOffset)}`
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
		`${pad(d.getMilliseconds(), 3)} (${tz})`
	)
}

const formatTickLabel = (d: Date): string => {
	if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	}
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const chartContainer = document.getElementById('chart') as HTMLElement

const chart = createChart(chartContainer, {
	width       : chartContainer.clientWidth,
	height      : chartContainer.clientHeight,
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
		timeVisible        : true,
		secondsVisible     : true,
		tickMarkFormatter  : () => ''	// placeholder; replaced after load
	}
})

const series = chart.addLineSeries()

// Tooltip container styling
const tooltip = document.createElement('div')
tooltip.className = 'custom-tooltip'
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

// Local cache for tooltip lookup
const tooltipCache = new Map<number, any>()

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

		chart.applyOptions({
			timeScale: {
				tickMarkFormatter: (ts: number) =>
					formatTickLabel(toLocalDate(ts))
			}
		})

		series.setData(points)
		chart.timeScale().fitContent()
	})
	.catch(err => {
		console.error('Failed to fetch tick data:', err)
	})

chart.subscribeCrosshairMove(param => {
	if (!param.time || !param.seriesData.has(series)) {
		tooltip.style.display = 'none'
		return
	}

	const ts      = param.time as number
	const nearest = tooltipCache.get(ts)

	if (!nearest || !param.point) {
		tooltip.style.display = 'none'
		return
	}

	const d = nearest.timeObj

	tooltip.innerText =
		`${formatFullTimestamp(d)}\n` +
		`price:   ${nearest.value}\n` +
		`volume:  ${nearest.volume}\n` +
		`side:    ${nearest.side}`

	const chartRect = chartContainer.getBoundingClientRect()
	tooltip.style.left    = `${chartRect.left + param.point.x + 10}px`
	tooltip.style.top     = `${chartRect.top  + param.point.y + 10}px`
	tooltip.style.display = 'block'
})
