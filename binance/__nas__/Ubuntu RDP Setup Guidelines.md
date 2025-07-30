# Setup Guide: RDP & NAS @`Ubuntu Desktop 24.04.2 LTS`

## TODO:
*	Document From `DuckDNS` (easy) to `CloudFlare + Purchased Domain` (advanced): [EXTERNAL DASHBOARD SERVICE](#external-dashboard-service)  
*	Migration from `Filezilla` to `rsync & gsync`
*	Introduce `WireGuard` so that ports are not exposed.

## 💡Tips  

1. To check the Ubuntu system’s internal IP address, type at Terminal:
```bash
ip a | grep inet
```

2. To test the external accessibility of a port from another Windows system, type at PowerShell:
```powershell
Test-NetConnection -ComputerName <your-domain> -Port <your-port>
```

<!-- ## ⚡Frequently Accessed Contents
* [Router `Port Forwarding`](#26-📶-router-port-forwarding)
* [Configure `.rdp` Files for Intranet and External Access](#28-📁-configure-rdp-files-for-intranet-and-external-access) -->

## 📝Table of Contents  
[1. System Stability and Maintenance](#1-system-stability-and-maintenance)  
[1.1 ☕ Completely `Prevent Sleep`](#11-☕-completely-prevent-sleep)  
[1.2 ⚙️ Set Dynamic `Power Management` for CPU and GPU](#12-⚙️-set-dynamic-power-management-for-cpu-and-gpu)  
[1.3 🔐 Restrict Automatic Updates to `Security Patches` Only](#13-🔐-restrict-automatic-updates-to-security-patches-only)  
[1.4 🕓 Enable Accurate Time Sync with `Chrony`](#14-🕓-enable-accurate-time-sync-with-chrony)

[2. RDP Setup](#2-rdp-setup)  
[2.1 🧩 Install and Enable `xrdp` Service](#21-🧩-install-and-enable-xrdp-service)  
[2.2 🚫 Disable `Wayland` (if GUI apps open on local screen only)](#22-🚫-disable-wayland-if-gui-apps-open-on-local-screen-only)  
[2.3 🌐 Assign or Monitor `Internal IP Address`](#23-🌐-assign-or-monitor-internal-ip-address)  
[2.4 🛡️ Allow Remote Desktop Through `UFW Firewall`](#24-🛡️-allow-remote-desktop-through-ufw-firewall)  
[2.5 🦆 DuckDNS Setup for `External Access`](#25-🦆-duckdns-setup-for-external-access)  
[2.6 📶 Router `Port Forwarding`](#26-📶-router-port-forwarding)  
[2.7 📡 `DNS + Port` Check](#27-📡-dns--port-check)  
[2.8 📁 Configure `.rdp` Files for `Intranet` and `External Access`](#28-📁-configure-rdp-files-for-intranet-and-external-access)

[3. 📂 Remote File System Access Using FileZilla (SFTP)](#3-📂-remote-file-system-access-using-filezilla-sftp)

[4. RnD Environment Preparation](#4-rnd-environment-preparation)  
[4.1 🧬 Install `Anaconda` and `PyTorch` Environment](#41-🧬-install-anaconda-and-pytorch-environment)

[5. Final Verification and Checklist](#5-final-verification-and-checklist)  
[5.1 ✅ `Summary` Checkpoints](#51-✅-summary-checkpoints)  
[5.2 🔁 `Reboot` Checklist](#52-🔁-reboot-checklist)  

[6. Monitor Status of Port Externally](#6-monitor-status-of-port-externally): [`UptimeRobot`](https://uptimerobot.com/)

---

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
    Identifier     "Device0"
    Driver         "nvidia"
    VendorName     "NVIDIA Corporation"
    Option         "AllowEmptyInitialConfiguration" "true"
    Option         "ConnectedMonitor" "DFP-0"
    Option         "CustomEDID" "DFP-0:/etc/X11/edid.bin"
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

---

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

---

### 1.3 🔐 Restrict Automatic Updates to `Security Patches` Only

To avoid unexpected package upgrades that may break remote access or conda environments, we restrict Ubuntu's unattended upgrades to `security-only`:

Edit the file:

```bash
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
```

Recommended configuration:

```ini
Unattended-Upgrade::Allowed-Origins {
//      "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
//      "${distro_id}:${distro_codename}-updates";
//      "${distro_id}:${distro_codename}-proposed";
//      "${distro_id}:${distro_codename}-backports";
};
```

✅ This keeps your system protected with security fixes while avoiding disruptive updates.

---

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

---

#### 🧪 Check Synchronization Status

```bash
watch -n 1 chronyc tracking
```

| Field             | Meaning                                               |
| ----------------- | ----------------------------------------------------- |
| `Reference ID`    | The IP or hostname of the current NTP source          |
| `Stratum`         | NTP hierarchy level (1 = most accurate)               |
| `System time`     | Current offset between local time and NTP server time |
| `Last offset`     | Most recent observed offset                           |
| `RMS offset`      | Average recent offset                                 |
| `Root delay`      | Round-trip delay to the reference server              |
| `Root dispersion` | Maximum expected error compared to NTP time           |
| `Update interval` | Time between updates                                  |
| `Leap status`     | Leap second info (normally `Normal`)                  |

Also, the following command is proven to be useful:
```bash
chronyc sourcestats -v
```

---

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

---


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

---

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

---

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

---

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

---

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

---

### 2.6 📶 Router `Port Forwarding`

This step varies by router model. The example below uses a TP-Link DSL Router UI.

Login to router at `192.168.1.1`

**Navigate:** Advanced → NAT Forwarding → Virtual Servers → Add

| Field         | Value                     |
| ------------- | ------------------------- |
| Service Type  | \<name as wished>         |
| External Port | <your-port>                      |
| Internal IP   | (your Ubuntu internal IP) |
| Internal Port | <your-port>                      |
| Protocol      | TCP                       |
| Status        | Enabled                   |

---

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

---

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

---

## 3. 📂 Remote File System Access Using `FileZilla` (SFTP)

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

| Setting      | Value                                 |
| ------------ | ------------------------------------- |
| **Host**     | `sftp://<your-subdomain>.duckdns.org` |
| **Username** | `<your-username>`                     |
| **Password** | `<your-password>`                     |
| **Port**     | `22`                                  |

Once connected, you can browse and transfer files between your local machine and the Ubuntu server over a secure SSH channel.

---

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

---

## 5. Final Verification and Checklist

### 5.1 ✅ `Summary` Checkpoints

| Feature                                    | Confirmed |
| ------------------------------------------ | --------- |
| Lid close disables suspend                 | ✅         |
| RDP works on local LAN                     | ✅         |
| RDP works via DuckDNS                      | ✅         |
| Port forwarding is live                    | ✅         |
| Session is Xorg, not Wayland               | ✅         |
| Apps open inside RDP, not on host's screen | ✅         |
| `.rdp` files configured                    | ✅         |
| CPU dynamic power managed via auto-cpufreq | ✅         |
| GPU persistence mode active                | ✅         |
| Anaconda & PyTorch (CUDA) configured       | ✅         |

---

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
/xfce4-power-manager/blank-on-ac                        0
/xfce4-power-manager/blank-on-battery                   0
/xfce4-power-manager/brightness-inactivity-on-ac        0
/xfce4-power-manager/brightness-level-on-battery        1
/xfce4-power-manager/brightness-on-battery              9
/xfce4-power-manager/brightness-switch                  0
/xfce4-power-manager/brightness-switch-restore-on-exit  1
/xfce4-power-manager/dpms-on-battery-off                0
/xfce4-power-manager/dpms-on-battery-sleep              0
/xfce4-power-manager/monitor-power-off-on-ac            false
/xfce4-power-manager/power-button-action                3
/xfce4-power-manager/show-tray-icon                     false
/xfce4-power-manager/sleep-display-ac                   0
/xfce4-power-manager/sleep-on-ac                        0
[     6.786] (**) NVIDIA(0): Option "AllowEmptyInitialConfiguration" "true"
[     6.786] (**) NVIDIA(0): Option "ConnectedMonitor" "DFP-0"
[     6.786] (**) NVIDIA(0): ConnectedMonitor string: "DFP-0"
[     6.863] (**) NVIDIA(0): Using ConnectedMonitor string "DFP-0".
[     6.870] (--) NVIDIA(GPU-0): DFP-0: connected
[     6.919] (II) NVIDIA(0): Virtual screen size determined to be 1024 x 768
[     7.693] (--) NVIDIA(GPU-0): DFP-0: connected
[     7.714] (--) NVIDIA(GPU-0): DFP-0: connected
[     7.717] (--) NVIDIA(GPU-0): DFP-0: connected
[     7.745] (--) NVIDIA(GPU-0): DFP-0: connected
[     8.553] (--) NVIDIA(GPU-0): DFP-0: connected
[     8.870] (--) NVIDIA(GPU-0): DFP-0: connected
  prefer blanking:  no    allow exposures:  yes
  timeout:  0    cycle:  600
DPMS (Display Power Management Signaling):
  Server does not have the DPMS Extension
     Active: inactive (dead)
     Active: inactive (dead)
     Active: inactive (dead)
     Active: inactive (dead)
```

✅ If all succeed, no additional manual action is needed after reboot.

---

## 6. Monitor Status of Port Externally

**A.** In [`UptimeRobot`](https://uptimerobot.com/), you can set up a monitor for your ports being forwarded so that you can check its status and uptime wherever you are.

**B.** Temporarily enabling `Exposed Host (DMZ)` in your router can be useful for troubleshooting RDP connectivity issues from outside your network. This is helpful when you want to quickly verify if your RDP server is reachable from the internet, or to rule out port forwarding misconfigurations.

> ⚠️ **Warning:**  
> DMZ exposes your entire device to the internet, bypassing most router-level protections. This significantly increases the risk of hacking, malware, and unauthorized access. **Always disable DMZ immediately after testing.** Never leave it enabled longer than necessary.

---

























# EXTERNAL DASHBOARD SERVICE

## 0. Add an HTMLResponse Endpoint at FastAPI
`stream_binance.py`에 
`@APP.get("/dashboard", response_class=HTMLResponse)`
Endpoint 추가

## 1. Nginx 설정 (우분투 서버)

### 1.1. 우분투 서버에서 다음 명령어 실행:

```bash
# Nginx 설치
sudo apt update
sudo apt install nginx

# 설정 파일 생성
sudo nano /etc/nginx/sites-available/binance-dashboard
```

설정 파일 내용:

```nano
server {
	listen 80;
	server_name c01hyka.duckdns.org 192.168.1.107 localhost;

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

```bash
# 설정 활성화
sudo ln -s /etc/nginx/sites-available/binance-dashboard /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 1.2. 방화벽(UFW)에서 80/tcp 허용
```bash
sudo ufw allow 80/tcp
sudo ufw status
```

Hint:  
- Port 8000: localhost dev.
- Port 80:  HTTP Traffic
- Port 443: HTTPS Traffic

### 1.3. 라우터에서 포트포워딩 허용

Rounter에 의해 지정된 Device IP는 우분투 홈서버에서 `ip a | grep inet` 명령어로 확인가능.
라우터 관리 페이지에서 포트포워딩 허용:
```bash
TCP/UDP Entry & Destination Port 80
```

### 1.4 DuckDNS 설정 확인
우분투 홈서버의 이러한 IPv4와 IPv6는 각각 다음 명령어를 통해 확인 가능합니다:
```bash
curl -4 ifconfig.me
curl -6 ifconfig.me
```
DuckDNS 대시보드에 IPv4와 IPv6 각각의 공인 주소를 입력해야 합니다. 예를 들어:
- IPv4: `85.x.2x9.2x3`
- IPv6: `2a?2:1?10:90?2:6?00:c8e:c??e:??af:cd??`

### 1.x. 대시보드 접근
- http://localhost:8000/dashboard		at the development computer
- http://192.168.1.107/dashboard		at the script running server (internal)
- http://c01hyka.duckdns.org/dashboard	at the script running server (external)

## 4. (선택사항) HTTPS 적용
```bash
# Let's Encrypt SSL 인증서
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d c01hyka.duckdns.org
```

## 🔍 부하 분석 비교
기존 방식 (로컬 HTML 파일)
```bash
브라우저 → WebSocket(ws://localhost:8000/ws/dashboard) → stream_binance.py
```
제안한 방식 (Nginx + 대시보드 엔드포인트)

```bash
브라우저 → Nginx → FastAPI(/dashboard) → 동일한 WebSocket → stream_binance.py
```

✅ 부하가 동일한 이유

1. WebSocket 연결은 그대로
- 기존: ws://localhost:8000/ws/dashboard
- 신규: ws://c01hyka.duckdns.org/ws/dashboard (Nginx가 프록시)
- 동일한 /ws/dashboard 엔드포인트 사용

2. 추가된 것은 HTML 서빙뿐
- /dashboard 엔드포인트는 한 번만 HTML을 반환
- 이후 모든 실시간 데이터는 기존 WebSocket 그대로

3. Nginx는 경량 프록시
- 메모리 사용량: 1-5MB
- CPU 오버헤드: 거의 없음

---

# Binance Dashboard: DuckDNS → CloudFlare + sognex.com 변경

---

## 1. 지금까지 진행 완료된 사항

### 1.1 도메인 구매 및 CloudFlare 연결
- 도메인 `sognex.com`을 Porkbun에서 구매.
- CloudFlare에 도메인 추가 및 네임서버 변경 완료:
  - `holly.ns.cloudflare.com`
  - `margo.ns.cloudflare.com`
- DNSSEC는 비활성화 상태로 확인됨.
- WHOIS Privacy 활성화 상태로 개인 정보 보호 확인됨.

### 1.2 CloudFlare 설정
- DNS 레코드 추가:
  - **A 레코드**:
    - Name: `@`
    - Content: 서버의 외부 IP 주소
    - Proxy Status: Proxied
    - TTL: Auto
  - **CNAME 레코드**:
    - Name: `www`
    - Content: `sognex.com`
    - Proxy Status: Proxied
    - TTL: Auto
- SSL/TLS 설정:
  - SSL Mode: Full로 설정.
- AI 크롤러 차단 활성화:
  - 모든 페이지에서 AI 크롤러 차단.
  - `robots.txt`를 통해 AI 학습 방지 신호 전송.

---

## 2. 앞으로 해야 할 일

### 2.1 Nginx 설정 변경
기존 DuckDNS 설정을 `sognex.com`으로 변경:
1. Nginx 설정 파일 수정:
   - 파일 경로: `/etc/nginx/sites-available/binance-dashboard`
   - 변경 내용:
     ```nginx
     server {
         listen 80;
         server_name sognex.com www.sognex.com;

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
2. 설정 적용:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

### 2.2 HTTPS 활성화
1. Let's Encrypt를 사용하여 SSL 인증서 설치:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d sognex.com -d www.sognex.com
   ```
2. 인증서 설치 후 Nginx 설정 자동 업데이트 확인.

### 2.3 방화벽 및 보안 설정
1. UFW를 사용하여 CloudFlare IP만 허용:
   ```bash
   sudo ufw allow from <Cloudflare IP Range> to any port 80,443
   ```
   - Cloudflare IP 범위는 [Cloudflare IP 목록](https://www.cloudflare.com/ips/)에서 확인 가능.
2. CloudFlare에서 **Under Attack Mode** 활성화.

### 2.4 외부 접근 테스트
1. 브라우저에서 `http://sognex.com` 또는 `https://sognex.com`을 입력하여 Binance Dashboard 접근 확인.
2. CloudFlare 대시보드에서 트래픽 및 보안 상태 점검.

---

## 참고
- 기존 DuckDNS 설정은 더 이상 사용하지 않음.
- 모든 외부 접근은 `sognex.com`을 통해 이루어짐.