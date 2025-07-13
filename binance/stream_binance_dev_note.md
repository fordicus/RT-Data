### TODO

1. **EXTERNAL DASHBOARD SERVICE**

   * dashboard_page() 함수가 하드 코딩 되어있음
   * duckdns는 신뢰할 수 없음
   * UptimeRobot이 대시보드 포트를 모니터링하도록 설정
   * 모니터링 지표 중 문제 발생 시 텔레그렘 메시지 전송

2. **홈서버 관리 가이드 통합 (RT-Data 저장소)**

- dashboard_page() 함수 디플로이 관련 세팅 문서에 통합
	- 홈서버 관리 가이드 문서를 RT-Data Git 저장소에 통합 및 정리

---
<br></br>

아래 아이디어들은 **“기능은 그대로 두고 속도와 자원 사용량만 줄인다”**-는 목표에 맞춰 ROI(기대 효과 ↔ 수정 난도) 순으로 정리했습니다. 대부분 **CPython만으로도 꽤 큰 체감 향상**을 낼 수 있고, 정말로 I/O 한계에 부딪힐 때만 C/Rust 바인딩을 고민해도 늦지 않습니다.

## 1. 가장 큰 병목부터 없애기

| 구간                                             | 현재 동작                                   | 병목 원인                                       | 개선안                                                                                                           |
| ---------------------------------------------- | --------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **① JSON 직렬화**                                 | `json.dumps(..., separators=(",",":"))` | 순수 Python 구현 + GIL                          | **`orjson.dumps` 또는 `msgspec.json.encode`** 사용 (둘 다 Rust 백엔드) → 5-15× 빠름, GC 압력 감소 ([GitHub][1], [GitHub][2]) |
| **② 매 스냅샷마다 `flush()`**                        | OS 버퍼를 강제로 비워 디스크 syscall 호출            | SSD라도 수천 OPS로 제한                            | **Flush 주기를 타임/건수로 완화**   `if queue.qsize() % 100 == 0: json_writer.flush()`                                  |
| **③ 즉시 압축(zip\_and\_remove)**                  | 현재 루프 스레드에서 ZIP 수행                      | CPU 집약 + 디스크 I/O 중첩                         | **`loop.run_in_executor()`** 로 백그라운드에 오프로드 (ThreadPool 1-2개면 충분)                                              |
| **④ 매번 `os.makedirs(tmp_dir, exist_ok=True)`** | 이미 존재하는 폴더에도 시스템콜                       | 불필요 syscall                                 | 전 회차 `current_dir` 캐싱 후 바뀔 때만 생성                                                                              |
| **⑤ 과도한 `del` 호출**                             | “GC 빨리 돌리자” 의도                          | CPython 참조 카운트는 블록 끝에서 이미 0; `del` 자체도 오버헤드 | 읽기성 + 속도 모두 ↓ → **대부분 제거**                                                                                    |

---

## 2. 코드 스케치 (핵심만)

```python
import orjson     # pip install orjson
from functools import partial
from itertools import islice
from concurrent.futures import ThreadPoolExecutor

# 전역
ZIP_EXEC = ThreadPoolExecutor(max_workers=2)
BATCH_SIZE = 100        # 스냅샷 100개마다 디스크 flush
ENC = partial(orjson.dumps, option=orjson.OPT_APPEND_NEWLINE)  # \n 포함

async def symbol_dump_snapshot(symbol: str) -> None:
    ...
    last_flush_cnt = 0
    
    while True:
        snapshot = await queue.get()
        if not EVENT_STREAM_ENABLE.is_set():
            continue

        # ==== (1) 핸들 회전 로직은 그대로 ====

        # ==== (2) 직렬화 & 버퍼링 ====
        json_writer.write(ENC(snapshot))
        last_flush_cnt += 1
        if last_flush_cnt >= BATCH_SIZE:
            json_writer.flush()
            last_flush_cnt = 0

        # ==== (3) ZIP 작업을 논블로킹으로 ====
        if last_suffix != suffix and last_suffix is not None:
            ZIP_EXEC.submit(zip_and_remove, last_file_path)
```

*`orjson.OPT_APPEND_NEWLINE`* 을 쓰면 `+"\n"`도 필요 없습니다.

---

## 3. 추가 미세 튜닝

1. **uvloop**: Linux 기준 `asyncio` 루프를 Cythonized libuv로 교체 → context-switch 적고 타이머 정확도↑.

   ```python
   import uvloop, asyncio
   uvloop.install()
   ```
2. **Buffered writer 직접 지정**
   `open(file_path, "ab", buffering=1024*1024)` (바이너리 + 1 MiB 버퍼) 후 `orjson.dumps` 결과를 그대로 `.write()`
   → 텍스트 모드보다 변환 단계 하나 줄어듭니다.
3. **압축 형식 변경**: 하루치 파일을 **zstd(‐T0)** 로 압축하면 CPU 사용량은 비슷하거나 적고, 속도는 2-4×.
   `python-zstandard` 가 GIL 해제를 지원해 백그라운드 스레드 효율이 좋습니다.
4. **msgspec.Struct** 를 정의해 스냅샷의 스키마가 고정돼 있다면
   `encode(snapshot_struct)` 가 단순 dict보다 추가 20-30 % 가속을 보여줍니다 ([jcristharif.com][3]).
5. **멀티-프로세스?**
   디스크 쓰기 자체가 병목이라면 공정하게 분산 가능. 하지만 파일-핸들 회전 로직이 복잡해져 ROI가 떨어집니다.

---

## 4. “완전히 다른 언어”가 필요한 경우

* **초당 수만 스냅샷** 이상 → Python I/O 스레드도 버거우면

  * **Rust** 로 writer 스레드를 작성하고 `PyO3` 로 노출 (orjson이 이미 이런 방식).
  * **Go**: 고루틴 + 채널로 디스크 라이터 분리.
  * **Cython**: 큰 효과는 `zip_and_remove` 같은 CPU-핫스팟에 한정.
* 하지만 **I/O 제한(SSD 쓰기, 압축)** 이 병목이면 언어 바꿔도 큰 이득은 없습니다. 먼저 위 Python 튜닝으로 실제 디바이스 한계까지 끌어올려 보시는 걸 권장합니다.

---

### TL;DR

* `orjson`/`msgspec` 로 직렬화 교체 + flush 주기 완화 + ZIP 백그라운드화 ⇒ **대부분의 실전 환경에서 5-10× TPS 상승**
* 나머지는 “디스크 자체가 감당 못 할 때” 고민해도 늦지 않아요.

[1]: https://github.com/ijl/orjson?utm_source=chatgpt.com "ijl/orjson: Fast, correct Python JSON library supporting ... - GitHub"
[2]: https://github.com/jcrist/msgspec?utm_source=chatgpt.com "jcrist/msgspec: A fast serialization and validation library, with builtin ..."
[3]: https://jcristharif.com/msgspec/benchmarks.html?utm_source=chatgpt.com "Benchmarks - msgspec"


---
<br></br>

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