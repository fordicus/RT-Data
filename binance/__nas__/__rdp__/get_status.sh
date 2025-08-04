#!/bin/bash  

echo "=== Core Services ==="
systemctl status xrdp | grep Active
systemctl status auto-cpufreq | grep Active
systemctl status nvidia-persist.service | grep Active
systemctl status chrony | grep Active

echo "=== Power Management ==="
xfconf-query -c xfce4-power-manager -l -v | grep -E "(blank|sleep|monitor-power)-on-ac"
xset q | grep -E 'timeout.*0|DPMS.*disabled|prefer blanking.*no'

echo "=== Display & Sleep Prevention ==="
grep -E 'AllowEmpty|ConnectedMonitor|Virtual screen size|DFP-0: connected' /var/log/Xorg.0.log 2>/dev/null | grep -v 'WW' | tail -3
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target | grep Active

echo "=== WireGuard & DNS ==="
systemctl status wg-quick@wg0 | grep Active
systemctl status dnsmasq | grep Active
ip addr show wg0 2>/dev/null | grep "inet 10.10.0.1" || echo "❌ wg0 interface not ready"
ss -ulpn | grep "10.10.0.1:53" >/dev/null && echo "✅ dnsmasq listening on wg0" || echo "❌ dnsmasq not listening on wg0"
