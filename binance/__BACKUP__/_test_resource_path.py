# test_resource_path.py

from init import resource_path
from pathlib import Path

print(
	"[TEST] dashboard.html exists:",
	Path(
		resource_path(
			"dashboard.html",
		)
	).exists()
)
