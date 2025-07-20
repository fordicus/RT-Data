# dashboard.py

#———————————————————————————————————————————————————————————————————————————————

import psutil, time, asyncio, logging
from util import my_name

#———————————————————————————————————————————————————————————————————————————————

async def monitor_hardware(
	network_load_mbps: int,
	cpu_load_percentage: float,
	mem_load_percentage: float,
	storage_percentage: float,
	hardware_monitoring_interval: float,
	cpu_percent_duration: float,
	desired_max_sys_mem_load: float,
	logger: logging.Logger,
):

	#———————————————————————————————————————————————————————————————————————————
	# Hardware monitoring function that runs as an async coroutine.
	# Updates global hardware metrics using psutil with non-blocking operations.
	# For details, see `https://psutil.readthedocs.io/en/latest/`.
	#———————————————————————————————————————————————————————————————————————————

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

	#———————————————————————————————————————————————————————————————————————————
	# Main monitoring loop
	#———————————————————————————————————————————————————————————————————————————

	prev_counters = psutil.net_io_counters()
	prev_sent = prev_counters.bytes_sent
	prev_recv = prev_counters.bytes_recv
	prev_time = time.time()

	logger.info(f"[{my_name()}] Hardware monitoring started.")

	while True:

		try:

			wt_start = time.time()

			cpu_load_percentage = await get_cpu_load()
			mem_load_percentage = await get_memory_load()
			storage_percentage  = await get_storage_load()
			(
				network_load_mbps,
				prev_sent,
				prev_recv,
				prev_time,
			) = await get_network_load(prev_sent, prev_recv, prev_time)

			# High Memory Load Warning (disabled for now)
			# if mem_load_percentage > desired_max_sys_mem_load:
			#	 logger.warning(
			#		 f"[{my_name()}] High memory load detected: "
			#		 f"{mem_load_percentage:.2f}% > {desired_max_sys_mem_load:.2f}%"
			#	 )

		except Exception as e:

			logger.error(
				f"[{my_name()}] Error monitoring hardware: {e}",
				exc_info=True,
			)

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