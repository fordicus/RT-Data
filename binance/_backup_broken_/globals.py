import asyncio, logging
from io import TextIOWrapper
from collections import OrderedDict, deque

SYMBOLS:				list[str] = []

SNAPSHOTS_QUEUE_DICT:	dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]] = {}
RECORDS_MERGED_DATES:	dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:	dict[str, OrderedDict[str]] = {}

LATENCY_DICT:			dict[str, deque[int]] = {}
MEDIAN_LATENCY_DICT:	dict[str, int] = {}
DEPTH_UPDATE_ID_DICT:	dict[str, int] = {}
LATEST_JSON_FLUSH:		dict[str, int] = {}
JSON_FLUSH_INTERVAL:	dict[str, int] = {}