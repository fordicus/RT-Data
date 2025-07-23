### 1. 소프트웨어의 목적 (Purpose)

* **저지연‧고안정 실시간 주문서(Depth20) 수집**
  *stream\_binance.py*는 바이낸스 **WebSocket** 스트림(`@depth20@100ms`)을 구독하여 지정한 암호화폐 심볼들의 호가 스냅샷을 **100 ms 간격**으로 받아옵니다 .
* **네트워크 품질 기반 스트림 제어**
  별도 **estimate\_latency** 코루틴이 서버‑클라이언트 왕복 지연(latency)을 지속 측정하고, 임계값을 초과하면 **gate\_streaming\_by\_latency**가 스트림 자체를 일시 정지시켜 데이터 불일치와 과부하를 방지합니다 .
* **안정적 데이터 영속화 및 로깅**
  수집된 스냅샷은 분(minute) 단위 `.jsonl`로 저장 후 즉시 **zip** 압축하고, 일(日) 단위로 다시 합쳐 하나의 아카이브로 보존하여 디스크 I/O를 최소화합니다 .
* **실시간 운영 Dashboard 제공**
  **FastAPI** + **WebSocket** 기반 대시보드가 지연·플러시 주기·큐 크기, 그리고 CPU/메모리/네트워크 부하 등을 시각화해 운영 가시성을 확보합니다 .
* **프로세스‑안전 종료(Graceful Shutdown)**
  **ShutdownManager**가 `ProcessPoolExecutor`, 열려 있는 파일 핸들, Signal(SIGINT/SIGTERM)을 한곳에서 관리해 중단 시 데이터 손실과 메모리 누수를 예방합니다 .
* **보강 도구**
  ‑ *get\_binance\_chart.py*: 과거 **aggTrades** CSV .zip을 병렬로 내려받아 백필(back‑fill)용 데이터 세트를 구축 .
  ‑ *fs\_to\_html.py*: 리포 지트리 구조를 HTML로 렌더링하여 문서화 자동화 .

---

### 2. 기술적 방법론 (Technical Methodology)

| 서브시스템  | 핵심 기법(영어)                                              | 설명                                                                                                                                                                                |
| ------ | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 실시간 수집 | **asyncio**, **websockets**, back‑pressure **Queue**   | `put_snapshot()` 코루틴이 비동기 소켓으로부터 메시지를 해석‑보정(지연, 계산 오버헤드) 후 심볼별 `asyncio.Queue`에 넣습니다 .                                                                                            |
| 지연 관리  | **statistics.median**, 이벤트 플래그                         | `estimate_latency()`가 심볼별 지연값을 데크(deque)에 쌓아 중앙값을 갱신하고, `gate_streaming_by_latency()`가 두 이벤트(`event_latency_valid`, `event_stream_enable`)를 토글하여 스트림 ON/OFF를 제어합니다 .              |
| 스냅샷 덤프 | 파일 롤오버, **ProcessPoolExecutor**                        | `symbol_dump_snapshot()`이 분 단위 파일을 열고, 롤오버 시 직전 파일을 닫아 \*\*proc\_zip\_n\_remove\_jsonl()\*\*로 압축·삭제, 일자 변경 시 \*\*symbol\_consolidate\_a\_day()\*\*를 별도 프로세스로 호출해 일일 아카이브를 생성합니다 . |
| 모니터링   | **FastAPI**, **WebSocket**, **psutil**                 | `DashboardServer`가 `/dashboard` HTML과 `/ws/dashboard` 소켓을 제공하며, `monitor_hardware()`가 CPU·메모리·디스크·네트워크 메트릭을 주기적으로 업데이트합니다 .                                                       |
| 로깅     | **logging.QueueHandler / QueueListener**, UTC ISO‑8601 | 멀티‑프로세스 안전 로그를 단일 큐에 집계 후 파일(`RotatingFileHandler`)과 콘솔에 동시 출력, 시계열 일관성을 위해 UTC 타임스탬프 사용 .                                                                                        |
| 종료 처리  | **thread‑safe state**, signal hook                     | `ShutdownManager`가 실행 중인 executor와 파일 핸들을 원자적으로 정리하고, 중복 종료를 방지하는 내부 플래그를 유지합니다 .                                                                                                 |
| 구성 관리  | `.conf` 파싱                                             | `init.load_config()`가 모든 파라미터(SYMBOLS, interval, backoff 등)를 로드해 런타임에 주입합니다 .                                                                                                     |

---

#### 종합 정리

이 프로그램은 **네트워크 상태를 실시간 감시하며 지연이 허용 범위 내일 때만** 바이낸스 주문서 스트림을 받아 **고해상도(100 ms) LOB 데이터를 안정적으로 축적**하고, 파일 압축·병합을 통해 저장 효율을 높입니다. 또한 **모니터링 대시보드와 안전한 종료 메커니즘**을 갖춰 24×7 운영이 가능한 **프로덕션급 데이터 인프라**를 목표로 설계되었습니다.
