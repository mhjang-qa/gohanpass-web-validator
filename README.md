# GO Hanpass Web Auto Validator

웹 시나리오 자동 검증 및 QA 리포트 통합 플랫폼입니다.

서버나 클라우드에 배포하면 로컬 PC가 꺼져 있어도 스케줄에 따라 GO Hanpass 웹 시나리오를 실행하고, 실행 결과와 스냅샷을 Notion 리포트로 남깁니다.

## 주요 기능

- 웹 콘솔에서 시나리오 선택 후 즉시 실행
- Asia/Seoul 기준 요일/시간 스케줄 실행
- 실행 중 실시간 로그 자동 갱신
- 실행 중 스냅샷 자동 저장 및 웹 화면 표시
- 시나리오별 PASS/FAIL/N/A 집계
- Notion DB 자동 업로드
- Notion 상세 페이지에 테스트 요약, 테스트 상세 표, 시나리오별 스냅샷 첨부
- Render/Docker 배포 지원

## 로컬 실행

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium chromium-headless-shell
cp .env.example .env
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

접속 URL:

```text
http://127.0.0.1:8080
```

## 환경변수

필수:

```env
NOTION_TOKEN=Notion_Internal_Integration_Secret
NOTION_DB_ID=5ad73fbd195182bcb4b201fb9d76815f
```

권장:

```env
HEADLESS=true
NOTION_UPLOAD=true
TIMEZONE=Asia/Seoul
```

선택:

```env
SCENARIO_DIR=scenarios
```

`SCENARIO_DIR`를 지정하지 않으면 저장소 내부 `scenarios/` 폴더를 사용합니다.

## 시나리오

현재 웹 실행 기준 시나리오:

- `00_web_login.py`: 웹 전용 로그인 시나리오
- `01_login.py`: `00_web_login.py`를 호출하는 호환 wrapper
- `02_home.py`: 홈 화면 주요 기능 검증
- `03_travel.py`: 여행 영역 검증
- `96_full_menu_audit.py`: 전체 메뉴 탐색 검증
- `97_auto_click_payment.py`: 결제 탭 메뉴 검증
- `98_auto_click_travel.py`: 여행 탭 메뉴 검증
- `99_auto_click_main.py`: 메인 화면 클릭 후보 검증

웹 실행 시 모든 주요 시나리오는 공통 로그인 헬퍼를 사용합니다. 로그인 세션이 없거나 `로그인 후 이용해주세요.` 팝업이 발생하면 자동 로그인 후 이어서 진행합니다.

## 웹 콘솔 동작

- 최초 화면에서 시나리오는 기본 미선택 상태입니다.
- 즉시 실행 시 선택한 시나리오는 실행 중에도 체크 상태로 유지됩니다.
- 실행 기록은 2초마다 자동 갱신됩니다.
- 실행 중인 run은 `running` 상태와 강조 테두리로 표시됩니다.
- 스냅샷 간격은 즉시 실행/스케줄 실행에서 각각 설정할 수 있습니다.
- 의미 없는 회색 화면 스냅샷은 저장하지 않고 기존 유효 스냅샷을 유지합니다.

## Notion 리포트

Notion DB 필수/권장 컬럼:

| 컬럼명 | 타입 | 설명 |
| --- | --- | --- |
| 제목 | title | 리포트 제목 |
| 버전 | rich_text | 실행 버전 |
| 플랫폼 | select 또는 rich_text | 실행 플랫폼 |
| PASS | number | PASS 건수 |
| FAIL | number | FAIL 건수 |
| N/ A 또는 N/A | number | N/A 건수 |
| Total | number | 전체 TC 수 |
| 상태 | status 또는 select | 성공/실패 상태 |
| 결과 | rich_text | 요약 결과 |
| 등록일 | date | 등록일 |
| 테스트 결과 | select | 테스트 성공/테스트 실패 |

`테스트 결과` select 옵션:

- `테스트 성공`
- `테스트 실패`

상세 페이지 구성:

- `테스트 요약`: callout 블록, 문장 단위 줄바꿈
- `테스트 상세`: 시나리오별 표
- 표 컬럼: 테스트 항목, 테스트 설명, 결과
- 시나리오별 스냅샷: 각 시나리오 결과 아래 image 블록으로 첨부

## Render 배포

Render Web Service 설정:

- Root Directory: 비움
- Build Command:

```bash
pip install -r requirements.txt && python -m playwright install --with-deps chromium chromium-headless-shell
```

- Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render 환경변수:

```env
NOTION_TOKEN=...
NOTION_DB_ID=5ad73fbd195182bcb4b201fb9d76815f
HEADLESS=true
NOTION_UPLOAD=true
TIMEZONE=Asia/Seoul
```

주의:

- Build Command에서 `playwright install ...`를 직접 호출하지 말고 `python -m playwright install ...`를 사용해야 합니다.
- Render Free Web Service는 요청이 없으면 sleep 상태가 될 수 있습니다. 업무시간 동안 유지하려면 외부 uptime monitor에서 `/` 또는 `/api/runs`를 주기적으로 호출합니다.
- Playwright 안정성이 중요하면 Render native Python보다 Docker 배포가 더 예측 가능합니다.

## Docker 배포

```bash
docker build -t go-hanpass-web-validator .
docker run -d \
  --name go-hanpass-web-validator \
  --env-file .env \
  -p 8080:8080 \
  go-hanpass-web-validator
```

Docker 배포 시에도 저장소 내부 `scenarios/`를 그대로 사용합니다.

## API

- `GET /api/scenarios`: 실행 가능한 시나리오 목록
- `POST /api/runs`: 즉시 실행 시작
- `GET /api/runs`: 최근 실행 기록
- `GET /api/runs/{run_id}`: 특정 실행 상세
- `GET /api/current-run`: 현재 실행 중인 run
- `GET /api/schedule`: 스케줄 조회
- `POST /api/schedule`: 스케줄 저장
- `GET /output/...`: 스냅샷/출력 파일 정적 접근

## 운영 메모

- 외부 공개 시 인증이 없습니다. Render에 공개 배포할 경우 Basic Auth, VPN, 사내망, reverse proxy 인증 중 하나를 붙이는 구성이 필요합니다.
- Notion 업로드 실패는 실행 자체를 failed로 표시합니다.
- 스냅샷 캡처 실패는 테스트 실패로 집계하지 않고 로그에만 짧게 남깁니다.
