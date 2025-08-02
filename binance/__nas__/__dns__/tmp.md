### 한줄 요약

WireGuard(사설 VPN)만 쓰기로 했다면 **Cloudflare**에서는 *거의 손댈 게 없다*.
남는 일은 “DNS-Only (회색 구름) A/AAAA 레코드 유지 + IP 자동갱신 스크립트” 정도야.

---

## 해야 할(또는 안 해도 되는) 일 체크리스트

| 구분                                  | 해야 할 것                                                                                                                      | 왜/언제 필요한가                                                         |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **1. DNS Proxy 해제**                 | `rdp.sognex.com`, `sftp.sognex.com`을 **DNS Only**(회색 구름)로 두기 <br>– *HTTP가 아니면 Orange-Proxy가 트래픽을 막음* ([Cloudflare Docs][1]) | RDP·SFTP는 3389/22 TCP를 직접 쓰지만, 이제 외부 포트는 차단돼 있어. “DNS 해결만” 해주면 충분 |
| **2. A/AAAA 레코드 유지**                | 여전히 **공인 IP**(또는 DDNS)를 가리키도록 유지 <br>– 새로운 **vpn.sognex.com** 서브도메인을 만들어 WireGuard 51820/UDP 용으로 써도 OK                      | 클라이언트가 WireGuard에 붙을 때 이 주소를 참조                                   |
| **3. Cloudflare IP 화이트리스트 제거**      | UFW에서 `<Cloudflare IP Ranges>` 허용 루프를 통째로 삭제                                                                                | 외부 3389/22 포트를 완전히 닫았으니, Cloudflare IP만 열어 두는 정책 자체가 불필요          |
| **4. DDNS 스크립트 그대로 사용**             | 가정용 회선이라 IP가 변하면 **Cloudflare API**로 A레코드 업데이트하는 기존 파이썬 스크립트 유지                                                             | WireGuard도 결국 공인 IP로 접속하므로, 레코드 최신화가 계속 필요                        |
| **5. (선택) Zero Trust/ Argo Tunnel** | WireGuard가 이미 포트를 0개로 만드는 역할을 하므로, <br>Cloudflare Tunnel·Access로 RDP/SSH를 프록시할 **추가 이득은 적음**                                | 단, 사내·모바일 디바이스마다 별도 VPN을 깔기 싫다면 대안이 될 수 있음                        |

> **이미 가이드에 있던 “향후 TODO → WireGuard 도입”을 실행했으니, <br>Cloudflare 보안 규칙 자동 갱신 작업(TODO)도 사실상 무의미해졌어.**&#x20;

---

## 변경 후 동작 흐름

1. **클라이언트**

   1. `wg-quick up client.conf` → VPN 터널 형성
   2. 내부 DNS(스플릿 DNS)든 외부 DNS든 `rdp.sognex.com` → **10.0.0.1** 로 해석
   3. `mstsc / sftp` 클라이언트가 10.0.0.1:3389/22 접속

2. **Cloudflare**

   * *단순 권위 DNS* 로서 질의에 IP만 응답
   * HTTP/S 트래픽만 Orange-Proxy(WAF, CDN) 적용 가능

3. **서버/라우터**

   * 외부에서 열려 있는 것은 **51820/UDP 한 포트**뿐
   * UFW도 “51820/udp allow” 한 줄이면 끝

---

## 어린이 설명 🍬

“클라우드플레어는 이제 **주소 안내소** 역할만 해. 친구(클라이언트)가 ‘집(서버) 주소’ 묻으면 ‘여기야!’ 하고 번호만 가르쳐 주고, 문단속(포트 여닫기)은 WireGuard가 다 해 주니까 더는 도와줄 일이 없지!”

---

### 결론

* **Cloudflare에선 DNS 레코드만 잘 유지**하면 끝.
* UFW 화이트리스트·Proxy 상태 같은 복잡한 설정은 **WireGuard가 등장하면서 필요 없어졌다**.
  즉, 현재 세팅 기준으로는 별도 추가 작업 없다—‘DNS Only’만 확인하고 편히 쉬어도 돼!

[1]: https://developers.cloudflare.com/dns/proxy-status/?utm_source=chatgpt.com "Proxy status - DNS"
