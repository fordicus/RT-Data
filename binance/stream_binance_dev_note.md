### TODO

#### **1. 심볼별 CPU/I-O 바운드 병합 쓰레드**

`MERGE_LOCKS[symbol]`는 심볼별로 관리되지만, 실제 병합 함수가 모든 심볼을 한 번에 처리하면 의도치 않게 여러 심볼의 병합이 동시에 중복 실행될 수 있습니다.  따라서 `merge_all_symbols_for_day` 대신, 아래와 같이 `merge_day_zips_to_single_jsonl(symbol, day_str, ...)`을 직접 쓰레드에서 호출하는 방식이 더 안전합니다:

```python
if last_day != day_str and last_day not in MERGED_DAYS:
    MERGED_DAYS.add(last_day)
    threading.Thread(
        target=merge_day_zips_to_single_jsonl,
        args=(symbol, last_day, LOB_DIR, PURGE_ON_DATE_CHANGE == 1),
    ).start()
```

이렇게 하면 `merge_day_zips_to_single_jsonl` 함수가 심볼별로 독립적인 쓰레드에서 실행되므로,  
아래와 같은 블로킹 작업들을 별도의 쓰레드에서 효율적으로 처리할 수 있습니다.  
따라서 이 함수 내부에서 다시 쓰레드를 생성할 필요가 없습니다:

- `with open(merged_path, "w", encoding="utf-8") as fout:`
- `with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:`
- `shutil.rmtree(tmp_dir)`

이렇게 리팩터링 후, `merge_all_symbols_for_day()` 함수는 불필요해질 것이므로 삭제 가능하다.

#### **2. 대시보드 안정성 개선**

TODO:
- 로거 생성
- 예외처리 로직 개선
- 대시보드 사망시 메인 프로세스의 대응

알려진 문제:

```bash
[2025-07-07T21:46:40.885047+00:00] WARNING: [put_snapshot] Failed to process message: [Errno 104] Connection reset by peer
Traceback (most recent call last):
  File "stream_binance.py", line 1489, in put_snapshot
  File "<string>", line 2, in __getitem__
  File "multiprocessing/managers.py", line 822, in _callmethod
  File "multiprocessing/connection.py", line 250, in recv
  File "multiprocessing/connection.py", line 430, in _recv_bytes
  File "multiprocessing/connection.py", line 395, in _recv
ConnectionResetError: [Errno 104] Connection reset by peer
[2025-07-07T21:46:40.891352+00:00] WARNING: [put_snapshot] Failed to process message: [Errno 32] Broken pipe
Traceback (most recent call last):
  File "stream_binance.py", line 1489, in put_snapshot
  File "<string>", line 2, in __getitem__
  File "multiprocessing/managers.py", line 821, in _callmethod
  File "multiprocessing/connection.py", line 206, in send
  File "multiprocessing/connection.py", line 427, in _send_bytes
  File "multiprocessing/connection.py", line 384, in _send
BrokenPipeError: [Errno 32] Broken pipe
```

**가능한 원인들:**

- **1. 대시보드 프로세스(또는 Manager 서버)가 비정상적으로 종료됨**
  - 예: uvicorn/FastAPI 내부 예외, 포트 충돌, 메모리 부족(OOM), OS에 의한 강제 종료(SIGKILL 등)
  - 대시보드 프로세스가 죽으면 Manager IPC 채널이 끊기고, 메인 프로세스에서 공유 dict 접근 시 ConnectionResetError/BrokenPipeError가 발생

- **2. WebSocket 핸들러에서 예외 발생 후 루프 종료**
  - 대시보드의 WebSocket 핸들러에서 IPC 오류 등 예외 발생 시, print 후 break로 루프가 종료되어 더 이상 데이터를 송출하지 않음
  - 이로 인해 대시보드가 "조용히 죽은 것"처럼 동작할 수 있음

- **3. 메인 프로세스가 Manager 객체를 명시적으로 종료하거나, 프로세스 종료 시 리소스 정리 미흡**
  - 일반적으로는 메인 프로세스가 살아있다면 드문 케이스

- **4. 시스템 리소스 부족/네트워크 장애**
  - 메모리 부족, 파일 디스크립터 고갈, 네트워크 장애 등으로 IPC 채널이 끊길 수 있음

- **5. 포트 충돌/uvicorn 실행 실패**
  - 이미 8080 포트가 사용 중이거나, uvicorn 실행 중 내부 오류 발생 시 대시보드 프로세스가 즉시 종료될 수 있음

**대응방안:**

- 메인 프로세스에서 대시보드 프로세스의 상태를 주기적으로 감시(`is_alive()`)하고, 죽었을 경우 자동으로 재시작
- WebSocket 핸들러에서 예외 발생 시 단순 break가 아니라, 로그 기록 및 필요시 관리자 알림/재시작 로직 추가
- Manager 객체의 생명주기와 리소스 정리를 명확히 관리
- 포트 충돌, 리소스 부족 등 치명적 예외 발생 시 로그를 남기고, 재시작 정책을 적용

**코드 예시:**

```python
if __name__ == "__main__":
    # ...
    MANAGER = Manager()
    SHARED_STATE_DICT = MANAGER.dict({
        "med_latency": MANAGER.dict()
    })

    dashboard_args = (
        float(CONFIG.get("DASHBOARD_STREAM_FREQ", 0.03)),
        SHARED_STATE_DICT,
    )
    dashboard_process = Process(
        target=start_dashboard_server,
        args=dashboard_args
    )
    dashboard_process.start()

    async def monitor_dashboard_process_async():
        global dashboard_process
        restart_timeout = 10  # TODO: assign .conf const

        while True:
            if not dashboard_process.is_alive():
                logger.warning("[main] Dashboard process died. Restarting...")
                dashboard_process = Process(
                    target=start_dashboard_server,
                    args=dashboard_args
                )
                dashboard_process.start()

                waited = 0
                while not dashboard_process.is_alive() and waited < restart_timeout:
                    await asyncio.sleep(0.5)
                    waited += 0.5

                if not dashboard_process.is_alive():
                    logger.error(
                        "[main] Dashboard process failed to start after restart_timeout."
                    )

            await asyncio.sleep(2)  # TODO: assign .conf const

    async def main():
        # ...
        asyncio.create_task(monitor_dashboard_process_async())
        # ...
```

#### **3. 홈서버 시간 동기화**
- 우분투 홈서버를 크로니 통해 신뢰도 확보

#### **4. 기타 기능 추가**
- 키 관리 방식 개선:
	SHARED_STATE_DICT의 키(med_latency)를 상수로 정의하여 관리하면 유지보수성과 확장성이 향상됩니다.

- 하드웨어 리소스 모니터링 구현:
	cpu_usage, memory_usage, disk_usage를 psutil 라이브러리를 사용하여 구현하고, WebSocket 엔드포인트에서 클라이언트에 전송해야 합니다.

#### **5. [일관된 참고사항] 성능 최적화 염두에 둘 것**
- 현재 단계에서는 `uvloop`를 적용하지 않지만, 추후 포팅 가능성을 염두에 두고 설계를 유연하게 유지합니다.
- 데이터 직렬화/역직렬화에 `orjson`을 사용할 수 있도록 준비합니다.

#### **6. 테스트 및 프로파일링**
- 대시보드가 심볼별 `med_latency`를 정확히 표시하는지 확인합니다.
- WebSocket 연결 안정성과 데이터 전달 속도를 테스트합니다.
- 프로파일링 도구를 사용하여 병목 지점을 식별하고 최적화합니다.

# Web Dashboard for `stream_binance.py`
`stream_binance.py` 스크립트의 상태와 성능을 실시간으로 모니터링하기 위해 리소스 효율적인 대시보드를 설계합니다. 이 대시보드는 다음 정보를 실시간으로 보고합니다:

1. [의도한 대로 프로토타입 되었음] `put_snapshot()`에서 각 심볼의 `med_latency`.
2. [다음에 할 예정] 각 심볼의 스냅샷이 `dump_snapshot_for_symbol()`에서 얼마나 자주 플러시되는지.
3. [다음에 할 예정] 하드웨어 리소스 (여유 공간 확인용):
   3.1. OS 기준 CPU 부하,
   3.2. OS 기준 네트워크 부하,
   3.3. OS 기준 디스크 공간.

설계 기준:

1. 대시보드는 외부에서 브라우저를 통해 접근 가능해야 합니다.
2. 대시보드가 코드의 기능을 방해하지 않아야 합니다 (no RestAPI, no browser refresh).

# 상세 구현 계획
### 낮은 개발 코스트로 대시보드 구현
1. [의도한 대로 프로토타입 되었음] **프로세스 간 공유 메모리 사용**:
   - Python의 `multiprocessing.Manager`를 사용하여 심볼별 데이터를 공유하는 dictionary를 생성합니다.
   - `stream_binance.py`는 데이터를 쓰고, 대시보드 프로세스는 읽기만 하도록 설계하면 안전합니다.

2. [의도한 대로 프로토타입 되었음] **WebSocket 서버와 데이터 공유**:
   - 대시보드 프로세스는 FastAPI를 사용하여 WebSocket 서버를 실행하고, 공유 메모리에서 데이터를 읽어 클라이언트에 실시간으로 전송합니다.

3. [다음에 할 예정] **모니터링 데이터 수집**:
   - `psutil` 라이브러리를 사용하여 CPU, 네트워크, 디스크 사용량을 수집하고 대시보드에 표시합니다.

### 대시보드 스트림 분리 방법
1. [의도한 대로 프로토타입 되었음] **별도 프로세스에서 FastAPI 실행**:
   - 대시보드용 FastAPI 앱을 별도의 프로세스로 실행하여 메인 프로세스와 완전히 분리합니다.
   - 메인 프로세스는 기존의 `stream_binance.py` 기능에 집중하고, 대시보드 프로세스는 데이터를 소비하여 클라이언트에 제공하는 역할을 합니다.

2. [의도한 대로 프로토타입 되었음] **프로세스 간 통신 (IPC)**:
   - 메인 프로세스에서 대시보드 프로세스로 데이터를 전달하기 위해 shared memory를 사용합니다.
   - 메인 프로세스에서 dictionary of dictionary로 정의된 `SHARED_STATE_DICT`에 데이터를 쓰고, 대시보드 프로세스는 이를 읽어 클라이언트에 전달합니다.
   - 메인 프로세스는 데이터를 생산하고, 대시보드 프로세스는 이를 소비하여 WebSocket 클라이언트에 전송합니다.
   - 데이터 전달은 비동기적으로 이루어져야 하며, 메인 프로세스의 성능에 영향을 주지 않도록 설계합니다.

---
## 참고사항
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