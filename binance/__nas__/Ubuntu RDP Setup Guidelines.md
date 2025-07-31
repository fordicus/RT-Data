# Setup Guide: RDP & NAS @`Ubuntu Desktop 24.04.2 LTS`


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## TODO:
*	Document From `DuckDNS` (easy) to `CloudFlare + Purchased Domain` (advanced): [EXTERNAL DASHBOARD SERVICE](#external-dashboard-service)  
*	Migration from `Filezilla` to `rsync & gsync`
*	Introduce `WireGuard` so that ports are not exposed.
*	From `http` to `https`

## 💡Tips  

1. To check the Ubuntu system’s `internal IP` address, type at Terminal:
```bash
ip a | grep inet
```

2. To test the `external accessibility` of a port from another Windows system, type at PowerShell:
```powershell
Test-NetConnection -ComputerName <your-domain> -Port <your-port>
```

<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 📝Table of Contents  

***For RDP (Remote Desktop Protocol)***  

[***1. System Stability and Maintenance***](#1-system-stability-and-maintenance)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.1 ☕ Completely `Prevent Sleep`](#11-☕-completely-prevent-sleep)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.2 ⚙️ Set Dynamic `Power Management` for CPU and GPU](#12-⚙️-set-dynamic-power-management-for-cpu-and-gpu)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.3 🔐 Restrict Automatic Updates to `Security Patches` Only](#13-🔐-restrict-automatic-updates-to-security-patches-only)  
&nbsp;&nbsp;&nbsp;&nbsp;[1.4 🕓 Enable Accurate Time Sync with `Chrony`](#14-🕓-enable-accurate-time-sync-with-chrony)  

[***2. RDP Setup***](#2-rdp-setup)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.1 🧩 Install and Enable `xrdp` Service](#21-🧩-install-and-enable-xrdp-service)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.2 🚫 Disable `Wayland` (if GUI apps open on local screen only)](#22-🚫-disable-wayland-if-gui-apps-open-on-local-screen-only)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.3 🌐 Assign or Monitor `Internal IP Address`](#23-🌐-assign-or-monitor-internal-ip-address)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.4 🛡️ Allow Remote Desktop Through `UFW Firewall`](#24-🛡️-allow-remote-desktop-through-ufw-firewall)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.5 🦆 DuckDNS Setup for `External Access`](#25-🦆-duckdns-setup-for-external-access)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.6 📶 Router `Port Forwarding`](#26-📶-router-port-forwarding)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.7 📡 `DNS + Port` Check](#27-📡-dns--port-check)  
&nbsp;&nbsp;&nbsp;&nbsp;[2.8 📁 Configure `.rdp` Files for `Intranet` and `External Access`](#28-📁-configure-rdp-files-for-intranet-and-external-access)  

[***3. Remote File System Access Using `FileZilla` (SFTP)***](#3-remote-file-system-access-using-filezilla-sftp)  

[***4. RnD Environment Preparation***](#4-rnd-environment-preparation)  

&nbsp;&nbsp;&nbsp;&nbsp;[4.1 🧬 Install `Anaconda` and `PyTorch` Environment](#41-🧬-install-anaconda-and-pytorch-environment)  

[***5. Final Verification and Checklist for RDP***](#5-final-verification-and-checklist)  
&nbsp;&nbsp;&nbsp;&nbsp;[5.1 ✅ `Summary` Checkpoints](#51-✅-summary-checkpoints)  
&nbsp;&nbsp;&nbsp;&nbsp;[5.2 🔁 `Reboot` Checklist](#52-🔁-reboot-checklist)  

[***6. Monitor Status of Port Externally***](#6-monitor-status-of-port-externally)  
&nbsp;&nbsp;&nbsp;&nbsp;[🟢 `UptimeRobot`](https://uptimerobot.com/)  


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 1. System Stability and Maintenance

### 1.1 ☕ Completely `Prevent Sleep`

**Modify `/etc/systemd/logind.conf`**:

```bash
# /etc/systemd/logind.conf

HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
```

Apply the changes:

```bash
sudo systemctl restart systemd-logind
```

To disable AC power-based sleep/blanking behavior in `Xfce`, create and execute the following script:

```bash
nano ~/disable-xfce-ac-power-saving.sh  
chmod +x ~/disable-xfce-ac-power-saving.sh  
./disable-xfce-ac-power-saving.sh
```

```bash
# ~/disable-xfce-ac-power-saving.sh  

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

```bash
mkdir -p ~/.config/autostart  
nano ~/.config/autostart/disable-xfce-ac-power-saving.desktop
```

```ini
# ~/.config/autostart/disable-xfce-ac-power-saving.desktop

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
sudo nano /etc/X11/xorg.conf
```
```bash
# /etc/X11/xorg.conf

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
nano ~/.xsession
```
```bash
# ~/.xsession

xset s off
xset s noblank
xset -dpms
startxfce4
```
Any new `Xorg` sessions will follow this configuration onward.



We also ensure the systemd inhibitor settings as follows. Run once:
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

At this point, we have successfully configured the server to prevent it from entering sleep mode.

Remark. `HDMI Dummy Plug Dongle` (Headless Display Emulator) can emulate a live monitor.



### 1.2 ⚙️ Set Dynamic `Power Management` for CPU and GPU

`auto-cpufreq` provides full dynamic scaling for CPUs based on load, while NVIDIA GPUs already auto-scale by default. However, enabling `persistence mode` prevents delays or CUDA errors after reboot—especially important for headless or remote systems where no monitor is attached.

#### Enable auto-cpufreq for CPU

```bash
sudo snap install auto-cpufreq --classic
sudo auto-cpufreq --install
```

**To verify:**

```bash
systemctl status auto-cpufreq
```

Should show: `active (running)`

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
```

**To verify:**

```bash
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
sudo apt install chrony
```

Chrony starts automatically upon installation.

#### ⚙️ Configure Regional NTP Servers

Edit the configuration file:

```bash
sudo nano /etc/chrony/chrony.conf
```

Replace or append NTP server pools to use geographically close and reliable sources, e.g., in Switzerland, one may access:

```conf
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

Also, the following command is proven to be useful:
```bash
chronyc sourcestats -v
```



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
```

If using GNOME (default Ubuntu Desktop), ensure correct session:

```bash
echo "gnome-session" > ~/.xsession
sudo systemctl restart xrdp
```

**To verify:** run `systemctl status xrdp` and ensure it shows "active (running)".



### 2.2 🚫 Disable `Wayland` (if GUI apps open on local screen only)

**Edit:** `/etc/gdm3/custom.conf`

```ini
WaylandEnable=false
```

Reboot:

```bash
sudo reboot
```

**To verify:** after RDP login, applications should open inside the remote session, not on the physical screen.



### 2.3 🌐 Assign or Monitor `Internal IP Address`

Check internal IP. For UNIX systems:
```bash
ip a | grep inet
```
For Windows:
```bash
ipconfig
```


Example result: `192.168.0.100` from  
```bash
inet 192.168.0.100/24 brd 192.168.0.255 scope global dynamic noprefixroute eth0
```

This address is used for local LAN `.rdp` connections.



### 2.4 🛡️ Allow Remote Desktop Through `UFW Firewall`

```bash
sudo ufw allow <your-port>/tcp
sudo ufw enable
```

Verify:

```bash
sudo ufw status
```

Check that <your-port>/tcp is listed as `ALLOW`.



### 2.5 🦆 DuckDNS Setup for `External Access`

1. Register at [https://www.duckdns.org](https://www.duckdns.org)
2. Choose a subdomain (e.g., `\<your-subdomain\>.duckdns.org`)
3. DuckDNS supports `GitHub` login for convenience `as I used`.
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

| Field		 | Value					 |
| ------------- | ------------------------- |
| Service Type  | \<name as wished>		 |
| External Port | <your-port>					  |
| Internal IP   | (your Ubuntu internal IP) |
| Internal Port | <your-port>					  |
| Protocol	  | TCP					   |
| Status		| Enabled				   |



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

### 3.1 Install and Start the SSH Server on Ubuntu

```bash
sudo apt update
sudo apt install openssh-server -y

sudo systemctl start ssh
sudo systemctl enable ssh
sudo systemctl status ssh | grep Active
```

### 3.2 Check the Local IP Address (Optional)

Use the following command to confirm the internal IP address of your Ubuntu server:

```bash
hostname -I
```

You should see an address like `192.168.x.x`.

### 3.3 Allow SSH Through the Firewall (UFW)

```bash
sudo ufw allow 22/tcp
sudo ufw status | grep 22
```

### 3.4 Install FileZilla Client on Windows

Download the FileZilla client:
👉 [https://filezilla-project.org/download.php?type=client](https://filezilla-project.org/download.php?type=client)

Use the following configuration for SFTP access:

| Setting	  | Value								 |
| ------------ | ------------------------------------- |
| **Host**	 | `sftp://<your-subdomain>.duckdns.org` |
| **Username** | `<your-username>`					 |
| **Password** | `<your-password>`					 |
| **Port**	 | `22`								  |

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

## 5. Final Verification and Checklist for RDP

### 5.1 ✅ `Summary` Checkpoints

| Feature									| Confirmed |
| ------------------------------------------ | --------- |
| Lid close disables suspend				 | ✅		 |
| RDP works on local LAN					 | ✅		 |
| RDP works via DuckDNS					  | ✅		 |
| Port forwarding is live					| ✅		 |
| Session is Xorg, not Wayland			   | ✅		 |
| Apps open inside RDP, not on host's screen | ✅		 |
| `.rdp` files configured					| ✅		 |
| CPU dynamic power managed via auto-cpufreq | ✅		 |
| GPU persistence mode active				| ✅		 |
| Anaconda & PyTorch (CUDA) configured	   | ✅		 |



### 5.2 🔁 `Reboot` Checklist

After reboot, we want to ensure all services are active and the laptop will not be suspended:
```bash
nano get_status.sh
```
```bash
# get_status.sh

systemctl status xrdp | grep Active
systemctl status auto-cpufreq | grep Active
systemctl status nvidia-persist.service | grep Active
systemctl status chrony | grep Active
xfconf-query -c xfce4-power-manager -l -v
grep -E 'AllowEmpty|ConnectedMonitor|Virtual screen size|DFP-0: connected' /var/log/Xorg.0.log | grep -v 'WW'
xset q | grep -E 'timeout|DPMS|prefer blanking|cycle'
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target | grep Active
```
```bash
chmod +x get_status.sh
```

The expected output after running `./get_status.sh` reads:
```bash
	 Active: active (running) since Tue 2025-07-08 18:38:13 CEST; 6min ago
	 Active: active (running) since Tue 2025-07-08 18:38:11 CEST; 6min ago
	 Active: active (exited) since Tue 2025-07-08 18:38:18 CEST; 6min ago
	 Active: active (running) since Tue 2025-07-08 18:38:12 CEST; 6min ago
/xfce4-power-manager/blank-on-ac						0
/xfce4-power-manager/blank-on-battery				   0
/xfce4-power-manager/brightness-inactivity-on-ac		0
/xfce4-power-manager/brightness-level-on-battery		1
/xfce4-power-manager/brightness-on-battery			  9
/xfce4-power-manager/brightness-switch				  0
/xfce4-power-manager/brightness-switch-restore-on-exit  1
/xfce4-power-manager/dpms-on-battery-off				0
/xfce4-power-manager/dpms-on-battery-sleep			  0
/xfce4-power-manager/monitor-power-off-on-ac			false
/xfce4-power-manager/power-button-action				3
/xfce4-power-manager/show-tray-icon					 false
/xfce4-power-manager/sleep-display-ac				   0
/xfce4-power-manager/sleep-on-ac						0
[	 6.786] (**) NVIDIA(0): Option "AllowEmptyInitialConfiguration" "true"
[	 6.786] (**) NVIDIA(0): Option "ConnectedMonitor" "DFP-0"
[	 6.786] (**) NVIDIA(0): ConnectedMonitor string: "DFP-0"
[	 6.863] (**) NVIDIA(0): Using ConnectedMonitor string "DFP-0".
[	 6.870] (--) NVIDIA(GPU-0): DFP-0: connected
[	 6.919] (II) NVIDIA(0): Virtual screen size determined to be 1024 x 768
[	 7.693] (--) NVIDIA(GPU-0): DFP-0: connected
[	 7.714] (--) NVIDIA(GPU-0): DFP-0: connected
[	 7.717] (--) NVIDIA(GPU-0): DFP-0: connected
[	 7.745] (--) NVIDIA(GPU-0): DFP-0: connected
[	 8.553] (--) NVIDIA(GPU-0): DFP-0: connected
[	 8.870] (--) NVIDIA(GPU-0): DFP-0: connected
  prefer blanking:  no	allow exposures:  yes
  timeout:  0	cycle:  600
DPMS (Display Power Management Signaling):
  Server does not have the DPMS Extension
	 Active: inactive (dead)
	 Active: inactive (dead)
	 Active: inactive (dead)
	 Active: inactive (dead)
```

✅ If all succeed, no additional manual action is needed after reboot.


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

## 6. Monitor Status of Port Externally

**A.** In [`UptimeRobot`](https://uptimerobot.com/), you can set up a monitor for your ports being forwarded so that you can check its status and uptime wherever you are.

**B.** Temporarily enabling `Exposed Host (DMZ)` in your router can be useful for troubleshooting RDP connectivity issues from outside your network. This is helpful when you want to quickly verify if your RDP server is reachable from the internet, or to rule out port forwarding misconfigurations.

> ⚠️ **Warning:**  
> DMZ exposes your entire device to the internet, bypassing most router-level protections. This significantly increases the risk of hacking, malware, and unauthorized access. **Always disable DMZ immediately after testing.** Never leave it enabled longer than necessary.


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

# EXTERNAL DASHBOARD SERVICE

## 0. Add an `HTMLResponse` & `WebSocket` Endpoint via `FastAPI @Python`
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

**Access Examples:**
- `http://localhost:8000/dashboard` - Development computer
- `http://<your-internal-ip>/dashboard` - Internal network access
- `http://<your-domain>/dashboard` - External access

**Port Configuration:**
- Port 8000: FastAPI application (localhost)
- Port 80: Inbound HTTP traffic
- Port 443: Inbound HTTPS traffic



## 1. NginX Configuration

### 1.1. Install and Configure NginX

Execute the following commands on your Ubuntu server:

```bash
sudo apt update
sudo apt install nginx
sudo nano /etc/nginx/sites-available/<name-your-site>
```

**Configuration file content:**

```nginx
# /etc/nginx/sites-available/<name-your-site>

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
**Activate the configuration:**
```bash
sudo ln -s /etc/nginx/sites-available/<name-your-site> /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```



### 1.2. Allow Traffic Through `UFW Firewall`
```bash
sudo ufw allow <inbound-port>/tcp
sudo ufw status
```
**To verify:** Check that `<inbound-port>/tcp` is listed as `ALLOW`.



### 1.3. Router Port Forwarding Configuration

The device IP assigned by your router can be checked on the Ubuntu home server using:

```bash
ip a | grep inet
```

Configure port forwarding in your router's management interface:

| Field		 | Value			 |
| ------------- | ----------------- |
| Service Type  | Custom			|
| Protocol	  | TCP			   |
| External Port | `<inbound-port>`  |
| Internal IP   | `<your-device-ip>`|
| Internal Port | `<inbound-port>`  |
| Status		| Enabled		   |



### 1.4. External IP Address Verification

Check your Ubuntu server's external IPv4 and IPv6 addresses:

```bash
curl -4 ifconfig.me
curl -6 ifconfig.me
```

**For DuckDNS users:** Update your DuckDNS dashboard with both IPv4 and IPv6 public addresses:
- IPv4: e.g., `85.x.2x9.2x3`
- IPv6: e.g., `2a?2:1?10:90?2:6?00:c8e:c??e:??af:cd??`



## 2. (Optional) HTTPS Implementation

For secure connections, implement SSL/TLS using Let's Encrypt:

```bash
# Install certbot for automated SSL certificate management
sudo apt install certbot python3-certbot-nginx

# Obtain and configure SSL certificate
sudo certbot --nginx -d <your-domain>
```

**Note:** Replace `<your-domain>` with your actual domain name (e.g., `example.duckdns.org` or `yourdomain.com`).

The certificate will be automatically renewed by certbot's systemd timer service.


<!-- ———————————————————————————————————————————————————————————————————————————————— -->

# Dynamic IPv4 Adaptation through CloudFlare for your Domain

## 1. Purchase and Transfer your Domain:  
Purchase `<your-domain>` through *Porkbun*, which includes these default properties:
- Disabled `DNSSEC`
- *WHOIS* Privacy  

Transfer `<your-domain>` from *Porkbun* to *CloudFlare*. The new name servers are:
- `holly.ns.cloudflare.com`
- `margo.ns.cloudflare.com`

## 2. IPv4-Dynamic DNS Setup via CloudFlare API
Create an *API Token* at CloudFlare, where `<your-domain>` is included as a *specific zone*.
The required permission for this API token is `Zone:DNS:Edit`. 

Next, in the CloudFlare dashboard for `<your-domain>`, create an `A-Record` as follows:
```CloudFlareDashboard
DNS Tab ≫ Records ≫ Add a Record:
- Type: A
- Name: www
- IPv4 address: <public-ipv4-of-your-router>
- Ensure: Proxied & TTL Auto
```
The following command gives `<public-ipv4-of-your-router>` 
from any system behind the same router:
```bash
curl -4 https://api.ipify.org
```
Then, the *ID* of `A-Record` that you just created is polled via:
```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones/<cloudflare-dns-zone-id>/dns_records" \
	 -H "Authorization: Bearer <cloudflare-zone-dns-edit-api-token>" \
	 -H "Content-Type: application/json"
```

You now have all required credentials:
1. `<cloudflare-zone-dns-edit-api-token>` — from API token creation
2. `<cloudflare-dns-zone-id>` — available immediately after the domain transfer
3. `<cloudflare-dns-a-record-id>` — from the curl command above

Use such credentials to automate dynamic IPv4 updates at CloudFlare:
	
```python
# update_dynamic_ipv4_at_cloudflare.py

import os, requests			 	# requests==2.32.4
from dotenv import load_dotenv	# python-dotenv==1.1.1

load_dotenv()
CloudFlareApiToken = os.getenv("CloudFlareApiToken")
DnsZoneID		   = os.getenv("DnsZoneID")
DnsRecordAID	   = os.getenv("DnsRecordAID")
YourDomain		   = os.getenv("YourDomain")

def get_public_ip():

	return requests.get(
		"https://api.ipify.org"
	).text

def update_dns_record(ip):
	
	url = (
		f"https://api.cloudflare.com/client/v4/zones/"
		f"{DnsZoneID}/dns_records/{DnsRecordAID}"
	)
	headers = {
		"Authorization": f"Bearer {CloudFlareApiToken}",
		"Content-Type": "application/json",
	}
	data = {
		"type":	   "A",
		"name":	   YourDomain,
		"content": ip,
		"ttl":	   1,
		"proxied": True,
	}
	response = requests.put(
		url,
		json	= data,
		headers = headers
	)
	return response.json()

if __name__ == "__main__":
	
	print(
		update_dns_record(
			get_public_ip()
		),
		flush = True,
	)
```
Once you run this script, the expected output reads:
```bash
{
  "result": {
	"id":		   "<cloudflare-dns-a-record-id>",
	"name":		   "<your-domain>",
	"type":		   "A",
	"content":	   "<public-ipv4-of-your-router>",
	"proxiable":   true,
	"proxied":	   true,
	"ttl":		   1,
	"settings":	   {},
	"meta":		   {},
	"comment":	   null,
	"tags":		   [],
	"created_on":  "Some UTC+0 Datetime",
	"modified_on": "Some UTC+0 Datetime"
  },
  "success":	   true,
  "errors":		   [],
  "messages":	   []
}
```

### NginX 설정 업데이트

기존 설정을 `sognex.com`으로 변경합니다:

```bash
sudo nano /etc/nginx/sites-available/binance-dashboard
```

```nginx
# /etc/nginx/sites-available/binance-dashboard

server {
	listen 80;
	server_name www.sognex.com 192.168.1.107 localhost;

	location / {
		proxy_pass http://localhost:8000;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
	}

	location /ws/ {
		proxy_pass http://localhost:8000;
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

설정 활성화 및 적용:
```bash
# only if the symbolic link already exists
sudo rm /etc/nginx/sites-enabled/binance-dashboard

sudo ln -s /etc/nginx/sites-available/binance-dashboard /etc/nginx/sites-enabled/
ls -la /etc/nginx/sites-enabled/binance-dashboard
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status nginx
```

<!-- ### 2.4 HTTPS 및 SSL 인증서 설정

Let's Encrypt를 사용하여 SSL 인증서를 설치합니다:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d sognex.com -d www.sognex.com
```

인증서 자동 갱신 확인:
```bash
sudo systemctl status certbot.timer
``` -->

### 2.5 고급 보안 설정

#### UFW 방화벽을 CloudFlare IP 범위로 제한
```bash
# CloudFlare IP 범위 허용 (IPv4) - 수정된 버전
for ip in $(curl -s https://www.cloudflare.com/ips-v4); do
    sudo ufw allow from $ip to any port 80 proto tcp
    sudo ufw allow from $ip to any port 443 proto tcp
done

# CloudFlare IP 범위 허용 (IPv6) - 필요한 경우
# for ip in $(curl -s https://www.cloudflare.com/ips-v6); do
# 	sudo ufw allow from $ip to any port 80 proto tcp
# 	sudo ufw allow from $ip to any port 443 proto tcp
# done

sudo ufw reload
```
> ⚠️ 장단점 (?)  
+ 웹 서버를 CloudFlare 뒤에 "숨기는" 효과를 만들어 보안을 크게 향상  
+ CloudFlare 의존성: CloudFlare 서비스에 완전히 의존  
+ IP 변경: CloudFlare가 IP 범위를 변경하면 업데이트 필요  
+ 복잡성: UFW 규칙이 많아짐

#### CloudFlare 보안 기능 활성화
1. **SSL/TLS 모드**: Full (Strict) 권장
2. **Always Use HTTPS**: 활성화
3. **HSTS**: 활성화
4. **Security Level**: Medium 또는 High
5. **Bot Fight Mode**: 활성화

### 2.6 연결 테스트 및 검증

```bash
sudo apt update
sudo apt install net-tools

# FastAPI 서비스가 8000 포트에서 실행 중인지 확인
sudo netstat -tlnp | grep :8000

# 로컬에서 직접 접근 테스트
curl http://localhost:8000/dashboard
curl http://192.168.1.107:8000/dashboard
```

#### 외부 접근 테스트
```bash
# DNS 확인
nslookup www.sognex.com
dig www.sognex.com

# CloudFlare를 통한 웹사이트 접근 테스트
curl http://www.sognex.com/dashboard

# HTTP 상태 코드 확인
curl -s -o /dev/null -w "%{http_code}" http://www.sognex.com/dashboard

# 포트 연결 테스트
telnet www.sognex.com 80
# 연결 후, 다음을 입력하고 Enter를 두 번 누릅니다:
GET /dashboard HTTP/1.1
Host: www.sognex.com
```

#### 웹 브라우저 테스트
1. `https://sognex.com/dashboard` - HTTPS 접속 확인
2. `http://sognex.com/dashboard` - HTTP to HTTPS 리다이렉트 확인
3. WebSocket 연결 테스트: Developer Tools에서 네트워크 탭 확인

#### 모니터링 설정
UptimeRobot 또는 CloudFlare Analytics를 사용하여 서비스 상태를 모니터링합니다.

---

## 최종 결과

모든 설정이 완료되면:
- 기존 DuckDNS 설정은 더 이상 필요하지 않습니다
- 동적 IP 변경 시 자동으로 DNS 레코드가 업데이트됩니다
- CloudFlare의 CDN, DDoS 보호, SSL/TLS 기능을 활용할 수 있습니다
- All external access is now routed through sognex.com. -->

<!-- #### 크론 작업 설정
위 스크립트를 주기적으로 실행하여 IP를 업데이트합니다:

1. 스크립트를 실행 가능하게 만들고 테스트:
   ```bash
   chmod +x /path/to/update_cloudflare_dns.py
   python3 /path/to/update_cloudflare_dns.py
   ```

2. 크론 작업 설정:
   ```bash
   crontab -e
   ```

3. 5분마다 실행되도록 설정:
   ```bash
   */5 * * * * cd /path/to/your/project && /usr/bin/python3 update_cloudflare_dns.py >> /var/log/dns_update.log 2>&1
   ```