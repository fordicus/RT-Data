# 2025-07-03

이해를 돕기 위해 아래 문서를 참고 자료로 제공한다:
- `BOLT_Project_2025-07-03.pdf`
- `stream_binance.py`
- `RULESET.md`
- `RULESET-ABSOLUTE.md`

나는 현재 `BOLT_Project_2025-07-03.pdf`에 개략적으로 서술된 BOLT 프로젝트를 진행 중이다.

오늘의 주요 목표는 `stream_binance.py` 스크립트의 작동 원리와 구조를 상세히 이해하는 것이다.  
이 스크립트는 Binance의 Level 2 DOM 데이터를 실시간으로 수집하기 위해 개발되었으며,  
현재 Binance에서는 해당 데이터를 streaming 방식으로만 제공하고 있기 때문에, 별도의 수집 스크립트가 필요하다.

Bybit는 일정 구간의 Execution Chart 및 DOM Data를 다운로드할 수 있지만,  
Binance는 streaming 방식이므로 차별화된 접근이 요구된다.

`stream_binance.py`는 대부분 ChatGPT의 도움으로 작성되었기 때문에,  
현재 나는 이 코드의 내부 구조와 세부 로직을 완전히 이해하지 못한 상태이다.

또한, AI 협업 시 따라야 할 가이드라인이 `RULESET.md` 및 `RULESET-ABSOLUTE.md`에 명시되어 있으니,  
이를 기반으로 일관된 방식으로 반응해주기를 바란다.

이제, 위의 파일들을 기반으로 `stream_binance.py`의 구조와 내용을 분석하고,  
내가 완전히 이해할 수 있도록 도와줄 수 있겠니?

---

