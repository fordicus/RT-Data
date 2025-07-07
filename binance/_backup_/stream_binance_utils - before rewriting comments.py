# stream_binance_utils.py
# Refer to RULESET.md for coding guidelines.

r"""............................................................................

Note:
	- The production binary is built via `compile_linux.bat`, which uses Docker
	  to produce a statically linked Linux executable from `stream_binance_dashboard.py`.
	- No Python environment is required at runtime for the production build.

....................................................................................

Dependency:
	Python ≥ 3.9
	fastapi==0.111.0
	uvicorn==0.30.1
	psutil==5.9.0

Functionality:
	Serve a WebSocket endpoint for real-time monitoring of `stream_binance.py`.
	Stream shared memory metrics (`med_latency`) and hardware resource usage.

IO Structure:
	Inputs:
		- Shared memory dictionary from `stream_binance.py`.
	Outputs:
		- WebSocket endpoint:
			/ws/med_latency → JSON: real-time metrics

....................................................................................
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from multiprocessing import Manager
import asyncio, psutil

# Create FastAPI app

app = FastAPI()

# Access shared memory (passed from the main process)

def dashboard(
	dashboard_stream_freq,
	stream_binance_dashboard
):

	@app.websocket("/ws/med_latency")
	async def websocket_med_latency(websocket: WebSocket):

		await websocket.accept()

		while True:

			try:

				# Read data from shared memory and send to client

				data = {
					"med_latency": dict(stream_binance_dashboard.get("med_latency", {}))
					# "cpu_usage": psutil.cpu_percent(interval=None),
					# "memory_usage": psutil.virtual_memory().percent,
					# "disk_usage": psutil.disk_usage('/').percent
				}

				await websocket.send_json(data)
				await asyncio.sleep(dashboard_stream_freq)

			except WebSocketDisconnect:

				break

			except Exception as e:

				print(f"WebSocket error: {e}")
				break

	import uvicorn

	try:

		uvicorn.run(app, host="0.0.0.0", port=8080)

	except KeyboardInterrupt:

		print("[dashboard] Terminated by user (Ctrl + C).")

		# TODO: Logging?