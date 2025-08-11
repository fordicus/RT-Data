# dashboard.py

#———————————————————————————————————————————————————————————————————————————————

import os, asyncio, orjson, random, time, statistics, psutil, logging
from contextlib import asynccontextmanager
from collections import deque
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from util import (
	my_name,
	resource_path,
	get_current_time_ms,
	ms_to_datetime,
)

#———————————————————————————————————————————————————————————————————————————————
# Dashboard Server Class
#———————————————————————————————————————————————————————————————————————————————

class DashboardServer:

	"""
	Class to manage the dashboard server.
	Encapsulates FastAPI app and related functionalities.
	"""

	#———————————————————————————————————————————————————————————————————————————
	# Initialization
	#———————————————————————————————————————————————————————————————————————————
	
	def __init__(
		self,
		state_refs: dict,
		config: dict,
		shutdown_manager,
		logger: logging.Logger,
		monitoring_deque_len: int = 100,
	):

		"""
		Args:
			state_refs: Dictionary of global variable references.
			config: Dashboard configuration values.
			shutdown_manager: Instance of the shutdown manager.
			logger: Logger instance.
		"""
		
		self.state = state_refs
		self.config = config
		self.shutdown_manager = shutdown_manager
		self.logger = logger

		self.snapshot_qsizes_dict: dict[str, deque[int]] = {}
		self.snapshot_qsizes_dict.clear()
		self.snapshot_qsizes_dict.update({
			symbol: deque(maxlen=monitoring_deque_len)
			for symbol in self.state['SYMBOLS']
		})

		self._html_cache = None
		
		#———————————————————————————————————————————————————————————————————————
		# Connection Management (No Locks - Atomic Operations under GIL)
		#———————————————————————————————————————————————————————————————————————
		
		self.active_connections = 0
		
		#———————————————————————————————————————————————————————————————————————
		# Hardware Monitoring Variables (Class-Level)
		#———————————————————————————————————————————————————————————————————————
		
		self.network_load_mbps:	  float = 0.0
		self.cpu_load_percentage: float = 0.0
		self.mem_load_percentage: float = 0.0
		self.storage_percentage:  float = 0.0
		
		#———————————————————————————————————————————————————————————————————————
		# FastAPI App Creation
		#———————————————————————————————————————————————————————————————————————
		
		self.app = self._create_fastapi_app()

	#———————————————————————————————————————————————————————————————————————————
	# FastAPI App Creation
	#———————————————————————————————————————————————————————————————————————————
	
	def _create_fastapi_app(self) -> FastAPI:

		"""Create and configure the FastAPI app."""
		
		@asynccontextmanager
		async def lifespan(app):

			try:

				yield

			except KeyboardInterrupt:

				self.logger.info(
					f"[{my_name()}] "
					f"Application terminated by user (Ctrl + C)."
				)

			except Exception as e:

				self.logger.error(
					f"[{my_name()}] Unhandled exception: {e}",
					exc_info=True
				)

			finally:

				if (
					self.shutdown_manager
					and not self.shutdown_manager.is_shutdown_complete()
				):

					self.logger.info(
						f"[{my_name()}] "
						f"ShutdownManager called"
					)
					self.shutdown_manager.graceful_shutdown()
		
		# Create FastAPI app

		app = FastAPI(lifespan=lifespan)
		
		# Register routes

		app.get(
			"/dashboard",
			response_class=HTMLResponse
		)(
			self._dashboard_page
		)
		app.websocket(
			"/ws/dashboard"
		)(
			self._dashboard_websocket
		)
		
		return app

	#———————————————————————————————————————————————————————————————————————————
	# Dashboard Page Handler
	#———————————————————————————————————————————————————————————————————————————
	
	def _read_html_file(self, html_path: str) -> str:

		"""Synchronous file reading helper for async delegation."""

		with open(html_path, "r", encoding="utf-8") as f:

			return f.read()
	
	async def _dashboard_page(self, request: Request):

		try:

			if self._html_cache is None:

				html_path = resource_path("dashboard.html", self.logger)
				
				if not await asyncio.to_thread(os.path.exists, html_path):

					self.logger.error(
						f"[{my_name()}] HTML file not found: {html_path}"
					)
					raise HTTPException(
						status_code=500,
						detail="Dashboard HTML file missing"
					)
				
				self._html_cache = await asyncio.to_thread(
					self._read_html_file, html_path
				)
			
			return HTMLResponse(content=self._html_cache)
			
		except Exception as e:

			self.logger.error(
				f"[{my_name()}] Failed to serve dashboard: {e}",
				exc_info=True
			)
			raise HTTPException(
				status_code=500,
				detail="Internal server error"
			)

	#———————————————————————————————————————————————————————————————————————————
	# Monitoring Data Builder
	#———————————————————————————————————————————————————————————————————————————

	async def _build_monitoring_data(self) -> dict:

		"""
		Build monitoring data with async yield points for better GIL sharing.
		"""
		
		# Build median latency data with yield point
		med_latency = {}
		for symbol in self.state['SYMBOLS']:
			med_latency[symbol] = self.state[
				'MEAN_LATENCY_DICT'
			].get(symbol, 0)
			await asyncio.sleep(0)
		
		# Build flush interval data with yield point
		flush_interval = {}
		for symbol in self.state['SYMBOLS']:
			
			symbol_data = self.state[
				'JSON_FLUSH_INTERVAL'
			].get(symbol, [])

			if not symbol_data:
				flush_interval[symbol] = -1

			else:
				flush_interval[symbol] = int(
					statistics.fmean(symbol_data)
				)

			await asyncio.sleep(0)
		
		# Build snapshot interval data with yield point
		snapshot_interval = {}
		for symbol in self.state['SYMBOLS']:
			
			snapshot_interval[symbol] = int(
				statistics.fmean(
					self.state[
						'PUT_SNAPSHOT_INTERVAL'
					].get(symbol)
				)
			)
			await asyncio.sleep(0)
		
		# Build queue size data with yield point
		queue_size = {}
		for symbol in self.state['SYMBOLS']:
			self.snapshot_qsizes_dict[symbol].append(
				self.state['SNAPSHOTS_QUEUE_DICT'][symbol].qsize()
			)
			queue_size[symbol] = int(
				statistics.fmean(self.snapshot_qsizes_dict[symbol])
			)
			await asyncio.sleep(0)
		
		return {
			"med_latency":		 med_latency,
			"flush_interval":	 flush_interval,
			"snapshot_interval": snapshot_interval,
			"queue_size":		 queue_size,
			"hardware": {
				"network_mbps":	   round(self.network_load_mbps, 2),
				"cpu_percent":	   self.cpu_load_percentage,
				"memory_percent":  self.mem_load_percentage,
				"storage_percent": self.storage_percentage
			},
			"websocket_peer": self.state['WEBSOCKET_PEER']['value'],
			"last_updated":	  ms_to_datetime(
				get_current_time_ms()
			).isoformat(),
		}

	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Handler
	#———————————————————————————————————————————————————————————————————————————
	
	async def _dashboard_websocket(
		self, websocket: WebSocket
	):

		"""
		Dashboard WebSocket handler.
		"""
	
		reconnect_attempt = 0
		
		while True:

			try:

				# Limit connections (atomic operation without locks)

				if (
					self.active_connections 
					>= self.config['MAX_DASHBOARD_CONNECTIONS']
				):

					await websocket.close(
						code=1008,
						reason="Too many dashboard clients connected."
					)
					self.logger.warning(
						f"[{my_name()}] "
						f"Connection refused: too many clients."
					)
					return
				
				self.active_connections += 1  # Atomic operation
				
				try:
					
					await websocket.accept()
					reconnect_attempt = 0
					
					# Track session time

					start_time_ms = get_current_time_ms()
					max_session_ms = (
						self.config['MAX_DASHBOARD_SESSION_SEC'] * 1000 
						if self.config['MAX_DASHBOARD_SESSION_SEC'] > 0
						else None
					)
					
					# Main data transmission loop

					while True:

						try:

							# Build monitoring data with async yield points

							data = await self._build_monitoring_data()
							
							await websocket.send_text(
								orjson.dumps(data).decode()
							)
							
							# Check session time

							if max_session_ms is not None:

								current_time_ms = get_current_time_ms()

								if (
									(current_time_ms - start_time_ms)
									> max_session_ms
								):

									await websocket.close(
										code=1000,
										reason="session time limit"
									)
									break
							
							await asyncio.sleep(
								self.config['DASHBOARD_STREAM_INTERVAL']
							)
							
						except WebSocketDisconnect:

							self.logger.info(
								f"[{my_name()}] "
								f"ws client disconnects"
							)
							break
							
						except asyncio.CancelledError:

							self.logger.info(
								f"[{my_name()}] "
								f"ws handler task cancelled"
							)
							break
							
						except Exception as e:

							self.logger.warning(
								f"[{my_name()}] "
								f"ws error: {e}",
								exc_info=True
							)
							
							if isinstance(
								e, (
									ConnectionResetError,
									ConnectionAbortedError
								)
							):	break
							
							else:
								
								await asyncio.sleep(1)
								continue
					
					break  # Normal termination
					
				finally:
					
					self.active_connections -= 1  # Atomic operation
					
			except Exception as e:

				reconnect_attempt += 1

				self.logger.warning(
					f"[{my_name()}] Accept failed "
					f"(attempt {reconnect_attempt}): {e}",
					exc_info=True
				)
				
				# Exponential backoff

				backoff = min(
					self.config['MAX_BACKOFF'], 
					self.config['BASE_BACKOFF'] * (2 ** reconnect_attempt)
				) + random.uniform(0, 1)
				
				if (
					reconnect_attempt
					> self.config['RESET_CYCLE_AFTER']
				):
					reconnect_attempt = self.config['RESET_BACKOFF_LEVEL']
				
				self.logger.info(
					f"[{my_name()}] "
					f"Retrying accept in {backoff:.1f} seconds..."
				)
				await asyncio.sleep(backoff)

#———————————————————————————————————————————————————————————————————————————————
# Hardware Monitoring Function
#———————————————————————————————————————————————————————————————————————————————

async def monitor_hardware(
	dashboard_server: DashboardServer,		# Pass DashboardServer instance
	hardware_monitoring_interval: float,
	cpu_percent_duration:		  float,
	desired_max_sys_mem_load:	  float,
	logger: logging.Logger,
):

	"""
	Hardware monitoring function that runs as an async coroutine.
	Updates dashboard server's hardware metrics using psutil
	with non-blocking operations.
	For details, see `https://psutil.readthedocs.io/en/latest/`.
	"""

	async def get_cpu_load() -> float:

		return await asyncio.to_thread(
			psutil.cpu_percent,
			interval=cpu_percent_duration
		)

	async def get_memory_load() -> float:

		memory_info = await asyncio.to_thread(
			psutil.virtual_memory
		)
		return memory_info.percent

	async def get_storage_load() -> float:

		disk_info = await asyncio.to_thread(
			psutil.disk_usage, '/'
		)

		return disk_info.percent

	async def get_network_load(
		prev_sent, prev_recv, prev_time
	):
	
		curr_time = time.time()
		counters = await asyncio.to_thread(
			psutil.net_io_counters
		)
		curr_sent = counters.bytes_sent
		curr_recv = counters.bytes_recv

		sent_diff = curr_sent - prev_sent
		recv_diff = curr_recv - prev_recv
		time_diff = curr_time - prev_time

		if time_diff > 0:
			total_bytes = sent_diff + recv_diff
			network_load_mbps = (
				(total_bytes * 8) 
				/ (time_diff * 1_000_000)
			)
		else:
			network_load_mbps = 0.0

		return (
			network_load_mbps,
			curr_sent,
			curr_recv,
			curr_time
		)

	prev_counters = psutil.net_io_counters()
	prev_sent = prev_counters.bytes_sent
	prev_recv = prev_counters.bytes_recv
	prev_time = time.time()

	logger.info(
		f"[{my_name()}]💻 hw monitor on"
	)

	while True:

		try:
			wt_start = time.time()

			# Batch async operations with yield points between each

			dashboard_server.cpu_load_percentage = await get_cpu_load()
			await asyncio.sleep(0)
			
			dashboard_server.mem_load_percentage = await get_memory_load()
			await asyncio.sleep(0)
			
			dashboard_server.storage_percentage = await get_storage_load()
			await asyncio.sleep(0)
			
			(
				dashboard_server.network_load_mbps,
				prev_sent, prev_recv, prev_time,
			) = await get_network_load(
				prev_sent, prev_recv, prev_time
			)
			await asyncio.sleep(0)
			
		except Exception as e:

			logger.error(
				f"[{my_name()}] Error monitoring hardware: {e}",
				exc_info=True,
			)
			await asyncio.sleep(0)

		finally:

			sleep_duration = max(
				0.0,
				(
					hardware_monitoring_interval 
					- (time.time() - wt_start)
				),
			)
			await asyncio.sleep(sleep_duration)

#———————————————————————————————————————————————————————————————————————————————

def create_dashboard_server(
	state_refs: dict, 
	config: dict, 
	shutdown_manager, 
	logger: logging.Logger
) -> DashboardServer:

	"""
	Factory function for creating a dashboard server instance.
	
	Args:
		state_refs: References to global state variables.
		config: Configuration values.
		shutdown_manager: Shutdown manager instance.
		logger: Logger instance
	
	Returns:
		DashboardServer: Configured dashboard server instance.
	"""

	return DashboardServer(
		state_refs,
		config,
		shutdown_manager,
		logger,
	)

#———————————————————————————————————————————————————————————————————————————————