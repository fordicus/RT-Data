import requests
import re
from collections import defaultdict
from functools import reduce

REQUIREMENTS_FILE = "requirements.txt"

def parse_requirements(file_path):
    pattern = re.compile(r"([a-zA-Z0-9_\-]+)==([^\s]+)")
    with open(file_path, "r") as f:
        lines = f.readlines()
    return [pattern.match(line.strip()).groups() for line in lines if pattern.match(line.strip())]

def get_supported_versions(pkg_name, version):
    url = f"https://pypi.org/pypi/{pkg_name}/{version}/json"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        classifiers = data["info"].get("classifiers", [])
        versions = {
            cls.split("::")[-1].strip()
            for cls in classifiers
            if cls.strip().startswith("Programming Language :: Python ::")
        }
        # 필터: "X.Y" 형태만 유지
        clean_versions = sorted([v for v in versions if re.fullmatch(r"\d+\.\d+", v)])
        return clean_versions
    except Exception as e:
        print(f"[!] Error fetching {pkg_name}=={version}: {e}")
        return []

def main():
    reqs = parse_requirements(REQUIREMENTS_FILE)
    support_map = defaultdict(list)

    print(f"\n📦 Parsing {REQUIREMENTS_FILE} ...")
    for pkg, ver in reqs:
        versions = get_supported_versions(pkg, ver)
        support_map[pkg] = versions
        print(f"  - {pkg}=={ver} supports: {', '.join(versions) if versions else 'N/A'}")

    # 교집합 계산: N/A (빈 리스트) 무시
    non_empty_support = [v for v in support_map.values() if v]
    if not non_empty_support:
        print("\n⚠️ No version info found for any package.")
        return

    common = reduce(lambda a, b: list(set(a) & set(b)), non_empty_support)
    common_sorted = sorted(common, key=lambda v: list(map(int, v.split("."))))

    print("\n✅ Common supported Python versions (excluding N/A packages):")
    print("   →", ", ".join(common_sorted) if common_sorted else "⚠️ No common version found.")

if __name__ == "__main__":
    main()
