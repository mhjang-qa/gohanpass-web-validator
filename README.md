# GO Hanpass Web Auto Validator

웹 시나리오 자동 검증 및 QA 리포트 통합 플랫폼입니다.

서버나 클라우드에 배포하면 로컬 PC가 꺼져 있어도 스케줄에 따라 GO Hanpass 웹 시나리오를 실행하고, 실행 결과와 스냅샷을 Notion 리포트로 남깁니다.

직접 URL로 접속하면 기존 로그인 화면이 유지되며, `GO Hanpass QA Console`에서 signed launch URL로 진입한 경우에만 로그인 화면을 건너뜁니다.

## 주요 기능

- 웹 콘솔에서 시나리오 선택 후 즉시 실행
- Asia/Seoul 기준 요일/시간 스케줄 실행
- 실행 중 실시간 로그 자동 갱신
- 실행 중 스냅샷 자동 저장 및 웹 화면 표시
- 시나리오별 PASS/FAIL/N/A/ERROR 집계
- 웹 UI 시나리오와 API 검증 시나리오 통합 실행
- Notion DB 자동 업로드
- Notion 업로드 성공 후 Slack 간단 알림 전송
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
SLACK_WEBHOOK_URL=
SESSION_SECRET=<validator session secret>
VALIDATOR_USER=qa
VALIDATOR_PASSWORD=qa
QA_CONSOLE_SHARED_SECRET=<console-child 공통 랜덤 문자열>
QA_CONSOLE_ALLOWED_ORIGIN=https://gohanpass-qa-console.onrender.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=none
```

선택:

```env
SCENARIO_DIR=scenarios
API_BASE_URL=https://go.hanpass.com
API_TIMEOUT_SECONDS=15
API_TOKEN=
API_HEADERS={}
RESULT_DASHBOARD_URL=
```

`SCENARIO_DIR`를 지정하지 않으면 저장소 내부 `scenarios/` 폴더를 사용합니다.

API 검증 환경변수:

- `API_BASE_URL`: API 검증 요청의 기준 URL입니다.
- `API_TIMEOUT_SECONDS`: API 요청 타임아웃입니다.
- `API_TOKEN`: Bearer 토큰이 필요한 API 검증 시 사용합니다.
- `API_HEADERS`: 추가 헤더를 JSON object 문자열로 지정합니다. 예: `{"X-Client":"qa"}`

민감정보는 `.env`에만 설정하고 시나리오 파일에는 하드코딩하지 않습니다.

Slack 알림:

- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL입니다. 값이 없으면 알림만 생략되고 테스트/Notion 업로드 결과에는 영향을 주지 않습니다.
- 대상 채널: `#slice_gh-test`
- Slack App: `GO 한패스 QA 봇`
- Slack 알림은 Notion 업로드가 성공한 이후에만 전송됩니다.
- 메시지 항목은 테스트 완료 여부, 실패 건수, 결과 링크만 포함합니다.
- 결과 링크는 Notion 페이지 URL을 우선 사용하고, 없을 경우 `RESULT_DASHBOARD_URL`, `PUBLIC_BASE_URL`, `RENDER_EXTERNAL_URL` 순서로 대체합니다.

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

API 검증 시나리오:

- `10_api_health_check.py`: 기준 URL health/root 응답 검증
- `11_api_home_check.py`: home endpoint 응답 검증
- `12_api_travel_check.py`: travel endpoint 응답 검증

API 시나리오는 파일명과 시나리오 메타데이터 기준으로 `api` 타입으로 노출됩니다. `/api/scenarios` 응답에는 웹/API 타입이 함께 포함되며, 웹 콘솔에서도 API 시나리오를 선택해 즉시 실행 또는 스케줄 실행할 수 있습니다.

`01_login.py`는 기존 호환 wrapper 용도로 보존되며 신규 실행 목록에서는 기존 정책대로 제외됩니다.

## 판정 기준

웹 UI 시나리오:

- 기존 시나리오가 반환하는 `PASS`, `FAIL (...)`, `N/A (...)` 결과를 그대로 집계합니다.
- 시나리오 실행 중 예외가 발생하면 `FAIL`로 집계합니다.

API 검증 시나리오:

- HTTP `200`: `PASS`
- HTTP `400`: `FAIL`
- HTTP `401`, `403`: `ERROR`
- HTTP `404`: `FAIL`
- HTTP `500` 이상: `ERROR`
- 그 외 `4xx`: `FAIL`
- 그 외 예상하지 못한 status code 또는 요청 예외/타임아웃: `ERROR`

각 API 검증 결과에는 `endpoint`, `method`, `status_code`, `result`, `reason`이 저장됩니다. API 검증은 화면 스냅샷이 없을 수 있으므로 스냅샷 첨부는 선택 사항입니다.

## 웹 콘솔 동작

- 최초 화면에서 시나리오는 기본 미선택 상태입니다.
- 즉시 실행 시 선택한 시나리오는 실행 중에도 체크 상태로 유지됩니다.
- 실행 기록은 2초마다 자동 갱신됩니다.
- 실행 중인 run은 `running` 상태와 강조 테두리로 표시됩니다.
- 스냅샷 간격은 즉시 실행/스케줄 실행에서 각각 설정할 수 있습니다.
- 의미 없는 회색 화면 스냅샷은 저장하지 않고 기존 유효 스냅샷을 유지합니다.
- 직접 URL 진입 시에는 수동 로그인 화면이 표시됩니다.
- QA Console에서 `/sso/launch`로 진입한 경우에만 토큰 검증 후 자동 로그인 상태가 저장됩니다.
- QA Console 로그아웃 시 `/sso/logout`이 호출되어 저장된 인증 상태와 iframe/window context가 함께 초기화됩니다.

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
| 등록일 | date 또는 created_time | 등록일. created_time은 Notion이 자동 입력 |
| 테스트 결과 | select | 테스트 성공/테스트 실패 |

`테스트 결과` select 옵션:

- `테스트 성공`
- `테스트 실패`

상세 페이지 구성:

- `테스트 요약`: callout 블록, 문장 단위 줄바꿈
- `테스트 상세`: 시나리오별 표
- 표 컬럼: 테스트 항목, 테스트 설명, 결과
- 시나리오별 스냅샷: 웹 시나리오는 결과 표 오른쪽 컬럼에 배치, API 시나리오는 별도 스냅샷 없음

API 검증 결과도 같은 실행 리포트에 포함됩니다. API 시나리오의 상세 표에는 테스트 항목, Method, Endpoint, Status Code, 결과, 실패 사유가 표시됩니다. Notion DB의 기존 `PASS`, `FAIL`, `N/A`, `Total` 컬럼 형식은 유지하며, `ERROR`는 상세 페이지 요약과 결과 텍스트에 함께 표시됩니다.

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
SESSION_SECRET=<validator session secret>
VALIDATOR_USER=qa
VALIDATOR_PASSWORD=<운영 비밀번호>
QA_CONSOLE_SHARED_SECRET=<console-child 공통 랜덤 문자열>
QA_CONSOLE_ALLOWED_ORIGIN=https://gohanpass-qa-console.onrender.com
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=none
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
