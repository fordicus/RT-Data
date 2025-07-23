# test_resource_path.py

from util import resource_path
from pathlib import Path

app_conf_exists  = Path(resource_path("app.conf")).exists()
dashboard_exists = Path(resource_path("dashboard.html")).exists()

print(f"[TEST] app.conf exists: {app_conf_exists}")
print(f"[TEST] dashboard.html exists: {dashboard_exists}")

if (
	app_conf_exists
	and dashboard_exists
):	  exit(0)
else: exit(1)