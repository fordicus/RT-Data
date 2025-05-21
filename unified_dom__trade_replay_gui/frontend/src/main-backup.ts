import {
	createChart,
	CrosshairMode,
} from 'lightweight-charts'

/** Utility: Pad number to fixed width */
const pad = (n: number, width = 2) => String(n).padStart(width, '0')

/** Utility: Format UNIX timestamp (seconds) to local Date */
const toLocalDate = (ts: number): Date => new Date(ts * 1000)

/** Utility: Format time for tooltip title */
const formatFullTimestamp = (d: Date): string => {
	const tzOffset = -d.getTimezoneOffset() / 60
	const sign = tzOffset >= 0 ? '+' : '-'
	const tz = `UTC ${sign}${Math.abs(tzOffset)}`
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.` +
		`${pad(d.getMilliseconds(), 3)} (${tz})`
	)
}

/** Utility: Format for tick label */
const formatTickLabel = (d: Date): string => {
	if (d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0) {
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
	}
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// Prepare chart container
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
		timeVisible    : true,
		secondsVisible : true,

		// Placeholder – will be overwritten after preprocessed data ready
		tickMarkFormatter: () => ''
	}
})

const series = chart.addLineSeries()

// Prepare tooltip
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

// Global cache for tooltip access
const tooltipCache = new Map<number, any>()

fetch('http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17')
	.then(res => res.json())
	.then(data => {
		// Preprocess: sort, cache, and prepare for chart
		const points = data.map((pt: any) => {
			const localDate = toLocalDate(pt.time)

			tooltipCache.set(pt.time, {
				timeObj  : localDate,
				value    : pt.value,
				volume   : pt.volume,
				side     : pt.side
			})

			return {
				time : pt.time,
				value: pt.value
			}
		})

		points.sort((a, b) => a.time - b.time)

		// Override tickMarkFormatter using preprocessed local times
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

// Tooltip logic
chart.subscribeCrosshairMove(param => {
	if (!param.time || !param.seriesData.has(series)) {
		tooltip.style.display = 'none'
		return
	}

	const ts = param.time as number
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
	tooltip.style.left = `${chartRect.left + param.point.x + 10}px`
	tooltip.style.top  = `${chartRect.top  + param.point.y + 10}px`
	tooltip.style.display = 'block'
})
