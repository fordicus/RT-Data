# latency.py

#———————————————————————————————————————————————————————————————————————————————
# Binance latency sanity check
#———————————————————————————————————————————————————————————————————————————————
# Observed ≈ 114 ms one‑way latency 
# 	(local_recv_ts − server_event_ts)
# from Swiss.
#
# Plausibility:
#   • Likely route: Switzerland → AWS ap‑northeast‑1 (Tokyo, Spot REST primary)
#	 or Cloudflare / GCP PoP → Binance WS broker.
#	 Propagation CH→JP ≈50‑60 ms; add router, TLS, Anycast & broker hops
#	 ≈10‑25 ms ⇒ practical upper‑bound 100‑140 ms → 114 ms fits.
#   • Binance exposes several hosts:
#	   - Primary REST:   api.binance.com  (Tokyo)
#	   - Alternatives:   api1.binance.com, api‑gcp.binance.com
#	   - Market data:	data‑api.binance.vision
#	 All WS endpoints are Anycast, so region may vary per connection.
#   • Measurement: server_event_ts comes in the WS payload; Chrony‑synced local
#	 clock, parsing+GC <1 ms, clock skew ±1 ms ⇒ figure is trustworthy.
#———————————————————————————————————————————————————————————————————————————————

import asyncio, logging
import websockets, time, random, statistics, orjson
import numpy as np
from collections import deque
from typing import Optional
from util import (
	my_name,
	get_ssl_context,
	NanoTimer,
	get_current_time_ms, 
	format_ws_url,
	ensure_logging_on_exception,
)

#———————————————————————————————————————————————————————————————————————————————
# Old Name					New Name				Type
#———————————————————————————————————————————————————————————————————————————————
# MEAN_LATENCY_DICT       
# mean_latency_dict			lat_mon.latency			dict[str, int]
#
# EVENT_LATENCY_VALID     
# event_latency_valid		lat_mon.evnt_ok_		asyncio.Event
#
# EVENT_STREAM_ENABLE     
# event_stream_enable		lat_mon.evnt_go_		asyncio.Event
#
# EVENT_1ST_SNAPSHOT      
# event_1st_snapshot		lat_mon.evnt_1st_dom	asyncio.Event
# 							lat_mon.evnt_1st_exe
#
# latency_routine_sleep_sec	lat_mon.rouslsec		float
#———————————————————————————————————————————————————————————————————————————————

class LatencyMonitor:
	
	def __init__(self, 
		latency_deque_size:	 	   int,
		latency_threshold_ms:	   int,
		latency_routine_sleep_sec: float,
		symbols:			 	   list[str],
	):
		
		self.deque_sz = latency_deque_size
		self.thrs_ms  = latency_threshold_ms
		self.rouslsec = latency_routine_sleep_sec
		
		self.latency: dict[str, int] = {}
		self.latency.clear()
		self.latency.update({
			symbol: None
			for symbol in symbols
		})

		self.evnt_ok_ = asyncio.Event()
		self.evnt_go_ = asyncio.Event()

		self.evnt_1st_dom = asyncio.Event()
		self.evnt_1st_exe = asyncio.Event()

#———————————————————————————————————————————————————————————————————————————————
# LEGACY FUNCTIONS
#———————————————————————————————————————————————————————————————————————————————

async def gate_streaming_by_latency(
	lat_mon:		LatencyMonitor,
	symbols:		list[str],
	logger:			logging.Logger,
	evnt_shutdown:	asyncio.Event,
):

	has_logged_warmup = False

	while not evnt_shutdown.is_set():				# infinite standalone loop

		#———————————————————————————————————————————————————————————————————————

		try:

			latency_passed	= lat_mon.evnt_ok_.is_set()
			is_stream_on	= lat_mon.evnt_go_.is_set()
			has_all_latency	= all(
				lat_mon.latency[s]
				is not None
				for s in symbols
			)

			if (
				latency_passed
				and not is_stream_on
			):

				logger.info(
					f"[{my_name()}]"
					f"📈 latency normalized"
				)

				lat_mon.evnt_go_.set()
				has_logged_warmup = False

			elif not latency_passed:

				if (
					not has_all_latency
					and not has_logged_warmup
				):

					logger.info(
						f"[{my_name()}]🔥 warming up"
					)

					has_logged_warmup = True

				elif (
					has_all_latency
					and is_stream_on
				):

					logger.warning(
						f"[{my_name()}]"
						f"📉 latency degraded"
					)

					lat_mon.evnt_go_.clear()

			await asyncio.sleep(lat_mon.rouslsec)

		#———————————————————————————————————————————————————————————————————————

		except asyncio.CancelledError:

			raise # logging unnecessary

		#———————————————————————————————————————————————————————————————————————

		except Exception as e:

			logger.error(
				f"[{my_name()}] "
				f"Exception in latency gate: "
				f"{e}",
				exc_info=True
			)

			await asyncio.sleep(lat_mon.rouslsec)

		#———————————————————————————————————————————————————————————————————————
			
	logger.info(
		f"[{my_name()}] task ends"
	)

#———————————————————————————————————————————————————————————————————————————————
