---
title: Go + gRPC アプリケーション 構成ベストプラクティス
created_at: 2026-11-20
version: 0.2（ドラフト）
status: ドラフト
---

# Go + gRPC アプリケーション 構成ベストプラクティス

Go + gRPC（+ grpc-gateway）アプリケーションの、ディレクトリ構成・コード配置・ライブラリ・ローカル環境・DB・ビルド・設定ファイルの規範。誰が作っても同じ構成に収束することを目的とする。

## 0. 表記

### 0.1 規範語

| 記号 | 意味 |
| --- | --- |
| **MUST / MUST NOT** | 変更しない |
| **SHOULD** | 既定。変えるときは理由を記録する（記録先は本書の外。§0.3） |
| **MAY** | 任意 |

### 0.2 プレースホルダ

| プレースホルダ | 意味 | 例 |
| --- | --- | --- |
| `{{module}}` | Go module path | `github.com/acme/example-app` |
| `{{app}}` | リポジトリ名 / バイナリ名（kebab-case） | `example-app` |
| `{{svc}}` | proto パッケージ名・生成物ディレクトリ名（lower） | `example` |
| `{{svc}}pb` | 生成 Go パッケージ名 | `examplepb` |
| `{{ENV_PREFIX}}` | 環境変数 prefix（UPPER_SNAKE） | `EXAMPLE_APP` |
| `{{db}}` | DB 名 | `example` |
| `{{feature}}` / `{{Feature}}` | 集約名（lower_snake / PascalCase）。Entity・Service・Repository のパッケージ名に使う。**仮名**。実名は、本書を使ってドメイン層を生成するときに決めて置き換える。コード例の `Feature` / `feature` は、この仮名に対応する | `feature` / `Feature` |
| `{{caller}}` | UseCase を束ねる呼び出し元の単位（lower_snake）。呼び出し元が 1 つなら `{{svc}}` にする。**仮名**。実名は、ドメイン層の生成時に決めて置き換える | `caller` |
| `{{usecase_group}}` | UseCase パッケージの名前（ユースケース群、lower_snake）。業務上の機能単位で切る。集約名と一致しなくてよい。基準に合わない場合は、外れる理由を記録する（記録先は本書の外。§0.3）。**仮名**。実名は、ドメイン層の生成時に決めて置き換える | `usecase_group` |
### 0.3 対象範囲

対象: アプリケーションのコード構成、依存ライブラリ、ローカル開発環境（Docker / Compose）、DB、ビルドとコード生成、リポジトリの設定ファイル。
対象外: 本番インフラ、デプロイ方法、CI/CD、IaC（組織・環境で決まるため）。

業務（ドメイン）に依存する名前、規則、表は、本書に書かない（MUST NOT）。集約・Entity・VO の名前、ユースケースと呼び出し元の分け方、業務 sentinel、採番規則などは、本書を使ってドメイン層を生成するときに決める。それらの記録先と、決める手順は、本書の外で定める（本書の対象外）。本書の規則が「記録する」「表で残す」と書く内容は、その記録先で持つ。本書のコード例に出る `Feature` / `Child` などは、ドメインに依存しない仮名であり、ドメイン層の生成時に実名へ置き換える。本書に書くのは、ドメインが何であっても成り立つ構成と規則、および名前を決める基準だけである。

### 0.4 用語

| 用語 | 意味 |
| --- | --- |
| REST gateway | grpc-gateway による REST ↔ gRPC の変換。gRPC server と同一プロセスで動く（§3.6） |
| gateway（`<system>_gateway`） | コードの中で完結しない外部システム（API、ファイル、メッセージなど）とやりとりする部品（§3.5.5） |

### 0.5 タスク別の必読節

タスクの種類ごとに、読む節を示す。読むのは「必読節」と「参照先」の両方である。「参照先」は、必読節の本文が `§` で直接指す節である。必読節の本文に、この表にない節への参照が新たに出たら、その節も読む。`§<番号>` は、その節と子の節すべてを指す。「常時」の行は、どのタスクでも読む。

| タスク種別 | 必読節 | 参照先 |
| --- | --- | --- |
| 常時 | §0.1, §0.2 | §0.3 |
| 新規ファイル・パッケージの追加 | §2, §3.4.1, §3.9 | §0.2, §3.1, §3.2, §3.4.2, §3.4.3, §3.5.3, §3.5.5, §7.5, §9, §11 |
| レイヤをまたぐ変更（Controller から Repository まで） | §3.1, §3.2, §3.3, §3.4.1, §3.4.2, §3.5.1, §3.5.2 | §3.4.3, §3.5.3, §3.5.4, §3.5.5, §3.9, §5.4, §6.5, §9.2, §10 |
| Controller の追加・変更 | §3.1, §3.2 | §3.4.1, §3.4.3, §3.5.3, §3.5.4, §3.5.5, §3.9, §5.4, §9.2, §10 |
| UseCase の追加・変更 | §3.1, §3.3 | §3.2, §3.4.1, §3.4.3, §3.5.4, §3.5.5, §3.9, §6.5 |
| Domain（Entity、VO、Domain Service）の追加・変更 | §3.4 | §3.2, §3.5.3, §3.5.5, §5.4, §10 |
| Repository・DB アクセスの追加・変更 | §3.5.1, §3.5.2, §3.5.3, §3.5.4, §6 | §3.2, §3.3, §3.5.5, §9, §10 |
| 外部システム連携（gateway）の追加・変更 | §3.5.5 | §0.4, §3.1, §3.2, §3.3, §3.5.2, §9 |
| gRPC サーバー・DI・エントリポイントの変更 | §3.6, §3.7, §3.8 | §9, §10 |
| 新規依存ライブラリの追加 | §4 | §6.2, §9, §10 |
| API・proto の変更 | §5, §7.2, §7.4 | §3.2, §10, §11.3 |
| スキーマ・seed の変更 | §6 | §3.3, §3.5.5, §9 |
| 設定・環境変数の変更 | §9 | §3.3, §3.5.5, §3.7, §3.8, §6.1, §8.2 |
| ログ・エラーの変更 | §3.4.3, §10 | §3.2, §3.5.3, §3.5.5, §5.4 |
| ビルド・生成・テストの変更 | §7 | §3.1, §11.3 |
| Docker・Compose の変更 | §8 | §9.2 |
| 設計方針の確認（原則、この表） | §0.5, §1 | §3.1 |

---

## 1. 設計原則

| # | 原則 | 帰結 |
| --- | --- | --- |
| P1 | 契約を実装から分離する（contract-first） | API は proto、DB は `schema/*.sql`、依存は `go.mod` が正本 |
| P2 | 依存方向を固定する | Controller → UseCase → Domain ← Infrastructure。アーキテクチャテストで守る。例外は `queryable` 経由の `sqlx` への間接依存だけ（§3.1） |
| P3 | 生成物は生成元から再生成する | proto / Wire / Mock / OpenAPI は手編集しない。生成物は commit する。AI は生成物を読まず、生成元（`proto/**`、`internal/di/server.go`、Repository interface、`schema/*.sql`）を読む |
| P4 | 再現性を最優先する | 外部ツール・イメージ・依存はすべて pin。`latest` / `master` を使わない |
| P5 | ローカル完結 | Docker + Make + Go だけで開発できる。ホストへ入れるツールは最小限 |
| P6 | データ整合性を優先する | DB 書き込みは transaction。排他は明示。時刻は 1 つのタイムゾーン方針に固定 |
| P7 | 外部依存を増やさない | 標準ライブラリ + 実績のある OSS。社内基盤・ベンダー SDK に依存しない |
| P8 | 判断を文章に残す | SHOULD を外れるときは理由を記録する |

---

## 2. ディレクトリ構成

### 2.1 ツリー

```text
{{app}}/
├── cmd/
│   └── {{app}}/main.go                # サーバーのエントリポイント（1 つ）
├── internal/                          # アプリケーションコード（§3.1）
│   ├── controller/                    # gRPC ↔ UseCase の変換
│   ├── usecase/
│   │   ├── usecaseerror/              # UseCase 層の sentinel（§3.4.3）
│   │   └── {{caller}}/{{usecase_group}}_usecase/ # 呼び出し元ごとに束ねる。ユースケース編成 + transaction 境界
│   ├── domain/
│   │   ├── entity/{{feature}}_entity/ # Entity
│   │   ├── vo/                        # Value Object（不変条件・振る舞いを持つ型。§3.4.1）
│   │   ├── types/                     # 検証も振る舞いも持たない型（ID の別名型など。§3.4.1）
│   │   ├── service/{{feature}}_service/ # Domain Service（業務ルールと Repository 呼び出し）
│   │   ├── repository/                # Repository interface と Repository 層の sentinel
│   │   └── domainerror/               # Domain 層の sentinel（業務とカテゴリ）
│   ├── infrastructure/                # Domain interface の実装
│   │   ├── {{feature}}_repository.go
│   │   ├── repository_error.go        # ドライバのエラー → Repository 層 sentinel の変換（全 Repository 共通。§3.5.3）
│   │   ├── clock/ id/ config/
│   │   ├── stub/                      # テスト用 stub。固定値を返す（§7.5）
│   │   ├── <system>_gateway/          # 外部システムとの窓口（§3.5.5）
│   │   └── grpc/                      # gRPC server / REST gateway / interceptor
│   └── di/                            # Wire（server.go / app.go / wire_gen.go）
├── pkg/                               # internal を import しない汎用部品
│   ├── mysql/                         # 接続・DSN・transaction 実行（queryable/ を含む）
│   ├── snowflake/                     # ID 生成
│   └── timezone/                      # タイムゾーンの集約（§9.2）
├── proto/
│   ├── {{svc}}/*.proto                # API 契約の正本
│   └── protodep/googleapis/google/api/ # 依存 proto（pin して commit）
├── gen/grpc/{{svc}}/                  # proto 生成物（手編集禁止・commit）
├── openapi/gen/                       # OpenAPI 生成物（手編集禁止・commit）
├── schema/NN_<table>.sql              # 宣言的スキーマ（mysqldef 入力）
├── seed/NN_<table>.sql                # ローカル初期データ
├── configs/local.yaml                 # 非機密設定。既定はこの 1 ファイル（§9）
├── docker/
│   ├── go/Dockerfile                  # アプリイメージ（multi-stage）
│   ├── mysql/{init.sql,my.cnf}        # ローカル MySQL 設定（data/ は git 管理外）
│   ├── mysqldef/Dockerfile            # スキーマ適用ツール
│   └── protoc-gen/Dockerfile          # protoc + プラグイン
├── test/mock/                         # gomock 生成物（手編集禁止・commit）
├── docker-compose.yaml
├── Makefile
├── gomockhandler.json
├── go.mod / go.sum
├── .gitignore / .dockerignore / .cursorignore / .coderabbit.yaml   # §11
└── README.md
```

### 2.2 規則

| # | 規則 | 強度 |
| --- | --- | --- |
| D1 | 単一 Go module。`go.work` を作らない | MUST |
| D2 | アプリケーションコードは `internal/` に置く。外部公開 API を持たない | MUST |
| D3 | `pkg/` は `internal/` を import しない。業務概念を持たない（接続・ID 生成など技術部品のみ） | MUST |
| D4 | `cmd/` に置くのは配線と起動・停止のみ。業務ロジックを書かない。サーバーのエントリポイントは `cmd/{{app}}/main.go` の 1 つ。環境ごとに main を複製しない | MUST |
| D5 | パッケージは役割ごとに命名する。Entity と Domain Service は集約名（`<feature>_entity` / `<feature>_service`）。UseCase は呼び出し元（`{{caller}}`）の配下に、ユースケース群の名前（`<usecase_group>_usecase`）で置く。3 つの名前を揃えることは要求しない。サフィックスは省略しない | MUST |
| D6 | `gen/`・`openapi/gen/`・`test/mock/`・`internal/di/wire_gen.go` は生成物。手編集しない。commit する | MUST |
| D7 | proto は `proto/{{svc}}/`。依存 proto は `proto/protodep/` に置き、取得元の commit SHA を Makefile で pin する | MUST |
| D8 | スキーマは 1 テーブル 1 ファイル `NN_<table>.sql`（NN は依存順の 2 桁連番） | MUST |
| D9 | バイナリ出力は `bin/{{app}}`、またはリポジトリ直下 `/{{app}}`。いずれも `.gitignore` する | SHOULD |
| D10 | 実行時に必要な静的ファイル（画像など）は専用ディレクトリに置き、Dockerfile の最終 stage へ明示的に COPY する | SHOULD |

---

## 3. アプリケーションコード構成

### 3.1 レイヤと依存

```text
 gRPC / HTTP
     │
 Controller ──▶ UseCase ──▶ Domain Service ──▶ Domain Repository (interface)
     │            │                                    ▲
     │            │                                    └── 実装: Infrastructure ──▶ pkg/*
     │            └──▶ pkg/mysql（transaction を開始するのは UseCase だけ。queryable を Domain Service に渡す）
     └──▶ domainerror
```

| レイヤ | パス | 責務 | import してよい | import してはいけない |
| --- | --- | --- | --- | --- |
| Controller | `internal/controller` | proto 型 ⇄ UseCase 入出力（プリミティブ）の変換、日時の表示整形、sentinel → gRPC status 変換。入力値の検証（日付のパースなど）はしない（UseCase が `vo.Parse*` で行う） | `gen/grpc`、`usecase/*`、`usecase/usecaseerror`、`domain/domainerror`、`pkg/timezone` | `domain/vo`、`domain/types`、`domain/entity`、`domain/service`、`domain/repository`、`infrastructure`、SQL |
| UseCase | `internal/usecase/<caller>/<usecase_group>_usecase` | 処理順序の編成、**transaction の開始と終了**、Domain Service の呼び出し、Input/Output の定義、Input（プリミティブ）→ `vo` / `types` / Entity の変換、Entity → Output（プリミティブ）の詰め替え。Repository は呼ばない | `domain/service`、`domain/entity`、`domain/vo`、`domain/types`、`domain/domainerror`、`pkg/mysql`、`pkg/mysql/queryable`、`pkg/timezone` | `domain/repository`、`infrastructure`、`gen/grpc`、gRPC/HTTP 型、`database/sql` と `sqlx` の直接利用 |
| Domain | `internal/domain/**` | 業務ルール、状態遷移、Repository interface と、その呼び出し（Domain Service）、業務エラー | 標準ライブラリ、`domain` 内、`pkg/mysql/queryable`（Repository と Domain Service の引数型）、`pkg/timezone`（業務ルールで使う日付・時刻の判定） | `infrastructure`、`gen/grpc`、`pkg/mysql`（`queryable` 以外）、DB ドライバー、gRPC/HTTP |
| Infrastructure | `internal/infrastructure/**` | Repository 実装、外部システムの gateway（§3.5.5）、時刻・ID・設定、gRPC server / REST gateway、interceptor | `domain/*`、`pkg/*`、各種ライブラリ | 業務ルールの再定義 |
| DI | `internal/di` | Wire による組み立て | 全レイヤ | — |

- 依存方向の違反は**アーキテクチャテストで検出する**（MUST）。最小要件は「`domain` が `infrastructure` を import しない」。AST の `parser.ImportsOnly` で全 `.go`（`_test.go` を除く）を走査する。次も同様に検査する（SHOULD）: `usecase` が `domain/repository` を import しない、`usecase` が `infrastructure` を import しない、`domain` が `pkg/mysql/queryable` 以外の `pkg/mysql` を import しない、`pkg` が `internal` を import しない、`controller` が `domain/vo` / `domain/types` / `domain/entity` / `domain/service` を import しない。
- Controller に業務分岐を書かない（MUST NOT）。分岐が必要なら Domain Service へ移す。
- `queryable`（§3.5.4）は `sqlx.QueryerContext` / `sqlx.ExecerContext` を埋め込むため、Domain は `queryable` 経由で `sqlx` に間接依存する。これは意図した例外とする（`sqlx.GetContext` / `SelectContext` を使えて Repository 実装が短くなる。標準ライブラリだけの最小 interface にすると、行のスキャンを手書きするかコード生成が必要になる）。

#### 3.1.1 境界で渡す型

境界を越える値の形を次のとおり固定する。内側（Domain）の型を外側（Controller）に出さないことで、入力規則や業務の値の変更が Controller に波及しない。

| 境界 | 渡すもの | import |
| --- | --- | --- |
| Controller → UseCase | `<Op>Input` のプリミティブ（raw value） | Controller は `domain/vo` / `domain/types` / `domain/entity` を import しない |
| UseCase → Domain | `vo`、Entity、`types`。UseCase が Input から `vo.Parse*` / `New*` で変換し、不正な値はここで落とす | UseCase が `domain/vo` / `domain/entity` / `domain/types` を import する |
| Domain → UseCase → Controller | `<Op>Output` のプリミティブ。UseCase が Entity / `vo` から詰め替える | Controller は Domain の型を受け取らない |

- enum も同じ向きにする。Controller は proto の enum を数値にして Input に入れる。UseCase が `vo.Parse*` で `vo` にする。戻りは UseCase が `vo` から数値を取り出して Output に入れ、Controller が数値を proto の enum に `switch` で変換する（§3.9）。
- `domainerror` は上の対象外とする。Controller は `ErrorConverter` のために import してよい（§3.2）。
- `vo` と `types` の分け方は §3.4.1 のとおり。import できる層は同じで、違いは型が不変条件・振る舞いを持つかどうかだけである。

### 3.2 Controller

| 規則 | 強度 |
| --- | --- |
| 1 proto service = 1 Controller 構造体 = 1 ファイル（`<service>_controller.go`）。各構造体は `Unimplemented<Service>Server` を埋め込む | SHOULD |
| 全メソッドの失敗は `ErrorConverter.ToStatus(err)` を通して返す。直接 `status.Error` を作らない | MUST |
| 日時の文字列化は Controller の 1 関数（例 `FormatJST`）に集約する。`timezone.Location`（§9.2）に変換してから整形する。Domain は `time.Time` を扱う | MUST |
| 64bit ID の JSON 文字列化は REST gateway に任せ、Controller で手変換しない | MUST |
| proto の optional / 未設定の表現は Controller が組み立てる（例: ある field が「無効」を示すとき、付随する field を設定しない） | SHOULD |

`ErrorConverter`:

判定は `errors.Is` で、次の順に行う。**ctx 由来のエラーを最初に判定する**（`ErrCanceled` や他のカテゴリ sentinel に包まれていても、中に ctx エラーがあれば 1 で決まる）。カスタムエラー型の `Code` フィールドは使わない。

1. `errors.Is(err, context.Canceled)` は `codes.Canceled`、`errors.Is(err, context.DeadlineExceeded)` は `codes.DeadlineExceeded`。`ErrorInfo` は載せない。
2. `usecaseerror` のカテゴリ sentinel（§3.4.3 の5つ）を、下表の gRPC code にする。`ErrorInfo.Reason` は sentinel の文字列（例 `not_found`）。
3. `domainerror` の業務 sentinel を、業務 sentinel の対応表（§5.4）の gRPC code にする。`ErrorInfo.Reason` は sentinel の文字列。表に無い業務 sentinel も `codes.Internal` + `"internal"`。
4. それ以外（sentinel に包まれていない未知のエラーを含む）は `codes.Internal` + `"internal"`。DB のドライバエラーのうち §3.5.3 の判定表に無いものも、ここで `Internal` になる。

| `usecaseerror` | gRPC code |
| --- | --- |
| `ErrNotFound`（`not_found`） | `NotFound` |
| `ErrConflict`（`conflict`） | `Aborted` |
| `ErrInvalidArgument`（`invalid_argument`） | `InvalidArgument` |
| `ErrCanceled`（`canceled`） | `Canceled` |
| `ErrUnavailable`（`unavailable`） | `Unavailable` |

- 変換時のログは 1 回だけ出す（`err.Error()` のみ。資格情報を含めない）。レベルは §10 に従う。

### 3.3 UseCase

#### 3.3.1 実装例

```go
// internal/usecase/{{caller}}/{{usecase_group}}_usecase/{{usecase_group}}.go
type UseCase struct {
	db      *mysql.Clients       // Writer / Reader。transaction を開始できるのは UseCase だけ
	service feature_service.Feature // DB 操作は Domain Service が Repository を呼んで行う
	clock   Clock                // 時刻・ID は UseCase 側に consumer-defined interface を置く
	ids     IDGenerator
}

// internal/usecase/{{caller}}/{{usecase_group}}_usecase/create_feature.go   ← 1 ユースケース 1 ファイル `<verb>_<noun>.go`
func (u *UseCase) Create(ctx context.Context, in CreateInput) (*CreateOutput, error) {
	now := u.clock.Now()
	id := u.ids.NewID()

	// Input（プリミティブ）→ vo / types。不正な値はここで落とす（domainerror.ErrInvalidArgument → usecaseerror）
	domainIn, err := in.toDomain()
	if err != nil {
		return nil, toUseCaseError(err)
	}

	// transaction の外: 事前読み取りは Reader の queryable を Domain Service に渡す
	children, err := u.service.FindChildren(ctx, u.db.Reader.ReadQueryable(ctx), in.ChildIDs())
	if err != nil {
		return nil, toUseCaseError(err) // domainerror → usecaseerror。§3.4.3
	}

	// transaction の内: 書き込み。コールバックの wq を Domain Service に渡す。Repository は呼ばない
	var created *feature_entity.Feature
	err = u.db.Writer.RunInWriteTx(ctx, func(ctx context.Context, wq queryable.WriteQueryable) error {
		var err error
		created, err = u.service.Create(ctx, wq, domainIn, children, now, id)
		return err
	})
	if err != nil {
		return nil, toUseCaseError(err)
	}
	return newCreateOutput(created), nil
}
```

#### 3.3.2 規則

| 規則 | 強度 |
| --- | --- |
| **transaction を開始するのは UseCase だけ**。`pkg/mysql` の `RunInWriteTx` を呼ぶ。Domain Service / Repository / Controller は開始しない | MUST |
| **Repository を呼ばない**。`domain/repository` を import しない。DB の読み書きは Domain Service のメソッドを呼ぶ | MUST NOT |
| Domain Service には、transaction の外では `Reader.ReadQueryable(ctx)`、transaction の中ではコールバックの `wq` を渡す。Domain Service の中で別の `queryable` を取り直さない | MUST |
| 1 つの論理処理で `RunInWriteTx` を入れ子にしない。独立した原子性が必要な場合に限り、UseCase が複数回を**直列に**呼ぶ | MUST |
| コミット・ロールバックを呼び出し側で書かない。コールバックが `error` を返せばロールバック、`nil` ならコミットされる | MUST |
| 読み取りだけの処理は transaction を開かず、`Reader.ReadQueryable(ctx)` を Domain Service に渡す | MUST |
| 事前読み取りと入力検査は transaction の外で終える。transaction の中は書き込みと、更新直前の整合性確認（`FOR UPDATE`、TOCTOU 回避）に限る。集計・一覧などの重い読み取りを中に入れない | SHOULD |
| 入出力は UseCase パッケージ内で `<Op>Input` / `<Op>Output` として定義する。フィールドはプリミティブ（数値・文字列・真偽値・`time.Time`）とそのスライス、および入れ子の Input / Output 構造体に限る。`vo` / `types` / Entity を載せない（enum は数値で持つ）。Input → `vo` / `types` / Entity の変換（`vo.Parse*`、`New*`。Input の `toDomain()` など）と、Entity → Output の詰め替えは UseCase の中で行う（§3.1.1） | MUST |
| 時刻・ID 生成・乱数は、UseCase パッケージに小さな interface（`Clock` / `IDGenerator`）を置き、Wire で実装を束縛する。取得した値を Domain Service の引数で渡す。`time.Now()` を UseCase / Domain で直接呼ばない | MUST |
| 構造体名は常に `UseCase`、コンストラクタは `New`。具象型のまま Controller に渡す。UseCase を interface にしない | MUST |
| 1 ユースケース 1 ファイル。共有の型・構造体は `<feature>.go` | MUST |
| 外部 API 呼び出しを transaction の中に入れるかは、プロジェクトで決めて記録する（§6.5） | MUST |
| Domain Service のカテゴリ sentinel は、返す前に `toUseCaseError` で `usecaseerror` の同名 sentinel に包む（§3.4.3）。業務 sentinel は `domainerror` のものを中に残し、そのまま返す | MUST |

### 3.4 Domain

#### 3.4.1 パッケージ

| パッケージ | 内容 | 命名 |
| --- | --- | --- |
| `entity/<feature>_entity` | 識別子を持つ構造体。振る舞いは最小限。パッケージ名は集約名 | `Feature`, `Child` |
| `vo` | 不変条件や振る舞いを持つ型。不正な値を拒否する（`Parse*` / `New*`）、または値から導く振る舞い（`Contains` など）を持つ。型を持たない純関数は置かない（業務ルールは Domain Service。§3.4.2） | `FeatureStatus`（列挙値を検証する）、`DateRange`（範囲の整合を検証し、`Contains` を持つ） |
| `types` | 検証も振る舞いも持たない型。意味を区別するための名前付きの型（ID の別名型など）。`Parse*` / `New*` / `Restore*` を持たない | `FeatureID`（`uint64` の別名型） |
| `service/<feature>_service` | 集約の業務ルールと、そのルールに必要な Repository 呼び出し。transaction は開始しない。時刻と ID は引数で受け取る | interface 名 = 集約名（`Feature`）、実装は非公開構造体、`New(...) Feature` |
| `repository` | Repository interface（`queryable` を引数に取る）と、Repository 層のカテゴリ sentinel | `<Feature>Repository`、`ErrNotFound` など |
| `domainerror` | Domain 層の sentinel。カテゴリ5つと、ドメイン層の生成時に足す業務 sentinel | `Err*` |

#### 3.4.2 Domain Service

```go
// DB 操作はここで Repository を呼ぶ。transaction は開始しない。queryable は UseCase から受け取る。
type Feature interface {
	FindChildren(ctx context.Context, rq queryable.ReadQueryable, ids []uint64) ([]child_entity.Child, error)
	Create(ctx context.Context, wq queryable.WriteQueryable, in FeatureInput, children []child_entity.Child, now time.Time, id uint64) (*feature_entity.Feature, error)
}

type feature struct {
	features repository.FeatureRepository
	children repository.ChildRepository
}

func (s *feature) FindChildren(ctx context.Context, rq queryable.ReadQueryable, ids []uint64) ([]child_entity.Child, error) {
	children, err := s.children.FindByIDs(ctx, rq, ids)
	if err != nil {
		return nil, toDomainError(err) // repository sentinel → domainerror。§3.4.3
	}
	return children, nil
}

func (s *feature) Create(ctx context.Context, wq queryable.WriteQueryable, in FeatureInput, children []child_entity.Child, now time.Time, id uint64) (*feature_entity.Feature, error) {
	// 複数 Entity にまたがる判定は Domain Service のルール（children と in の突き合わせなど。省略）。
	// 1 つの Entity で完結する検証は Entity の New* の中で行う
	created, err := feature_entity.NewFeature(id, in.Name(), now)
	if err != nil {
		return nil, err
	}
	if err := s.features.Insert(ctx, wq, created); err != nil {
		return nil, toDomainError(err)
	}
	return created, nil
}
```

| 規則 | 強度 |
| --- | --- |
| DB の読み書きは Domain Service が Repository を呼んで行う。UseCase / Controller は Repository を呼ばない | MUST |
| Domain Service は transaction を開始しない。`*mysql.Clients` を保持しない。`queryable` は引数で受け取り、それだけを Repository に渡す | MUST |
| 時刻取得、ID 生成、外部 I/O（gateway の直接呼び出し）を持たない。時刻と ID は引数で受け取る | MUST |
| 業務ルールのうち Entity に属するものは Entity のメソッドに置く。Domain Service は Repository の呼び出し順と、Entity に属さないルール（複数 Entity にまたがる判定など）を置く | SHOULD |
| 業務エラーは `domainerror` の sentinel（`errors.New`）で返す。同値判定は `errors.Is` | MUST |
| Repository の sentinel は `toDomainError` で `domainerror` の同名カテゴリ sentinel に `fmt.Errorf("%w: %w", ...)` で包む。Repository の sentinel をそのまま返さない | MUST |
| 入力の不正は `domainerror.ErrInvalidArgument`（原因があるときは `fmt.Errorf("%w: %w", domainerror.ErrInvalidArgument, 原因)`）。技術的失敗もカテゴリ sentinel に包む | MUST |
| ステータスなどの列挙値は VO で検証する。不正値を黙って通さない | MUST |

#### 3.4.2a Entity の生成（`New*` / `Restore*`）

Entity は、新規生成と復元の2つの関数で作る。どちらも Entity パッケージの関数で行い、フィールドは非公開にする。

| 関数 | 使う場面 | 検証 | 戻り値 |
| --- | --- | --- | --- |
| `New<Entity>` | 新規作成。UseCase / Domain Service の経路と、CLI・バッチ・マイグレーションを含む | `New*` の中で行う。違反は `fmt.Errorf("%w: %w", domainerror.ErrInvalidArgument, 原因)` などの sentinel で返す | `(*T, error)` |
| `Restore<Entity>` | Repository が DB の行から Entity に戻すとき | しない。保存済みの値を組み立てるだけ | `*T` |

| 規則 | 強度 |
| --- | --- |
| `Restore*` は Repository 実装だけが呼ぶ。Domain Service / UseCase / Controller / CLI / バッチからは呼ばない | MUST |
| 任意の setter（フィールドを個別に書き換える `Set*`）を置かない。状態の変更は、業務上の意図を表すメソッド（例 `Rename`、`Deactivate`）で行い、その中で検証してからフィールドへ代入する。フィールドへ代入してよいのは `New*`、`Restore*`、意図を表すメソッドの内部だけ | MUST |
| 値オブジェクト（VO）も同じ形にする。`New*` は検証付き、`Restore*` は復元専用。任意の setter は置かない | SHOULD |

```go
// internal/domain/entity/feature_entity/feature.go
type Feature struct {
	id        uint64 // フィールドは非公開
	name      string
	createdAt time.Time
}

// 新規生成。検証付き。UseCase / Domain Service / CLI / バッチはこれを使う
func NewFeature(id uint64, name string, createdAt time.Time) (*Feature, error) {
	if name == "" {
		return nil, fmt.Errorf("%w: %w", domainerror.ErrInvalidArgument, errors.New("name must not be empty"))
	}
	return &Feature{id: id, name: name, createdAt: createdAt}, nil
}

// 復元専用。Repository の行 → Entity でだけ呼ぶ。検証しない
func RestoreFeature(id uint64, name string, createdAt time.Time) *Feature {
	return &Feature{id: id, name: name, createdAt: createdAt}
}
```

#### 3.4.3 sentinel error

エラーは sentinel（`errors.New` のパッケージ変数）で定義する。`Code` フィールドを持つカスタムエラー型は使わない。sentinel は Domain、Repository、UseCase の3層に置く。同値判定は `errors.Is`。業務 sentinel は、UseCase 層の sentinel を足すまで `domainerror` のまま返す。

カテゴリは次の5つに固定する。3層で同じ文字列にする。業務 sentinel（名前と文字列は本書では決めない）は、ドメイン層の生成時に `domainerror` と、それを返す UseCase の `usecaseerror` へ足す。

| sentinel | 文字列 | いつ使うか |
| --- | --- | --- |
| `ErrNotFound` | `not_found` | 行が無い、更新対象が無い |
| `ErrConflict` | `conflict` | 一意制約違反、デッドロック、ロック待ちタイムアウトなどの競合 |
| `ErrInvalidArgument` | `invalid_argument` | 保存できない値、入力の不正 |
| `ErrCanceled` | `canceled` | ctx 由来の中断（`context.Canceled` / `context.DeadlineExceeded`）。gRPC code は sentinel ではなく ctx エラー自体で決める（§3.2） |
| `ErrUnavailable` | `unavailable` | 外部システム（gateway）に繋がらない、外部が応答しない（§3.5.5）。DB のドライバエラーには、§3.5.3 の判定表に載せたものにだけ使う |

```go
// internal/domain/domainerror/error.go（repository と usecaseerror も同じ5つ）
var ErrNotFound = errors.New("not_found")

// Domain Service: Repository 層 → Domain 層。UseCase の toUseCaseError（Domain 層 → UseCase 層）も同形
func toDomainError(err error) error {
    switch {
    case errors.Is(err, repository.ErrNotFound):
        return fmt.Errorf("%w: %w", domainerror.ErrNotFound, err)
    case errors.Is(err, repository.ErrConflict):
        return fmt.Errorf("%w: %w", domainerror.ErrConflict, err)
    case errors.Is(err, repository.ErrInvalidArgument):
        return fmt.Errorf("%w: %w", domainerror.ErrInvalidArgument, err)
    case errors.Is(err, repository.ErrCanceled):
        return fmt.Errorf("%w: %w", domainerror.ErrCanceled, err)
    case errors.Is(err, repository.ErrUnavailable):
        return fmt.Errorf("%w: %w", domainerror.ErrUnavailable, err)
    default:
        return err // カテゴリ外はそのまま返す。ErrorConverter が Internal にする（§3.2）
    }
}

// toUseCaseError は 5 カテゴリを usecaseerror の同名 sentinel に包む。
// default は、業務 sentinel（UseCase 層の sentinel を足してから包む）、ctx エラー、未知のエラーをそのまま返す。後 2 者は ErrorConverter が判定する（§3.2）
```

| 規則 | 強度 |
| --- | --- |
| sentinel は `var Err* = errors.New("<snake_case>")`。比較は `errors.Is` | MUST |
| カテゴリ5つは `domainerror`、`repository`、`usecaseerror` の3パッケージに置く | MUST |
| 層を越えるときは自層の同名 sentinel に `fmt.Errorf("%w: %w", <自層の sentinel>, err)` で包む（sentinel と原因の両方を `errors.Is` / `errors.As` で辿れる。複数の `%w` は Go 1.20 以降）。sentinel を付けず原因だけ残すときは `fmt.Errorf("<動詞> <対象>: %w", err)` | MUST |
| エラーを `errors.Join` や `%v` で包まない（`errors.Join` は `Error()` が改行区切りになり、1 行 1 イベントのログ（§10）に反する。`%v` は文字列化されて `errors.Is` が辿れない） | MUST NOT |
| 業務 sentinel の一覧と gRPC / HTTP の対応は表で残す（§5.4。記録先は本書の外）。業務ルールに対応するものだけを足し、本書では先に作らない | MUST |

エラーコード ⇄ gRPC code ⇄ HTTP status の対応表を必ず持つ（§5.4。記録先は本書の外）。カテゴリ5つの gRPC code は §3.2 で固定する。

### 3.5 Infrastructure（Repository、pkg/mysql、Gateway）

#### 3.5.1 Repository の実装例

```go
// domain/repository/feature_repository.go（interface。引数の queryable で読み書きを型として区別する）
type FeatureRepository interface {
	FindChild(ctx context.Context, rq queryable.ReadQueryable, id uint64) (*child_entity.Child, error)
	Insert(ctx context.Context, wq queryable.WriteQueryable, feature *feature_entity.Feature) error
}

// infrastructure/feature_repository.go（実装。状態を持たない）
type featureRepository struct{}

func NewFeatureRepository() repository.FeatureRepository { return &featureRepository{} }

type childRow struct { // DB 行。db タグを持つ。Entity とは別型
	ChildID uint64 `db:"child_id"`
	// ...
}

func (r childRow) toEntity() *child_entity.Child { /* Restore* で復元する */ }

func (r *featureRepository) FindChild(ctx context.Context, rq queryable.ReadQueryable, id uint64) (*child_entity.Child, error) {
	const query = `SELECT ... FROM children WHERE child_id = ?`
	var row childRow
	if err := sqlx.GetContext(ctx, rq, &row, query, id); err != nil {
		return nil, toRepositoryError("select child", err) // ドライバのエラーは共通の変換関数に通す（判定表は下）
	}
	return row.toEntity(), nil
}
```

#### 3.5.2 Repository の規則

| 規則 | 強度 |
| --- | --- |
| コンストラクタは **Domain の interface を返す**。実装構造体は非公開 | MUST |
| 1 Repository = 1 ファイル `<feature>_repository.go`（`internal/infrastructure/` 直下・フラット） | MUST |
| DB に触る全メソッドは、第 1 引数 `ctx`、第 2 引数に `queryable.ReadQueryable`（読み取り）または `queryable.WriteQueryable`（書き込み）を受け取り、**それだけ**を使って実行する。DB 接続を構造体に保持しない。`ctx` に transaction を載せて取り出す方式を使わない | MUST |
| 書き込み transaction の中で呼ばれる読み取りメソッドには、コールバックの `wq` が渡される（`WriteQueryable` は `ReadQueryable` を満たす） | MUST |
| SQL は `const query` に書き、**プレースホルダ（`?`）で値を渡す。文字列連結しない** | MUST |
| DB 行 → Entity の変換は `<x>Row.toEntity()` に集約する。`SELECT *` を使わず列を明示する | MUST |
| ドライバのエラーは `toRepositoryError` で変換し、下の判定表に従う。**ctx 由来を最初に判定する**。表に無いエラーを `Unavailable` などの sentinel に包まない（`%w` で返し、`ErrorConverter` に `Internal` にさせる） | MUST |
| `UPDATE` の `RowsAffected()==0` は、ドライバのエラーではないので、Repository のメソッドが `repository.ErrNotFound` を返す | MUST |
| Repository 内で transaction を開始しない | MUST NOT |
| 行ロックが必要な読み取りは、メソッド名に意図を出す（例 `Lock...`）。`FOR UPDATE` は transaction 内でのみ使う | MUST |

#### 3.5.3 Repository のエラー判定表

Repository のエラー判定表（`toRepositoryError` は上から順に判定する）。`toRepositoryError` は全 Repository 共通の 1 関数で、`internal/infrastructure/repository_error.go` に置く。ドライバ `github.com/go-sql-driver/mysql` は、`pkg/mysql` と区別するため別名 `mysqldriver` で import する。

| 順 | 条件 | 返すもの |
| --- | --- | --- |
| 1 | `errors.Is(err, context.Canceled)` または `errors.Is(err, context.DeadlineExceeded)` | `fmt.Errorf("%w: <動詞> <対象>: %w", repository.ErrCanceled, err)` |
| 2 | `errors.Is(err, sql.ErrNoRows)` | `fmt.Errorf("%w: <動詞> <対象>: %w", repository.ErrNotFound, err)` |
| 3 | `*mysql.MySQLError`（ドライバ）の `Number` が 1062（一意制約違反）、1213（デッドロック）、1205（ロック待ちタイムアウト） | `fmt.Errorf("%w: <動詞> <対象>: %w", repository.ErrConflict, err)` |
| — | 上記以外 | sentinel に包まず `fmt.Errorf("<動詞> <対象>: %w", err)` で返す（最終的に `Internal`。§3.2） |

- 値の不正（1264 / 1406）など、表に無い MySQL エラー番号は `Internal` になる。`vo` と `New*` の検証漏れを示すので、`ErrInvalidArgument` にしない。分類を足すときは、この表と `toRepositoryError` を同時に直す。
- 1213 / 1205 を `ErrConflict`（`Aborted`）にする理由: 並行処理による中断で、呼び出し側が再試行すれば成功し得るため。バグを示す `Internal` と区別する。サーバー内では再試行しない。
- 順 1 を先に置く理由: ctx 由来のエラーは、クライアントの切断や期限切れという呼び出し側の事情で、DB や SQL の障害ではない。他の判定や「表に無いエラーは `Internal`」より先に分け、`Canceled` / `DeadlineExceeded` として返す（障害として `Error` ログやアラートに出さない。§3.2、§10）。

#### 3.5.4 pkg/mysql と transaction

```go
// pkg/mysql/queryable/queryable.go  — interface だけのパッケージ。Repository interface の引数型として Domain からも import できる
type ReadQueryable interface{ sqlx.QueryerContext }                       // QueryContext / QueryxContext / QueryRowxContext
type WriteQueryable interface{ ReadQueryable; sqlx.ExecerContext }        // + ExecContext。*sqlx.DB と *sqlx.Tx が満たす

// pkg/mysql — いずれも interface（モック可能にする）
type ReadonlyClient interface {
	ReadQueryable(ctx context.Context) queryable.ReadQueryable
}
type WritableClient interface {
	ReadonlyClient
	WriteQueryable(ctx context.Context) queryable.WriteQueryable
	RunInWriteTx(ctx context.Context, fn func(ctx context.Context, wq queryable.WriteQueryable) error) error
}
type Clients struct {
	Writer WritableClient // 書き込み。transaction はここから開く
	Reader ReadonlyClient // 純粋な読み取り。Writer と同じホストに接続する（§6.1、§9）
}
```

- 接続: `sqlx.Open("mysql", DSN)` → pool 設定 → `PingContext`（5 秒）。DSN は `parseTime=true&loc=<URL エンコードしたタイムゾーン>&charset=utf8mb4` を必ず付ける（MUST）。
- `RunInWriteTx` の契約（MUST）:
  - `BeginTxx` → `fn` が `nil` を返せば `Commit`、`error` を返せば `Rollback` して元のエラーを返す。`panic` は `Rollback` して再 panic する。
  - `BeginTxx` と `Commit` の失敗は、`fmt.Errorf("begin transaction: %w", err)` / `fmt.Errorf("commit transaction: %w", err)` で返す。sentinel には包まない（`pkg/mysql` は `repository` を import できない。D3）。ctx 由来なら `ErrorConverter` が `Canceled` / `DeadlineExceeded` にし、それ以外は `Internal` になる（§3.2）。接続断も `Internal` になり、`Unavailable` にしない（「未知の DB エラーは `Internal`」の帰結。DB 障害は `Internal` のログとして出る）。
  - `Rollback` 自体が失敗した場合は、元のエラーを `%w` で包んで返し、ログにも出す。
  - transaction を `ctx` に載せない。呼び出し側は渡された `wq` だけを使う。
  - transaction が `ctx` に載らないため、ネストは検出できない（別接続で新しい transaction が始まり、ロック待ちでデッドロックし得る）。ネスト禁止は UseCase の規則（§3.3）で担保する。
- `pkg/mysql` は DSN 組み立てと `RunInWriteTx` の契約（コミット / ロールバック / panic）のテストを持つ。`go-sqlmock` で行い、実 DB には接続しない。

#### 3.5.5 Gateway（外部システムとのやりとり）

外部システム（API、ファイル、メッセージなど）とやりとりする部品（§0.4）。DB も外部システムだが gateway は作らず、Repository が `queryable` で直接アクセスする（§3.5.2）。

外部システムを呼ぶ経路は 1 本に固定する。gateway は `infrastructure` の中に閉じ、Domain 側の口は Repository interface にする。

##### 3.5.5.1 呼び出し経路と実装例

```text
UseCase → Domain Service → Repository interface（Domain。Domain の型だけ）
                                 ▲
                                 └── 実装: infrastructure の Repository ──▶ <system>_gateway（interface と実装は同一ファイル）
```

```go
// internal/infrastructure/notice_gateway/notice_gateway.go（interface と実装は同じファイル）
type NoticeGateway interface {
	Send(ctx context.Context, payload NoticePayload) error // NoticePayload は gateway パッケージ内の型。Domain に出さない
}

type noticeGateway struct { /* HTTP クライアント、タイムアウト、リトライ設定など */ }

func NewNoticeGateway(/* ... */) NoticeGateway { return &noticeGateway{ /* ... */ } }

// internal/domain/repository/feature_notice_repository.go（interface。Domain の型だけ。DB に触らないので queryable を取らない）
type FeatureNoticeRepository interface {
	Publish(ctx context.Context, feature *feature_entity.Feature) error
}

// internal/infrastructure/feature_notice_repository.go（実装。gateway を呼ぶ）
type featureNoticeRepository struct{ gateway notice_gateway.NoticeGateway }

func (r *featureNoticeRepository) Publish(ctx context.Context, feature *feature_entity.Feature) error {
	return r.gateway.Send(ctx, notice_gateway.NewNoticePayload(feature)) // Entity → DTO の変換は gateway 側の 1 か所
}
```

##### 3.5.5.2 規則

| 規則 | 強度 |
| --- | --- |
| 置き場所は `internal/infrastructure/<system>_gateway/`。`<system>` は相手のシステム名 | MUST |
| gateway の interface と実装は同じファイルに書く（interface、非公開の実装構造体、`New*` の順）。interface を Domain、`usecase`、`pkg` に置かない | MUST |
| 外部システムを使う Domain 側の口は Repository interface（`domain/repository`）とする。Repository interface は Domain の型だけで定義し、gateway の型を引数・戻り値に使わない。Repository 実装が gateway を呼ぶ | MUST |
| DB に触らない Repository のメソッド（外部システムへの送信など）は、`queryable` を引数に取らない | MUST |
| UseCase / Domain Service / Controller は gateway を呼ばず、import しない。外部システムは Repository 経由で呼ぶ（interface が `infrastructure` にあるため、UseCase は import できない。§3.1） | MUST |
| transaction のコミット後に外部システムへ送る処理は、UseCase が transaction の外で Domain Service のメソッドを呼び、Domain Service が Repository の外部向けメソッドを呼ぶ。UseCase は Repository を呼ばない（§3.3）ので、この経路になる | MUST |
| 呼び出しのタイムアウトは定数にせず、設定ファイル（§9）に置く。gateway ごとに指定でき、`http.Client.Timeout` または `context.WithTimeout` で適用する | MUST |
| リトライは gateway パッケージ内の 1 関数にまとめ、呼び出しごとに同じループを書かない。`pkg` には切り出さない。待機は `select` で `ctx.Done()` を見る。`time.Sleep` を使わない。回数と待機間隔は設定から受け取る | MUST |
| 外部システムへ副作用のある呼び出し（書き込み・送信・削除）は、冪等性キーを使うか、リトライしてよいかを、表で残す（呼び出し / 冪等性キー / リトライ可否。記録先は本書の外）。リトライするのは、表で「可」とした呼び出しだけにする | MUST |
| 外部システムの DTO（リクエスト・レスポンスの型）は gateway パッケージ内の非公開型にする。DTO ⇄ Entity の変換は、gateway ごとに 1 か所へ集約する（例: `<x>DTO.toEntity()` / `new<X>DTO(entity)`）。DTO を Controller / UseCase / Domain に出さない | MUST |
| 外部システムのエラー（HTTP ステータス、外部の gRPC `status`、SDK のエラー型）を gateway の外へ出さない。Repository 層のカテゴリ sentinel に `fmt.Errorf("%w: %w", <sentinel>, err)` で包んで返す。判定は次の順に行う。① ctx 由来（`errors.Is(err, context.Canceled)` / `context.DeadlineExceeded`）は `repository.ErrCanceled`（**最初に判定する**）。② 繋がらない、外部が応答しない（外部の gRPC `Unavailable` / `DeadlineExceeded` の `status`、HTTP の接続失敗・タイムアウト。外部の `status` の `DeadlineExceeded` は ctx のエラーではない）は `repository.ErrUnavailable`。③ 外部が返した NotFound・競合・引数の不正は、対応するカテゴリ。④ 判定できないものは sentinel に包まず `%w` で返す（最終的に `Internal`。§3.2）。`%v` で包まない | MUST |

### 3.6 gRPC サーバーと REST gateway（`internal/infrastructure/grpc`）

| 要素 | 規則 | 強度 |
| --- | --- | --- |
| gRPC server | `grpc.NewServer(grpc.ChainUnaryInterceptor(RequestLog, Recovery))`。**RequestLog が外側、Recovery が内側**（panic を回収した結果の status を RequestLog が記録する） | MUST |
| RequestLog | `method` / `code` / `elapsed_ms` を Info で出す（§10） | MUST |
| Recovery | panic を回収し、`panic` と `stack` を Error ログに出し、`codes.Internal` / `"internal"` を返す | MUST |
| 登録 | 全 service、`grpc.health.v1`（`""` を SERVING）、`reflection` を登録する | MUST |
| REST gateway の接続 | 同一プロセス内から `grpc.NewClient("127.0.0.1:<grpc_port>", insecure)` で loopback 接続する | MUST |
| marshaler | `protojson`: `UseProtoNames` / `UseEnumNumbers` / `EmitUnpopulated`、unmarshal は `DiscardUnknown` | SHOULD |
| エラー | `runtime.WithErrorHandler` で `status` → HTTP status と `{"error":"<reason>"}` を組み立てる。grpc-gateway 標準のエラー形式は使わない | SHOULD |
| ミドルウェア | 外側から `timeout` → `originGate` → `cors` → ルーティング。`http.Server.ReadHeaderTimeout` を必ず設定する | MUST |
| CORS | `rs/cors`。許可 origin は設定ファイルの allowlist のみ。`*` を使わない。許可外 origin は 403 | MUST |
| 認証 | 方針はプロジェクトで決める。無い場合は「無い」と明記する（暗黙にしない） | MUST |

gRPC と REST gateway は**同一プロセス**にする。サーバーのエントリポイントは 1 つで、両方の listener を起動する（§3.8）。REST gateway を別プロセス・別コンテナに分けない。

プロセス分離は、規模が大きくなり REST gateway だけを独立してスケールさせる必要が出てから検討する。初期構成では分離しない。

### 3.7 DI（Wire）

| 規則 | 強度 |
| --- | --- |
| `internal/di/server.go` に `//go:build wireinject` を付け、`Initialize(cfg config.Config, logger *slog.Logger) (*Application, error)` に `wire.Build` を書く。設定は `main` が読んで引数で渡す。DI の provider の中で設定ファイルや環境変数を読まない（§3.8） | MUST |
| UseCase が使う port interface（`Clock` / `IDGenerator` など）と `*mysql.Clients` の `Writer` / `Reader` は、`wire.Bind` または provider で実装に束縛する | MUST |
| `internal/di/app.go` に `Application`（`GRPC` / `HTTP` / `DB` / `Logger` / アドレス）、`Close()`、環境依存の provider（`provideMySQL` など）を置く | MUST |
| `wire_gen.go` は手編集しない（`make wire` で生成して commit） | MUST |
| グローバル変数・`init()` でのシングルトン生成をしない（純粋な定数設定と、`pkg/timezone` の `Location`（§9.2）を除く） | SHOULD |

### 3.8 エントリポイント

#### 3.8.1 サーバー（`cmd/{{app}}/main.go`）

起動口は 1 つ。起動・停止の手順を固定する。ローカル用に main を複製しない。ローカルとの差は設定ファイルと環境変数で吸収する（§9）。

1. `*slog.Logger` を作る（§10）。ロガーの出力形式は設定に依存させない（§10 でプロジェクトごとに固定する）。
2. `signal.NotifyContext(ctx, SIGTERM, SIGINT)`。
3. `config.Load()` で設定を読む（§9）。失敗なら標準エラーに出して `os.Exit(1)`。
4. `timezone.Init(<MYSQL_TZ の値>)`（§9.2）。DB 接続より前に行う。失敗なら標準エラーに出して `os.Exit(1)`。
5. `di.Initialize(cfg, logger)`。失敗なら標準エラーに出して `os.Exit(1)`。`defer app.Close()`。DB 接続はこの中で行う。Snowflake のノード番号は §9.1 で決め（provider の中）、決定に失敗したときも `Initialize` がエラーを返し、ここで起動を止める。
6. `net.Listen("tcp", app.GRPCAddress)` → gRPC `Serve` と REST gateway `ListenAndServe` をそれぞれ goroutine で起動し、エラーを `errCh` に流す。
7. `ctx.Done()` または `errCh` で停止。`http.ErrServerClosed` は異常として扱わない。
8. タイムアウト付き（既定 5 秒）で `HTTP.Shutdown` → `GRPC.GracefulStop()`。

手順 3〜5 の順序は固定する（MUST）。`timezone.Init` を `di.Initialize` の中に入れない。DB 接続は `Initialize` の中で行うため、`Initialize` の前に `timezone.Init` を済ませておかないと、DSN の `loc=` と `pkg/timezone` の `Location` が食い違う時間帯ができる。

### 3.9 命名・コーディング規約

| 項目 | 規則 | 強度 |
| --- | --- | --- |
| ファイル名 | `snake_case.go`。1 ユースケース/1 Repository = 1 ファイル。Controller のファイル名は §3.2 | MUST |
| パッケージのディレクトリ | ディレクトリ名はパッケージ名と一致させる。`snake_case`。ハイフンは使わない。`cmd/{{app}}` は package `main` の起動口であり、名前は §0.2 に従う | MUST |
| パッケージ名 | 命名は D5 に従う。アンダースコアを許容する（Go の慣習より構成の一意性を優先） | MUST |
| エラー | 包み方は §3.4.3。`panic` はプログラムエラー専用 | MUST |
| enum | DB に保存する値、外部 API の値、proto の enum に対応する値は `iota` を使わず、数値を明示する。外部との変換は `switch` で行い、`pb.X(v)` のような型キャストをしない。変換の分担は §3.1.1。内部だけで閉じる enum は `iota` を使ってよい | MUST |
---

## 4. ライブラリ・エコシステム

### 4.1 採用ライブラリ

> バージョンは 2026-11 時点の pin 例であり、正本ではない。版の正本は、プロジェクトの宣言ファイル（`go.mod`、`docker/**/Dockerfile`、`Makefile`）である。新規採用時は最新安定版を確認して pin し直してよい。ただし同一ファミリは揃える（§4.3）。

| 用途 | ライブラリ | pin 例 | 備考 |
| --- | --- | --- | --- |
| 言語 | Go | 1.27.3 | `go.mod` の `go`、Dockerfile、Makefile の `GOTOOLCHAIN` を一致させる |
| RPC | `google.golang.org/grpc` | v1.85.0 | |
| Protobuf runtime | `google.golang.org/protobuf` | v1.36.12 | |
| REST gateway | `github.com/grpc-ecosystem/grpc-gateway/v2` | v2.33.0 | runtime と generator は同一 version |
| 共通 proto | `google.golang.org/genproto/googleapis/{api,rpc}` | go.mod 参照 | `errdetails` / `annotations` |
| DB ドライバー | `github.com/go-sql-driver/mysql` | v1.10.1 | |
| SQL 拡張 | `github.com/jmoiron/sqlx` | v1.4.0 | ORM は使わない（§4.2） |
| DI | `github.com/google/wire` | v0.7.0 | |
| Mock | `go.uber.org/mock` | v0.6.0 | 管理に `gomockhandler` v1.7.0 |
| ログ | `log/slog`（標準ライブラリ） | Go に従う | 外部のログライブラリを足さない。ハンドラとフォーマットは §10 |
| 環境変数 | `github.com/kelseyhightower/envconfig` | v1.4.0 | prefix は `{{ENV_PREFIX}}` |
| CORS | `github.com/rs/cors` | v1.11.1 | |
| 採番 ID | `github.com/bwmarrin/snowflake` | v0.3.0 | 主キー用。`NodeBits = 6`、`StepBits = 16`。ノード番号の決め方は §9.1 |
| 識別子 | `github.com/oklog/ulid/v2` | v2.1.2 | 時系列ソート可能な文字列キー用 |
| テスト比較 | `github.com/google/go-cmp` | 必要時に追加 | |
| 設定ファイル（YAML） | `gopkg.in/yaml.v3` | 採用時に pin | 不明キーはエラー（§9） |

### 4.2 採用しないもの

| 不採用 | 理由 |
| --- | --- |
| ORM（GORM / ent など） | SQL と Repository 境界を明示する方針。`sqlx` で足りる |
| 逐次 migration ツール（goose / migrate など） | スキーマは宣言的に管理する（§6.2） |
| `plugins=grpc`（旧 protoc-gen-go） | `protoc-gen-go` と `protoc-gen-go-grpc` を分ける |
| 手書き REST ハンドラーで API 契約を定義すること | proto-first。REST は grpc-gateway で生成 |
| 社内基盤ライブラリ・ベンダー SDK・APM エージェント | P7 |
| `logrus` などの外部ログライブラリ | 標準の `log/slog` に統一する。ログの仕組みを二重に持たない |

### 4.3 バージョン整合ルール

1. `grpc` 本体と `protoc-gen-go-grpc` の version を揃える。`protoc-gen-go-grpc` は grpc-go のネストしたモジュールなので、**タグ付きソースから入れる**。
2. `protoc-gen-go` と `google.golang.org/protobuf`、grpc-gateway の runtime と generator（`protoc-gen-grpc-gateway` / `protoc-gen-openapiv2`）はそれぞれ同一 version。
3. Go のバージョンは `go.mod` / `docker/go/Dockerfile` / `docker/protoc-gen/Dockerfile` / `Makefile` の `GOTOOLCHAIN` の 4 箇所で一致させる。
4. 開発ツール（wire / mockgen / gomockhandler / goimports / staticcheck）は `make tools` で**すべて version 指定**して入れる（`@latest` 禁止）。

### 4.4 Lint / 静的検査

`goimports -l`（差分があれば失敗。`wire_gen.go` は除外）+ `go vet ./...` + `staticcheck ./...`。`golangci-lint` は採用しない。

---

## 5. API 契約

### 5.1 proto 規約

| 規則 | 強度 |
| --- | --- |
| 構文は proto3。パッケージは `{{svc}}.v1`、配置は `proto/{{svc}}/<service>.proto` | MUST |
| `go_package = "{{module}}/gen/grpc/{{svc}};{{svc}}pb"` | MUST |
| 1 ファイル 1 service。service 名は `<Feature>Service` | MUST |
| REST は `google.api.http` annotation を各 RPC に付ける。パスは `/api/<resource>`（kebab-case） | MUST |
| 配列をトップレベルで返す GET は `response_body: "<repeated field>"` | SHOULD |
| 金額は整数（`uint32`/`uint64`）、ID は `uint64`（JSON では REST gateway が文字列化）、日時は表示用 `string` | SHOULD |
| JSON 上で出し分けたい field は proto3 `optional` にする | SHOULD |
| JSON のキー名を固定したい場合は `json_name` を明示する | SHOULD |

### 5.2 生成物

`gen/grpc/{{svc}}/`（`*.pb.go` / `*_grpc.pb.go` / `*.pb.gw.go`）、`openapi/gen/{{svc}}.swagger.json`（`allow_merge=true,merge_file_name={{svc}},use_proto3_field_semantics=true`）。

### 5.3 OpenAPI

proto の派生物であり、フロントエンドとの共有契約。proto を変更したら再生成して commit する（MUST）。フロントエンドへの受け渡し方法はプロジェクトで決める。

### 5.4 エラー契約

```text
usecaseerror / domainerror の sentinel
    ─ErrorConverter（errors.Is）→ gRPC status(code, ErrorInfo.Reason=<sentinel の文字列>)
    ─REST gateway ErrorHandler→ HTTP status + {"error":"<sentinel の文字列>"}
```

- カテゴリ5つの gRPC code は §3.2 で固定する。業務 sentinel の「コード / HTTP / gRPC / 意味」の表を必ず作る（記録先は本書の外）。ログレベルを既定（`Warn`。§10）から変える sentinel は、この表に「ログレベル」の列を足して記録する。
- 業務上の「無効」を通常分岐にしたい場合は、エラーではなく成功応答にする（例: 応答に有効かどうかを示す field を持たせる）。
- 想定外のエラーは `Internal` / `"internal"` 固定。詳細はサーバー側のログにだけ出す。

---

## 6. データベース

### 6.1 ローカル DB

| 項目 | 規則 |
| --- | --- |
| エンジン | MySQL 8.4 LTS（`mysql:8.4`）。サポート終了版を使わない |
| 文字コード | `utf8mb4` / `utf8mb4_unicode_ci`（サーバー設定と各テーブルの両方） |
| タイムゾーン | サーバー `default-time-zone`、コンテナ `TZ`、DSN `loc=`、アプリの `pkg/timezone`（§9.2）を同じ値に揃える（値はプロジェクトの方針で 1 つに固定） |
| データベース | `{{db}}` を `docker/mysql/init.sql` で作成し、アプリ用ユーザーに権限を付与する。テスト用 DB は作らない |
| 接続 pool | Writer 用と Reader 用の 2 系統を持つ（`pkg/mysql.Clients`）。Reader は Writer と同じホスト（`DBHOST`）に接続する。Reader 用のホストは設定項目を置かない（§9）。`max_open_conns` / `max_idle_conns` / `conn_max_lifetime` を設定ファイルで指定 |
| 永続化 | `docker/mysql/data/` を bind mount。`.gitignore` / `.dockerignore` / `.cursorignore` に入れる |

### 6.2 スキーマ管理（宣言的）

| 規則 | 強度 |
| --- | --- |
| スキーマの正本は `schema/NN_<table>.sql`（`CREATE TABLE` のみ。`CREATE DATABASE` / `USE` を含めない） | MUST |
| 適用は `mysqldef`（Docker イメージ、version pin）。`make db-migrate-local` は **dry-run → 本適用** の順に実行する | MUST |
| 破壊的変更（`DROP` を含む差分）は dry-run の出力を確認してから適用する | MUST |
| 逐次 migration ファイルを作らない | MUST NOT |

### 6.3 テーブル設計規約

```sql
CREATE TABLE <table> (
  <table>_id BIGINT UNSIGNED NOT NULL,            -- 主キー: 採番 ID。AUTO_INCREMENT を使わない
  -- ...
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (<table>_id),
  KEY idx_<table>_<col> (<col>)                   -- 非 UNIQUE
  -- UNIQUE KEY uq_<table>_<col> (<col>)           -- UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='<説明>';
```

| 規則 | 強度 |
| --- | --- |
| 主キーは Snowflake（`BIGINT UNSIGNED`）。自然キーを使う場合は理由をコメントに書く（例: ULID を `VARCHAR(26)`） | SHOULD |
| **物理外部キーを置かない**。関係は論理的に管理し、整合は UseCase の transaction と Domain の業務ルールで担保する | SHOULD |
| 日時は `DATETIME`（タイムゾーン方針は §6.1）。`TIMESTAMP` を使わない | SHOULD |
| index 名は `idx_<table>_<col>`、UNIQUE は `uq_<table>_<col>`。範囲検索・ロック対象の列に index を張る | MUST |
| テーブルと、意味の補足が必要な列に `COMMENT` を付ける | SHOULD |
| 状態列は数値コード（`TINYINT UNSIGNED`）+ VO で検証する | SHOULD |

### 6.4 seed

- `seed/NN_<table>.sql`。**冪等**にする（`INSERT ... AS new ON DUPLICATE KEY UPDATE ...`）。
- `make seed-local` は `docker compose exec -T mysql mysql ...` で流す。
- seed はマスタ用途のみ。テストデータを入れない。

### 6.5 transaction と排他

transaction の開始位置と `queryable` の渡し方は §3.3。

| 規則 | 強度 |
| --- | --- |
| ロックが必要な処理は、**何をロックするか**を表で残す（処理 / transaction / ロック対象。記録先は本書の外） | MUST |
| transaction の中で外部 API（HTTP / gRPC）を呼ぶかどうかは、プロジェクトで決めて記録する。**既定は呼ばない**（transaction 保持時間が外部呼び出しの往復分だけ延び、ロック競合・接続枯渇を招く）。呼ぶ場合は「外部側の失敗で DB も自動ロールバックして整合性を優先する」という理由を書く | MUST |
| コミット後に通知（publish など）を送る場合は、失敗しても整合性が崩れない通知に限り、コミット成功後に transaction の外で送る（呼び出しの経路は §3.5.5）。失敗時はリトライで追随する。コミット後に `ctx` がキャンセルされても送りたい場合は、親のキャンセルだけを切り離した `ctx` を使う | SHOULD |
| ロック付きの読み取りで連番などを採番する場合は、「範囲を `SELECT ... FOR UPDATE` → 最大値 + 1」など、ロック範囲を明示した方式にする。対象が 0 件のときの挙動（ギャップロック・デッドロック）を検証する。そのような採番があるかは本書では決めない | MUST |
---

## 7. ビルド・コード生成

### 7.1 Makefile のターゲット

ターゲット名と意味は固定する。

| ターゲット | 内容 |
| --- | --- |
| `init` | `tools` → `images` → `compose-up` → `wait-mysql` |
| `tools` | wire / mockgen / gomockhandler / goimports / staticcheck を **version 指定**で `go install` |
| `images` | `protoc-gen` と `mysqldef` の Docker イメージをビルド |
| `compose-up` | `docker compose up -d` |
| `wait-mysql` | `mysqladmin ping` で最大 30 回（2 秒間隔）待つ。失敗は exit 1 |
| `pull-proto-dep` | `google/api/{annotations,http}.proto` を **commit SHA 固定**で取得 |
| `gen` | `gen-proto-all` → `wire` → `gen-mock` |
| `gen-proto-all` | Docker 経由の protoc で Go / gRPC / REST gateway / OpenAPI を生成（`pull-proto-dep` に依存） |
| `wire` | `wire ./internal/di` |
| `gen-mock` | `gomockhandler -config=gomockhandler.json mockgen` |
| `build` | `go build -o bin/{{app}} ./cmd/{{app}}` |
| `lint` | goimports 差分なし + `go vet` + `staticcheck` |
| `test` | `go test ./...`。テストは DB に接続しない（§7.5） |
| `verify` | `build` → `lint` → `test`（**`gen` を含めない**） |
| `db-migrate-local` | `schema/*.sql` を連結して mysqldef に渡す（dry-run → 本適用） |
| `seed-local` | `seed/*.sql` を投入 |

- `SCHEMA_FILES` / `SEED_FILES` / `PROTO_FILES` は Makefile の変数に列挙する（順序が意味を持つ）。
- `export GOTOOLCHAIN := go<version>` と `export PATH := $(GOBIN):$(PATH)` を先頭で設定する。

### 7.2 protoc の実行

ホストに protoc を入れず、`docker/protoc-gen/Dockerfile` から作ったイメージで実行する。

```makefile
docker run --rm -v "$(CURDIR):/work" -w /work $(PROTOC_IMAGE) \
  -I proto -I proto/protodep/googleapis \
  --go_out=. --go_opt=module=$(MODULE) \
  --go-grpc_out=. --go-grpc_opt=module=$(MODULE) \
  --grpc-gateway_out=. --grpc-gateway_opt=module=$(MODULE) \
  --openapiv2_out=openapi/gen \
  --openapiv2_opt=allow_merge=true,merge_file_name={{svc}},use_proto3_field_semantics=true \
  $(PROTO_FILES)
```

`docker/protoc-gen/Dockerfile` の要件:

- ベース: `golang:<go version>-bookworm`。`ARG TARGETARCH` で `arm64` / `amd64` を切り替える（未対応アーキは exit 1）。
- protoc は GitHub Releases の zip を **version 指定**で `/usr/local` に展開する。
- `protoc-gen-go` / `protoc-gen-grpc-gateway` / `protoc-gen-openapiv2` は `go install ...@<version>`。`protoc-gen-go-grpc` は grpc-go のタグを `git clone --depth 1 --branch <version>` して `cmd/protoc-gen-go-grpc` で `go install`。
- `ENTRYPOINT ["protoc"]`、`WORKDIR /work`。

### 7.3 Wire / Mock

- Wire: `make wire`。`internal/di/wire_gen.go` を commit。
- Mock: `gomockhandler.json` に **ソース interface → 出力先** を登録する（SOURCE_MODE、package は `mock`、出力は `test/mock/<name>.go`）。対象は `internal/domain/repository` の interface（Domain Service のテストが差し替える。§7.5）。checksum は gomockhandler が管理するので手編集しない。
- Mock が必要な interface を増やしたら `gomockhandler.json` に追記し、`make gen-mock` を実行する。

### 7.4 生成物

| 生成物 | 生成元 | コマンド | commit | 手編集 |
| --- | --- | --- | --- | --- |
| `gen/grpc/{{svc}}/*` | `proto/**` | `make gen-proto-all` | する | 禁止 |
| `openapi/gen/*` | `proto/**` | `make gen-proto-all` | する | 禁止 |
| `internal/di/wire_gen.go` | `internal/di/server.go` | `make wire` | する | 禁止 |
| `test/mock/*` | Repository interface、`gomockhandler.json` | `make gen-mock` | する | 禁止 |
| `go.sum` | `go.mod` | `go mod tidy` | する | 禁止 |

API の形、DI の配線、Mock の対象は生成物ではなく生成元で確認する。`*.pb.go` のメソッド名は `proto/**` の service / rpc から決まる。生成物は `.cursorignore` で AI の参照対象から外す（§11.3）。commit はする。

### 7.5 テスト

| 規則 | 強度 |
| --- | --- |
| 標準 `testing` + table-driven。テストは同じパッケージの `_test.go` | MUST |
| Domain（Entity / VO / types）のテストは I/O がないためモックを使わない。境界値・不正値・状態遷移を網羅する | MUST |
| 単体テストの既定対象は Domain Service。`test/mock` の gomock で Repository を差し替える。テストが `queryable` を渡し、Domain Service は transaction を開始しない。時刻と ID は引数で渡して決定的にする | MUST |
| UseCase の単体テストは書かない。transaction の開始は `pkg/mysql` の `RunInWriteTx` の契約テストで検証する。業務ルールと Repository の呼び出し順は Domain Service のテストで検証する | SHOULD |
| `pkg/*` は単体テストを持ち、`make test` の対象に含める。`RunInWriteTx` の契約テストは `go-sqlmock` で行い、実 DB には接続しない | MUST |
| テストは実 DB に接続しない。Repository の SQL を DB で検証しない | MUST NOT |
| DB から得る値が必要なテストは、対象 interface を実装した stub を使い、固定の値を返す。stub は `internal/infrastructure/stub` に置く。DB クライアントを持たない | MUST |
| `t.Skip` で原因不明の失敗を隠さない。アサーションを弱めて通さない。テスト間で実行順序に依存しない | MUST NOT |
| アーキテクチャテスト（§3.1）を持つ | MUST |

---

## 8. ローカルインフラ（Docker / Compose）

### 8.1 `docker-compose.yaml`

| サービス | 内容 |
| --- | --- |
| `mysql` | `image: mysql:8.4`、`ports: "3306:3306"`、`TZ`、`--character-set-server` / `--collation-server`、`init.sql` と `my.cnf` を read-only mount、`./docker/mysql/data:/var/lib/mysql`、`healthcheck`（`mysqladmin ping`、interval 5s / timeout 5s / retries 30 / start_period 20s） |
| `{{app}}` | `build: { context: ., dockerfile: docker/go/Dockerfile }`、gRPC / REST gateway の port を公開、DB 接続先などを**環境変数 `{{ENV_PREFIX}}_*` で上書き**、`depends_on: mysql: condition: service_healthy` |

| 規則 | 強度 |
| --- | --- |
| compose に置くのは**アプリと MySQL だけ**。クラウド認証情報の mount、外部 network、private module 用の build arg を入れない | MUST |
| アプリの設定は「ファイル（非機密）+ 環境変数（接続情報）」。compose では環境変数で DB ホストを `mysql:3306` に切り替える | MUST |
| ローカル専用の DB 資格情報は compose に書いてよい。**本番相当の秘匿値を書かない** | MUST |
| ホストの `go run` とコンテナのアプリを同時に起動しない（port 競合）。README に明記する | SHOULD |
| ホットリロード（Air など）・デバッガー（Delve）は MAY。入れる場合は開発用 target を別に分け、本体の Dockerfile を汚さない | MAY |

### 8.2 `docker/go/Dockerfile`

| 規則 | 強度 |
| --- | --- |
| multi-stage。build stage は `golang:<go version>`。`go.mod` / `go.sum` を先に COPY して `go mod download` し、ソースの COPY より前に依存を取得する。`CGO_ENABLED=0 go build -buildvcs=false -o /out/{{app}} ./cmd/{{app}}` | MUST |
| 最終 stage は `debian:bookworm-slim` + `ca-certificates`。実行バイナリ、`configs/local.yaml`、実行時の静的ファイル（D10）を COPY し、gRPC / REST gateway の port を `EXPOSE` する | MUST |
| タイムゾーンは `pkg/timezone` で `time/tzdata` を import して同梱する（イメージ側に tzdata を要求しない。§9.2） | MUST |
| 最終 stage は非 root ユーザーで実行する | SHOULD |

### 8.3 MySQL コンテナ設定

- `docker/mysql/init.sql`: `CREATE DATABASE IF NOT EXISTS {{db}}`（`utf8mb4` / `utf8mb4_unicode_ci`）、アプリ用ユーザーへ `GRANT ALL`。テスト用 DB は作らない。
- `docker/mysql/my.cnf`: `character-set-server` / `collation-server` / `default-time-zone`、`[client] default-character-set`。

### 8.4 mysqldef イメージ

`docker/mysqldef/Dockerfile`: `debian:bookworm-slim` + `curl` / `tar` で GitHub Releases の `mysqldef_linux_${ARCH}.tar.gz` を **version 指定**で取得し、`ENTRYPOINT ["mysqldef"]`。`ARG TARGETARCH` で `arm64` / `amd64` を切り替える。接続はコンテナからホストの MySQL へ `--add-host=host.docker.internal:host-gateway` を付けて `-h host.docker.internal` とする。

---

## 9. 設定管理

| 層 | 置き場所 | 内容 | 読み込み |
| --- | --- | --- | --- |
| 非機密設定 | `configs/local.yaml` が既定。環境ごとの差分は `configs/<env>.yaml` | port、pool、timeout、CORS allowlist、外部システム（gateway）の timeout・リトライ回数・待機間隔（§3.5.5）。`snowflake_node_id` はローカルだけ（§9.1） | `{{ENV_PREFIX}}_CONFIG_PATH`（既定 `configs/local.yaml`） |
| 接続情報・環境 | 環境変数 `{{ENV_PREFIX}}_*` | `ENV`、`DBUSER`、`DBPASS`、`DBHOST`、`MYSQL_TZ`（IANA 名。DSN `loc=` と `pkg/timezone` に使う。§9.2）、`CONFIG_PATH` | `envconfig`（prefix 付き。`default` タグで既定値） |

| 規則 | 強度 |
| --- | --- |
| 設定は `main` が `config.Load()` で 1 回だけ読む。渡し方と起動順序は §3.7、§3.8 | MUST |
| 必須項目が欠けたら起動時にエラーにする（port など）。任意項目は既定値を持つ | MUST |
| 設定ファイルの不明キーはエラーにする（誤字を黙って無視しない） | MUST |
| YAML は `gopkg.in/yaml.v3` + `KnownFields(true)` で読む。手書きパーサーを書かない | SHOULD |
| ログに出してよい設定は `SafeFields()` のような許可リスト方式で選ぶ。**DB 資格情報をログに出さない** | MUST |
| 既定で置く設定ファイルは `configs/local.yaml` だけ。`configs/test.yaml` は置かない | MUST |
| 環境ごとに非機密の差分が必要なら `configs/<env>.yaml` を足してよい。環境名はデプロイ先で決まるため、この文書では定めない。差分は `local.yaml` から最小にし、機密値は置かない。足した環境名は記録する（記録先は本書の外）。イメージで使うファイルは Dockerfile で明示的に COPY する | SHOULD |
| DB のホストは `DBHOST` 1 つで指定する。Reader は Writer と同じ `DBHOST` に接続し、Reader 用のホストの設定項目は置かない。Reader を別ホスト（レプリカ）にする必要が出たら、そのときに設定項目を足す | MUST |
| DB のポートは MySQL の既定（3306）を使い、設定項目にしない | MUST |
| DB 名（`{{db}}`）は本書では決めない。ドメイン層の生成時に値を決め、設定項目（環境変数または YAML）を足す | MUST |

### 9.1 Snowflake のノード番号

ノード番号は 0〜63（`NodeBits = 6`）。一意性が要るのは、同じ DB に書くプロセスの間だけである。別システムの IP と重なってよい。

| 環境 | ノード番号 | 強度 |
| --- | --- | --- |
| ローカル（`ENV=local`。既定） | `configs/local.yaml` の `snowflake_node_id` | MUST |
| ローカル以外 | そのプロセスが動く IP（サーバ、コンテナ、ECS のタスク）の IPv4 の下位 6 bit。設定ファイルの値は使わない | MUST |
| 取得失敗 | 起動を失敗させる。標準エラーに出して `os.Exit(1)`。失敗をノード番号 `0` として続行しない | MUST |

下位 6 bit が `0` でも、IP の取得に成功していればその値を使う。同じ DB に書くプロセス同士でこの 6 bit が重ならない配置にする。1 つの `/26`（またはそれより狭いサブネット）に収まり、プロセスごとに IP が分かれていれば、IP が違えば下位 6 bit も違う。

### 9.2 タイムゾーン（`pkg/timezone`）

プロジェクトで 1 つに固定したタイムゾーンを `pkg/timezone` に集約し、各層はこれを参照する。

```go
// pkg/timezone/timezone.go
package timezone

import (
	"fmt"
	"time"
	_ "time/tzdata" // イメージに tzdata が無くても読める（§8.2）
)

// defaultName はプロジェクトの方針で決めた値。MYSQL_TZ の既定値と揃える
const defaultName = "Asia/Tokyo"

// Location はプロジェクトで 1 つに固定したタイムゾーン。Init 以外から書き換えない
var Location = mustLoad(defaultName)

// Init は起動時に 1 回だけ呼ぶ。MYSQL_TZ の値を渡す
func Init(name string) error {
	loc, err := time.LoadLocation(name)
	if err != nil {
		return fmt.Errorf("load location %q: %w", name, err)
	}
	Location = loc
	return nil
}

func mustLoad(name string) *time.Location {
	loc, err := time.LoadLocation(name)
	if err != nil {
		panic(err) // 定数の誤り。プログラムエラー
	}
	return loc
}
```

| 規則 | 強度 |
| --- | --- |
| タイムゾーンの `*time.Location` は `pkg/timezone` の `Location` 1 つにする。システム用と DB 用に分けない（§6.1 で同じ値に揃えるため） | MUST |
| 値は環境変数 `{{ENV_PREFIX}}_MYSQL_TZ`（§9）から取り、起動時に `timezone.Init` で 1 回だけ設定する。呼ぶ順序は §3.8。DSN の `loc=` と同じ値を使う | MUST |
| `Init` が失敗したら起動を止める。固定オフセット（`time.FixedZone`）に黙って落とさない | MUST |
| `Location` を `Init` 以外から書き換えない。テストでも差し替えない（並列実行で競合する） | MUST NOT |
| `pkg/timezone` の外で `time.LoadLocation` / `time.FixedZone` を書かない（テストを含む）。テストの時刻は `time.Date(..., timezone.Location)` で作る | MUST NOT |
| `time.Local` を書き換えない。`time.Local` や `time.Now()` の既定ロケーションに頼らず、必要な所で `.In(timezone.Location)` に変換する | MUST NOT |
| `Clock` の実装（§3.3）は `time.Now().In(timezone.Location)` を返す | SHOULD |

---

## 10. ログ・エラー・可観測性

| 項目 | 規則 | 強度 |
| --- | --- | --- |
| ロガー | 標準の `log/slog`。`*slog.Logger` を DI で渡す。出力は stdout。`slog.SetDefault` とパッケージ関数（`slog.Info` など）は使わない | MUST |
| フォーマット | 1 行 1 イベント。ハンドラは `slog.NewTextHandler`（`key=value`）または `slog.NewJSONHandler` のどちらかにプロジェクトで固定する。メッセージは固定の文字列にし、可変の値は属性（`slog.String("method", m)` など）で渡す | SHOULD |
| ログに出す | method / code / elapsed_ms / error（`err.Error()`）/ panic + stack | MUST |
| ログのレベル | クライアントの切断・期限切れ（`Canceled` / `DeadlineExceeded`）は `Warn`。`Error` にしない。カテゴリ sentinel は、`not_found` / `invalid_argument` / `conflict` を `Warn`、`unavailable` を `Error`。未知のエラー（`Internal`）は `Error`。業務 sentinel は `Warn` を既定とする。既定から変える sentinel は、§5.4 の対応表の「ログレベル」の列で記録する | MUST |
| ログに出さない | リクエスト・レスポンス本文、資格情報、トークン | MUST NOT |
| ヘルスチェック | `grpc.health.v1` を使う。REST gateway に専用 endpoint を足さない | SHOULD |

---

## 11. 設定ファイル群

### 11.1 `.gitignore`

Go の一般的な ignore（バイナリ、テスト出力、カバレッジ）に、次を加える。

```gitignore
go.work
go.work.sum
.env
.env.*
docker/mysql/data/
/{{app}}
/bin/{{app}}
```

- 生成物（`gen/` / `openapi/gen/` / `test/mock/` / `wire_gen.go`）は ignore しない（commit する。§7.4）。
- 他言語向けの項目を持ち込まない。

### 11.2 `.dockerignore`

`.dockerignore` は `.gitignore`（§11.1）と同じパターンに `.git` を足したものにする。Docker 公式は、ビルドコンテキストを小さくするため、`.gitignore` に揃えることと、`.git`（ビルド中に git コマンドを使わない場合）とローカルのビルド成果物を除外することを挙げている（[Optimize for building in the cloud](https://docs.docker.com/build-cloud/optimization/)）。`designs` は入れない。

- ビルドに必要な `gen/` `internal/` `pkg/` `cmd/` `configs/` と実行時静的ファイルは除外しない。

### 11.3 `.cursorignore`

```text
.env
.env.*
docker/mysql/data/
bin/
coverage.*
*.pem
*.key
gen/
openapi/gen/
test/mock/
internal/di/wire_gen.go
```

- 生成物（`gen/`、`openapi/gen/`、`test/mock/`、`internal/di/wire_gen.go`）は除外する（MUST）。AI は生成物を読まず、生成元を読む（§7.4）。`.gitignore` には入れない。commit はする。
- 認証ファイルとデータディレクトリも除外する。

### 11.4 `.coderabbit.yaml`

CodeRabbit を使う場合の値。

| 項目 | 値 |
| --- | --- |
| `language` | プロジェクトの言語（例 `ja-JP`） |
| `reviews.path_filters` | `!gen/grpc/**` / `!openapi/gen/**` / `!**/wire_gen.go` / `!test/mock/**` / `!go.sum` / `!docker/mysql/data/**` |
| `reviews.tools` 有効 | `gitleaks`、`osv-scanner`、`hadolint`（Dockerfile）、`markdownlint`、`yamllint`、`shellcheck`（シェルスクリプトがある場合） |
| `reviews.tools` 無効 | Go 以外の言語用ツール全般。`golangci-lint` も無効（lint は staticcheck。§4.4） |
| `reviews.path_instructions` | 下表 |

| path | 指摘させる観点 |
| --- | --- |
| `**/*.go` | §3 の MUST / MUST NOT の違反全般。特に、依存方向と import 禁止（§3.1）、生成物の手編集、SQL の文字列連結、transaction の開始位置・ネスト・`ctx` への格納、`errors.Join` / `%v` による sentinel の包み、`logrus` の import、`slog.SetDefault` とパッケージ関数の使用、`pkg/timezone` の外での `time.LoadLocation` / `time.FixedZone`、`time.Local` の書き換え |
| `proto/**` | field 番号の再利用、破壊的変更、annotation と path の不一致 |
| `schema/**` | `CREATE DATABASE` / `USE` の混入、物理外部キー、AUTO_INCREMENT、index 命名 |
| `**/*_test.go` | table-driven、生成 Mock の手修正、`t.Skip`、実 DB への接続 |
| `docker/**` | version pin 漏れ、`latest`、root 実行、不要な秘匿値 |

### 11.5 その他

| ファイル | 規則 |
| --- | --- |
| `go.mod` | `module {{module}}`、`go <version>`。`replace` を使わない。`go mod tidy` 済みで commit |
| `gomockhandler.json` | §7.3。手編集しない |
| `README.md` | 前提（Docker / Make / Go version）、`make init` → `make db-migrate-local` → `make seed-local` の手順、ポート、停止方法、API 確認例 |
| `.editorconfig` | MAY（Go は `gofmt` / `goimports` に従う） |