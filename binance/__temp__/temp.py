#———————————————————————————————————————————————————————————————————————————————
# GLOBAL ARRAYS
#———————————————————————————————————————————————————————————————————————————————

SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}
EXECUTIONS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}

FHNDLS_LOB_SPOT_BINANCE:	dict[str, tuple[str, TextIOWrapper]] = {}
FHNDLS_EXE_SPOT_BINANCE:	dict[str, tuple[str, TextIOWrapper]] = {}

SHARED_TIME_DICT:			dict[str, float] = {}

#———————————————————————————————————————————————————————————————————————————————

PUT_SNAPSHOT_INTERVAL:		dict[str, deque[int]] = {}

LOB_SAV_INTV_SPOT_BINANCE:	dict[str, deque[int]] = {}
EXE_SAV_INTV_SPOT_BINANCE:	dict[str, deque[int]] = {}

MEAN_LATENCY_DICT:			dict[str, int] = {}
WEBSOCKET_PEER:				dict[str, str] = {"value": "UNKNOWN"}

#———————————————————————————————————————————————————————————————————————————————