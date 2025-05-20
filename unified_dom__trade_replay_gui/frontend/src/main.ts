import { createChart } from 'lightweight-charts'

const chartContainer = document.getElementById('chart') as HTMLElement

const chart = createChart(chartContainer, {
	width: chartContainer.clientWidth,
	height: chartContainer.clientHeight,
	layout: {
		background: { color: '#111' },
		textColor: '#DDD',
	},
	grid: {
		vertLines: { color: '#222' },
		horzLines: { color: '#222' },
	},
	timeScale: {
		timeVisible: true,
		secondsVisible: true
	},
	localization: {
		// Show full time precision on hover: YYYY-MM-DD hh:mm:ss.fff
		timeFormatter: (ts) => {
			const d = new Date(ts * 1000)
			const yyyy = d.getFullYear()
			const MM = String(d.getMonth() + 1).padStart(2, '0')
			const dd = String(d.getDate()).padStart(2, '0')
			const hh = String(d.getHours()).padStart(2, '0')
			const mm = String(d.getMinutes()).padStart(2, '0')
			const ss = String(d.getSeconds()).padStart(2, '0')
			const fff = String(d.getMilliseconds()).padStart(3, '0')
			return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}.${fff}`
		}
	}
})

const series = chart.addLineSeries()

fetch('http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17')
	.then(res => res.json())
	.then(data => {
		const points = data.map((pt: any) => ({
			time: pt.time,
			value: pt.value,
		}))

		points.sort((a, b) => a.time - b.time)

		console.log('Loaded points:', points.slice(0, 5))
		series.setData(points)
		chart.timeScale().fitContent()
	})
	.catch(err => {
		console.error('Failed to fetch tick data:', err)
	})