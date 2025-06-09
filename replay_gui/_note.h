
마지막 박스의 내용물:
- 바디 필로우
- 고중량 이불

---

Certain items that I may leave or give away:

	1) Matratze
	2) Mikrowelle
	3) Kunststoffkorb x2
	4) Klappbarer Tisch

You can tell me which item belongs to which
category of the following:

	1) leave it at the room for the next tenant
	2) give away to any others

---

	I have thoroughly cleaned the entire room
to the best of my ability. Naturally, it may
not look as fresh as newly renovated.

	Just as a small personal suggestion:
If you consider refreshing the room for future
tenants, it might be helpful to partially repaint
a few small areas on the walls (less than 2% of
the total wall surface).

---

























































| 항목						| 설명												|
|---------------------------|---------------------------------------------------|
| 과거 시계열 길이				| 60분 (past LOB + OHLCV features 포함)				|
| 데이터 frequency*			| 1분 (1-minute candle / LOB snapshot 기준 시계열)	|
| 포지션 진입 가능한 최소 단위	| 매 1분 (minute-level MDP 기반 의사결정 및 포지션 조정)	|
* 1분 단위 LOB snapshot은 너무 sampling frequency가 낮아 많은 정보가 소실된다.

🧠 마하세븐식 관점에서의 비판
| 관점                        | 설명                                                                                |
| ------------------------- | --------------------------------------------------------------------------------- |
| 🕒 **Sampling frequency** | 마하세븐은 **틱 단위**, 심하면 **10ms \~ 100ms** 수준의 체결강도, 잔량변화, 스프레드 변화를 실시간으로 추적합니다.       |
| 📉 **시장 반응속도**            | 실전 단타의 핵심은 **호가 변화의 미세한 '심리' 반응을 빠르게 읽고 대응**하는 것이며, 1분 단위 snapshot은 이미 **과거**입니다. |
| 🔍 **데이터 압축 손실**          | 1분으로 sampling하면 **중간 체결 흐름, 주문취소, 체결강도 증가** 등의 중요한 정보를 잃습니다.                      |
| 💡 **유동성 흐름 추적**          | 마하세븐은 '잔량 소멸 후 재적재' 같은 **유동성 페이크/진짜 여부**를 보고 베팅합니다. 이는 1분 데이터에선 절대 안 보입니다.        |

---
