# GO Hanpass Web Auto Validator

웹 기반 자동화 실행기입니다. 로컬 GUI와 달리 서버나 클라우드에 배포하면 PC가 꺼져 있어도 스케줄에 따라 실행할 수 있습니다.

## 실행

```bash
cd "web-auto-vaildator(go-hanpass)"
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium chromium-headless-shell
cp .env.example .env
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

브라우저에서 `http://127.0.0.1:8080` 접속.

## PC가 꺼져도 실행하는 방식

이 앱은 항상 켜져 있는 환경에서 실행되어야 합니다.

1. 클라우드 VM/서버: AWS EC2, GCP Compute Engine, Oracle Cloud, 사내 서버.
2. PaaS/컨테이너: Render, Fly.io, Railway 같은 Playwright 지원 런타임.
3. GitHub Actions 스케줄: UI는 없지만 정해진 시간에 CLI 실행 가능.

운영 기준으로는 VM 또는 컨테이너 배포가 가장 단순합니다. 서버가 켜져 있으면 웹 UI, API, 스케줄러가 계속 동작합니다.

## Docker 배포

```bash
docker build -t go-hanpass-web-validator .
docker run -d \
  --name go-hanpass-web-validator \
  --env-file .env \
  -p 8080:8080 \
  go-hanpass-web-validator
```

주의: Docker 배포 시 `SCENARIO_DIR`에 접근 가능한 위치로 시나리오 파일을 포함하거나 볼륨 마운트해야 합니다. 클라우드 VM에서는 이 프로젝트와 `mobile-web-validator`를 같은 상위 폴더에 두는 구성이 가장 단순합니다.

## 환경변수

필수:
- `NOTION_TOKEN`: Notion Internal Integration Secret
- `NOTION_DB_ID`: 최종 저장할 Notion 데이터베이스 ID

권장:
- `HEADLESS=true`: Render 같은 서버 환경에서는 `true`가 기본
- `NOTION_UPLOAD=true`: 실행 결과를 Notion에 자동 업로드
- `TIMEZONE=Asia/Seoul`: 스케줄 기준 시간대

로컬 몽레포용 오버라이드:
- `SCENARIO_DIR`: 시나리오 `.py` 폴더
- `MOBILE_VALIDATOR_DIR`: 기존 GUI 프로젝트 경로. 현재 구조에서는 Notion 업로더 재사용에만 사용

## Render 설정

Render Web Service에서 아래처럼 설정합니다.

- Root Directory: 비움
- Build Command:

```bash
pip install -r requirements.txt && python -m playwright install --with-deps chromium chromium-headless-shell
```

- Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

환경변수는 최소 아래 5개를 넣습니다.

```env
NOTION_TOKEN=...
NOTION_DB_ID=5ad73fbd195182bcb4b201fb9d76815f
HEADLESS=true
NOTION_UPLOAD=true
TIMEZONE=Asia/Seoul
```

주의:
- Render의 Build Command에 `playwright install ...`를 직접 쓰면 실패합니다.
- 반드시 `python -m playwright install ...` 형태로 호출해야 합니다.
