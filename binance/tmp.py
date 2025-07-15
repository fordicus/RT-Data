from concurrent.futures import ProcessPoolExecutor

def func(x: str):
	# ... do something with pickled `x` ...
	return

EXECUTOR = ProcessPoolExecutor(max_workers=4)
print(type(EXECUTOR))
exit()