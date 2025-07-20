r""" ———————————————————————————————————————————————————————————————————
   A Collection of Worthy Python Script Templates written by c01hyka
														  2025-07-12
———————————————————————————————————————————————————————————————————— """

async def WEBSOCKET_INGESTION_TEMPLATE() -> None:
	
	""" ————————————————————————————————————————————————————————————————
	Resource/Connection/Reference-stable Template for WebSocket Ingestion
	———————————————————————————————————————————————————————————————— """
	
	while True:
		
		try:
			
			async with websockets.connect(WS_URL) as ws:
				
				""" ————————————————————————————————————————————————————
				You may log a successful WebSocket connection here.
				———————————————————————————————————————————————————— """
				
				async for raw in ws:
					
					""" ————————————————————————————————————————————————
					Even though the for-loop syntax might be confusing,
					`async for raw in ws:` runs indefinitely until the
					WebSocket is disconnected, whether the disconnection
					is normal or abnormal.
					———————————————————————————————————————————————— """
					
					try:
						
						""" ————————————————————————————————————————————
						# process a message
						———————————————————————————————————————————— """
						
						pass
						
					except Exception as e:
						
						""" ————————————————————————————————————————————
						# failed to process a message: put some logs.
						———————————————————————————————————————————— """
						
						continue
						
					finally:
						
						""" ————————————————————————————————————————————
						# must delete temporary references
						———————————————————————————————————————————— """
						
		except Exception as e:
			
			""" ————————————————————————————————————————————————————————
			WebSocket connection is interrupted: implement a back-off.
			———————————————————————————————————————————————————————— """
			
			await asyncio.sleep(backoff)
			
		finally:
			
			""" ————————————————————————————————————————————————————————
			`ws` is still referenced, even though the resource is has a
			guarantee to be released due to the `with` statement.
			———————————————————————————————————————————————————————— """
			
			del ws

""" ————————————————————————————————————————————————————————————————————
	⚛️ Fire-and-Forget / GIL-Free / Atomic Process Concurrency
———————————————————————————————————————————————————————————————————— """

from concurrent.futures import ProcessPoolExecutor

def func(x: str):
	# ... do something with pickled `x` ...
	return

EXECUTOR = ProcessPoolExecutor(max_workers=4)
for i in range(4):
	EXECUTOR.submit(func, i)

# ...any codes agnostic to {EXECUTOR, func, i}...
# just safely release EXECUTOR on exit(), e.g.,:
#	EXECUTOR.shutdown(wait=True)
#	or atexit.register(EXECUTOR.shutdown, wait=True)
#	with `wait=True` if the return of `func` is guaranteed.

""" ————————————————————————————————————————————————————————————————————
# Parallel processes / Shared state, Synchronized by Lock.
———————————————————————————————————————————————————————————————————— """

from multiprocessing import shared_memory, Process, Lock
import struct  # int ↔ Byte

def worker(shm_name, lock):
	
	shm = shared_memory.SharedMemory(name=shm_name)

	with lock:
		value = struct.unpack('i', shm.buf[:4])[0]
		value += 1
		shm.buf[:4] = struct.pack('i', value)

	shm.close()

if __name__ == "__main__":
	
	shm = shared_memory.SharedMemory(create=True, size=4)
	shm.buf[:4] = struct.pack('i', 0)

	lock = Lock()
	processes = [
		Process(target=worker, args=(shm.name, lock))
		for _ in range(4)
	]

	for p in processes: p.start()
	for p in processes: p.join()

	result = struct.unpack('i', shm.buf[:4])[0]
	print("Final Result:", result)  # Final Result: 4

	shm.close()
	shm.unlink()

# ——————————————————————————————————————————————————————————————————————