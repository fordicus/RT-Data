# stream_binance_utils.py
# Refer to RULESET.md for coding guidelines.

r"""............................................................................

How to Use:
	Open `stream_binance_dashboard.html`
	in a web browser to access the dashboard.

Functionality:
	Serve a WebSocket endpoint for real-time monitoring of `stream_binance.py`.
	Stream shared memory metrics (`shared_state_dict`) and
	hardware resource usage.

IO Structure:
	Inputs:
		- Shared memory dictionary from `stream_binance.py`.
	Outputs:
		- WebSocket endpoint:
			/ws/med_latency → JSON: real-time metrics

Dependency:
	See `requirements.txt` for the list of dependencies.
	This script is always internally run by `stream_binance.py`.

TODO:
	- Logging on a critical failure via an independent `logger`.
	- If this script accesses an external resource, ensure it is
	  included in the resources bundled during PyInstaller execution,
	  using `stream_binance.resource_path`.

....................................................................................
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from multiprocessing import Manager
import asyncio

app = FastAPI()

# ───────────────────────────────────────────────────────────────────────────────

def dashboard(
	dashboard_stream_freq,
	shared_state_dict
):

	@app.websocket("/ws/med_latency")
	async def websocket_med_latency(websocket: WebSocket):

		await websocket.accept()

		while True:

			try:

				# Read data from shared memory and send to client

				data = {
					"med_latency": dict(shared_state_dict.get("med_latency", {}))
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

# ───────────────────────────────────────────────────────────────────────────────