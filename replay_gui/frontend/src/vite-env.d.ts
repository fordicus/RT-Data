import { defineConfig } from 'vite'

export default defineConfig({
	resolve: {
		alias: {
			'lightweight-charts': 'lightweight-charts/dist/lightweight-charts.esm.js'
		}
	}
})
