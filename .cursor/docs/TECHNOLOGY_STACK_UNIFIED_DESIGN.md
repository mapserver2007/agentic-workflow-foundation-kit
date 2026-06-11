---
title: Web アプリケーション技術スタック 統一設計書（Cloudflare + Hono + Next.js + OpenAPI First）
exported_at: 2026-06-05
updated_at: 2026-06-05
version: 1.0（DRAFT を正本化。デプロイ層・開発フロー・バージョン方針・code-first トレードオフ評価を補完）
status: 正本（Source of Truth）
reference_specs:
  - OpenAPI Specification 3.1.0 (https://spec.openapis.org/oas/v3.1.0.html)
  - Cloudflare Workers - Next.js (OpenNext) (https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)
  - OpenNext for Cloudflare (https://opennext.js.org/cloudflare)
  - Hono (https://hono.dev/)
  - openapi-typescript / openapi-fetch (https://openapi-ts.dev/)
  - Redocly CLI (https://redocly.com/docs/cli/)
  - Spectral (https://docs.stoplight.io/docs/spectral/)
  - Prism (https://docs.stoplight.io/docs/prism/)
  - Cloudflare Vitest integration (https://developers.cloudflare.com/workers/testing/vitest-integration/)
---

# Web アプリケーション技術スタック 統一設計書 v1

* 作成日: 2026-06-05（v1.0）
* スコープ: Web アプリケーションを **設計 → 開発 → デプロイ** する技術スタックの統一方針
* 構成: **Cloudflare（実行基盤）+ Hono（API 実装）+ Next.js（フロントエンド）+ OpenAPI First（契約の正本）**
* v1.0 での主な補完: (1) タイトルにあって本文に欠けていた **Cloudflare デプロイ層** の追加 (2) ローカル開発・CI・デプロイの **具体フロー** (3) 各ツールの **現行バージョン方針**（裏取り済み） (4) spec-first を選ぶことの **code-first（chanfana 等）に対する正直なトレードオフ評価**

本ドキュメントは、本プロジェクトで Web アプリケーションを構築する際の技術スタックを **唯一無二の正本（Source of Truth）** として定義する。用語は [Appendix C: 用語集](#appendix-c-用語集) に集約する。

> **このドキュメントの位置付け（命名規約）**: 本ファイルは `UPPER_SNAKE_CASE.md` = **Meta 層（判断フレームワーク・横断ルール）**。プロジェクト固有の実 API 仕様・実装詳細は Domain 層（`docs/spec.md` / `docs/api.md` 等）に置き、本書はそれらが従うべき**型と原則**を定義する。命名規約の根拠は `AI_AGENT_UNIFIED_DESIGN.md §12 Layer 1`。

---

## 目次

### Part 1: 概念編（なぜ）

1. [全体方針と設計思想](#1-全体方針と設計思想)
2. [なぜ OpenAPI First か](#2-なぜ-openapi-first-か)
3. [採用しない方針（code-first）とその評価](#3-採用しない方針code-firstとその評価)
4. [OpenAPI First と Cloudflare / Hono / Next.js は矛盾しない](#4-openapi-first-と-cloudflare--hono--nextjs-は矛盾しない)
5. [設計原則](#5-設計原則)

### Part 2: アーキテクチャ編（何を）

6. [全体アーキテクチャとデプロイトポロジ](#6-全体アーキテクチャとデプロイトポロジ)
7. [モノレポ構成](#7-モノレポ構成)
8. [レイヤ責務と契約境界](#8-レイヤ責務と契約境界)

### Part 3: 技術スタック編（具体）

9. [技術スタック一覧とバージョン方針](#9-技術スタック一覧とバージョン方針)
10. [API 定義層（OpenAPI 3.1）](#10-api-定義層openapi-31)
11. [型生成・クライアント層](#11-型生成クライアント層)
12. [Frontend 層（Next.js on Cloudflare Workers）](#12-frontend-層nextjs-on-cloudflare-workers)
13. [Backend 層（Hono on Cloudflare Workers）](#13-backend-層hono-on-cloudflare-workers)
14. [データ・ストレージ層（Cloudflare バインディング）](#14-データストレージ層cloudflare-バインディング)
15. [Mock・契約テスト層](#15-mock契約テスト層)

### Part 4: 開発・デプロイ編（どう動かす）

16. [ローカル開発フロー](#16-ローカル開発フロー)
17. [契約駆動の実装順序](#17-契約駆動の実装順序)
18. [CI で担保すること](#18-ci-で担保すること)
19. [デプロイ（環境分離・Secrets・Service Bindings）](#19-デプロイ環境分離secretsservice-bindings)
20. [API 設計ルールも OpenAPI に寄せる](#20-api-設計ルールも-openapi-に寄せる)
21. [認証・認可（Cloudflare Access）](#21-認証認可)
22. [OpenAPI First の現実的な割り切り](#22-openapi-first-の現実的な割り切り)
23. [UI 設計・実装フロー](#23-ui-設計実装フロー)

### Part 5: 意思決定編

24. [最終結論](#24-最終結論)

### Appendix

* [A: spec-first vs code-first の比較（chanfana 等の正直な評価）](#appendix-a-spec-first-vs-code-first-の比較)
* [B: 技術選定の根拠と一次情報ソース](#appendix-b-技術選定の根拠と一次情報ソース)
* [C: 用語集](#appendix-c-用語集)
* [D: 参照](#appendix-d-参照)
* [E: 導入チェックリスト（段階導入）](#appendix-e-導入チェックリスト段階導入)

---

## Part 1: 概念編（なぜ）

### 1. 全体方針と設計思想

Web サービスの構成として、以下を基本方針とする。

* **Frontend** は Next.js + TypeScript（Cloudflare Workers 上で OpenNext アダプタにより実行）
* **Backend** は Hono + TypeScript（Cloudflare Workers 上で実行）
* **API 定義** は OpenAPI を正本とする（spec-first）
* Hono のコードから OpenAPI を生成する方式は採用しない
* OpenAPI を先に定義し、Hono はその契約に従って実装する
* Next.js は OpenAPI から生成された型付きクライアントを利用する
* **実行基盤** は Cloudflare（Workers / D1 / R2 / KV 等）に統一する

思想を一言で表すと以下である。

```text
OpenAPI = API 契約の正本（Source of Truth）
Next.js = 契約を消費するクライアント
Hono    = 契約を満たすサーバー実装
Cloudflare = フロント/バック/データを載せる単一の実行基盤
CI      = 契約違反を検出する門番
```

この方針の核心は **「型安全性」ではなく「API 契約の独立性」** である。型安全性だけなら Hono RPC や Zod ベースの code-first でも達成できる。本設計があえて spec-first を選ぶ理由は次章で述べる。

---

### 2. なぜ OpenAPI First か

Hono / Next.js / TypeScript のモノレポでは、Hono RPC や Zod ベースの code-first により OpenAPI なしでも高い型安全性を得られる。それでも本設計が OpenAPI First を採用するのは、**API 契約を実装から独立した長期資産として扱う**ためである。

OpenAPI First を採用する理由:

* API 仕様を実装言語・フレームワークから独立させられる
* 将来的に Go / Flutter / Python など他言語クライアントと連携しやすい
* API 仕様をレビュー対象・設計対象として扱える（PR で「契約」を議論できる）
* フロントエンドとバックエンドの実装順を分離できる
* Mock・型生成・ドキュメント生成・契約テストに利用できる
* 破壊的変更を CI で検出できる
* API を長期的なプロダクト資産として管理できる

> **トレードオフの明示（Humble 原則）**: Cloudflare / Hono エコシステムには code-first 向けの公式ツール（`chanfana` 等）が整備されており、小規模 API では code-first の DX が優位である。spec-first はこの既定パスとはやや異なる方向である（Cloudflare 全体が code-first を唯一推奨しているわけではない）。この選択の対価と判断根拠は [Appendix A](#appendix-a-spec-first-vs-code-first-の比較) で正直に評価する。本章の結論は「外部境界・他言語連携・長期契約管理を重視する場合に spec-first が優位」という条件付きである。

---

### 3. 採用しない方針（code-first）とその評価

以下の code-first / implementation-first の方式は **本設計では採用しない**。

* Hono の route 定義から OpenAPI を生成する
* Zod schema から OpenAPI を逆生成する
* `@hono/zod-openapi` / `chanfana` を **API 仕様の正本** として使う
* Hono RPC を API 契約の唯一の根拠にする
* 実装コードを読まないと API 仕様が分からない状態にする

**ただし code-first は「悪い設計」ではない。** 以下の条件下ではむしろ合理的である。

* クライアントが Next.js のみ
* バックエンドが Hono のみ
* 開発者全員が TypeScript に強い
* 外部公開 API ではない
* API 仕様書は副産物でよい
* 開発速度を最優先したい
* 小規模な MVP や内部 BFF である

この場合、Zod / Hono route を「TypeScript で書かれた仕様」とみなせる。ただし API 契約が TypeScript / Hono の実装構造に強く結びつくため、**長期的な API 管理や他言語連携には不向きになりやすい**。本設計はこの「実装への結合」を避けることを優先する。

---

### 4. OpenAPI First と Cloudflare / Hono / Next.js は矛盾しない

Cloudflare / Hono / Next.js を採用することと、OpenAPI First を徹底することは矛盾しない。むしろ役割を分けることで両方の利点を活かせる。

```text
OpenAPI（正本）
  ↓ openapi-typescript（型生成）
api-types（生成型）
  ↓ openapi-fetch / openapi-react-query
Next.js 用 API client（契約を消費）
  ↓ fetch / Service Binding
Hono 実装（契約を満たす・request/response validation）
  ↓ Wrangler
Cloudflare Workers（実行基盤）
  ↑
CI（契約テスト・breaking change check）
```

TypeScript の開発体験（型補完・エディタ支援）は、OpenAPI から型やクライアントを生成することで十分に補える。Cloudflare の DX（`wrangler dev` によるローカル実行、`workerd` ランタイム）もこのパイプラインに自然に組み込める。

---

### 5. 設計原則

本設計は以下の原則に基づく。各原則の詳細は対応する章を参照。

| 原則 | 要約 | 参照 |
| --- | --- | --- |
| 1. 契約は単一の正本 | `openapi.yaml`（bundle 後）を API 契約の唯一の Source of Truth とする | §10 |
| 2. 生成物はコミットせず CI で再生成・差分検出 | 型・クライアント・bundle は生成物。手編集を禁じ、CI で「生成 → diff」を行う | §11, §18 |
| 3. 実装は契約に従属 | Hono handler は手書きするが、型は OpenAPI 由来を使い、request/response を validation する | §13 |
| 4. 契約違反は CI で落とす | lint / bundle / breaking change / 契約テスト / response validation を必須ゲートにする | §18 |
| 5. 実行基盤は Cloudflare に統一 | フロント（OpenNext）・バック（Hono）・データ（D1/R2/KV）を同一基盤に載せ運用を単純化 | §6, §19 |
| 6. 環境は宣言的に分離 | dev / staging / production を Wrangler の environment と Secrets で分離 | §19 |
| 7. サーバー完全自動生成に期待しない | OpenAPI からは型・client・mock・test・diff を生成し、Hono 実装は手書きにする | §22 |
| 8. UI も設計を正本化する | API 契約と対称に、画面設計成果物（構造化 UI 仕様）を UI の正本とし、フロント実装をそれに従わせ、実装結果は設計へ回収する | §23 |

---

## Part 2: アーキテクチャ編（何を）

### 6. 全体アーキテクチャとデプロイトポロジ

本構成は **2 つの Cloudflare Worker**（フロントエンドとバックエンド）+ Cloudflare のデータバインディングで構成する。

```text
            ┌──────────────────────────────────────────────┐
   ブラウザ │              Cloudflare ネットワーク           │
  ───────▶ │                                              │
            │  ┌────────────────────┐   Service Binding    │
            │  │ apps/web (Worker)  │  または fetch(HTTPS)  │
            │  │ Next.js @opennext  │ ───────────────┐     │
            │  └────────────────────┘                │     │
            │     ▲ 型付き client                      ▼     │
            │     │ (openapi-fetch)        ┌────────────────────┐
            │     │                        │ apps/api (Worker)  │
            │     └── OpenAPI 契約 ───────▶ │ Hono + validation  │
            │                              └────────────────────┘
            │                                  │   │   │
            │                              D1  R2  KV  Queues   │
            └──────────────────────────────────────────────┘
```

**デプロイ単位:**

| コンポーネント | 実行形態 | アダプタ / ツール |
| --- | --- | --- |
| `apps/web`（Next.js） | Cloudflare Worker | `@opennextjs/cloudflare`（OpenNext アダプタ）+ Wrangler |
| `apps/api`（Hono） | Cloudflare Worker | Wrangler（Hono は Workers ネイティブ） |
| データ層 | Cloudflare マネージド | D1 / R2 / KV / Queues 等の binding |

**Web → API の通信:** 同一 Cloudflare アカウント内なら **Service Bindings**（Worker 間直接呼び出し、ネットワーク往復なし）を推奨。クロスアカウントや外部公開時は通常の HTTPS（`fetch`）。どちらの場合も型は OpenAPI 由来で統一する。

> **正確性メモ**: Cloudflare 上の Next.js は **`@opennextjs/cloudflare`（OpenNext アダプタ）が公式推奨**。旧 `@cloudflare/next-on-pages` は Edge ランタイム限定で機能制約が大きく、現在は OpenNext へ移行が推奨されている。OpenNext は Next.js の **Node.js ランタイム**を `workerd` 上で動かすため、App Router / RSC / SSR / ISR / Server Actions / Middleware / 画像最適化（Cloudflare Images 経由）に対応する。

---

### 7. モノレポ構成

```text
repo-root/
├── apps/
│   ├── web/                   # Next.js frontend（OpenNext → Cloudflare Worker）
│   │   ├── next.config.ts     # initOpenNextCloudflareForDev を呼ぶ
│   │   ├── open-next.config.ts # defineCloudflareConfig()
│   │   └── wrangler.jsonc      # nodejs_compat / compatibility_date / bindings
│   └── api/                   # Hono backend（Cloudflare Worker）
│       ├── src/index.ts       # Hono app（handler は手書き）
│       └── wrangler.jsonc
│
├── packages/
│   ├── api-spec/              # OpenAPI 定義（契約の正本）
│   │   ├── openapi.yaml        # ルート（$ref で分割）
│   │   ├── paths/
│   │   └── components/
│   ├── api-types/             # OpenAPI から生成した型（生成物・コミット任意）
│   ├── api-client/            # Next.js 用の型付き API client（openapi-fetch ラッパ）
│   └── api-contract-test/     # OpenAPI と Hono 実装の契約テスト
│
├── pnpm-workspace.yaml         # ワークスペース定義
├── turbo.json                  # タスクオーケストレーション（任意）
├── package.json
├── AGENTS.md / CLAUDE.md       # AI エージェント Context
└── docs/                       # spec.md / api.md / DECISIONS.md 等
```

* **パッケージマネージャ**: `pnpm`（workspace 機能を利用）を推奨。
* **タスクランナー**: `Turborepo`（`turbo.json`）でビルド・型生成・テストの依存関係とキャッシュを管理（任意だが規模が増えると有効）。
* `api-types` は生成物。コミットするかは方針次第だが、**コミットする場合は CI で「再生成 → diff」を必須**にする（[§18](#18-ci-で担保すること)）。

---

### 8. レイヤ責務と契約境界

| レイヤ | パッケージ / アプリ | 責務 | 「やってはいけない」こと |
| --- | --- | --- | --- |
| 契約 | `packages/api-spec` | API の唯一の正本を OpenAPI で定義 | 実装都合で契約を後追い変更する |
| 型 | `packages/api-types` | OpenAPI から型を生成 | 手編集する |
| クライアント | `packages/api-client` | 型付き fetch クライアントを提供 | URL/型を手書きで重複定義する |
| フロント | `apps/web` | UI と契約消費 | API 仕様を独自に再解釈する |
| サーバー | `apps/api` | 契約を満たす実装 + validation | OpenAPI を再記述する / route から仕様を逆生成する |
| 契約テスト | `packages/api-contract-test` | 契約と実装のズレを検出 | テストを skip して通す |

**契約境界の原則**: 仕様変更は必ず `api-spec` の OpenAPI から始める。実装（Hono）やクライアント（Next.js）から仕様を「事後的に確定させない」。

---

## Part 3: 技術スタック編（具体）

### 9. 技術スタック一覧とバージョン方針

> **バージョン方針**: 下表は本書執筆時点（2026-06）の現行安定版を基準にした **方針**であり、固定バージョンの宣言ではない。実際の固定は各 `package.json` / `wrangler.jsonc` で行う。「最終リリースが古く後継がある」ライブラリは採用しない。

| レイヤ | 技術 | バージョン方針 | 備考 |
| --- | --- | --- | --- |
| 実行基盤 | Cloudflare Workers | — | `workerd` ランタイム |
| デプロイ CLI | Wrangler | v4 系 | OpenNext 利用時は 3.99.0 以上必須、実質 v4 推奨 |
| Frontend | Next.js | 15 / 16 系 | 14 は OpenNext 側で 2026 Q1 にサポート終了 |
| Next.js アダプタ | `@opennextjs/cloudflare` | 1.x 系（GA） | 公式推奨。`next-on-pages` は不採用 |
| Backend | Hono | 4 系 | Workers ネイティブ |
| API 定義 | OpenAPI | 3.1 | JSON Schema 2020-12 準拠 |
| OpenAPI lint | Spectral | 6 系 | ルールセットをリポジトリで管理 |
| OpenAPI bundle/diff | Redocly CLI | 1 系 | `bundle` / `lint` / breaking diff |
| 型生成 | openapi-typescript | 7 系 | OpenAPI 3.1 対応 |
| フロント client | openapi-fetch | 0.x（安定） | メンテナンスモードだが本番安定 |
| データ取得統合 | openapi-react-query | 0.x | TanStack Query 統合（任意） |
| 自動生成 client（代替） | Orval | 7 系 | React Query/SWR フックを自動生成したい場合の代替 |
| Mock | Prism | 5 系 | OpenAPI モックサーバー（3.1 は一部制約あり） |
| 契約テスト | Vitest + `@cloudflare/vitest-pool-workers` | — | `workerd` 上でテスト実行 |
| ランタイム言語 | TypeScript | 5 系 | strict |
| パッケージ管理 | pnpm | 9 系以降 | workspace |
| タスク管理 | Turborepo | 2 系 | 任意 |

---

### 10. API 定義層（OpenAPI 3.1）

**正本**: `packages/api-spec/openapi.yaml`。大きくなる場合は `$ref` で `paths/` `components/` に分割し、**配布・ツール投入時は `redocly bundle` で 1 ファイルに束ねる**。

**ツール:**

* **OpenAPI 3.1**（JSON Schema 2020-12 と整合）
* **Redocly CLI**: `lint`（構文・スタイル）/ `bundle`（$ref 解決）/ breaking change diff
* **Spectral**: 独自ルールセット（命名・必須フィールド・エラー形式の統一等）を `.spectral.yaml` で管理

**運用ルール:**

* `operationId` は必須（型・クライアント生成のキーになる）
* エラーレスポンス形式は共通スキーマ（[§20](#20-api-設計ルールも-openapi-に寄せる)）に統一
* バージョンは URL パス（`/v1/...`）で表現

---

### 11. 型生成・クライアント層

* **型は生成物**: OpenAPI（bundle 済み）から `openapi-typescript` で型を生成し `api-types` に置く。**手編集禁止**。CI で「再生成 → diff」を必須化する（[§5](#5-設計原則) 原則2 / [§18](#18-ci-で担保すること)）。
* **クライアントは型付き fetch**: フロントは OpenAPI 由来の型付き client（`openapi-fetch`）を用い、**URL・型を手書きで重複定義しない**（[§8](#8-レイヤ責務と契約境界)）。データ取得フック統合（`openapi-react-query`）は任意。
* **到達経路の制約（[§21](#21-認証認可)）**: クライアントは Access 保護下の信頼境界（web オリジン / Service Binding）経由でのみ api に到達する。ブラウザに api の公開エンドポイントを露出する構成（`NEXT_PUBLIC_` での api URL 配布）は採らない。
* **ライブラリ選定**: `openapi-fetch` はメンテナンスモードだが仕様が安定し本番利用可。フック自動生成が必要なら **Orval** を代替検討する（生成コード量とのトレードオフ）。
* 生成コマンド・client 実装コードは Domain 層（`docs/` 配下の実装ガイド）に置く。

---

### 12. Frontend 層（Next.js on Cloudflare Workers）

Next.js は **`@opennextjs/cloudflare`** で Cloudflare Workers にデプロイする。

**前提設定（正確性に直結）:**

* `wrangler.jsonc` で `nodejs_compat` フラグを有効化
* `compatibility_date` を **`2024-09-23` 以降**に設定
* Wrangler は **3.99.0 以上**（実質 v4 推奨）
* Next.js の **Node.js ランタイム**を使用する（Edge ランタイムではない）

**設定方針（コードは Domain 層の実装ガイドに置く）:**

* `next.config.ts` で OpenNext のローカル開発初期化（`initOpenNextCloudflareForDev`）を呼び、ローカルでも binding を利用可能にする。
* `open-next.config.ts` で Cloudflare 向け設定（`defineCloudflareConfig`）を定義する。
* `apps/web` のスクリプトは 3 系統に分ける: 高速反復の通常 dev（`next dev`）／本番に近い確認の preview（OpenNext build → preview、`workerd` 上）／deploy（OpenNext build → deploy）。

> **重要**: `next dev` は Node.js 上で動くため本番（`workerd`）と挙動が異なりうる。**統合テスト・最終確認は preview（`wrangler dev` 経由の workerd）で行う**。

> **UI 設計との関係**: 画面（UI）の構成・レイアウト・状態表現・導線は **UI 設計成果物（構造化 UI 仕様）を正本**とし、本層の実装はそれに従う。設計駆動の手順・責務は [§23](#23-ui-設計実装フロー) を参照。

**対応機能（OpenNext アダプタ）:** App Router / Pages Router / Route Handlers / RSC / SSG / SSR / ISR / Server Actions / レスポンスストリーミング / Middleware / 画像最適化（Cloudflare Images 経由）。Next.js 15.2 で導入された Node.js Middleware は未対応の場合があるため、利用時は最新の対応状況を確認する。

---

### 13. Backend 層（Hono on Cloudflare Workers）

Hono は Workers ネイティブのため、Wrangler でそのままデプロイできる。

**実装方針 — Hono 側で OpenAPI を再記述しない。**

避けること:

```text
Hono route に API 仕様を書く
Zod schema を API 仕様の正本にする
handler 内に OpenAPI 相当の型を手書きする
実装から OpenAPI を生成する（chanfana / @hono/zod-openapi を正本化する）
```

採用すること:

```text
OpenAPI から生成された型を使う（api-types を import）
OpenAPI に従って handler を実装する
request validation を行う（契約に対する入力検証）
response validation を行う（契約に対する出力検証）
CI で OpenAPI とのズレを検出する
```

**実装の要件（具体コードは Domain 層の実装ガイドに置く）:**

* handler は OpenAPI 由来の型（`api-types`）を import し、`wrangler.jsonc` の binding と一致する型付き `Bindings`（D1 / R2 等）を受け取る。
* 各 operation の handler は手書きし、契約に一致する response を返す。
* request / response の validation を通し、実行時に契約逸脱を検出する。

Hono の役割は **OpenAPI 契約を満たす実装**に徹する。request/response の validation は実行時に契約逸脱を検出する安全網であり、CI の契約テストと二段構えにする。

> **エラーハンドリング**: 共通エラー形式（[§20](#20-api-設計ルールも-openapi-に寄せる)）は Hono の集約エラーハンドラに寄せ、全 handler で一貫した `ErrorResponse` を返す。

---

### 14. データ・ストレージ層（Cloudflare バインディング）

データ層も Cloudflare のマネージドサービスに寄せ、`wrangler.jsonc` の **binding** として宣言的に接続する。要件に応じて選択する（全て必須ではない）。

| サービス | 用途 | binding 種別 |
| --- | --- | --- |
| **D1** | リレーショナル（SQLite 互換）。主データストア | `d1_databases` |
| **R2** | オブジェクトストレージ（画像・ファイル）。OpenNext の ISR キャッシュにも利用可 | `r2_buckets` |
| **KV** | 低レイテンシ Key-Value（セッション・フラグ・キャッシュ） | `kv_namespaces` |
| **Queues** | 非同期ジョブ・バッチ | `queues` |

**設計指針:**

* バインディングは型（`Bindings`）として Hono / Next.js 双方に渡し、環境変数の直書きを避ける。
* スキーマ定義・マイグレーションは `docs/data-models.md`（Domain 層）に記述し、本書からは型のみを規定する。
* 機密値（API キー等）は binding ではなく **Secrets**（[§19](#19-デプロイ環境分離secretsservice-bindings)）で管理する。

---

### 15. Mock・契約テスト層

**Mock（Prism）:** OpenAPI（bundle 済み）から即席モックサーバーを起動し、バックエンド実装を待たずにフロント開発を進める。

> OpenAPI 3.1 の一部機能（複雑な JSON Schema 構文）で Prism の対応が限定的な場合がある。モックが返せない箇所は例として注記し、契約テスト（下記）で実装側を担保する。

**契約テスト（Vitest + Workers pool）:** Hono アプリを `workerd` ランタイム上で実行し、OpenAPI 契約との一致（status code / response body のスキーマ適合）を検証する。

* テストは `@cloudflare/vitest-pool-workers` を用い、**Node.js ではなく `workerd` 上**で実行する（本番ランタイムとの乖離を防ぐ）。
* 具体的な Prism 起動コマンド・契約テストのサンプルコード・`vitest.config.ts` は Domain 層（`docs/` 配下の実装ガイド）に置く。

---

## Part 4: 開発・デプロイ編（どう動かす）

### 16. ローカル開発フロー

```text
0. UI 設計（画面）        画面設計成果物（構造化 UI 仕様）を正本化（docs/ui-designs/）→ §23
1. 契約を編集            packages/api-spec/openapi.yaml
2. lint + bundle         redocly lint && redocly bundle
3. 型生成                openapi-typescript → api-types
4. （並行）フロント実装   next dev + Prism mock（UI 設計成果物に従い実装・API 未実装でも進められる）
5. （並行）バック実装     wrangler dev（Hono を workerd で起動）
6. 結合確認              web の preview（workerd）+ api の wrangler dev
7. 契約テスト            vitest（workers pool）
8. UI 設計回収           UI 確定後に UI 設計書 / 機械可読 UI 仕様を正本化（docs/ui-designs/）→ §23
```

UI 設計（ステップ 0）は API 契約定義と並ぶ**上流設計**であり、フロント実装（ステップ 4）はその成果物に従う。実装中の改善は決定ログに逐次蓄積し、区切りでステップ 8 として設計へ回収する（詳細は [§23](#23-ui-設計実装フロー)）。

ルートから Turborepo 経由で「dev 並行起動（web の `next dev` / api の `wrangler dev`）」「型生成（OpenAPI → 型）」「テスト（単体 + 契約）」をタスクとして実行する。具体的なタスク名・コマンドは Domain 層（`docs/` 配下の実装ガイド）に置く。

**ローカルと本番データの分離:** ローカル開発では本番 D1 / R2 / KV / Queues の binding に接続しない。dev / staging 用の binding またはローカルエミュレーションを用いる。remote binding を有効化する場合は、本番データを変更しない読み取り専用検証に**運用ルールとして**限定する（remote bindings 自体は書き込みを技術的に禁止しないため、PR レビューで設定を明示確認する）。環境別 binding の宣言は [§19](#19-デプロイ環境分離secretsservice-bindings) に従う。

---

### 17. 契約駆動の実装順序

仕様変更は **必ず契約から**始める。逆流（実装 → 契約）を禁止する。

```text
①  api-spec の OpenAPI を変更（PR でレビュー）
   ↓
②  redocly lint / spectral → 契約の妥当性を確認
   ↓
③  openapi-typescript で型を再生成（CI で diff チェック）
   ↓
④  api-client / Next.js: 新しい型に追従（型エラーが変更箇所を教える）
   ↓
⑤  Hono: 契約を満たすよう handler を実装 + validation
   ↓
⑥  契約テスト・response validation で一致を確認
   ↓
⑦  breaking change check（既存契約を壊していないか）
```

この順序により、「フロントとバックが別々の理解で実装してズレる」事故を構造的に防ぐ。

---

### 18. CI で担保すること

OpenAPI First で最も重要なのは **仕様と実装のズレを放置しないこと**。CI では最低限以下を確認する。

```text
OpenAPI lint            （redocly lint / spectral）
OpenAPI bundle          （redocly bundle が成功する）
breaking change check   （前バージョン契約との差分）
型生成                  （openapi-typescript）
生成物の差分チェック     （生成 → git diff が空であること）
Next.js build           （opennextjs-cloudflare build が通る）
Hono build              （api Worker がビルドできる）
contract test           （vitest / workers pool）
response validation test（実装が契約どおりの応答を返す）
```

**検出すべきズレ:**

```text
OpenAPI にある path/method が未実装
Hono にある path/method が OpenAPI に存在しない
定義外の status code を返している
response body が schema と一致しない
error response 形式が統一されていない
認証必須 API が public になっている
```

> **原則 2 の運用**: 型・bundle・client は生成物。CI で「再生成 → `git diff --exit-code`」を行い、**生成物が最新でない PR を落とす**。これにより「手で型を直して契約と乖離する」事故を防ぐ。

---

### 19. デプロイ（環境分離・Secrets・Service Bindings）

**デプロイは Wrangler に統一**する。フロント（OpenNext）・バック（Hono）とも `wrangler deploy` 系で Cloudflare Workers に配置する。

**環境分離（宣言的）:** `wrangler.jsonc` の environment 機能で dev / staging / production を分離し、各環境向けに `wrangler deploy` する。環境固有の設定値（`compatibility_date` / `compatibility_flags` / 環境別 `vars`）は宣言的に持つ。具体的な `wrangler.jsonc` 例・deploy コマンドは Domain 層（`docs/` 配下の実装ガイド）に置く。

**データ binding の環境分離:** dev / staging / production は Wrangler environment で明示的に分離し、各環境で D1 / R2 / KV / Queues の binding を**別リソース**にする。ローカル開発・preview が production binding を参照しないことを**不変条件**とする（[§16](#16-ローカル開発フロー)）。

**Secrets（機密値）:** 平文の `vars` ではなく Wrangler の Secrets 機能で管理し、環境ごとに登録する。

**Web → API 接続:** 同一アカウント内は **Service Bindings** を推奨（Worker 間直接呼び出しで往復レイテンシなし）。外部公開・クロスアカウント時は HTTPS。いずれも型は OpenAPI 由来で統一する。

**リリース手順の責務分離:** デプロイの具体的な順序・ロールバック手順は Meta 層の `docs/RELEASE_PROCESS.md` に、Git 不可逆操作の禁止事項は `AGENTS.md` の Boundaries に従う（無断 push / commit 禁止）。

---

### 20. API 設計ルールも OpenAPI に寄せる

エラー形式・認証・権限・所有者チェックも可能な限り OpenAPI 側に記述し、契約として一元管理する。

**共通エラースキーマ:** エラー応答は OpenAPI の共通スキーマ（`ErrorResponse`）に統一する。少なくとも機械可読な `code` と人間可読な `message` を必須とし、補足 `details` を任意で持つ。全エラー応答がこのスキーマに従うことを契約上の不変条件とする。

**認可情報を `x-` 拡張で管理:** 各 operation の認証要否（`security`）と認可メタデータ（権限・所有者チェック等を `x-` 拡張で）を契約に宣言し、実装・ポリシー生成の単一の根拠とする。

これら（共通エラースキーマ・認可メタデータ）の具体的な OpenAPI 記述（YAML）は Domain 層（`docs/` 配下の実 API 仕様）に置く。これにより将来的に以下へ展開しやすくなる。

* 権限一覧の自動生成
* API ドキュメント生成
* Mock 生成
* テストケース生成
* API Gateway / Cloudflare Access ポリシー生成
* 管理画面向け API 一覧生成

---

### 21. 認証・認可

認証・認可は API 契約（OpenAPI）と実行基盤（Cloudflare）の双方に跨る横断関心事である。本設計では **初期フェーズの利用者を PO 本人に限定**し、アプリにログイン機能を持たせず、**Cloudflare Access** でエッジ前段に認証・認可を寄せる。

#### 方針の要点

* **認証**: Cloudflare Access の **One-Time PIN**（メールに届く 6 桁コード）を用いる。アプリ側にログイン画面・ユーザーテーブル・パスワード・セッション管理を持たない。
* **認可**: Cloudflare Access Policy で **PO 本人のメールのみ `Allow`** する。許可リストは Cloudflare 側でサーバーサイド管理され、ブラウザ（HTML/JS）に露出しない。許可外メールは PIN 入力に成功しても認可段階で拒否される。
* **初期フェーズの受容リスク**: One-Time PIN はメール受信箱に依存するため、メールアカウント侵害時は認証突破につながりうる（単要素）。初期 PO 単独利用ではこの単要素性を受容し、利用者増加時は Google Workspace / Microsoft Entra ID 等の IdP 連携へ移行する。

#### 責務分離

| 項目 | 担当 |
| --- | --- |
| 認証 | Cloudflare Access（One-Time PIN） |
| 認可 | Cloudflare Access Policy（PO メールのみ Allow） |
| アプリ内権限管理 | 初期フェーズは原則不要 |
| web Worker の経路保護 | Cloudflare Access Application |
| api Worker の経路保護 | 公開ルート非割当 + Service Binding 到達のみ |

#### Q-AUTH 論点の確定

| ID | 論点 | 決定 |
| --- | --- | --- |
| Q-AUTH-1 | ブラウザ / 管理画面の認証 | **Cloudflare Access + One-Time PIN**（初期は PO メールのみ Allow） |
| Q-AUTH-2 | 外部公開 API の認証 | **初期は非公開**（Access 配下）。公開時に Bearer JWT 等を別途設計 |
| Q-AUTH-3 | Web → API 間の認証 | **Service Bindings 維持**（[§6](#6-全体アーキテクチャとデプロイトポロジ) / [§19](#19-デプロイ環境分離secretsservice-bindings)）。api Worker は公開ルートを持たず、web Worker からのみ到達させる |
| Q-AUTH-4 | マシン間（machine-to-machine） | **初期は不要**。必要時に Access Service Token を検討 |
| Q-AUTH-5 | api Worker をやむを得ず公開する場合 | **Access Application または Access Service Token による保護を必須**とする |

#### Workers トポロジでの経路保護

Cloudflare Access の一般的な構成は **自前オリジン**を前提に、オリジン直アクセスを **Cloudflare Tunnel** で遮断して Access 迂回を防ぐ。本スタックはアプリを **Cloudflare Workers 上で実行**する（自前オリジンを持たない）ため、保護対象は「自前オリジン」ではなく Worker のルートになる。Workers 構成では Tunnel の代わりに以下を**不変条件**とする。

* web Worker の本番カスタムドメインに **Access Application** を適用する
* web Worker / api Worker ともに直アクセス可能な `*.workers.dev` ルートを無効化する
* web Worker / api Worker ともに **Preview URLs（`preview_urls`）を無効化**する（`workers.dev` ルート無効化とは**別設定**であり、有効なままだとバージョン別プレビュー URL から Access の外で到達されうる）
* api Worker は原則としてカスタムドメイン・公開 Route を割り当てず、**Service Binding 経由でのみ**到達させる
* api Worker をやむを得ず公開する場合は、Access Application または Access Service Token による保護を必須とする
* 厳密化する場合は Worker 側で `Cf-Access-Jwt-Assertion` の **JWT 署名を検証**する

自前オリジン（VM / コンテナ等）を併設する場合に限り、**Cloudflare Tunnel** でオリジンを保護する。

> **正確性メモ**: `*.workers.dev` ルートの無効化（`workers_dev`）と Preview URLs（`preview_urls`）は独立した設定である。経路保護はこの両方を無効化して初めて成立する。具体の設定キー・記述例は Domain 層の `wrangler.jsonc` 実装ガイドで確定する。

#### Service Binding 経路での identity 伝播

Cloudflare Access が付与するヘッダー（`Cf-Access-Authenticated-User-Email` / `Cf-Access-Jwt-Assertion`）は、Access で保護された**公開 HTTP リクエストの入口で web Worker に到達**する。一方、web Worker から api Worker への **Service Binding 呼び出しは内部呼び出し**であり、Access の HTTP 前段を再度通らない。

したがって identity 信頼の前提は「**api Worker が Service Binding 以外から到達不能であること**」（上記の経路保護）である。その上で、api Worker で「誰が操作したか」を記録する場合は、web Worker が Access で検証済みの identity を api Worker へ渡す。渡し方は以下のいずれかとする。

* 元 Request をそのまま Service Binding で転送する（Cf-Access-* ヘッダーは Request に付随して伝播する）
* `Cf-Access-Jwt-Assertion` を検証して得た subject / email / aud 等の claim を渡す
* web Worker 側で正規化した actor オブジェクトを渡す

api Worker は、**ブラウザや外部クライアントから直接渡された同名ヘッダーを信頼してはならない**。api Worker が公開ルートを持たない構成では、identity の信頼境界は web Worker と Service Binding に置く。

api Worker 側でも JWT を検証する場合、検証対象の `aud` は **web Worker を保護している Access Application の Audience タグ**を用いる。

#### JWT 検証の段階方針

初期 PO 単独利用では、Access Application + `workers.dev` 無効化 + Preview URLs 無効化 + api Worker の公開ルート非割当を**必須防御**とし、Worker 側 JWT 署名検証は**任意**とする。

ただし、以下のいずれかに該当した時点で Worker 側 JWT 署名検証を**必須化**する。

* 社内メンバーを Access Policy に追加する
* 外部公開 API を追加する
* api Worker に公開 Route / カスタムドメインを割り当てる
* Preview URLs を有効化する
* 管理画面と一般公開画面を同一コードベースで扱う
* 監査ログをセキュリティ証跡として扱う

#### 将来の拡張方針

* **社内メンバー追加**: Access Policy の Allow にメール / メールドメインを追加する。この時点で Worker 側 JWT 署名検証を必須化する。
* **ユーザー増加時**: One-Time PIN から Google Workspace / Microsoft Entra ID 等の IdP 連携へ移行し、グループ単位で認可する。
* **一般公開時**: 公開画面と管理画面を分離する。管理画面・ステージングは公開後も Access で保護を継続する。
* **外部公開 API**: Access 前提から切り離し、Bearer JWT / API key / OAuth 等の API レベル認証を別途設計する。

#### OpenAPI 契約との関係

OpenAPI の `security` / `x-permission`（[§20](#20-api-設計ルールも-openapi-に寄せる)）は、将来アプリ側で API レベルの認可を行う際の宣言に用いる。初期フェーズはエッジ（Access）で一元防御するため、CI の「認証必須 API が public になっている」検出（[§18](#18-ci-で担保すること)）は外部公開 API を追加する段階で実効性を持つ。

ただし、api Worker に公開 Route / カスタムドメインを割り当てる場合は、OpenAPI 上で `security` 未定義の管理系 operation が存在しないことを CI で検出する。

---

### 22. OpenAPI First の現実的な割り切り

OpenAPI First では、**TypeScript サーバーコードの完全自動生成には期待しない**。gRPC / proto / protoc のように安定して綺麗なサーバー実装が生成される体験は、OpenAPI + TypeScript ではまだ弱い。

狙うべきでないもの:

```text
OpenAPI から Hono サーバーコードを完全生成する
```

狙うべきもの:

```text
OpenAPI から 型・client・mock・test・diff 検知 を生成する
Hono 実装は手書きにする
CI で契約違反を落とす
```

この割り切りにより、Cloudflare / Hono / Next.js の開発速度を活かしつつ、API 契約を OpenAPI に独立させられる。

---

### 23. UI 設計・実装フロー

フロントエンド（[§12](#12-frontend-層nextjs-on-cloudflare-workers)）は OpenAPI 契約を消費するだけでなく、利用者が触れる **画面（UI）** を提供する。本設計は UI も API 契約と同じ「**設計を正本化し、実装をそれに従わせる**」設計駆動で扱う。API 契約が `openapi.yaml` を正本にするのと対称に、**UI は画面設計成果物を正本**にする（[§5](#5-設計原則) 原則 8）。

> **レイヤの位置づけ**: 本節は Meta 層として **フローと責務の順序のみ**を規定する。具体的な生成ツール・スクリプト・テンプレート・コマンドは Domain 層（`docs/` 配下の実装ガイド・運用ツール）に置く。本書はそれらが従うべき型と原則を定義する。

#### 23.1 UI 設計フェーズ（画面設計の正本化）

画面キャプチャまたは自然言語の要件から、以下 3 種の成果物を **画面単位**で生成する。

| 成果物 | 位置づけ | 主な読み手 |
| --- | --- | --- |
| ワイヤーフレーム図 | 人間が視覚編集するビュー | 人間（レビュー・編集） |
| 構造化 UI 仕様（機械可読） | **設計の正本**（AI / CI が解析） | AI / ツール |
| 画面仕様書（人間可読） | 構造化仕様の説明ビュー | 人間（仕様共有） |

* **構造化 UI 仕様が正本**。図は人間がレビュー・編集するための視覚ビュー、仕様書は人間へ説明するためのビューであり、いずれも構造化仕様と相互変換・再正規化できる関係に保つ（図を編集したら構造化仕様へ正規化して取り込む）。
* 単一画面モデルに加え、**複数フレーム（状態差分・画面遷移）モデル**を扱う。1 画面内の状態（initial / loading / empty / error 等）やページ遷移を、フレームと遷移として表現する。
* 成果物は **1 画面 = 1 ディレクトリ**で、固定 ID（作成順の連番）を採番して Domain 層（`docs/ui-designs/` 配下）に保存する。ID は並び順が変わっても変更しない（参照安定性のため）。

#### 23.2 UI 実装フェーズ（実装と設計回収）

UI 実装は、上流の基本設計（Design Doc）と実装指示（AI 実装レポート、`docs/agent-tasks/reports/`）を入力に行い、実装結果を再び設計資産へ **回収**する。

* **実装方針**: 既存の UI コンポーネント / デザイントークンに準拠し、独自 CSS を最小化する。色・フォントを無秩序に直接指定せず、トークン / theme に従う。
* **状態別 UI を省略しない**: `initial` / `loading` / `empty` / `error` / `validation` / `permission` を必ず実装対象に含める。
* **対話的改善は 2 段階更新**で扱う:
  1. **逐次（修正のたび）**: 決定ログに 1 エントリ追記（追記専用）。**What だけでなく Why と固定度**を残し、棄却・保留の判断も生ログに残す。フル仕様書はここでは更新しない。
  2. **正本化（区切り）**: 蓄積した決定ログを **必須入力**に、UI デザイン設計書（人間可読）と機械可読 UI 仕様を生成する。採用された決定のみを正本へ畳み込み、棄却・保留は正本に混ぜない。
* **固定度（`must` / `should` / `may`）** で「人間が固定した意図」と「AI が補完・変更してよい範囲」を分離する。これにより正本から **冪等再実装**が可能になる（ピクセル一致ではなく、コンポーネント構成 / 状態表現 / レイアウトルール / トークン参照 / 主要導線の一致）。

> **ログ無しの正本化を禁止**: コードからは「何を（What）」しか復元できず、「なぜ（Why）・固定度」が欠落して再現不能な仕様書になる。逐次ログの蓄積を正本化の前提条件とする。これは API 契約で「実装から仕様を逆生成しない」（[§3](#3-採用しない方針code-firstとその評価) / [§13](#13-backend-層hono-on-cloudflare-workers)）とした原則を UI にも適用したものである。

#### 23.3 正本と責務境界

| 対象 | 正本 | UI 設計成果物がやってはいけないこと |
| --- | --- | --- |
| 業務仕様・権限・バリデーション | 基本設計（Design Doc） | UI 都合で業務仕様を再定義・変更する |
| API（path / schema / error） | OpenAPI 契約（[§10](#10-api-定義層openapi-31)） | UI 側で API 仕様を再解釈する（[§8](#8-レイヤ責務と契約境界)） |
| 画面構成・レイアウト・状態表現・導線 | UI 設計成果物（構造化 UI 仕様 / UI 設計書） | — |

UI は業務仕様・API を **消費する**側であり、これらの正本を変更しない。UI が正本となるのは画面の構成・レイアウト・状態表現・導線に限る。

#### 23.4 開発フロー上の位置と品質ゲート

UI 設計は API 契約定義と並ぶ **上流設計**であり、フロント実装（[§12](#12-frontend-層nextjs-on-cloudflare-workers)）はこの成果物に従う（全体フローは [§16](#16-ローカル開発フロー) ステップ 0 / 4 / 8）。

```text
UI 設計（画面設計の正本化）
  ↓ 画面設計成果物（構造化 UI 仕様）
フロント実装（既存コンポーネント / トークン準拠・状態別 UI）
  ↓ 対話的改善（決定ログ逐次追記：What + Why + 固定度）
設計回収（UI 設計書 + 機械可読 UI 仕様の正本化）
  ↓
冪等再実装 / 再現性検査（任意で視覚差分確認）
```

* **再現性 Lint**: 構造化 UI 仕様 / UI 設計書が冪等再実装に足る粒度か、決定ログに status / 固定度が付与されているかを検査対象にできる。
* **視覚差分（Visual Regression）**: 元実装と再実装のスクリーンショット差分で設計とのズレを確認する（任意）。
* 具体的な生成・検査コマンド・テンプレートは Domain 層（`docs/` 配下の実装ガイド・運用ツール）に置く。

---

## Part 5: 意思決定編

### 24. 最終結論

本構成では **OpenAPI First を採用し、実行基盤を Cloudflare に統一する**。

```text
API Definition:
  OpenAPI 3.1
  openapi.yaml を唯一の正本（spec-first）
  Redocly CLI + Spectral

Frontend:
  Next.js + TypeScript
  @opennextjs/cloudflare（OpenNext アダプタ）→ Cloudflare Workers
  openapi-typescript + openapi-fetch（+ openapi-react-query 任意）

UI:
  画面設計成果物（構造化 UI 仕様）を UI の正本（design-first）
  設計 → 実装 → 決定ログ逐次蓄積 → 設計回収 → 冪等再実装
  既存コンポーネント / デザイントークン準拠・状態別 UI

Backend:
  Hono + TypeScript → Cloudflare Workers
  OpenAPI generated types
  handler は手書き
  request / response validation
  contract test（Vitest + workers pool）

Data:
  Cloudflare D1 / R2 / KV / Queues（binding）

Deploy:
  Wrangler（env で dev/staging/production 分離、Secrets で機密管理）
  Web → API は Service Bindings 推奨

CI:
  lint / bundle / breaking diff / generate / build / contract test / response validation
```

Zod や Hono route から OpenAPI を逆生成する code-first は、TypeScript 内で高速に開発するには合理的だが、**API を長期的な契約・外部境界・他言語連携の資産として扱う**本設計では spec-first が適している。Cloudflare 公式 DX（chanfana 等）が code-first に寄っている点は認識した上で、契約独立性という目的のために spec-first を選ぶ（[Appendix A](#appendix-a-spec-first-vs-code-first-の比較)）。

UI も同じ思想を貫く。実装コードから事後的に画面仕様を起こすのではなく、**画面設計成果物（構造化 UI 仕様）を正本とする design-first** とし、フロント実装をそれに従わせ、実装中の判断は決定ログへ逐次蓄積して設計へ回収する（[§23](#23-ui-設計実装フロー)）。API は OpenAPI、UI は画面設計成果物を正本とすることで、**契約と画面の双方を実装から独立した資産として管理する**のが本設計の一貫した立場である。

---

## Appendix

### Appendix A: spec-first vs code-first の比較

本設計の核心的なトレードオフを正直に整理する。**Cloudflare / Hono エコシステムには code-first 向けの有力な公式ツールが整備されており（[`chanfana`](https://github.com/cloudflare/chanfana)：Cloudflare 製の OpenAPI ライブラリ、および [Cloudflare Workers 公式 quickstart の `chanfana-openapi-template`](https://developers.cloudflare.com/workers/get-started/quickstarts/)）、MVP・小規模 API では code-first の DX が優位**である。spec-first はこの既定パスとはやや異なる方向であることを明記する（Cloudflare がアーキテクチャ全体で code-first を唯一推奨しているわけではない）。

| 観点 | spec-first（本設計） | code-first（chanfana / @hono/zod-openapi） |
| --- | --- | --- |
| 正本 | `openapi.yaml`（実装非依存） | Zod schema / route 定義（TypeScript 実装） |
| 契約の独立性 | ◎ 言語・FW から独立 | △ TypeScript / Hono に結合 |
| 初速（小規模 TS のみ） | △ 契約を先に書く手間 | ◎ 実装即仕様、速い |
| 他言語クライアント連携 | ◎ 契約から各言語生成 | △ 実装を読まないと仕様不明 |
| ドキュメント鮮度 | ○ 契約が常に正 | ◎ 実装から自動生成で乖離しにくい |
| Cloudflare 公式 DX 適合 | △ 自前パイプライン構築 | ◎ `chanfana` テンプレートが用意 |
| 契約レビュー（PR） | ◎ 契約差分を直接レビュー | △ 実装差分から契約変化を読み取る |
| 破壊的変更検出 | ◎ 契約 diff で機械検出 | ○ 実装 diff 由来 |

**判断:** 外部公開 API / 他言語クライアント / 長期契約管理が要件にある場合は **spec-first**。クライアントが Next.js のみ・内部 BFF・MVP で初速最優先なら **code-first（chanfana）も合理的**。本プロジェクトは前者を想定し spec-first を採用するが、サブシステム単位でこの判断は再評価しうる。

> **chanfana の正確な位置付け**: Cloudflare 製の OpenAPI 3.1 スキーマ生成・検証ライブラリで、Zod スキーマから OpenAPI を生成する code-first ツール。Hono 用 `fromHono` アダプタを提供。本設計では正本としては採用しないが、「code-first を選ぶ場合の第一候補」として認識しておく。

---

### Appendix B: 技術選定の根拠と一次情報ソース

| 選定 | 根拠（一次情報） |
| --- | --- |
| Next.js を `@opennextjs/cloudflare` で配置 | Cloudflare 公式が OpenNext アダプタを推奨（`next-on-pages` は Edge 限定で非推奨化）。Node.js ランタイムで App Router/RSC/SSR/ISR に対応 |
| `nodejs_compat` + `compatibility_date 2024-09-23+` + Wrangler 3.99.0+ | OpenNext 利用の必須前提（公式ドキュメント） |
| Hono を Workers に直接配置 | Hono は Edge/Workers ネイティブ設計 |
| openapi-typescript / openapi-fetch | OpenAPI 3.1 → TS 型・型付き fetch の標準。openapi-fetch はメンテナンスモードだが安定 |
| 契約テストを workers pool で実行 | 本番 `workerd` との乖離防止（Cloudflare Vitest integration） |
| Redocly / Spectral / Prism | OpenAPI の lint / bundle / breaking diff / mock の標準ツールチェーン |

一次情報 URL は frontmatter の `reference_specs` を参照。

---

### Appendix C: 用語集

| 用語 | 説明 |
| --- | --- |
| OpenAPI First（spec-first） | API 仕様（OpenAPI）を正本とし、実装をそれに従わせる方式 |
| code-first | 実装（Zod / route）から OpenAPI を生成する方式（chanfana / @hono/zod-openapi） |
| 契約（API Contract） | クライアントとサーバーが従う API の合意。本設計では `openapi.yaml` |
| 契約テスト | 実装が契約どおりの応答を返すかを検証するテスト |
| response validation | 実行時に応答が契約スキーマに一致するか検証する処理 |
| breaking change check | 契約の後方互換性を壊す変更を CI で検出すること |
| Cloudflare Workers | Cloudflare のエッジ実行環境。`workerd` ランタイム |
| `workerd` | Cloudflare Workers のオープンソースランタイム |
| OpenNext / `@opennextjs/cloudflare` | Next.js を Cloudflare Workers 上で動かす公式推奨アダプタ |
| Wrangler | Cloudflare Workers のビルド・デプロイ CLI |
| binding | Worker から Cloudflare リソース（D1/R2/KV 等）へ宣言的に接続する仕組み |
| Service Bindings | Worker 間を直接呼び出す binding（ネットワーク往復なし） |
| D1 / R2 / KV / Queues | Cloudflare のマネージドデータサービス（SQL / オブジェクト / KV / キュー） |
| Hono | エッジ/Workers ネイティブの軽量 Web フレームワーク |
| chanfana | Cloudflare 製の code-first OpenAPI ライブラリ（Zod → OpenAPI） |
| Prism | OpenAPI からモックサーバーを起動する Stoplight 製ツール |
| Spectral | OpenAPI / JSON / YAML の lint ツール |
| Redocly CLI | OpenAPI の lint / bundle / diff を行う CLI |

---

### Appendix D: 参照

* [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0.html)
* [Cloudflare Workers — Next.js（OpenNext）](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)
* [OpenNext for Cloudflare](https://opennext.js.org/cloudflare) / [Get Started](https://opennext.js.org/cloudflare/get-started)
* [Hono 公式](https://hono.dev/)
* [openapi-typescript / openapi-fetch / openapi-react-query](https://openapi-ts.dev/)
* [Redocly CLI](https://redocly.com/docs/cli/)
* [Spectral](https://docs.stoplight.io/docs/spectral/)
* [Prism](https://docs.stoplight.io/docs/prism/)
* [Cloudflare Workers Vitest integration](https://developers.cloudflare.com/workers/testing/vitest-integration/)
* [chanfana（code-first 比較対象）](https://github.com/cloudflare/chanfana) / [Cloudflare Workers 公式 quickstart テンプレート一覧（`chanfana-openapi-template` を含む）](https://developers.cloudflare.com/workers/get-started/quickstarts/)
* [Orval（client 自動生成の代替）](https://orval.dev/)

---

### Appendix E: 導入チェックリスト（段階導入）

全てを一度に揃える必要はない。以下の優先度で段階導入する。

| 優先度 | 項目 | 理由 |
| --- | --- | --- |
| P0（必須） | モノレポ + `api-spec`（OpenAPI）+ openapi-typescript + Hono(api) + Next.js(web) の最小疎通 | 契約駆動の骨格 |
| P0（必須） | Wrangler でのローカル実行（`wrangler dev` / `preview`） | 本番ランタイムでの動作確認 |
| P1（早期） | Redocly lint + Spectral + CI の「生成 → diff」 | 契約と生成物の整合担保 |
| P1（早期） | 契約テスト（Vitest + workers pool） | 実装の契約逸脱検出 |
| P2（中期） | breaking change check / Prism mock | 互換性管理・並行開発 |
| P2（中期） | Service Bindings / Secrets / 環境分離 | 運用品質 |
| P3（長期） | `x-` 拡張からの権限/ポリシー自動生成 | 契約資産の活用拡大 |
