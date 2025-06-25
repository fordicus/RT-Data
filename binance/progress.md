목표는 다음과 같이 요약됩니다:

> **Binance Spot 시장의 L2 DOM 데이터를 가능한 빠르게 스트리밍해서, 실시간으로 로컬에 저장하는 파이프라인을 구축**하는 것.

---

## ✅ 전체 아키텍처 계획

### 📍 1단계: WebSocket 스트림 설정 (Binance Spot)

* ✅ **목표**: 가장 빠른 빈도 (`100ms`)로 Binance L2 DOM 데이터를 받는다.
* ✅ **대상 API**:
  `wss://stream.binance.com:9443/ws/<symbol>@depth@100ms`

  예시: `btcusdt@depth@100ms`
  (최대 20 bid + 20 ask 레벨 포함됨)

---

### 📍 2단계: 실시간 데이터 수신 구현

* ✅ **목표**: Python WebSocket 클라이언트를 사용하여 스트림으로부터 L2 DOM 이벤트를 수신
* ⛏️ 기술: `websockets`, `aiohttp`, 또는 `websocket-client` 등

---

### 📍 3단계: 수신된 데이터를 로컬 디스크에 실시간으로 저장

* ✅ **목표**: tick 단위 데이터 (`event time`, `bids`, `asks`)를 NDJSON 또는 compressed format으로 저장
* 💾 옵션:

  * `NDJSON`: line-delimited JSON, 실시간 append에 적합
  * `gzip + JSONL`: 하루 단위 압축 파일 (e.g., `2025-06-25_BTCUSDT_dom.jsonl.gz`)

---

### 📍 4단계: 에러/연결 끊김 대비

* ✅ **목표**: reconnect 로직 포함

  * `ping/pong` 응답
  * reconnect backoff
  * corrupted file 회피 (atomic flush)

---

### 📍 5단계: 멀티심볼 확장

* ✅ **목표**: `btcusdt`, `ethusdt`, `solusdt` 등 여러 심볼에 대해 동시에 스트리밍
* 📦 구현 전략:

  * 각 symbol별 stream 생성 or
  * `stream?streams=btcusdt@depth@100ms/ethusdt@depth@100ms` 식으로 multiplex stream

---

### 📍 6단계: 하루 단위 자동 롤링 파일 저장

* ✅ **목표**: UTC 기준 하루마다 새로운 파일 생성
* 📂 예시:

  ```
  data/
  ├── BTCUSDT/
  │   ├── 2025-06-25_dom.jsonl.gz
  │   └── 2025-06-26_dom.jsonl.gz
  └── ETHUSDT/
      └── ...
  ```

---

## 1️⃣ WebSocket 구독(spot market data)이 24시간 뒤에 종료되는 문제

### A. 원인

* Binance **User Data Stream**(계정/계좌 관련 이벤트 스트림)은 listenKey 기반으로, 기본 만료가 24시간입니다.
* 반면 **Market Data Stream**(depth, trade 등)은 공식 문서상 만료 시간이 명시되어 있지 않지만, 네트워크 이슈나 방화벽, 서버 정책에 의해 연결이 끊어질 수 있습니다.
* 특히 사용자 환경에 따라 24시간 이상 장시간 무중단 연결이 불안정할 수 있습니다.

> **참고 문서**
> • User Data Stream 만료: [https://binance-docs.github.io/apidocs/spot/en/#user-data-streams](https://binance-docs.github.io/apidocs/spot/en/#user-data-streams) (listenKey는 24시간 후 만료, 연장 필요)&#x20;
> • Market Data Stream 연결 안정성: [https://binance-docs.github.io/apidocs/spot/en/#diff-depth-stream](https://binance-docs.github.io/apidocs/spot/en/#diff-depth-stream) (ping/pong, 재접속 권장)&#x20;

---

### B. 해결책 제안

| 방법                             | 설명                                                                          | 장단점                                           |
| ------------------------------ | --------------------------------------------------------------------------- | --------------------------------------------- |
| **1. 자동 재연결 로직**               | 클라이언트 차원에서 `on_close` 이벤트 감지 시 즉시 재접속 및 재구독                                 | • 구현 간단<br>• 끊김 최소화<br>• 코드 복잡도 약간 증가         |
| **2. 23시간 50분 주기 재시작**         | 매일 UTC+0 자정 이후(예: 00:00:00)에 애플리케이션 재시작<br>→ 초기 REST 스냅샷 + WebSocket 재구독    | • 하루치 완전 초기화<br>• 역사 일관성 보장<br>• 운영 스케줄 관리 필요 |
| **3. 외부 프로세스 감독 (Supervisor)** | systemd, Docker Healthcheck, Kubernetes Liveness Probe 등으로<br>24시간마다 자동 재시작 | • 인프라 기반 자동화<br>• 애플리케이션 변경 불필요<br>• 인프라 의존 ↑ |
| **4. 이중화 연결**                  | 2개 이상의 WS 연결을 시차를 두고 유지<br>하나 끊기면 다른 하나로 페일오버                               | • 가용성 ↑<br>• 자원 소비 ↑                          |

**추천**: 우선은 **① 자동 재연결 + ping/pong 처리**를 구현하고,
운영 환경에서 끊김 빈도가 높으면 **② 23h 50m 주기 재시작** 방식을 추가하는 방식이 가장 깔끔합니다.

---

## 2️⃣ 30개 심볼 동시 스트리밍 최적화 방안

ByBit처럼 30개 심볼을 매일 끊김 없이 받으려면, Binance Spot API에서는 다음 두 가지 옵션이 있습니다.

| 옵션                     | 설명                                                                                                                                  | 문서 링크                                                                     |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **A. Combined Stream** | 하나의 WebSocket 연결로 여러 심볼 스트림을 병합하여 받아옴<br>`wss://stream.binance.com:9443/stream?streams=BTCUSDT@depth@100ms/ETHUSDT@depth@100ms/...` | • 지원 최대 스트림 수: 충분히 30개 이상 가능<br>• 연결 수 절감<br>• 에러·재연결 관리 용이               |
| **B. 멀티플 연결**          | 심볼 그룹(예: 10개씩)으로 나누어 별도 WS 연결 생성                                                                                                    | • Combined 스트림 사용 불가 시 대체<br>• 병렬 처리로 지연 최소화<br>• 연결 수 제한 주의(300 req/5분)  |

> **Combined Stream 예시**
>
> ```text
> wss://stream.binance.com:9443/stream?streams=
>   btcusdt@depth@100ms/
>   ethusdt@depth@100ms/
>   solusdt@depth@100ms/
>   … (총 30개 심볼)
> ```
>
> → 한 연결에서 모든 `depth@100ms` diff 이벤트 수신 가능&#x20;

### A vs. B 비교

| 항목     | Combined Stream          | 멀티플 연결                         |
| ------ | ------------------------ | ------------------------------ |
| 연결 관리  | 1개 연결<br>→ 재접속 로직 1개만 필요 | N개 연결<br>→ 각각 재접속 필요           |
| API 제약 | IP 당 300개 연결/5분 제한 없음    | 연결당 제한<300 req/5min (신규 구독) 고려 |
| 리소스 사용 | 네트워크 소켓 1개               | 소켓 N개, 스레드/이벤트 루프..            |
| 장애 대응  | 연결 하나 오류 시 전체 영향         | 한 그룹만 영향, 나머지 유지               |

**추천**: **Combined Stream**을 우선 사용하시고,

* 연결이 끊기면 자동 재연결 로직으로 복구
* 24시간 주기 재시작 전략을 병행
  … 이렇게 구성하시면 **30심볼, 100 ms 빈도로 무중단 수집**이 가능합니다.

---

