import os
from pathlib import Path


def load_symbols_manual(conf_path: str) -> list[str]:
    symbols = []
    with open(conf_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 빈 줄이나 주석(#)은 건너뛰기
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # SYMBOLS=... 부분 찾기 (대소문자 구분 필요 시 line.startswith('SYMBOLS'))
            if line.upper().startswith('SYMBOLS'):
                # "SYMBOLS =" 분리
                _, value = line.split('=', 1)
                # 쉼표로 나누고, 공백 제거
                symbols = [s.strip() for s in value.split(',') if s.strip()]
                break
    return symbols

symbols = load_symbols_manual('get_bybit_chart_dom.conf')

# 1) 가져오고 싶은 폴더 경로 지정
mother_directory = r'C:\workspace\RT-Data\data\from_2025-05-10_to_2025-06-17'
mother_path = Path(mother_directory)

# 2) os.listdir() 함수로 폴더 내 항목(파일·폴더) 이름 리스트 얻기
all_items = os.listdir(mother_directory)

# 3) 파일만 골라내기 (폴더는 제외)
file_names = [f for f in all_items if os.path.isfile(os.path.join(mother_directory, f))]

dict_symbols_cnt  = {sym: 0 for sym in symbols}
dict_symbols_size = {sym: 0 for sym in symbols}

def format_size(bytes_: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_ < 1024:
            return f"{bytes_:.2f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.2f} PB"
	
# Define Patterns

ob_ext = 'ob200.data.zip'	# order book
ex_ext = '.csv.gz'			# execution chart

for s in symbols:
	
	for f in file_names:
		
		ob_sym = '_' + s + '_'
		ex_sym = s + '_'
		
		if (((ob_sym in f) and (ob_ext in f)) or 
			((f.startswith(ex_sym)) and (ex_ext in f))):
		
			dict_symbols_cnt[s] += 1	# count the symbol's occurrance as file
			
			abs_path = mother_path / f
			
			byte_sz = os.path.getsize(abs_path)		# get the file size in byte
			
			dict_symbols_size[s] += byte_sz			# accumulate the total file size
			
dict_symbols_size = dict(
	sorted(dict_symbols_size.items(), key=lambda x: x[1], reverse=True)
)
			
for sym in dict_symbols_size:
	
	print(f"{sym:<10} {dict_symbols_cnt[sym]}: {format_size(dict_symbols_size[sym])}")

