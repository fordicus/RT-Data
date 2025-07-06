# Web Dashboard for `stream_binance.py`  
`stream_binance.py` 스크립트의 상태와 성능을 실시간으로 모니터링하기 위해
리소스 효율적인 대시보드를 설계합니다. 이 대시보드는 다음 정보를 실시간으로
보고합니다:

1. `put_snapshot()`에서 각 심볼의 `med_latency`.
2. 각 심볼의 스냅샷이 `dump_snapshot_for_symbol()`에서 얼마나 자주
   플러시되는지.
3. 하드웨어 리소스 (여유 공간 확인용):  
   3.1. OS 기준 CPU 부하,  
   3.2. OS 기준 네트워크 부하,  
   3.3. OS 기준 디스크 공간.  

설계 기준:

1. 대시보드는 외부에서 브라우저를 통해 접근 가능해야 합니다.
2. 대시보드가 코드의 기능을 방해하지 않아야 합니다 (no RestAPI, no browser refresh).

# 상세 구현 계획  
### 서버 측 (FastAPI + WebSockets)
1. **FastAPI 설정**:
   - WebSocket 엔드포인트를 포함한 FastAPI 애플리케이션 생성.
   - 실시간 데이터 스트리밍 엔드포인트 정의 (예: `/ws/metrics`).

2. **데이터 수집 훅**:
   - `stream_binance.py`에 다음 메트릭을 수집하기 위한 훅 통합:
     - 각 심볼의 `med_latency`.
     - 스냅샷 플러시 빈도.
     - 하드웨어 리소스 사용량 (CPU, 네트워크, 디스크).
   - 비차단 메서드 (예: `asyncio`)를 사용하여 성능 영향을 최소화.

3. **WebSocket 통합**:
   - 대시보드용 데이터는 코드의 핵심 기능 및 데이터와 완전히 분리되도록,
     별도의 변수 선언 후 데이터를 할당 혹은 복사하는 방식으로 구현.
   - 스크립트의 메인 프로세스가 대시보드와는 최대한 분리된 리소스를 사용하도록 설계.
   - 수집된 메트릭을 실시간으로 연결된 WebSocket 클라이언트에 푸시.
   - 락(lock) 또는 큐(queue)를 사용하여 공유 데이터에 대한 스레드 안전한 접근 보장.

4. **리소스 모니터링**:
   - `psutil`과 같은 라이브러리를 사용하여 CPU, 네트워크, 디스크
     모니터링.
   - 효율적인 전송을 위해 데이터를 집계 및 포맷.

### 클라이언트 측 (JavaScript + WebSockets)
1. **WebSocket 연결**:
   - 서버에 WebSocket 연결 설정.
   - 대시보드를 동적으로 업데이트하기 위해 들어오는 메시지 처리.

2. **대시보드 UI**:
   - HTML/CSS를 사용하여 깔끔하고 반응형 UI 설계.
   - 실시간으로 메트릭 표시 (예: 테이블, 차트).
   - Chart.js 또는 D3.js와 같은 라이브러리를 사용하여 시각화.

3. **에러 처리**:
   - WebSocket 실패에 대한 재연결 로직 구현.
   - 연결 문제 동안 대체 메시지 또는 지표 표시.

### 보안 및 확장성
1. **인증**:
   - 이 대시보드는 외부로 노출되지만, 나 혼자 사용할 것입니다.
     아이디 비번 필요없고, 최대 접속자수를 한명으로 유지하면 됩니다. 예를 들어,
     내가 웹소켓 접속을 시도하면, 기존에 접속해있던 클라이언트를 끊으면 됩니다.

2. **확장성**:
   - 여러 클라이언트를 효율적으로 처리하기 위해 데이터 전송 최적화.
   - 필요 시 서버를 로드 밸런싱으로 배포 고려.

### 테스트
1. **유닛 테스트**:
   - 개별 구성 요소 테스트 (예: WebSocket 엔드포인트, 데이터 훅).

2. **통합 테스트**:
   - `stream_binance.py`와 대시보드 간의 실시간 데이터 흐름 시뮬레이션.

3. **성능 테스트**:
   - 데이터 수집 및 전송이 `stream_binance.py`에 미치는 영향 측정.

---

다음 단계:
1. WebSocket 엔드포인트를 포함한 FastAPI 서버 구현.
2. `stream_binance.py`에 데이터 수집 훅 추가.
3. 클라이언트 측 대시보드 UI 및 WebSocket 로직 개발.
4. 시스템의 기능, 성능 및 확장성 테스트.
5. 크로니
6. 프로파일링

# Performance Boost Ideas

Rust로 전체 포팅하지 않고도 Python 환경에서 실질적인 성능 향상을 얻을 수 있는 실용적 엔지니어링 기법들:

1. **uvloop 적용**
   - `import uvloop; asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())`
   - libuv 기반 이벤트 루프 사용으로 기본 asyncio 대비 2~4배 빠른 성능
   - Windows 환경에서는 Docker Desktop 또는 WSL을 사용하여 테스트 가능
   - Docker 컨테이너 내부에서 uvloop를 활성화하여 Linux 환경에서 성능 확인 가능  
     `RUN pip install -r requirements.txt pyinstaller` @Dockerfile

2. **orjson 활용**
   - `orjson`은 Rust로 작성된 초고속 JSON 직렬화/역직렬화 라이브러리
   - 대량의 JSON 처리에서 2~10배 빠른 성능

3. **핵심 병목 지점만 Cython/Rust로 최적화**
   - 전체 포팅 대신, 프로파일링으로 병목 함수만 Cython(또는 Rust FFI)로 작성

**실행 전략:**
- 먼저 프로파일링으로 실제 병목 파악 → uvloop, orjson 등 쉬운 최적화부터 적용 → 가장 느린 부분만 선택적으로 Cython/Rust로 작성
- 위 기법 조합만으로도 Rust 전체 포팅 대비 적은 노력으로 2~5배 성능 향상 가능

