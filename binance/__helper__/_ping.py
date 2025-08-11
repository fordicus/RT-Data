import asyncio, time
import websockets  # pip install websockets

URL = (
	"wss://stream.binance.com:9443/stream?"
   "streams=btcfdusd@depth20@100ms/btcusdt@depth20@100ms/..."
)

async def ws_ping_rtt(
	url:			  str,
	n:				  int   = 5,
	ping_interval_ms: float = 0.,
):
	
	async with websockets.connect(
		url,
		ping_interval = None,
		ping_timeout  = 10,
	) as ws:
		
		for i in range(n):
			
			t0 = time.perf_counter()
			pong_waiter = await ws.ping()
			await pong_waiter
			
			rtt_ms = (time.perf_counter() - t0) * 1000
			print(
				f"RTT[{i+1}]: {rtt_ms:.1f} ms",
				flush = True,
			)
			
			await asyncio.sleep(
				ping_interval_ms / 1000.
			)

asyncio.run(ws_ping_rtt(URL))
