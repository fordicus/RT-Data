### ✅ TODO

1. **Post Mobile 메일 확인 & 안드레아**

   * 받은 편지함에서 Post Mobile 관련 메일 확인하기

2. **대시보드 주요 지표 파악 및 이상 감지 알림 설정**

   * 대시보드에서 가장 중요한 지표 식별
   * 해당 지표에 문제가 발생하면 Telegram으로 자동 알림 전송 설정

3. **성능 프로파일링 (Before & After)**

   * Stream을 구독할 Binance symbol 목록 확장
   * **(Before)**: 기존 코드 상태에서 1시간 동안 성능 프로파일링 데이터 수집
   * 성능 향상 아이디어를 코드에 통합
   * **(After)**: 수정된 코드에서 다시 1시간 동안 성능 프로파일링 데이터 수집

4. **UptimeRobot 설정**

   * UptimeRobot이 대시보드 상태만 모니터링하도록 설정

5. **대시보드 외부 공개**

   * 현재 대시보드를 외부에서 접근 가능하도록 노출 설정

6. **홈서버 관리 가이드 통합 (RT-Data 저장소)**

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
