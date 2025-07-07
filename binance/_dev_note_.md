# Web Dashboard for `stream_binance.py`
`stream_binance.py` 스크립트의 상태와 성능을 실시간으로 모니터링하기 위해 리소스 효율적인 대시보드를 설계합니다. 이 대시보드는 다음 정보를 실시간으로 보고합니다:

1. `put_snapshot()`에서 각 심볼의 `med_latency`.
2. 각 심볼의 스냅샷이 `dump_snapshot_for_symbol()`에서 얼마나 자주 플러시되는지.
3. 하드웨어 리소스 (여유 공간 확인용):
   3.1. OS 기준 CPU 부하,
   3.2. OS 기준 네트워크 부하,
   3.3. OS 기준 디스크 공간.

설계 기준:

1. 대시보드는 외부에서 브라우저를 통해 접근 가능해야 합니다.
2. 대시보드가 코드의 기능을 방해하지 않아야 합니다 (no RestAPI, no browser refresh).

# 상세 구현 계획
### 낮은 개발 코스트로 대시보드 구현
1. **프로세스 간 공유 메모리 사용**:
   - Python의 `multiprocessing.Manager`를 사용하여 심볼별 데이터를 공유하는 dictionary를 생성합니다.
   - `stream_binance.py`는 데이터를 쓰고, 대시보드 프로세스는 읽기만 하도록 설계하면 안전합니다.

2. **WebSocket 서버와 데이터 공유**:
   - 대시보드 프로세스는 FastAPI를 사용하여 WebSocket 서버를 실행하고, 공유 메모리에서 데이터를 읽어 클라이언트에 실시간으로 전송합니다.

3. **간단한 IPC 구현**:
   - `multiprocessing.Queue`를 사용하여 데이터를 전달할 수 있습니다. 이는 별도의 브로커 없이도 간단히 구현 가능합니다.

4. **모니터링 데이터 수집**:
   - `psutil` 라이브러리를 사용하여 CPU, 네트워크, 디스크 사용량을 수집하고 대시보드에 표시합니다.

### 대시보드 스트림 분리 방법
1. **별도 프로세스에서 FastAPI 실행**:
   - 대시보드용 FastAPI 앱을 별도의 프로세스로 실행하여 메인 프로세스와 완전히 분리합니다.
   - 메인 프로세스는 기존의 `stream_binance.py` 기능에 집중하고, 대시보드 프로세스는 데이터를 소비하여 클라이언트에 제공하는 역할을 합니다.

2. **프로세스 간 통신 (IPC)**:
   - 메인 프로세스에서 대시보드 프로세스로 데이터를 전달하기 위해 `multiprocessing.Queue`, `asyncio.Queue`, 또는 shared memory를 사용합니다.
   - 메인 프로세스는 데이터를 생산하고, 대시보드 프로세스는 이를 소비하여 WebSocket 클라이언트에 전송합니다.

3. **데이터 전달 방식**:
   - 메인 프로세스에서 `symbol_snapshots_to_render` 또는 `SNAPSHOTS_QUEUE_DICT`에 데이터를 쓰고, 대시보드 프로세스는 이를 읽어 클라이언트에 전달합니다.
   - 데이터 전달은 비동기적으로 이루어져야 하며, 메인 프로세스의 성능에 영향을 주지 않도록 설계합니다.

### 구체적인 개발 스텝
#### **1. 메인 프로세스에서 데이터 생산**
- `stream_binance.py`의 `put_snapshot()` 함수에서 심볼별 `med_latency`를 계산하고, 이를 `multiprocessing.Queue` 또는 `multiprocessing.Manager().dict`에 저장합니다.
- 데이터는 메인 프로세스에서 생산되며, 대시보드 프로세스에서 소비됩니다.

#### **2. 대시보드 프로세스에서 데이터 소비**
- 별도의 FastAPI 앱을 실행하여 WebSocket 엔드포인트를 생성합니다.
- WebSocket 엔드포인트는 메인 프로세스에서 공유된 데이터를 읽어 클라이언트에 실시간으로 전송합니다.

#### **3. 클라이언트 측 구현**
- 브라우저에서 WebSocket을 통해 데이터를 수신하고, HTML/JavaScript를 사용하여 대시보드 UI를 구현합니다.
- 심볼별 `med_latency`를 테이블 또는 그래프로 시각화합니다.

#### **4. 성능 최적화 준비**
- 현재 단계에서는 `uvloop`를 적용하지 않지만, 추후 포팅 가능성을 염두에 두고 설계를 유연하게 유지합니다.
- 데이터 직렬화/역직렬화에 `orjson`을 사용할 수 있도록 준비합니다.

#### **5. 테스트 및 프로파일링**
- 대시보드가 심볼별 `med_latency`를 정확히 표시하는지 확인합니다.
- WebSocket 연결 안정성과 데이터 전달 속도를 테스트합니다.
- 프로파일링 도구를 사용하여 병목 지점을 식별하고 최적화합니다.

---
### Performance Boost Ideas
Rust로 전체 포팅하지 않고도 Python 환경에서 실질적인 성능 향상을 얻을 수 있는 실용적 엔지니어링 기법들:

1. **uvloop 적용**:
   - `import uvloop; asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())`
   - libuv 기반 이벤트 루프 사용으로 기본 asyncio 대비 2~4배 빠른 성능
   - Windows 환경에서는 Docker Desktop 또는 WSL을 사용하여 테스트 가능
   - Docker 컨테이너 내부에서 uvloop를 활성화하여 Linux 환경에서 성능 확인 가능
     `RUN pip install -r requirements.txt pyinstaller` @Dockerfile

2. **orjson 활용**:
   - `orjson`은 Rust로 작성된 초고속 JSON 직렬화/역직렬화 라이브러리
   - 대량의 JSON 처리에서 2~10배 빠른 성능

3. **핵심 병목 지점만 Cython/Rust로 최적화**:
   - 전체 포팅 대신, 프로파일링으로 병목 함수만 Cython(또는 Rust FFI)로 작성

**실행 전략**:
- 먼저 프로파일링으로 실제 병목 파악 → uvloop, orjson 등 쉬운 최적화부터 적용 → 가장 느린 부분만 선택적으로 Cython/Rust로 작성
- 위 기법 조합만으로도 Rust 전체 포팅 대비 적은 노력으로 2~5배 성능 향상 가능.

