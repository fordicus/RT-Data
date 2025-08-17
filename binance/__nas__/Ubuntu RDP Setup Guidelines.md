# Setup Guide: RDP & NAS @`Ubuntu Desktop 24.04.2 LTS`


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 🟠 TODO:
*	Migration From `http` to `https`
*	Launch `cloudflare_ddns.py` at system reboot

## 💡Tips  

A. Update Software:
```bash
sudo apt update
sudo apt full-upgrade -y
```

B. To check the Ubuntu system’s `internal IP` address, type at Terminal:
```bash
hostname -I
```

C. To check the router’s `public IP` addresses, type at Terminal:
```bash
curl 'https://api.ipify.org'
curl 'https://api6.ipify.org'
```

D. Useful `connectivity` tests:
```bash
sudo systemctl status ssh
sudo netstat -tlnp

nslookup <your-domain>
ping <your-domain>

sudo tail -f /var/log/ufw.log
sudo tail -f /var/log/auth.log
sudo tail -f /var/log/xrdp.log

# PowerShell
Test-NetConnection -ComputerName <your-domain> -Port <your-port>
```

X. Monitor Status of Ports Externally: [`UptimeRobot`](https://uptimerobot.com/)

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 📝Table of Contents  

[***1. System Stability and Maintenance***](#1-system-stability-and-maintenance)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.1 ☕ Completely `Prevent Sleep`](#11-☕-completely-prevent-sleep)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.2 ⚙️ Set Dynamic `Power Management` for CPU and GPU](#12-⚙️-set-dynamic-power-management-for-cpu-and-gpu)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.3 🔐 Restrict Automatic Updates to `Security Patches` Only](#13-🔐-restrict-automatic-updates-to-security-patches-only)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.4 🕓 Enable Accurate Time Sync with `Chrony`](#14-🕓-enable-accurate-time-sync-with-chrony)  

[***2. RDP Setup***](#2-rdp-setup)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.1 🧩 Install and Enable `xrdp` Service](#21-🧩-install-and-enable-xrdp-service)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.2 🛠️ XFCE RDP Setup with D-Bus and Session Diagnostics](#22-🛠️-xfce-rdp-setup-with-d-bus-and-session-diagnostics)    
&nbsp;&nbsp;&nbsp;&nbsp;[2.3 🌐 Assign or Monitor `Internal IP Address`](#23-🌐-assign-or-monitor-internal-ip-address)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.4 🛡️ Allow Remote Desktop through UFW `Firewall` within the Local Network](#24-🛡️-allow-remote-desktop-through-ufw-firewall-within-the-local-network)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.5 🦆 DuckDNS Setup for `External Access`](#25-🦆-duckdns-setup-for-external-access)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.6 📶 Router `Port Forwarding`](#26-📶-router-port-forwarding)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.7 📡 `DNS + Port` Check](#27-📡-dns--port-check)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.8 📁 Configure `.rdp` Files for `Intranet` and `External Access`](#28-📁-configure-rdp-files-for-intranet-and-external-access)  

[***3. Remote File System Access Using `FileZilla` (SFTP)***](#3-remote-file-system-access-using-filezilla-sftp)  
&nbsp;&nbsp;&nbsp;&nbsp;[3.1 Install and Start the `SSH` Server on Ubuntu](#31-install-and-start-the-ssh-server-on-ubuntu)  
&nbsp;&nbsp;&nbsp;&nbsp;[3.2 Allow SFTP through UFW `Firewall` within the Local Network](#32-allow-sftp-through-ufw-firewall-within-the-local-network)  
&nbsp;&nbsp;&nbsp;&nbsp;[3.3 📶 Router `Port Forwarding`](#33-📶-router-port-forwarding)  
&nbsp;&nbsp;&nbsp;&nbsp;[3.4 Install `FileZilla` Client on Windows](#34-install-filezilla-client-on-windows)  

[***4. RnD Environment Preparation***](#4-rnd-environment-preparation)  

&nbsp;&nbsp;&nbsp;&nbsp;[4.1 🧬 Install `Anaconda` and `PyTorch` Environment](#41-🧬-install-anaconda-and-pytorch-environment)  

[***5. Dashboard Service for your App***](#5-dashboard-service-for-your-app)  
&nbsp;&nbsp;&nbsp;&nbsp;[5.1 Add `HTMLResponse` & `WebSocket` Endpoints via `FastAPI @Python`](#51-add-htmlresponse--websocket-endpoints-via-fastapi-python)  
&nbsp;&nbsp;&nbsp;&nbsp;[5.2 `NginX` Configuration at your Ubuntu Server](#52-nginx-configuration-at-your-ubuntu-server)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.2.1 Install and Configure `NginX`](#521-install-and-configure-nginx)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.2.2 Allow Dashboard Traffic through UFW `Firewall` within the Local Network](#522-allow-dashboard-traffic-through-ufw-firewall-within-the-local-network)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.2.3 `Port Forwarding` at your Router](#523-port-forwarding-at-your-router)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.2.4 Check `External IP` Addresses](#524-check-external-ip-addresses)  
&nbsp;&nbsp;&nbsp;&nbsp;[5.3 `Dynamic IPv4` Adaptation through CloudFlare for your Domain-Rounter](#53-dynamic-ipv4-adaptation-through-cloudflare-for-your-domain-rounter)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.3.1 Purchase and Transfer your `Domain`](#531-purchase-and-transfer-your-domain)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.3.2 IPv4-Dynamic DNS Setup via `CloudFlare API`](#532-ipv4-dynamic-dns-setup-via-cloudflare-api)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.3.3 `Security` Enhancements for your Domain](#533-security-enhancements-for-your-domain)  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[5.3.4 `Connectivity` Test](#534-connectivity-test)  

[***6. Tunneling RDP and SFTP through WireGuard***](#6-tunneling-rdp-and-sftp-through-wireguard)  
&nbsp;&nbsp;&nbsp;&nbsp;[6.1 A few Changes for the `CloudFlare and Router Settings`](#61-a-few-changes-for-the-cloudflare-and-router-settings)  
&nbsp;&nbsp;&nbsp;&nbsp;[6.2 `WireGuard` Setup](#62-wireguard-setup)  

[***Y. Reboot Checklist***](#y-reboot-checklist)  

[***Z. Security Considerations***](#z-security-considerations)  

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 1. System Stability and Maintenance

### 1.1 ☕ Completely `Prevent Sleep`

**Modify `/etc/systemd/logind.conf`**:

```bash
# sudo nano /etc/systemd/logind.conf

HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
```

Apply the changes:

```bash
sudo systemctl restart systemd-logind
```

To disable AC power-based sleep/blanking behavior in `Xfce`, create and execute the following script:

```bash
#-------------------------------------------------------------------------------
# sudo nano /etc/apt/sources.list.d/ubuntu.sources
# 
# Types: deb
# URIs: http://ch.archive.ubuntu.com/ubuntu/
# Suites: noble
# Components: main universe multiverse restricted		# add beyond main
# Architectures: amd64 i386
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
# 
# Types: deb
# URIs: http://security.ubuntu.com/ubuntu/
# Suites: noble-security
# Components: main universe multiverse restricted		# add beyond main
# Architectures: amd64 i386
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
# 
# sudo apt update && sudo apt install -y xfconf
# which xfconf-query
#-------------------------------------------------------------------------------
# sudo nano ~/disable-xfce-ac-power-saving.sh  
# chmod +x ~/disable-xfce-ac-power-saving.sh  
# ./disable-xfce-ac-power-saving.sh
#-------------------------------------------------------------------------------

set -e

echo "Applying Xfce power settings (AC mode)..."

xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/blank-on-ac \
	--create -t int -s 0

xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/sleep-on-ac \
	--create -t int -s 0

xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/sleep-display-ac \
	--create -t int -s 0

xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/monitor-power-off-on-ac \
	--create -t bool -s false

xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/brightness-inactivity-on-ac \
	--create -t int -s 0

echo "✅ All AC-mode power saving features have been disabled for Xfce."
```

To ensure the script above runs automatically at login:
```ini
# mkdir -p ~/.config/autostart  
# sudo nano ~/.config/autostart/disable-xfce-ac-power-saving.desktop

[Desktop Entry]
Type=Application
Exec=/bin/bash -c 'bash "$HOME/disable-xfce-ac-power-saving.sh"'  
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Disable XFCE AC Power Saving
Comment=Prevents suspend and screen blanking while on AC power
```

Next, let `xserver` be persistent all the time:
```bash
# sudo nano /etc/X11/xorg.conf

Section "Device"
	Identifier	 "Device0"
	Driver		 "nvidia"
	VendorName	 "NVIDIA Corporation"
	Option		 "AllowEmptyInitialConfiguration" "true"
	Option		 "ConnectedMonitor" "DFP-0"
	Option		 "CustomEDID" "DFP-0:/etc/X11/edid.bin"
EndSection
```
Apply the configuration above by restarting `Xorg`:
```
sudo systemctl restart display-manager
```

Prevent any display timeout or power-saving interruptions of `Xorg-based xrdp` without needing a physical monitor by configuring as follows:
```bash
# sudo nano ~/.xsession

xset s off
xset s noblank
xset -dpms
startxfce4
```
Any new `Xorg` sessions will follow this configuration onward.

To permanently prevent screen blanking and DPMS under GNOME with X11,
disable session idle timeout and power sleep:
```bash
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
gsettings set org.gnome.desktop.session idle-delay 0
```

To disable X11 screen blanking and DPMS on login,
append this to `~/.xprofile` (run once):
```bash
echo 'xset s off -dpms s noblank' >> ~/.xprofile
chmod +x ~/.xprofile
```

Then create a `.desktop` autostart entry:
```bash
# ~/.config/autostart/xset-noblank.desktop

[Desktop Entry]
Name=XSet No Blank
Exec=/usr/bin/xset s off -dpms s noblank
Type=Application
X-GNOME-Autostart-enabled=true
```

Ensure proper file ownership and check current X11 display power settings:
```
sudo chown $(whoami):$(whoami) ~/.config/autostart/xset-noblank.desktop
xset -q | grep -E "blanking|DPMS"
```

We ensure the systemd inhibitor settings as follows. Run once:
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

At this point, we have successfully configured the server to prevent it from entering sleep mode.

Remark. `HDMI Dummy Plug Dongle` (Headless Display Emulator) can emulate a live monitor.



### 1.2 ⚙️ Set Dynamic `Power Management` for CPU and GPU

`auto-cpufreq` provides full dynamic scaling for CPUs based on load, while NVIDIA GPUs already auto-scale by default. However, enabling `persistence mode` prevents delays or CUDA errors after reboot—especially important for headless or remote systems where no monitor is attached.

#### Enable auto-cpufreq for CPU

```bash
sudo snap install auto-cpufreq
snap services auto-cpufreq
```

#### Enable Persistence Mode for NVIDIA GPU

Create a systemd service:

```bash
sudo nano /etc/systemd/system/nvidia-persist.service
```

Paste:

```ini
[Unit]
Description=NVIDIA Persistence Mode
After=multi-user.target

[Service]
ExecStart=/usr/bin/nvidia-smi -pm 1
Type=oneshot
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reexec
sudo systemctl enable --now nvidia-persist.service

systemctl status nvidia-persist.service
```

Expect: `active (exited)` with command executed



### 1.3 🔐 Restrict Automatic Updates to `Security Patches` Only

To avoid unexpected package upgrades that may break remote access or conda environments, we restrict Ubuntu's unattended upgrades to `security-only`:

Edit the file:

```bash
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

Recommended configuration:

```ini
Unattended-Upgrade::Allowed-Origins {
//	  "${distro_id}:${distro_codename}";
		"${distro_id}:${distro_codename}-security";
		"${distro_id}ESMApps:${distro_codename}-apps-security";
		"${distro_id}ESM:${distro_codename}-infra-security";
//	  "${distro_id}:${distro_codename}-updates";
//	  "${distro_id}:${distro_codename}-proposed";
//	  "${distro_id}:${distro_codename}-backports";
};
```

✅ This keeps your system protected with security fixes while avoiding disruptive updates.



### 1.4 🕓 Enable Accurate Time Sync with `Chrony`

#### 📥 Install Chrony

```bash
sudo apt update
sudo apt install -y chrony
```

Chrony starts automatically upon installation.

#### ⚙️ Configure Regional NTP Servers

Edit the configuration file: replace or append NTP server pools to use geographically close and reliable sources, e.g., in Switzerland, one may access:
```conf
# sudo nano /etc/chrony/chrony.conf

pool ch.pool.ntp.org iburst
pool de.pool.ntp.org iburst
pool fr.pool.ntp.org iburst
pool it.pool.ntp.org iburst
pool time.cloudflare.com iburst
pool time.google.com iburst
pool pool.ntp.org iburst
```

Apply changes:

```bash
sudo systemctl restart chrony
```

Chrony will now sync with the specified servers and persist across reboots.



#### 🧪 Check Synchronization Status

```bash
chronyc sourcestats -v
watch -n 1 chronyc tracking
```

| Field			 | Meaning											   |
| ----------------- | ----------------------------------------------------- |
| `Reference ID`	| The IP or hostname of the current NTP source		  |
| `Stratum`		 | NTP hierarchy level (1 = most accurate)			   |
| `System time`	 | Current offset between local time and NTP server time |
| `Last offset`	 | Most recent observed offset						   |
| `RMS offset`	  | Average recent offset								 |
| `Root delay`	  | Round-trip delay to the reference server			  |
| `Root dispersion` | Maximum expected error compared to NTP time		   |
| `Update interval` | Time between updates								  |
| `Leap status`	 | Leap second info (normally `Normal`)				  |




#### 🔍 Verify Chrony Service

```bash
sudo systemctl status chrony
```

Sample output:

```
● chrony.service - chrony, an NTP client/server
	 Loaded: loaded (/usr/lib/systemd/system/chrony.service; enabled)
	 Active: active (running) since ...
```

* **Loaded:** indicates Chrony is enabled at boot
* **Active:** confirms it is running normally


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 2. RDP Setup

### 2.1 🧩 Install and Enable `xrdp` Service

`xrdp` is an open-source implementation of the Microsoft RDP server for Linux, enabling remote desktop access to Ubuntu systems.

```bash
sudo apt update
sudo apt install xrdp -y
sudo systemctl enable xrdp
sudo systemctl start xrdp
````

If using GNOME (default Ubuntu Desktop), ensure correct session:

```bash
echo "gnome-session" > ~/.xsession
sudo chown c01hyka:c01hyka ~/.xsession
chmod 755 ~/.xsession
sudo systemctl restart xrdp

systemctl status xrdp
```

**Note:**
If you encounter issues where GUI apps (like Nautilus) refuse to open or RDP sessions crash after login,
consider switching from `gnome-session` + `gdm3` to `xfce4` + `lightdm`.
This combination provides a more stable X11 environment for xrdp, resolving session scope and display binding issues.

```bash
# Install lightweight desktop and display manager
sudo apt install xfce4 xfce4-goodies -y

# During installation, choose "lightdm" when prompted
# Then restart xrdp:
sudo systemctl restart xrdp
```

### 2.2 🛠️ XFCE RDP Setup with D-Bus and Session Diagnostics

If switching to `xfce4` + `lightdm`, run the following script to ensure proper D-Bus session, eliminate GUI inconsistencies, and suppress common warnings (e.g., Nautilus, portal services):

```bash
#!/bin/bash

###############################################################################
# ✅ XFCE RDP Session Setup with dbus, GUI Optimizations, and Diagnostics
###############################################################################

# ▶️ Write clean ~/.xsession to launch XFCE with a guaranteed D-Bus session
cat <<'EOF' > ~/.xsession
#!/bin/bash

# Start dbus session (export all needed env vars)
if command -v dbus-launch >/dev/null 2>&1; then
    eval $(dbus-launch --sh-syntax)
    export DBUS_SESSION_BUS_ADDRESS
    export DBUS_SESSION_BUS_PID
fi

# Start XFCE desktop session
exec startxfce4
EOF

chmod +x ~/.xsession

# ▶️ Pre-create GTK bookmarks file to suppress Nautilus warnings
touch ~/.gtk-bookmarks

# ▶️ Mask resource-hungry user-level services (run once)
systemctl --user mask tracker3-miner-fs.service
systemctl --user mask tracker3.service
systemctl --user mask tracker3-store.service
systemctl --user mask xdg-desktop-portal.service

# ▶️ Restart XRDP to apply updated ~/.xsession
sudo systemctl restart xrdp


###############################################################################
# 🔍 Diagnostic: Confirm current dbus and session state
###############################################################################

# Check installed dbus-related packages
apt list --installed | grep dbus --no-pager

# Check system-level dbus broker status
systemctl status dbus

# Check session bus environment variable
echo "DBUS_SESSION_BUS_ADDRESS = $DBUS_SESSION_BUS_ADDRESS"

# Check which dbus-launch binary is used
which dbus-launch

# Review final .xsession content
echo -e "\nFinal .xsession content:"
cat ~/.xsession
```

Only execute this section if you are using `xfce4` as your RDP desktop environment.  
It ensures that session-wide D-Bus and GUI context are properly scoped within  
the XRDP virtual display, avoiding app misplacement or failure.


🧷 Let RDP Sessions Be Persistent Unless Server Reboots

Ensure the user session (and open windows) survive RDP disconnections or logouts,  
as long as the server is not rebooted:

```bash
# Check whether session persistence (linger) is enabled
loginctl show-user $USER | grep Linger

# If it shows "Linger=no", enable it to persist GUI sessions
sudo loginctl enable-linger $USER
```


### 2.3 🌐 Assign or Monitor `Internal IP Address`

Check internal IP:
```bash
ip a | grep inet	# Ubuntu
ipconfig			# Windows
```

Example result: `192.168.0.100` from  
```bash
inet 192.168.0.100/24 brd 192.168.0.255 scope global dynamic noprefixroute eth0
```

This address is used for local LAN `.rdp` connections.



### 2.4 🛡️ Allow Remote Desktop through UFW `Firewall` within the Local Network

```bash
sudo ufw enable
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-rdp-port> \
	proto tcp \
	comment 'Local Network → RDP'
sudo ufw reload
sudo ufw status

# 192.168.1.0/24 means the subnet range from 192.168.1.0 to 192.168.1.255.
# It includes all IP addresses within this range in the local network.
```

Check that <your-port>/tcp is listed as `ALLOW`.



### 2.5 🦆 DuckDNS Setup for `External Access` (Deprecated)

1. Register at [https://www.duckdns.org](https://www.duckdns.org)
2. Choose a subdomain (e.g., `\<your-subdomain\>.duckdns.org`)
3. DuckDNS supports `GitHub` login for convenience.
4. Follow official installation guide at [https://www.duckdns.org/install.jsp](https://www.duckdns.org/install.jsp) to download and run the appropriate `.sh` script

**To verify update success manually:**

```bash
~/duckdns/duck.sh && cat ~/duckdns/duck.log
```

Expect: `OK`



### 2.6 📶 Router `Port Forwarding`

This step varies by router model. The example below uses a TP-Link DSL Router UI.

Login to router at `192.168.1.1`

**Navigate:** Advanced → NAT Forwarding → Virtual Servers → Add

| Field			| Value						|
| ------------- | ------------------------- |
| Rule Nmae		| `<your-rule-name>`		|
| External Port | `<inbound-port>`  		|
| Internal IP   | `<your-device-ip>`		|
| Internal Port | `<inbound-port>`  		|
| Protocol		| TCP						|
| Status		| Enabled					|

### 2.7 📡 `DNS + Port` Check

From any system:

```bash
ping <your-domain>
```

To test the external accessibility of a port from another Windows system, type at PowerShell:
```powershell
Test-NetConnection -ComputerName <your-domain> -Port <your-port>
```

Expect: `TcpTestSucceeded: True`



### 2.8 📁 Configure `.rdp` Files for `Intranet` and `External Access`

This dual configuration separates `internal access` such as a local network sharing a router and `external access` paths—essential for systems behind NAT or using budget routers that lack advanced loopback or DDNS resolution features.

Create two `.rdp` files with content similar to the following:

**Intranet.rdp:**

```bash
full address:s:<your-internal-ip>:<your-port>
username:s:<your-username>
```

**External.rdp:**

```bash
full address:s:<your-duckdns-domain>.duckdns.org:<your-port>
username:s:<your-username>
```

Open using:

* Windows: `mstsc.exe`
* Linux: remmina / freerdp

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 3. Remote File System Access Using `FileZilla` (SFTP)

### 3.1 Install and Start the `SSH` Server on Ubuntu

```bash
sudo apt update && sudo apt install openssh-server -y

sudo systemctl start ssh
sudo systemctl enable ssh
sudo systemctl status ssh
```

Let `<your-ssh-port>` be listening for the inbound:
```bash
# sudo nano /etc/ssh/sshd_config

Port <your-ssh-port>
ListenAddress 0.0.0.0
ListenAddress ::
```
Restart `ssh` and confirm the status:
```bash
sudo systemctl restart ssh
sudo apt install -y net-tools
sudo netstat -tlnp
```

### 3.2 Allow SFTP through UFW `Firewall` within the Local Network

```bash
sudo ufw enable
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-ssh-port> \
	proto tcp \
	comment 'Local Network → SFTP'
sudo ufw reload
sudo ufw status

# 192.168.1.0/24 means the subnet range from 192.168.1.0 to 192.168.1.255.
# It includes all IP addresses within this range in the local network.
```

### 3.3 📶 Router `Port Forwarding` (Deprecated)
| Field			| Value						|
| ------------- | ------------------------- |
| Rule Nmae		| `<your-rule-name>`		|
| External Port | `<inbound-port>`  		|
| Internal IP   | `<your-device-ip>`		|
| Internal Port | `<inbound-port>`  		|
| Protocol		| TCP						|
| Status		| Enabled					|

### 3.4 Install `FileZilla` Client on Windows

Download the FileZilla client:
👉 [https://filezilla-project.org/download.php?type=client](https://filezilla-project.org/download.php?type=client)

Use the following configuration for SFTP access:

| Setting		| Value									|
| ------------- | ------------------------------------- |
| **Host**		| `sftp://<your-local-ip>`				|
| **Username**	| `<your-username>`						|
| **Password**	| `<your-password>`						|
| **Port**		| `<your-ssh-port>`						|

Once connected, you can browse and transfer files between your local machine and the Ubuntu server over a secure SSH channel.


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 4. RnD Environment Preparation

### 4.1 🧬 Install `Anaconda` and `PyTorch` Environment

#### Download and install Anaconda as instructed by [Anaconda Installation Guide](https://www.anaconda.com/docs/getting-started/anaconda/install#macos-command-line-installer)

**To verify GPU availability:**

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

Expected output:

* PyTorch version string (e.g., 2.5.1)
* `True` if CUDA is successfully enabled

#### Install PyTorch with CUDA

```bash
conda install pytorch torchvision torchaudio pytorch-cuda -c pytorch -c nvidia
```

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 5. Dashboard Service for your App

**Access Examples:**
- `http://localhost:8000/dashboard` - development computer
- `http://<your-internal-ip>/dashboard` - internal network access
- `http://<your-domain>/dashboard` - external access

**Port Configuration:**
- Port 8000: FastAPI application (localhost)
- Port 80: Inbound HTTP traffic
- Port 443: Inbound HTTPS traffic

### 5.1 Add `HTMLResponse` & `WebSocket` Endpoints via `FastAPI @Python`
First, ensure your FastAPI application has the necessary endpoints for serving the dashboard:
```python
	# Create FastAPI app

	app = FastAPI(lifespan=lifespan)
	
	# Register routes

	app.get(
		"/dashboard",
		response_class=HTMLResponse
	)(
		self._dashboard_page
	)
	app.websocket(
		"/ws/dashboard"
	)(
		self._dashboard_websocket
	)
```

### 5.2 `NginX` Configuration at your Ubuntu Server

#### 5.2.1 Install and Configure `NginX`

Configure:
```nginx
# sudo apt update && sudo apt install nginx
# sudo nano /etc/nginx/sites-available/<name-your-site>

server {
	listen <inbound-port>;
	server_name <your-domain> <your-internal-ip> localhost;

	location / {
		proxy_pass http://localhost:<outbound-port>;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
	}

	location /ws/ {
		proxy_pass http://localhost:<outbound-port>;
		proxy_http_version 1.1;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection "upgrade";
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
	}
}
```
Activate the configuration:
```bash
# Remove the default configuration (not needed for custom setups)
sudo rm /etc/nginx/sites-enabled/default

# Remove the symbolic link for the site configuration (if it exists)
sudo rm -f /etc/nginx/sites-enabled/<name-your-site>

# Create a new symbolic link for the site configuration
sudo ln -s /etc/nginx/sites-available/<name-your-site> /etc/nginx/sites-enabled/

# Validate the Nginx configuration for syntax and errors
sudo nginx -t

# Reload Nginx to apply the updated configuration
sudo systemctl reload nginx
```



#### 5.2.2 Allow Dashboard Traffic through UFW `Firewall` within the Local Network
```bash
sudo ufw enable
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-dashboard-port> \
	proto tcp \
	comment 'Local Network → Dashboard'
sudo ufw reload
sudo ufw status

# 192.168.1.0/24 means the subnet range from 192.168.1.0 to 192.168.1.255.
# It includes all IP addresses within this range in the local network.
```

#### 5.2.3 `Port Forwarding` at your Router (Deprecated)

The device IP assigned by your router can be checked on the Ubuntu home server using:

```bash
ip a | grep inet
```

Configure port forwarding in your router's management interface:

| Field			| Value						|
| ------------- | ------------------------- |
| Rule Nmae		| `<your-rule-name>`		|
| External Port | `<inbound-port>`  		|
| Internal IP   | `<your-device-ip>`		|
| Internal Port | `<inbound-port>`  		|
| Protocol		| TCP						|
| Status		| Enabled					|

#### 5.2.4 Check `External IP` Addresses

Check your Ubuntu server's external IPv4 and IPv6 addresses:
```bash
curl 'https://api.ipify.org'
curl 'https://api6.ipify.org'
```
From now on, the returned outputs will be denoted by
```bash
<public-ipv4-of-your-router>
<public-ipv6-of-your-router>
```

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

### 5.3 `Dynamic IPv4` Adaptation through CloudFlare for your Domain-Rounter

#### 5.3.1 Purchase and Transfer your `Domain`
Purchase `<your-domain>` through *Porkbun*, which includes these default properties:
- Disabled `DNSSEC`
- *WHOIS* Privacy  

Transfer `<your-domain>` from *Porkbun* to *CloudFlare*. The new *name servers* are such as:
- `holly.ns.cloudflare.com`
- `margo.ns.cloudflare.com`

#### 5.3.2 IPv4-Dynamic DNS Setup via `CloudFlare API`
Create an *API Token* at CloudFlare, where `<your-domain>` is included as a *specific zone*.  
The required permission for this API token is `Zone:DNS:Edit`. 

Next, in the CloudFlare dashboard for `<your-domain>`, create an *A Record* as follows:
```bash
DNS Tab ≫ Records ≫ Add a Record:
- Type: A
- Name: www		# the subdomain could be rdp, sftp, or anything.
- IPv4 address: <public-ipv4-of-your-router>
- Ensure: Proxied & TTL Auto	# DNS-only if not http or https
```

Then, the `ID` of *A Record*—that you just created—can be polled via:
```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones/<cloudflare-dns-zone-id>/dns_records" \
	 -H "Authorization: Bearer <cloudflare-zone-dns-edit-api-token>" \
	 -H "Content-Type: application/json"
```

You now have all required credentials:
1. `<cloudflare-zone-dns-edit-api-token>` — from API token creation
2. `<cloudflare-dns-zone-id>` — available immediately after the domain transfer
3. `<cloudflare-dns-a-record-id>` — from the curl command above

Use such credentials to automate dynamic IPv4 updates at CloudFlare,
for instance, through a Python script;  
see [Cloudflare API – Update DNS Record](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/edit/).

#### 5.3.3 `Security` Enhancements for your Domain (Deprecated)
Restrict UFW Firewall to CloudFlare IP Ranges via
```bash
sudo ufw enable

# Local Network
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-rdp-port> \
	proto tcp \
	comment 'Local Network → RDP'
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-ssh-port> \
	proto tcp \
	comment 'Local Network → SSH'
sudo ufw allow \
	from 192.168.1.0/24 \
	to any port <your-dashboard-port> \
	proto tcp \
	comment 'Local Network → HTTP'

# CloudFlare IPv4
for ip in $(curl -s https://www.cloudflare.com/ips-v4); do
	sudo ufw allow \
		from $ip \
		to any port <your-rdp-port> \
		proto tcp \
		comment 'CloudFlare'
	sudo ufw allow \
		from $ip \
		to any port <your-ssh-port> \
		proto tcp \
		comment 'CloudFlare'
	sudo ufw allow \
		from $ip \
		to any port <your-dashboard-port> \
		proto tcp \
		comment 'CloudFlare'
done

# Public IP of Your Router:
# 	Connecting through DNS but
#	within the Local Network
sudo ufw allow \
	from <your-public-ip> \
	to any port <your-rdp-port> \
	proto tcp \
	comment 'CloudFlare'
sudo ufw allow \
	from <your-public-ip> \
	to any port <your-ssh-port> \
	proto tcp \
	comment 'CloudFlare'
sudo ufw allow \
	from <your-public-ip> \
	to any port <your-dashboard-port> \
	proto tcp \
	comment 'CloudFlare'
sudo ufw reload
sudo ufw status
```

⚠️ Pros and Cons  
+ Pros: Enhances security by "hiding" the web server behind Cloudflare.  
+ Cons: Complete dependency on Cloudflare services.  
+ Complexity: Increases the number of UFW rules, making management more complicated.  
+ *IP Changes: Requires updates if Cloudflare modifies its IP ranges.*  

#### 5.3.4 `Connectivity` Test

```bash
sudo systemctl status ssh

# sudo apt update && sudo apt install net-tools
sudo netstat -tlnp

nslookup <your-domain>
ping <your-domain>

sudo tail -f /var/log/ufw.log
sudo tail -f /var/log/auth.log

# PowerShell
Test-NetConnection -ComputerName <your-domain> -Port <your-port>

# Test on Web Browsers
# http://localhost:<your-app-port>/<your-endpoint-name>
# http://<local-ip-of-server>:<your-app-port>/<your-endpoint-name>
# http://<your-domain>/<your-endpoint-name>
```

<!-- #### CloudFlare 보안 기능 활성화
1. **SSL/TLS 모드**: Full (Strict) 권장
2. **Always Use HTTPS**: 활성화
3. **HSTS**: 활성화
4. **Security Level**: Medium 또는 High
5. **Bot Fight Mode**: 활성화 -->

## 6. Tunneling RDP and SFTP through WireGuard

*WireGuard tunneling* allows you to avoid exposing the ports of your network system, unlike in the previous sections, thereby enhancing the security of your network. In this section, we assume that all steps from the previous sections have been completed, and that RDP and SFTP are already accessible through the exposed ports.

### 6.1 A few Changes for the `CloudFlare and Router Settings`

What changes regarding *CloudFlare*:  
+	separate *A Records* for {`rdp`, `sftp`, `www`}
are <span style="color:yellow">unified</span> to `vpn`,
while remaining as *DNS-only*;  
<span style="color:yellow">*delete*</span> `<CloudFlare IP Ranges>` allowed at *UFW*
for {`rdp`, `sftp`, `www`}.
+	*DDNS automation* script periodically updates
the public IPv4 of your router to *CloudFlare*  
only for the *A Record* designated to `vpn`.

What changes at *your router*:  
+	*Eliminate* port forwarding of
`<your-rdp-port>`,
`<your-ssh-port>`,  
and `<your-dashboard-port>`,
which also does not affect their local access.
+	Now, you have to add a port-forwarding rule that uses 
the <span style="color:yellow">*UDP*</span> protocol for *WireGuard:*  

| Field			| Value										|  
| ------------- | ----------------------------------------- |  
| Rule Nmae		| `<your-rule-name>`						|  
| External Port | `<your-udp-port>`  						|  
| Internal IP   | `<your-device-ip>`						|  
| Internal Port | `<your-udp-port>`  						|  
| Protocol		| <span style="color:yellow">*UDP*</span>	|  
| Status		| Enabled									|  

Then, everything has to be done for your router and *CloudFlare*
has been completed.

### 6.2. `WireGuard` Setup

***Install*** *Wireguard* and get the `public key`:
```bash
sudo apt update && sudo apt install -y wireguard

sudo -i								# privileged session starts
mkdir -p /etc/wireguard
chmod 700 /etc/wireguard			# restrict dir access to owner only
cd /etc/wireguard
umask 077							# ensure new files are owner-readable only
wg genkey | tee server.key | wg pubkey > server.pub
chmod 600 server.key
chmod 644 server.pub
sudo cat /etc/wireguard/server.key
sudo cat /etc/wireguard/server.pub
exit								# privileged session ends
```
***Configure*** *WireGuard* `interface` at the server:
```bash
# sudo nano /etc/wireguard/wg0.conf

[Interface]
Address	   = 10.10.0.1/24
ListenPort = <your-udp-port>
PrivateKey = </etc/wireguard/server.key>
SaveConfig = false	# only can be manually edited
```

***Activate*** *WireGuard* interface `wg0`:
```bash
# ⚠️ No need to override `wg-quick@wg0`.
# The default unit already handles proper 
# rdering and interface setup.
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0

ip addr show wg0
systemctl status wg-quick@wg0 --no-pager
sudo wg
```

***Tip.*** The commands below help when WireGuard behaves erratically.
```bash
# sudo systemctl stop wg-quick@wg0
# sudo systemctl disable wg-quick@wg0
# sudo systemctl reset-failed wg-quick@wg0
# ip link show | grep wg
# sudo wg show
```

***Configure*** UFW `firewall` rules:
```bash
sudo ufw allow \
	<your-udp-port>/udp \
	comment 'WireGuard'
sudo ufw allow \
	in on wg0 \
	to any port <your-rdp-port> \
	comment 'RDP via WireGuard'
sudo ufw allow \
	in on wg0 \
	to any port <your-ssh-port> \
	comment 'SSH via WireGuard'
sudo ufw allow \
    in on wg0 \
    to any port <your-http-port> \
    comment 'HTTP via WireGuard'

# in case IPv6 is not used for this purpose
sudo ufw status numbered \
	| grep -E '<your-udp-port>/udp \(v6\).*WireGuard|\(v6\) on wg0 .*WireGuard' \
	| awk -F'[][]' '{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2}' \
	| sort -rn \
	| xargs -r -I{} sudo ufw --force delete {}	

sudo ufw reload
sudo ufw status numbered
```

***Install*** `dnsmasq` for *Split DNS*, and then, append  
the following at the end of `/etc/dnsmasq.conf`:
```bash
# sudo apt update && sudo apt install -y dnsmasq
# sudo nano /etc/dnsmasq.conf

############################################
# Split-DNS for WireGuard (inline)
address=/vpn.<your-domain>/10.10.0.1
interface=wg0
bind-interfaces
port=53

# upstream resolvers
server=1.1.1.1
server=8.8.8.8
############################################
```

<span style="color:yellow">***Do***</span>
*generate* `dnsmasq-wireguard.service`:
```bash
# sudo nano /etc/systemd/system/dnsmasq-wireguard.service

[Unit]
Description=Lightweight DNS forwarder for WireGuard
After=network-online.target wg-quick@wg0.service
Requires=network-online.target

[Service]
ExecStartPre=/bin/bash -c 'for i in {1..10}; do ip addr show wg0 | grep -q "inet " && break; sleep 0.5; done'
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/dnsmasq.conf
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable --now dnsmasq-wireguard
sudo systemctl disable --now dnsmasq.service
sudo systemctl mask dnsmasq.service
systemctl status dnsmasq-wireguard --no-pager
systemctl is-enabled dnsmasq-wireguard
```

<span style="color:yellow">***Do***</span>
*disable* `systemd-resolved`</span>:
<!-- permanently disable systemd-resolved -->
```bash
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf
```

***<span style="color:yellow">Do</span>*** verify the `Split DNS`:
```bash
sudo systemctl daemon-reexec
sudo systemctl restart wg-quick@wg0
sudo systemctl restart dnsmasq-wireguard

sudo systemctl status dnsmasq --no-pager	# useful
ss -ulpn | grep :53							# 10.10.0.1:53

dig +short vpn.<your-domain>	@10.10.0.1 -p 53
dig +short google.com			@10.10.0.1 -p 53
```

***Add*** the UFW `firewall` rule for the *Split DNS*:
```bash
sudo ufw allow \
	in on wg0 \
	to any port 53 \
	proto udp \
	comment 'DNS via WireGuard'
sudo ufw status numbered \
	| grep -E '\(v6\) on wg0 .*DNS via WireGuard' \
	| awk -F'[][]' '{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2}' \
	| sort -rn \
	| xargs -r -I{} sudo ufw --force delete {}
sudo ufw reload
sudo ufw status numbered
```

***Generate and deliver*** the `client credientials` from the server:
```bash
sudo -i		# privileged session starts

cd /etc/wireguard
umask 077	# ensure new files are owner-readable only

# generate the client credientials
wg genkey \
	| tee <client-name>.key \
	| wg pubkey \
	> <client-name>.pub

# prepare to serve the client credentials
mv <client-name>.key /home/<your-id>/<client-name>.key
mv <client-name>.pub /home/<your-id>/<client-name>.pub

exit		# privileged session ends

# transfer the ownership to deliver the credientials
sudo chown <your-id>:<your-id> \
	/home/<your-id>/<client-name>.key \
	/home/<your-id>/<client-name>.pub
```

***Update*** *WireGuard* `interface` at the server:
```bash
# sudo nano /etc/wireguard/wg0.conf

[Interface]
Address	= 10.10.0.1/24
ListenPort = <your-udp-port>
PrivateKey = </etc/wireguard/server.key>
SaveConfig = false	# only can be manually edited

[Peer]	# new client is added
PublicKey  = <client-name.pub>
AllowedIPs = 10.10.0.2/32
PersistentKeepalive = 25
```

***Reload*** *WireGuard* `interace` at the server:
```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl restart wg-quick@wg0
sudo systemctl restart dnsmasq-wireguard

ip addr show wg0
sudo wg
systemctl status wg-quick@wg0 --no-pager
systemctl status dnsmasq-wireguard --no-pager
```

***Configure*** *WireGuard* `interface` at the client:
```bash
# <client-name>.conf

[Interface]
PrivateKey = <client-name.key>
Address	= 10.10.0.2/32
DNS		= 10.10.0.1

[Peer]
PublicKey  = <server.pub>
Endpoint   = vpn.<your-domain>:<your-udp-port>
AllowedIPs = 10.10.0.0/24
PersistentKeepalive = 3
```

***Verify*** after reboot:
```bash
systemctl status wg-quick@wg0 --no-pager
systemctl status dnsmasq-wireguard --no-pager
ip addr show wg0
ss -ulpn | grep 51820
dig @127.0.0.1 google.com
dig @1.1.1.1 google.com
```

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## Y. Reboot Checklist

After reboot, we want to ensure all services are active
and the server will not be suspended; see `stat.py`.


### 6.3 Enhancing Security via `fail2ban`
***Install*** and configure:
```bash
# git clone https://github.com/fail2ban/fail2ban.git
# cd fail2ban
# sudo python3 setup.py install
# sudo nano /etc/fail2ban/jail.local

[DEFAULT]
# Ban time (seconds) - 10 minutes
bantime = 600

# Observation window (seconds) - Count failures within 10 minutes
findtime = 600

# Maximum allowed failure attempts
maxretry = 5

# IPs that will never be banned (your own IP, trusted IPs)
ignoreip = 127.0.0.1/8 ::1 192.168.1.0/24

[sshd]
enabled = true
port = <your-ssh-port>
filter = sshd
logpath = /var/log/auth.log

[xrdp]
enabled = true
port = <your-rdp-port>
filter = xrdp
logpath = /var/log/xrdp.log
maxretry = 3
```

```bash
# sudo nano /etc/fail2ban/filter.d/xrdp.conf

[Definition]
# Fail2Ban will look for this pattern in /var/log/xrdp.log
failregex = .*xrdp_wm_log_msg: login failed for user .* from <HOST>.*$
ignoreregex =
```

```bash
# which fail2ban-server
# 	ExecStart=/usr/local/bin/fail2ban-server
# sudo nano /etc/systemd/system/fail2ban.service

[Unit]
Description=Fail2Ban Service
After=network.target iptables.service firewalld.service

[Service]
Type=simple
ExecStart=/usr/local/bin/fail2ban-server -xf start
ExecStop=/usr/local/bin/fail2ban-client stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

***Do*** *enable and start*:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo systemctl status fail2ban
```

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## Z. Security Considerations

**⚠️ Important Security Reminders:**

1. **Never commit actual credentials** to version control
2. **Use strong, unique passwords, and regularly change them**
3. **Regularly change ports** for RDP (3389) and SSH (22)
4. **Regularly update** your system and applications
5. **Use key-based authentication** for SSH instead of passwords
6. **Monitor access logs** regularly:
```bash
sudo tail -f /var/log/ufw.log
sudo tail -f /var/log/auth.log
sudo tail -f /var/log/xrdp.log
```

**🔒 Before Sharing or Committing:**
- Replace all actual values in your local copy with `<placeholders>` 
- Never commit files containing real API tokens, passwords, or IP addresses
- Use environment variables or separate config files for sensitive data