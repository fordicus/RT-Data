# TODO

> 이제 stream을 구독할 Binance symbol들도 확장을 고려해보세요.

---
## 성능 최적화 염두에 둘 것
> 현재 단계에서는 `uvloop`를 적용하지 않지만, 추후 포팅 가능성을 염두에 두고 설계를 유연하게 유지합니다.  
> 데이터 직렬화/역직렬화에 `orjson`을 사용할 수 있도록 준비합니다.
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