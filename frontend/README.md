# AI-Roundtable 프론트엔드

Next.js로 만든 화면 4개입니다: 질문(`/`), 토론 결과(`/debates/[id]`), 기록(`/history`), 설정(`/settings`).

## 실행

1. 백엔드를 먼저 실행합니다 (`backend/README.md` 참고, `--host 127.0.0.1 --port 8000`).
2. 의존성을 설치하고 개발 서버를 띄웁니다.
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. 브라우저에서 **http://localhost:3000** 을 엽니다. (`127.0.0.1:3000`으로 열면 백엔드가 CORS로 거절합니다.)

백엔드 주소를 바꾸려면 `NEXT_PUBLIC_API_BASE` 환경변수를 지정하세요 (기본 `http://127.0.0.1:8000`).

## 테스트 (백엔드·실제 AI를 호출하지 않음)

```bash
npm test
npm run typecheck
```
