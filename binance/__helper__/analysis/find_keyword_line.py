# find_keyword_line.py
#———————————————————————————————————————————————————————————————————————————————
# Usage:
#   python find_keyword_line.py "/path/to/file.log" "keyword"
#   python find_keyword_line.py "/path/to/file.log" "keyword" -i
#———————————————————————————————————————————————————————————————————————————————

import sys
import argparse
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser(
        description="파일을 라인 단위로 스캔해서 키워드가 포함된 모든 라인을 "
                    "카운터(%5d), 라인번호와 함께 출력합니다."
    )
    p.add_argument("file", help="읽을 파일의 절대경로 (absolute path)")
    p.add_argument("keyword", help="찾을 키워드 (keyword)")
    p.add_argument("-i", "--ignore-case", action="store_true",
                   help="대소문자 무시 (case-insensitive)")
    return p.parse_args()

def main():
    args = parse_args()

    file_path = Path(args.file).expanduser().resolve()
    keyword = args.keyword

    if not file_path.is_file():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        sys.exit(1)

    # 대소문자 무시 설정
    keyword_cmp = keyword.lower() if args.ignore_case else keyword

    matches = []
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            counter = 0
            for line_num, line in enumerate(f, start=1):
                hay = line.lower() if args.ignore_case else line
                if keyword_cmp in hay:
                    counter += 1
                    # %5d 포맷 카운터 + 라인번호 + 원문
                    print(f"{counter:5d}: {line_num}: {line.rstrip()}")
                    matches.append(line_num)
    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)

    if matches:
        print(f"\ncount: {len(matches)}")
        sys.exit(0)
    else:
        print("키워드를 찾을 수 없습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()
