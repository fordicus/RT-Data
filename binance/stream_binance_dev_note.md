### TODO

1. **대시보드 주요 지표 파악 및 이상 감지 알림 설정**

   * 대시보드에서 가장 중요한 지표 식별
   * 해당 지표에 문제가 발생하면 Telegram으로 자동 알림 전송 설정

2. **성능 프로파일링 (Before & After)**

   * Stream을 구독할 Binance symbol 목록 확장
   * **(Before)**: 기존 코드 상태에서 1시간 동안 성능 프로파일링 데이터 수집
   * 성능 향상 아이디어를 코드에 통합
   * **(After)**: 수정된 코드에서 다시 1시간 동안 성능 프로파일링 데이터 수집

3. **UptimeRobot 설정**

   * UptimeRobot이 대시보드 상태만 모니터링하도록 설정

4. **대시보드 외부 공개**

   * 현재 대시보드를 외부에서 접근 가능하도록 노출 설정

5. **홈서버 관리 가이드 통합 (RT-Data 저장소)**

   * 홈서버 관리 가이드 문서를 RT-Data Git 저장소에 통합 및 정리

---

### ⚙️ Performance Boost Ideas

**Rust 전체 포팅 없이도 Python 환경에서 실질적인 성능 향상을 달성할 수 있는 실용적 기법들:**

1. **uvloop 적용**

   * 코드 예시: `import uvloop; asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())`
   * libuv 기반 이벤트 루프 → 기본 asyncio 대비 **2\~4배 빠른 성능**
   * Windows에서는 Docker Desktop 또는 WSL 환경을 통해 테스트
   * Docker 환경에서 적용 예시:

     ```dockerfile
     RUN pip install -r requirements.txt pyinstaller
     ```

2. **orjson 활용**

   * Rust 기반 초고속 JSON 직렬화/역직렬화 라이브러리
   * `json` 대비 **2\~10배 빠른 처리 속도**
   * 대용량 데이터 처리에 특히 효과적

3. **핵심 병목 지점만 Cython 또는 Rust로 최적화**

   * 전체 포팅 대신, **프로파일링으로 병목 함수만 선별 최적화**
   * Cython 또는 Rust FFI를 통해 성능 개선

---

### 🚀 실행 전략

* 먼저 **프로파일링**으로 병목 구간 파악
* `uvloop`, `orjson` 등 **적용이 쉬운 최적화**부터 도입
* 성능 저하가 큰 함수에 한해 **선택적으로 Cython 또는 Rust FFI 적용**

> 위 전략 조합만으로도 **전체 Rust 포팅 대비 훨씬 적은 리팩토링 비용으로 2\~5배 성능 향상** 기대 가능

---
<br></br><br></br><br></br>















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
- IPv4: `85.6.249.253`
- IPv6: `2a02:1210:9002:6500:c8e:ce2e:23af:cdea`

### 1.x. 대시보드 접근
- http://localhost:8000/dashboard		(프로그램 실행 중인 컴퓨터에서)
- http://192.168.1.107/dashboard		(홈서버 가동중 동일 라우터 네트워크에서)
- http://c01hyka.duckdns.org/dashboard	(외부)

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
