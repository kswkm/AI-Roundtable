# AI-Roundtable 백엔드

여러 AI가 독립 의견 → 상호 검토 → 판정 AI 통합을 거쳐 하나의 최종 의견을 만드는 토론 서버입니다.

> **경고: 이 서버에는 인증이 없습니다.** 단일 사용자가 로컬에서만 쓰는 MVP입니다.
> 반드시 `--host 127.0.0.1`로 실행하고, `0.0.0.0`으로 바인딩하거나 네트워크에 노출하지 마세요.
> 또한 `Host` 헤더는 `localhost`와 `127.0.0.1`만 허용하며, 그 밖의 Host 요청은 400으로 거부합니다.

## 준비

1. [uv](https://docs.astral.sh/uv/)를 설치합니다.
2. 의존성을 설치합니다.
   ```bash
   cd backend
   uv sync
   ```
3. `.env.example`을 `.env`로 복사하고, 무료로 발급받은 API 키를 넣습니다. 키가 없는 슬롯은 선택할 수 없습니다.

## 연결 확인 (실제 API 호출, 슬롯마다 1회)

```bash
uv run python -m roundtable.smoke
```

`실패 — CreditsExhausted`가 나오면 그 회사의 무료 크레딧이 없는 상태입니다. 설정에서 다른 무료 모델로 바꾸세요
(예: `PUT /slots/2` 로 `openrouter`의 `:free` 모델).

## 서버 실행

```bash
uv run uvicorn roundtable.main:app --host 127.0.0.1 --port 8000
```

API 문서: http://127.0.0.1:8000/docs

## 테스트 (실제 API를 호출하지 않음)

```bash
uv run pytest
```
