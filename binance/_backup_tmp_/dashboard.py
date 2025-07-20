# dashboard.py

#———————————————————————————————————————————————————————————————————————————————

import psutil, time, asyncio, logging
from util import my_name

#———————————————————————————————————————————————————————————————————————————————

async def monitor_hardware(
	network_load_mbps:			  int,
	cpu_load_percentage:		  float,
	mem_load_percentage:		  float,
	storage_percentage:			  float,
	hardware_monitoring_interval: float,
	cpu_percent_duration:		  float,
	desired_max_sys_mem_load:	  float,
	logger:						  logging.Logger,
):

	#———————————————————————————————————————————————————————————————————————————
	# Hardware monitoring function that runs as an async coroutine.
	# Updates global hardware metrics using psutil with non-blocking operations.
	# For details, see `https://psutil.readthedocs.io/en/latest/`.
	#———————————————————————————————————————————————————————————————————————————
	
	# Initialize previous network counters for bandwidth calculation

	prev_counters = psutil.net_io_counters()
	prev_sent	  = prev_counters.bytes_sent
	prev_recv	  = prev_counters.bytes_recv
	prev_time	  = time.time()
	
	logger.info(
		f"[{my_name()}] Hardware monitoring started."
	)
	
	while True:

		try:
			
			wt_start = time.time()

			# CPU Usage: blocking call to get CPU load percentage

			cpu_load_percentage = await asyncio.to_thread(
				psutil.cpu_percent, 
				interval=cpu_percent_duration
			)
			
			# Memory Usage

			memory_info = await asyncio.to_thread(psutil.virtual_memory)
			mem_load_percentage = memory_info.percent
			
			# Storage Usage (root filesystem)

			disk_info = await asyncio.to_thread(psutil.disk_usage, '/')
			storage_percentage = disk_info.percent
			
			# Network Usage (Mbps)

			curr_time = time.time()
			counters  = await asyncio.to_thread(psutil.net_io_counters)
			curr_sent = counters.bytes_sent
			curr_recv = counters.bytes_recv
			
			# Calculate bytes transferred since last measurement

			sent_diff = curr_sent - prev_sent
			recv_diff = curr_recv - prev_recv
			time_diff = curr_time - prev_time
			
			# Convert to Mbps

			if time_diff > 0:

				total_bytes = sent_diff + recv_diff
				network_load_mbps = (
					(total_bytes * 8) / (time_diff * 1_000_000)
				)
			
			# Update previous values

			prev_sent = curr_sent
			prev_recv = curr_recv
			prev_time = curr_time

			# High Memory Load Warning
			# Disabled for now since it can confuse memray
			
			#if mem_load_percentage > desired_max_sys_mem_load:
			#
			#	logger.warning(
			#		f"[{my_name()}]\n"
			#		f"\t  {mem_load_percentage:.2f}% "
			#		f"(mem_load_percentage)\n"
			#		f"\t> {desired_max_sys_mem_load:.2f}% "
			#		f"(desired_max_sys_mem_load)."
			#	)
			
		except Exception as e:

			logger.error(
				f"[{my_name()}] "
				f"Error monitoring hardware: {e}",
				exc_info=True
			)

		finally:

			sleep_duration = max(
				0.0,
				hardware_monitoring_interval
				- (time.time() - wt_start)
			)

			await asyncio.sleep(sleep_duration)

#———————————————————————————————————————————————————————————————————————————————