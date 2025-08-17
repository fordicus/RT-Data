#!/usr/bin/env python3
import subprocess

# ANSI colors for terminal output
GREEN = "\033[92m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

# def run_cmd(cmd):
#     """Run a shell command and return stdout, or empty string if it fails."""
#     try:
#         return subprocess.check_output(cmd, shell=True, text=True).strip()
#     except subprocess.CalledProcessError:
#         return ""
        
def run_cmd(cmd):
    """Run a shell command and return stdout+stderr, or empty string if it fails."""
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError:
        return ""

def color_line(line, expected=True):
    """expected=True → Green, expected=False → Magenta."""
    if not line:
        return f"{MAGENTA}(no output){RESET}"
    return f"{GREEN}{line}{RESET}" if expected else f"{MAGENTA}{line}{RESET}"

print("=== Core Services ===")

# xrdp
print("[xrdp]")
xrdp = run_cmd("systemctl is-active xrdp")
print(color_line(f"Active: {xrdp}", xrdp == "active"))

# auto-cpufreq (snap service)
print("[auto-cpufreq]")
acf = run_cmd("snap services auto-cpufreq | grep auto-cpufreq.service")
print(color_line(acf, "active" in acf))

# chrony (time sync)
print("[chrony]")
chrony = run_cmd("systemctl is-active chrony")
print(color_line(f"Active: {chrony}", chrony == "active"))

print("\n=== Power Management ===")

# xfce4-power-manager settings
print("[xfce4-power-manager]")
xfce_pm = run_cmd(
    "xfconf-query -c xfce4-power-manager -l -v | grep -E '(blank|sleep|monitor-power)-on-ac'"
)
for line in xfce_pm.splitlines():
    expected = ("0" in line or "false" in line)
    print(color_line(f"  {line}", expected))

# xset DPMS and blanking
print("[xset]")
xset_out = run_cmd("xset q | grep -E 'timeout|DPMS|prefer blanking'")
for line in xset_out.splitlines():
    if "timeout" in line and "0" in line:
        print(color_line(f"  {line}", True))
    elif "prefer blanking" in line and "no" in line:
        print(color_line(f"  {line}", True))
    elif "prefer blanking" in line and "yes" in line:
        print(color_line(f"  {line}", False))
    elif "DPMS is Disabled" in line:
        print(color_line(f"  {line}", True))
    elif "DPMS is Enabled" in line:
        print(color_line(f"  {line}", False))
    else:
        print(f"  {line}")

print("\n=== Display & Sleep Prevention ===")

# Xorg hints
print("[Xorg Display Info]")
xorg_info = run_cmd(
    "grep -E 'AllowEmpty|ConnectedMonitor|Virtual screen size|connected' "
    "/var/log/Xorg.0.log 2>/dev/null | grep -v 'WW' | tail -3"
)
print(xorg_info if xorg_info else "  (no extra info)")

# xrandr outputs
print("[xrandr]")
print(run_cmd("xrandr | grep ' connected'"))

# systemd sleep targets
print("[systemd sleep targets]")
sleep_targets = [
    "sleep.target",
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
]

for target in sleep_targets:
    masked = run_cmd(f"systemctl list-unit-files | grep -w {target} | grep masked")
    if masked:
        print(color_line(f"  {target}: masked", True))
    else:
        status = run_cmd(f"systemctl status {target} | grep 'Active:'")
        expected = "inactive" in status.lower()
        print(color_line(f"  {target}: {status}", expected))

print("\n=== WireGuard & DNS ===")

# DNSMasq
print("[dnsmasq]")
for svc in ["dnsmasq.service", "dnsmasq-wireguard.service"]:
    dnsmasq_state = run_cmd(f"systemctl is-active {svc}")
    dnsmasq_enabled = run_cmd(f"systemctl is-enabled {svc}")
    if dnsmasq_state == "active":
        print(color_line(f"{svc}: Active (enabled={dnsmasq_enabled})", True))
    elif dnsmasq_enabled == "enabled":
        print(color_line(f"{svc}: {dnsmasq_state} (enabled but not running)", False))

# wg0 interface presence
print("[wg0 interface]")
wg0 = run_cmd("ip addr show wg0 2>/dev/null | grep 'inet '")
print(color_line(wg0, "10.10.0.1" in wg0))

# UDP listening ports
print("[listening UDP ports]")
udp_ports = run_cmd("ss -ulpn")
for line in udp_ports.splitlines():
    if ":51820" in line:  # WireGuard port
        print(color_line(f"  {line}", True))
    elif ":53" in line and "dnsmasq" in line:  # DNSMasq port
        print(color_line(f"  {line}", True))
    else:
        print(f"  {line}")

# Fail2ban
print("[fail2ban]")
fail2ban = run_cmd("systemctl is-active fail2ban")
print(color_line(f"Active: {fail2ban}", fail2ban == "active"))

# Fail2ban jails
print("[fail2ban jails]")
jails = run_cmd("sudo fail2ban-client status")
print(jails if jails else "(no jail info)")
