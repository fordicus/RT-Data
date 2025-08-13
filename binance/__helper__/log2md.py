#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
log2md.py — ANSI-colored Linux 로그를 Markdown(.md)로 변환
- ANSI SGR(escape sequence) → <span style="color:..."> 로 치환
- 줄 끝의 두 칸 공백("  ") 포함, 모든 공백/개행 보존
- 결과를 <pre>...</pre> 블록으로 감싸 Markdown 렌더러에서 색상/공백 유지
Usage:
    python log2md.py /absolute/path/to/your.log
    # 결과: /absolute/path/to/your.md
"""
from __future__ import annotations
import argparse
import html
import re
from pathlib import Path

ESC = "\x1b"
SGR_RE = re.compile(r"\x1b\[((?:\d+;)*\d+)m")

# 256-color (38;5;n)에서 자주 쓰는 코드만 정확 매핑 (요청 사양 1:1)
PALETTE_256_TO_HEX = {
    242: "#6c6c6c",  # cool gray (approx for 242)
    34:  "#00af00",  # green (approx for 34)
    214: "#ffaf00",  # orange
    196: "#ff0000",  # bright red
    199: "#ff005f",  # magenta red
}

# 기본 8색 (30–37) → HEX
BASIC_30_37 = {
    30: "#000000",  # black
    31: "#ff0000",  # red
    32: "#00ff00",  # green
    33: "#ffff00",  # yellow
    34: "#0000ff",  # blue
    35: "#ff00ff",  # magenta
    36: "#00ffff",  # cyan
    37: "#ffffff",  # white
}

RESET_CODES = {0}  # SGR reset

def _open_span(color_hex: str) -> str:
    return f'<span style="color:{color_hex}">'

def _close_span() -> str:
    return "</span>"

def _params_to_color_hex(params: list[int]) -> str | None:
    """
    지원:
      - 38;5;N (256-color)  → 일부 코드만 정확 매핑 (요청 셋)
      - 38;2;R;G;B (truecolor)
      - 30–37 (basic 8-color)
    그 외 코드는 색상 미변경(None).
    """
    if not params:
        return None

    # Truecolor: 38;2;R;G;B
    if len(params) >= 5 and params[0] == 38 and params[1] == 2:
        r, g, b = params[2], params[3], params[4]
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f"#{r:02x}{g:02x}{b:02x}"

    # 256-color: 38;5;N
    if len(params) >= 3 and params[0] == 38 and params[1] == 5:
        n = params[2]
        if n in PALETTE_256_TO_HEX:
            return PALETTE_256_TO_HEX[n]
        # 미지정 코드는 색상 미적용 (요청된 매핑 범위만 강제 1:1)
        return None

    # Basic 8 colors: 30–37
    if len(params) == 1 and params[0] in BASIC_30_37:
        return BASIC_30_37[params[0]]

    return None

def ansi_line_to_html(line: str) -> str:
    """
    ANSI 컬러 시퀀스를 HTML <span>으로 치환하고,
    라인 끝에서 열린 span을 닫는다.
    HTML 특수문자는 안전하게 escape.
    """
    out_parts = []
    last = 0
    open_span = False

    for m in SGR_RE.finditer(line):
        # 앞쪽 일반 텍스트 출력 (escape 필요)
        segment = line[last:m.start()]
        if segment:
            out_parts.append(html.escape(segment))
        last = m.end()

        # SGR 파라미터 해석
        params = [int(p) for p in m.group(1).split(";") if p]
        # reset?
        if any(p in RESET_CODES for p in params):
            if open_span:
                out_parts.append(_close_span())
                open_span = False
            # reset은 별도 텍스트 없음
            continue

        color_hex = _params_to_color_hex(params)
        if color_hex:
            # 새 color 적용 전, 기존 span 닫기
            if open_span:
                out_parts.append(_close_span())
            out_parts.append(_open_span(color_hex))
            open_span = True
        # 지원 외 SGR은 무시 (텍스트 변화 없음)

    # 남은 꼬리 텍스트
    tail = line[last:]
    if tail:
        out_parts.append(html.escape(tail))

    # 라인 종료 시 열린 span 정리
    if open_span:
        out_parts.append(_close_span())
        open_span = False

    return "".join(out_parts)

def convert_file_to_md(input_path: Path) -> Path:
    output_path = input_path.with_suffix(".md")
    with input_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # <pre> 블록으로 감싸서 공백/개행/두 칸 공백을 그대로 보존
    html_lines = [ansi_line_to_html(line.rstrip("\n")) for line in lines]
    content = "<pre>\n" + "\n".join(html_lines) + "\n</pre>\n"

    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    return output_path

def main():
    ap = argparse.ArgumentParser(description="ANSI-colored log → Markdown(.md) converter")
    ap.add_argument("input", type=str, help="Absolute path to input log file")
    args = ap.parse_args()
    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"input not found: {src}")
    dst = convert_file_to_md(src)
    print(f"Saved: {dst}")

if __name__ == "__main__":
    main()
