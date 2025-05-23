/**
 * Vite Configuration File for Frontend Dev Server
 *
 * 🧩 Purpose:
 * - Enable aliasing for clean imports (e.g., "@/utils")
 * - Proxy API requests to backend (FastAPI) running on port 8000
 * - Avoids CORS issues and prevents HTML fallback errors on /api/ calls
 *
 * 📁 Project context:
 * - This file should be in: frontend/vite.config.ts
 * - Works in tandem with: frontend/src/main.ts
 * - Static HTML: frontend/index.html
 */

import { defineConfig } from 'vite'
import path from 'path'

export default defineConfig({
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
		},
	},

	server: {
		proxy: {
			'/api': {
				target: 'http://localhost:8000',  // FastAPI backend
				changeOrigin: true,
				secure: false
			}
		}
	}
})
