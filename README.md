# 매출 분석 (sales-analysis)

분기·지점별 매출을 입력하고 요약 카드·그래프·표로 보는 Flask + SQLite 웹앱입니다.
기존 단일 HTML 아티팩트(`매출 분석.html`, 브라우저 localStorage 저장)를 서버 DB 저장 방식으로 옮겼습니다.
화면 디자인과 그래프 설정은 아티팩트와 같습니다.

## 로컬 구동

### Windows (PowerShell)
```powershell
cd sales-analysis
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
flask --app app init-db
flask --app app seed        # 예시 데이터 (선택)
flask --app app run --debug
```

> `python`이 Microsoft Store를 열거나 "찾을 수 없음"이 나오면 Python이 PATH에 없는 것입니다.
> 설치 경로로 직접 실행하세요. 예: `& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv`
> `Activate.ps1` 실행이 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 후 다시 시도하세요.

### macOS / Linux
```bash
cd sales-analysis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app app init-db
flask --app app seed
flask --app app run --debug
```

브라우저에서 `http://127.0.0.1:5000` 접속.

### 간단 실행
```powershell
python run.py
```
DB 파일(`instance/sales.db`)이 없으면 테이블을 만들고 예시 데이터 12건을 자동으로 넣습니다.

### 같은 사무실 다른 PC에서 보기
`flask --app app run --host 0.0.0.0` 으로 실행하고 `http://<내 PC IP>:5000` 으로 접속합니다 (방화벽 허용 필요).
정식 배포(Waitress/Gunicorn + 리버스 프록시)는 2차 작업 범위입니다.

## 배포 (Vercel + Supabase)

배포 환경은 파일을 저장할 수 없어 SQLite 대신 **Supabase Postgres**를 씁니다.
환경 변수 `DATABASE_URL`이 있으면 Postgres, 없으면 로컬 SQLite를 씁니다 (`app/db.py`).

| 구성 | 내용 |
|---|---|
| GitHub | 저장소 `261124_KORAIL` — `main`에 push하면 Vercel이 자동 배포 |
| Vercel | 프로젝트 `261124_korail` (Vercel은 이름에 대문자를 허용하지 않음), 서울(icn1) 리전. 진입점 `api/index.py`, 라우팅 `vercel.json` |
| Supabase | 프로젝트 `261124_KORAIL`, 서울(ap-northeast-2). 테이블은 `supabase/migrations/` |

- Vercel 환경 변수: `DATABASE_URL`(Supabase 트랜잭션 풀러, 포트 6543), `SECRET_KEY`
- 테이블 변경: `supabase/migrations/`에 SQL 추가 → `supabase db push --remote`
- 운영 DB에 예시 데이터 넣기: `DATABASE_URL`을 설정한 셸에서 `flask --app app seed`
- 데이터 변경 로그는 파일 대신 Vercel 로그(`vercel logs`)에 남습니다.
- Supabase 공개 REST API로 테이블에 접근하지 못하도록 RLS를 켜 두었습니다 (정책 없음).

> ⚠️ 1차 범위라 로그인이 없습니다. 배포 주소를 아는 사람은 누구나 데이터를 수정·초기화할 수 있습니다.

## 테스트
```powershell
pytest -q
```

## 기능
- 입력: 폼 1건, CSV 붙여넣기 / CSV 파일 업로드(UTF-8 또는 엑셀 기본 저장 형식 cp949, 1MB·5,000행 제한)
- 같은 분기+지점은 새 행 대신 값 갱신 (DB `UNIQUE(quarter, branch_id)`)
- 표: 열 정렬, 행 수정·삭제, 합계 행, 객단가
- 그래프 4종: 분기별 매출 추이, 지점별 매출 비교, 고객 수 비중, 객단가 추이
- 필터(분기·지점) → 요약/표/그래프 동시 반영. 필터 상태는 개인 설정으로 브라우저에 저장
- 예시 데이터 지우기, 데이터 초기화, 되돌리기(최근 10단계까지)
- 내보내기: CSV(UTF-8 BOM, 4열 — 그대로 다시 일괄 입력 가능), 엑셀(.xlsx, 객단가·합계 행·`#,##0` 서식)
- 지점 색 고정: 지점마다 색 번호(0~7)를 DB에 저장
- 데이터 변경 로그: `logs/app.log`
- 오프라인 동작: Chart.js 4.4.1을 `app/static/vendor/chart.umd.js`에 포함

### 글꼴
인터넷 없이 동작하도록 웹 글꼴을 내려받지 않습니다. PC에 Outfit / Noto Sans KR이 설치돼 있으면 그 글꼴을,
없으면 맑은 고딕(Windows)·Apple SD Gothic Neo(macOS)를 씁니다.
웹 글꼴을 쓰려면 `app/static/vendor/fonts/`에 woff2 파일을 두고 `style.css`에 `@font-face`를 추가하세요.

## 구조
```
app/
  __init__.py   앱 팩토리, 로깅, 오류 처리
  config.py     설정 (.env 읽음)
  db.py         SQLite 연결, init-db / seed 명령
  schema.sql    테이블
  seed.py       예시 데이터
  validators.py 입력 검증 (app.js와 같은 규칙)
  services.py   upsert, 요약, 그래프 데이터, 스냅샷/되돌리기, CSV, 내보내기
  api.py        /api/* JSON API
  views.py      / 화면
  templates/    base.html, index.html, error.html
  static/       css/style.css, js/app.js, vendor/chart.umd.js
tests/          pytest
run.py          python run.py 실행
```

## API 요약
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/branches` | 지점 목록 + 색 번호 |
| GET | `/api/quarters` | 데이터가 있는 분기 목록 |
| GET | `/api/sales` | 매출 목록 (`quarter`, `branches=1,3`, `sort`, `dir`) |
| POST | `/api/sales` | 1건 추가 (있으면 갱신: 201 추가 / 200 갱신) |
| PUT | `/api/sales/<id>` | 1건 수정 (분기·지점이 다른 행과 겹치면 409) |
| DELETE | `/api/sales/<id>` | 1건 삭제 |
| POST | `/api/sales/import` | CSV 일괄 입력 (`{csv}` 또는 multipart `file`) |
| DELETE | `/api/sales/sample` | 예시 데이터만 삭제 |
| POST | `/api/reset` | 전체 삭제 (`{"confirm":"RESET"}`) |
| POST | `/api/undo` | 직전 상태로 되돌리기 |
| GET | `/api/summary` | 요약 카드 수치 |
| GET | `/api/chart-data` | 그래프 데이터 (`bar_quarter`) |
| GET | `/api/status` | 예시 데이터 수, 되돌리기 가능 횟수 |
| GET | `/api/export.csv`, `/api/export.xlsx` | 현재 필터 기준 내보내기 |

오류 응답: `{"ok": false, "error": "한글 메시지", "field": "quarter"}`
