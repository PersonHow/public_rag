# Skvalves Demo — 交接與環境設定文件

> 當前版本：Phase 5 — RAG 查詢  
> 最後更新：2026-04-30

---

## 目錄

1. [系統概覽](#1-系統概覽)
2. [技術架構](#2-技術架構)
3. [專案目錄結構](#3-專案目錄結構)
4. [本機開發環境設定](#4-本機開發環境設定)
5. [環境變數說明](#5-環境變數說明)
6. [Docker 啟動](#6-docker-啟動)
7. [資料庫與 Migration](#7-資料庫與-migration)
8. [API 端點一覽](#8-api-端點一覽)
9. [前端架構說明](#9-前端架構說明)
10. [各 Phase 功能紀錄](#10-各-phase-功能紀錄)

---

## 1. 系統概覽

本系統為**多租戶 RAG（Retrieval-Augmented Generation）生產助理**，提供技術文件（PDF、DOCX、TAP/NC/DXF 圖面）的上傳、解析、向量化與語意查詢功能。

```
使用者 → Angular Web → FastAPI Backend
                            ├── Cloud SQL (PostgreSQL) — 結構化資料
                            ├── Google Cloud Storage   — 原始檔案 / 解析結果
                            ├── Qdrant                 — 向量索引
                            ├── Vertex AI / Gemini     — 文件理解 / Embedding
                            └── Cloud Tasks            — 非同步處理佇列
```

---

## 2. 技術架構

| 層級 | 技術 |
|------|------|
| 前端 | Angular 21、Standalone Components、Signal 狀態管理 |
| 後端 | FastAPI 0.115、Python 3.12、Uvicorn |
| 資料庫 | PostgreSQL（asyncpg + SQLAlchemy 2.0 async） |
| ORM / Migration | SQLAlchemy 2.0 + Alembic |
| 向量資料庫 | Qdrant（gRPC port 6334） |
| AI | Vertex AI Gemini 2.5 Flash（文件解析）、gemini-embedding-001（向量） |
| 儲存 | Google Cloud Storage |
| 非同步任務 | Google Cloud Tasks |
| 認證 | JWT（HS256，24 小時有效） |
| 容器 | Docker + docker-compose |
| 前端 Serve | Nginx（含 `/api/` 反向代理到後端） |

---

## 3. 專案目錄結構

```
Skvalves_Demo/
├── .env                    ← 實際環境變數（不進 git）
├── .env.example            ← 範本，複製後填寫
├── docker-compose.yaml     ← 一鍵啟動 api_center + web
├── Dockerfile              ← 後端 image（python:3.12-slim）
├── requirements.txt        ← Python 套件
├── alembic.ini             ← Alembic 設定
├── migrations/
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_phase2_multitenant.py
│       ├── 003_phase4_vector.py
│       └── 004_phase4_indexes.py
├── app/
│   ├── main.py             ← FastAPI 入口、Router 掛載、CORS
│   ├── core/
│   │   ├── config.py       ← 所有環境變數定義（pydantic-settings）
│   │   ├── database.py     ← async engine / session factory
│   │   ├── dependencies.py ← get_db、get_current_user 等 DI
│   │   └── logging.py      ← JSON 格式 log 設定
│   ├── models/             ← SQLAlchemy ORM models
│   ├── schemas/            ← Pydantic request / response schemas
│   ├── routers/            ← API 路由
│   │   ├── auth.py
│   │   ├── upload.py
│   │   ├── sessions.py
│   │   ├── rules.py
│   │   ├── query.py
│   │   ├── health.py
│   │   ├── admin/          ← 管理員專用（companies、users）
│   │   └── internal/       ← Cloud Tasks worker 呼叫端點
│   └── services/
│       ├── ai/             ← gemini.py、embedding.py、qdrant_service.py
│       ├── document/       ← detector.py、ocr.py、parser.py
│       └── storage/        ← gcs.py、tasks.py
└── web/                    ← Angular 前端
    ├── Dockerfile          ← 多階段：node build → nginx serve
    ├── nginx.conf          ← SPA fallback + /api/ 反代
    └── src/
        ├── styles.scss     ← 全域樣式入口
        ├── styles/
        │   ├── _tokens.scss    ← CSS Custom Properties（設計 token）
        │   ├── _mixins.scss    ← SCSS mixins（flex、斷點、input-base 等）
        │   └── _global.scss    ← 全域 utility class
        └── app/
            ├── app.routes.ts   ← 所有路由定義
            ├── app.config.ts   ← Angular providers、interceptors
            ├── core/
            │   ├── auth/       ← auth.guard.ts、role.guard.ts
            │   ├── http/       ← auth.interceptor.ts、error.interceptor.ts
            │   └── services/   ← auth、toast、upload、preview service
            ├── features/       ← 各頁面 component
            │   ├── auth/login/
            │   ├── hub/
            │   ├── upload/
            │   ├── preview/
            │   ├── chat/
            │   └── admin/
            ├── layouts/        ← app-shell（登入後）、auth-shell（登入前）
            └── shared/
                ├── models/     ← auth、upload、session、document model + index barrel
                ├── pipes/
                └── ui/         ← 共用元件（button、toast、stepper 等）
```

---

## 4. 本機開發環境設定

### 前置需求

| 工具 | 版本 |
|------|------|
| Python | 3.12+ |
| Node.js | 20+ |
| PostgreSQL | 15+（本機或 Docker） |
| gcloud CLI | 已安裝並登入 |
| Qdrant | 本機 Docker 或 VM |

### 後端

```bash
# 1. 複製環境變數範本
cp .env.example .env
# → 填入所有必填欄位（見第 5 節）

# 2. 建立虛擬環境並安裝套件
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Google 認證（Vertex AI / GCS 使用 ADC）
gcloud auth application-default login

# 4. 執行 DB migration
alembic upgrade head

# 5. 啟動後端
uvicorn app.main:app --reload --port 8000

# API Docs（development 模式）
# http://localhost:8000/docs
```

### 前端

```bash
cd web

# 安裝套件
npm install

# 啟動開發伺服器
npm start
# → http://localhost:4200

# 建置 production
npm run build
```

> **前端 API 指向**：`web/src/environments/environment.ts` 中 `apiUrl: 'http://localhost:8000'`  
> Docker 模式下 Nginx 將 `/api/` 反代到 `api_center:8080`，前端不需另外設定。

---

## 5. 環境變數說明

複製 `.env.example` 為 `.env`，依照下表填寫。

| 變數 | 必填 | 說明 |
|------|------|------|
| `app_env` | ✓ | `development` / `production` |
| `INTERNAL_TOKEN` | ✓ | Cloud Tasks worker 驗證 token；本機可用任意值 |
| `GOOGLE_CLOUD_PROJECT` | ✓ | GCP 專案 ID |
| `DATABASE_URL` | ✓ | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `DB_POOL_SIZE_MIN/MAX` | — | 連線池大小，預設 5 / 20 |
| `GCS_BUCKET_NAME` | ✓ | GCS bucket 名稱 |
| `GCS_PROJECT` | ✓ | GCS 所屬 GCP 專案 |
| `CLOUD_TASKS_PROJECT` | ✓ | Cloud Tasks 所屬專案 |
| `CLOUD_TASKS_LOCATION` | — | 預設 `asia-east1` |
| `CLOUD_TASKS_QUEUE` | — | 預設 `onceagain-rag-ingestion` |
| `WORKER_BASE_URL` | ✓ | Cloud Tasks 呼叫的 worker URL（本機：`http://localhost:8000`） |
| `JWT_SECRET_KEY` | ✓ | 產生方式：`openssl rand -hex 32` |
| `JWT_EXPIRE_HOURS` | — | Token 有效時數，預設 24 |
| `VERTEX_AI_PROJECT` | ✓ | Vertex AI 所屬專案 |
| `VERTEX_AI_LOCATION` | — | 預設 `us-central1` |
| `GEMINI_MODEL` | — | 預設 `gemini-2.5-flash` |
| `GEMINI_EMBEDDING_MODEL` | — | 預設 `gemini-embedding-001`（768 維） |
| `QDRANT_HOST` | ✓ | Qdrant 主機 IP 或 hostname |
| `QDRANT_PORT` | — | 預設 `6333`（REST）；gRPC 用 `6334` |
| `QDRANT_API_KEY` | — | 無 API Key 留空 |
| `QDRANT_COLLECTION_NAME` | ✓ | Qdrant collection 名稱 |

> **Production 注意**：`app_env=production` 時，config.py 的 `_validate_required_in_production` 會強制檢查所有必填欄位，缺少任一項會拒絕啟動。

---

## 6. Docker 啟動

```bash
# 確認 .env 已填寫完整

# 啟動所有服務（api_center + web）
docker compose up --build

# 服務端口
# - 後端 API：http://localhost:8000
# - 前端：   http://localhost:4200
```

**GCS 認證掛載**：`docker-compose.yaml` 將本機的 ADC 憑證掛載進容器：

```yaml
volumes:
  - ~/.config/gcloud/application_default_credentials.json:/secrets/adc.json:ro
```

確認此檔案存在（執行過 `gcloud auth application-default login` 即會產生）。

**Health check**：`api_center` 有 health check，`web` 服務等待後端健康後才啟動。後端健康端點：`GET /health`。

---

## 7. 資料庫與 Migration

```bash
# 套用所有 migration 到最新版本
alembic upgrade head

# 查看當前版本
alembic current

# 回滾一版
alembic downgrade -1
```

| Migration | 內容 |
|-----------|------|
| `001_initial_schema` | 基礎表：sessions、documents、chunks |
| `002_phase2_multitenant` | 多租戶：companies、users、company_rules，各表加 company_id |
| `003_phase4_vector` | Chunk 加 embed_text、code_gcs_path 欄位 |
| `004_phase4_indexes` | 向量查詢相關索引 |

**Cloud Run 連線**：使用 Unix socket，`DATABASE_URL` 格式：

```
postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
```

---

## 8. API 端點一覽

基礎路徑：`http://localhost:8000`（Docker 透過 Nginx `/api/` 反代）

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/health` | 健康檢查 | — |
| POST | `/auth/login` | 登入，回傳 JWT | — |
| POST | `/upload` | 上傳文件，建立 session | JWT |
| GET | `/sessions/{id}` | 查詢 session 狀態 | JWT |
| GET | `/sessions/{id}/chunks` | 取得解析後 chunks | JWT |
| POST | `/sessions/{id}/confirm` | 確認匯入 | JWT |
| POST | `/sessions/{id}/reject` | 拒絕匯入 | JWT |
| POST | `/query` | RAG 語意查詢 | JWT |
| GET | `/rules` | 取得公司解析規則 | JWT |
| POST | `/internal/tasks/process` | Cloud Tasks worker 呼叫 | INTERNAL_TOKEN |
| GET | `/admin/companies` | 列出所有公司 | JWT + superadmin |
| GET | `/admin/users` | 列出所有用戶 | JWT + admin |
| GET | `/docs` | Swagger UI（development only） | — |

---

## 9. 前端架構說明

### 路由（`app.routes.ts`）

```
/               → redirect → /hub
/login          → LoginComponent（auth-shell layout，未登入）
/hub            → HubComponent（app-shell layout，需登入）
/upload         → UploadComponent
/preview/:id    → PreviewComponent
/chat           → ChatComponent
/admin          → AdminSessionsComponent（需 admin 角色）
/admin/users    → AdminUsersComponent（需 admin 角色）
```

### 角色系統

| 角色 | 說明 |
|------|------|
| `superadmin` | 最高權限，可管理所有公司與用戶 |
| `company_admin` | 公司管理員，具 admin 路由存取權 |
| `field_user` | 一般用戶 |

### 全域樣式

- **設計 token**：`styles/_tokens.scss` — CSS Custom Properties（`--ink`、`--rust`、`--teal` 等）
- **Mixins**：`styles/_mixins.scss` — flex、斷點、`input-base`、`ink-box` 等可重用模式
- **全域 class**：`styles/_global.scss` — `.card`、`.field`、`.table`、`.btn`、`.spinner` 等
- **元件使用方式**：直接用全域 class，或在 component `.scss` 中使用 `var(--token)` 取色

### 核心 Services（`core/services/`）

| Service | 功能 |
|---------|------|
| `AuthService` | 登入 / 登出 / JWT 管理（localStorage） |
| `ToastService` | 全域 toast 通知（Signal） |
| `UploadService` | 文件上傳佇列管理（Signal + progress） |
| `PreviewService` | Session 資料載入、輪詢、確認 / 拒絕 |

---

## 10. 各 Phase 功能紀錄

| Phase | 功能 |
|-------|------|
| Phase 1 | 單租戶文件上傳、Gemini 解析、GCS 儲存、Cloud Tasks 非同步處理 |
| Phase 2 | 多租戶（companies / users）、JWT 認證、角色守衛 |
| Phase 3 | 公司自定義解析規則（company_rules），術語差異自動處理 |
| Phase 4 | Chunk 向量化（gemini-embedding-001）寫入 Qdrant，code_gcs_path 注入 |
| Phase 5 | RAG 語意查詢端點（`/query`），前端 Chat 頁面串接 |
