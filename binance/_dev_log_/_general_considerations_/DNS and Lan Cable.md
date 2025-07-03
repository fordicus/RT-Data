---

여러가지 이유로인하여, 바이낸스 스트리밍을 목적으로하는 홈 서버는 WiFi가 아닌 유선랜 연결이 필수적이다.

---

## 🧠 systemd-resolved 기반 DNS 구성 이해

현재 Ubuntu 시스템의 `/etc/resolv.conf`는 다음과 같이 설정되어 있음:

```bash
(base) c01hyka@c01hyka-Nitro-AN515-54:~/binance$ cat /etc/resolv.conf
```

예시 출력:

```
# This is /run/systemd/resolve/stub-resolv.conf managed by man:systemd-resolved(8).
# Do not edit.
...
nameserver 127.0.0.53
options edns0 trust-ad
search home
```

### 🔍 이게 의미하는 바

* `nameserver 127.0.0.53`은 **로컬 DNS 프록시**(stub resolver)를 뜻함
* 즉, 리눅스는 **실제로는 로컬에서 돌고 있는 `systemd-resolved`에게 질의**함
* 그 뒤 `systemd-resolved`는 **라우터 DNS 또는 ISP DNS**로 질의를 넘김 (예: `192.168.0.1`)
* 이 구성은 `/etc/resolv.conf` 파일을 **자동으로 관리하고 덮어씀**

### ⚠️ 문제점

* 우리가 `resolv.conf`를 직접 편집해도 **systemd-resolved가 나중에 다시 덮어씀**
* 따라서 **외부 고성능 DNS (예: Cloudflare, Google 등)** 을 직접 설정하려면:
  → `systemd-resolved`를 **중지**하고,
  → 해당 설정파일을 **완전히 교체**해야 함

---

## 🔧 외부 DNS를 수동으로 설정하는 방법

아래는 직접 설정할 수 있는 스크립트입니다.
한 번만 실행하면, 리부팅 후에도 DNS 설정이 그대로 유지됩니다.

```bash
nano ~/fix_dns.sh
```

스크립트 내용:

```bash
#!/bin/bash

# systemd-resolved 서비스 완전 비활성화
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved

# /etc/resolv.conf 파일 삭제 및 대체
sudo rm -f /etc/resolv.conf
sudo bash -c 'cat <<EOF > /etc/resolv.conf
nameserver 1.1.1.1        # Cloudflare (초저지연, 전세계 빠름)
nameserver 8.8.8.8        # Google (안정적이고 범용적)
nameserver 9.9.9.9        # Quad9 (보안 필터링 우수, 스위스 기반)
nameserver 208.67.222.222 # OpenDNS (Cisco 운영, fallback 용도)
EOF'
```

스크립트 저장 후 실행 권한 부여:

```bash
chmod +x ~/fix_dns.sh
```

한 번만 실행:

```bash
./fix_dns.sh
```

---

## ✅ 기대 효과 요약

| 항목                 | 설명                                       |
| ------------------ | ---------------------------------------- |
| 🔁 리부팅 이후에도 DNS 유지 | systemd-resolved 완전 비활성화로 영구 설정          |
| 🌐 DNS 지연 최소화      | Cloudflare → Google → Quad9 순서로 fallback |
| 💥 연결 실패 방지        | Binance WebSocket 등에서 재연결 성공률 향상         |
| 🛡 보안/속도/복원력 조합    | CDN 기반 DNS + 보안 필터 DNS 구성                |
| ⚙️ 유지보수 없음         | 한 번만 설정하면 끝. 재설정 불필요                     |

---

## 📌 정리

* 현재 systemd-resolved는 DNS 프록시로 동작 중이며 `/etc/resolv.conf`를 계속 덮어씀
* Binance WebSocket 안정성과 속도를 위해 외부 DNS를 수동으로 직접 설정
* 위 스크립트는 **한 번만 실행하면 영구 반영**, 별도 리부팅도 불필요
* 추후 영어로 변환하여 **Ubuntu Remote Access Guide**에 병합 예정

---
