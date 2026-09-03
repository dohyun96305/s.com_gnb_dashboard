# S.com GNB Hover 수집 및 대시보드

Samsung 국가별 사이트의 데스크톱 GNB를 hover하여 메뉴 링크와 캡처 이미지를 수집하고, 결과를 Streamlit 대시보드에서 확인 및 배포하는 도구입니다.

현재 사용 파일은 `config.py`, `gnb_explorer.py`, `gnb_dashboard.py`, `urls.csv`입니다. `temp/`는 이전 작업을 보관한 참고용 폴더이며 실행 대상이 아닙니다.

## 빠른 실행

```powershell
# 최초 1회: 라이브러리와 Chromium 준비
python -m pip install playwright streamlit
python -m playwright install chromium

# urls.csv에 등록한 전체 URL 수집
python .\gnb_explorer.py

# 한 국가만 수집
python .\gnb_explorer.py --test sec

# 브라우저를 보면서 수집
python .\gnb_explorer.py --test sec --headed

# 결과 대시보드 실행
python -m streamlit run .\gnb_dashboard.py
```

## 입력 방식

기본 실행은 `urls.csv` 첫 번째 열에서 URL을 읽습니다. 빈 행, `#`으로 시작하는 행, 중복 URL은 제외합니다.

`--test`를 사용하면 CSV 대신 `https://www.samsung.com/{국가코드}/` 한 개만 수집합니다. 국가 코드는 영문 소문자, 숫자, 하이픈으로 구성하며 10자 이하여야 합니다.

```powershell
python .\gnb_explorer.py --test br
python .\gnb_explorer.py --test uk --no-hover-screenshots
python .\gnb_explorer.py --csv .\my_urls.csv --output .\output\capture_gnb
```

주요 옵션:

```text
--test COUNTRY_CODE         지정 국가의 Samsung 홈 URL만 수집
--csv PATH                  수집 대상 CSV 경로
--output PATH               결과 루트 경로 (기본: output/capture_gnb)
--headed                    브라우저 창 표시
--preview-wait MS           각 hover 후 추가 대기 시간
--no-hover-screenshots      hover 캡처를 생략하고 JSON만 저장
--no-translation            DeepL 번역을 생략
--translation-cache PATH    번역 캐시 경로 (기본: output/translation_cache.json)
```

## DeepL 영어 번역

DeepL API Free 키를 Windows 환경 변수에 등록하면, 수집한 메뉴와 hover 항목에 영어 번역을 함께 저장합니다. API 키는 소스 코드나 JSON에 저장되지 않습니다.

```powershell
# 현재 PowerShell 창에서만 적용
$env:DEEPL_API_KEY = "DeepL API Free 키"

# 이후에도 유지하도록 사용자 환경 변수에 등록
[Environment]::SetEnvironmentVariable("DEEPL_API_KEY", "DeepL API Free 키", "User")
```

환경 변수를 새로 등록한 뒤에는 PowerShell을 다시 열고 실행합니다.

번역 캐시는 `output/translation_cache.json`에 저장됩니다. 같은 원문은 다음 국가나 다음 실행에서 API를 다시 호출하지 않습니다. UK와 US 사이트의 영어 원문은 API 호출 없이 그대로 `menuEnglish` 또는 `textEnglish`에 저장됩니다. SEC는 한국어 원문만 저장하며 DeepL 호출과 캐시 저장을 모두 건너뜁니다.

```json
{
  "menu": "주방가전",
  "menuEnglish": "Kitchen Appliances",
  "hoverItems": [
    {
      "text": "냉장고",
      "textEnglish": "Refrigerators",
      "href": "https://www.samsung.com/..."
    }
  ]
}
```

> 주의: 번역은 메뉴명과 짧은 문구를 개별적으로 영어로 옮긴 참고용 결과입니다. 문맥에 따라 표현이 달라질 수 있으므로, 분석·보고서에 사용하기 전 현지 메뉴 의도와 브랜드명·제품명 표기를 직접 확인해야 합니다.

DeepL 키가 없거나 API 요청에 실패해도 GNB 수집과 캡처는 계속 진행됩니다. 해당 실행에서는 원문만 저장됩니다.

번역 처리 후에는 URL별로 다음 로그가 출력됩니다.

```text
[translation] cache-hit=12, cache-saved=8, untranslated=0
```

`cache-hit`은 처리 시작 시 이미 `translation_cache.json`에 있던 고유 원문 수이고, `cache-saved`는 이번 실행에서 새로 캐시에 추가한 문구 수입니다. `untranslated`는 API 키 누락 또는 API 오류 등으로 영어 값을 만들지 못한 고유 원문 수입니다.

## 수집 과정

1. 페이지 진입 후 GNB와 쿠키 동의 UI가 나타날 때까지 대기합니다.
2. 쿠키 배너의 거절 버튼을 우선 탐색하고, 필요하면 배너 및 잔여 오버레이를 숨깁니다.
3. 상단 구조와 위치를 기준으로 데스크톱 GNB 루트를 찾습니다.
4. 최상위 메뉴를 순서대로 hover하고, 열린 패널의 링크와 캡처를 저장합니다.
5. 메뉴와 hover 항목의 영어 번역을 캐시에서 조회하고, 새 문구만 DeepL API Free로 번역합니다.

`href="javascript:void(0)"`처럼 href가 비어 있는 메뉴는 `onclick`의 URL 또는 `openCtaLink(...)` 인자를 확인해 메뉴 링크를 추출합니다.

## 결과 구조

```text
output/
├─ translation_cache.json
└─ capture_gnb/
   └─ {country}/
      └─ {YYYY-MM-DD-HHMM}/
         ├─ {url_slug}_gnb.json
         └─ hover_screenshots/
            └─ {url_slug}_{menu_index}_{menu_name}.jpg
```

국가 폴더명은 URL의 Samsung 경로 코드(`samsung.com/br/`의 `br`, `samsung.com/sec/`의 `sec`)를 사용합니다. 대시보드에서는 대문자로 표시합니다.

## 대시보드 확인

대시보드를 실행하면 사이드바에서 Country와 Date / Run을 선택할 수 있습니다. 상단 메뉴 상자는 국가와 제목 길이에 관계없이 가로 4칸으로 표시되며, 하나를 선택하면 해당 hover 캡처와 수집 링크를 함께 확인할 수 있습니다.

새로 수집한 JSON에 영어 번역이 있으면, 메뉴와 Collected Links의 Text는 원문 다음 줄에 `(English)` 형식으로 표시됩니다. 메뉴 상자와 Collected Links의 행 높이는 고정되며, 긴 문구는 말줄임표와 마우스 오버 툴팁으로 확인할 수 있습니다.

Collected Links의 No 열은 고정입니다. Text와 Link 사이의 헤더 경계를 드래그하면 두 열의 너비만 조절할 수 있습니다. 기존 JSON은 원문만 표시하며 그대로 열 수 있습니다.
