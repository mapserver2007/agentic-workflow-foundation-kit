---
title: AI Business Agent Suite (BAS) — 設計体系統合ドキュメント
exported_at: 2026-05-21
updated_at: 2026-06-07
version: 1.0（Confluence 17章の統合正本化）
status: 正本（Source of Truth）
reference_specs:
  - AI Agent 基盤 統一設計書 (AI_AGENT_UNIFIED_DESIGN.md)
  - BAS Confluence Space (https://showcasegig.atlassian.net/wiki/spaces/~588498106/)
  - Cursor Skills (https://cursor.com/docs/skills)
  - Cursor Rules (https://cursor.com/docs/rules)
  - Cursor Subagents (https://cursor.com/docs/subagents)
  - Cursor Hooks (https://cursor.com/docs/hooks)
---

# AI Business Agent Suite (BAS) — 設計体系統合ドキュメント

BAS（Business Agent Suite）は、AI エージェントのコンテキストウィンドウ制約を出発点として、**ACCD（AI Context Constraints Design）** という 5 軸の設計体系を構築したフレームワークである。

## 目次


### Part 1: 基盤設計

- [1. ACCD — AI とコードの役割分担](#1-accd--ai-とコードの役割分担)
- [2. Agent Conduct — AI の行動規律](#2-agent-conduct--ai-の行動規律)
- [3. Interaction Principles — PO との対話原則](#3-interaction-principles--po-との対話原則)
- [4. ビジョン — BAS が目指す先](#4-ビジョン--bas-が目指す先)

### Part 2: データ管理と品質保証

- [5. YAML 正本 + Markdown ビュー](#5-yaml-正本--markdown-ビュー)
- [6. セッションライフサイクル](#6-セッションライフサイクル)
- [7. 品質ゲートシステム — Receipt-driven Gates + Criteria-first Review](#7-品質ゲートシステム--receipt-driven-gates--criteria-first-review)
- [8. Deterministic Guard — AI 出力の決定的判定](#8-deterministic-guard--ai-出力の決定的判定)
- [9. Finding Code — AI エージェント開発のエラー体系](#9-finding-code--ai-エージェント開発のエラー体系)

### Part 3: 実行基盤とパイプライン

- [10. エンジンとモデル選択](#10-エンジンとモデル選択)
- [11. サブエージェントアーキテクチャ](#11-サブエージェントアーキテクチャ)
- [12. 提案書生成パイプライン — 7 ステップの全体像](#12-提案書生成パイプライン--7-ステップの全体像)
- [13. 仮説生成とシミュレーション](#13-仮説生成とシミュレーション)
- [14. エージェント間の壁打ちと結果合成](#14-エージェント間の壁打ちと結果合成)
- [15. Context Loading と読み制御](#15-context-loading-と読み制御)

### Part 4: 運用と拡張体系

- [16. Git ワークフローとコミット規約](#16-git-ワークフローとコミット規約)
- [17. スキル・ルール・Hook・サブエージェント — 4 層の拡張体系](#17-スキル・ルール・hook・サブエージェント--4-層の拡張体系)

---


# Part 1: 基盤設計


<a id="1-accd--ai-とコードの役割分担"></a>

## ACCD — AI とコードの役割分担

### 解く問題（Why）

AI エージェント（Cursor, Claude Code, Codex 等）によるソフトウェア開発には、人間の開発とは質的に異なる構造的制約がある。

### AI の 3 つの構造的制約

| 制約 | 結果 | 人間との違い |
| --- | --- | --- |
| **容量上限** | 1 回に読めるコード量に物理限界がある | 人間は IDE で自由にファイルを行き来できる |
| **揮発性** | セッションが終わると全記憶が消える | 人間は翌日も昨日の作業を覚えている |
| **断崖性** | ウィンドウ外の情報は「存在しない」 | 人間は「忘れた」と「知らない」を区別できる |

3 つ目が最も深刻である。人間が大きなプロジェクトを扱うとき、把握できる範囲は漸進的に狭まる。しかし AI にとってはコンテキストウィンドウの境界で認知が断崖的にゼロになる。プロジェクトに 50 ファイルあっても、ウィンドウに載せた 10 ファイル以外は AI にとって存在しない。

### これらの制約が引き起こす障害

1. **局所最適の罠**: ウィンドウ内のコードは完璧に書けるが、ウィンドウ外との整合性を保証できない
2. **記憶の断絶**: 前セッションで決めた方針を、次セッションの AI は知らない
3. **完了の幻覚**: 自分の作業範囲では完了に見えるが、全体としては未完了
4. **追従と手抜き**: ユーザーの指示に無批判に従い、問題を指摘しない（Sycophancy）

BAS はこれらの障害を出発点として、AI エージェント開発を構造的に制御するための設計体系 **ACCD（AI Context Constraints Design）** を構築した。

### BAS の独自性について

率直に言えば、ACCD を構成する個々のパターンは、ソフトウェア工学では既知の手法の適用である:

| BAS のパターン | 既知の工学手法 | BAS での独自性 |
| --- | --- | --- |
| Context Loading Table | 依存関係マニフェスト（package.json, requirements.txt） | `not_needed` の強制（何を読まないかを明示） |
| Receipt-driven Gates | CI/CD パイプラインゲート | PO 承認の鮮度チェック（YAML 変更後は再承認必須） |
| Deterministic Guard | 静的解析ルール（ESLint, Pylint） | Finding Code 体系との統合 |
| YAML 正本 + Markdown ビュー | MVC パターン（Model / View 分離） | `bas planning render` によるコード駆動の生成 |
| Lifecycle Contract | ステートマシン | `start_commit` による変更追跡の自動化 |
| Finding Code | HTTP ステータスコード、コンパイラエラーコード | severity + category の 2 軸分類 |

BAS が独自に行ったことは、「AI エージェントのコンテキストウィンドウ制約」という問題を定式化し、そこから 5 つの設計軸を導出して体系化したことにある。道具は既存のもの。使い方と組み合わせ方が新しい。

### 設計原理（How）

### 3 つの根本原理

ACCD は以下の 3 つの根本原理の上に構築されている。5 軸はこれらの原理から導出される。

#### 原理 1: AI は動的、コードは決定的

```text
AI の役割:   推論・構成・批判・仮説生成（動的）
コードの役割: 検証・計算・照合・状態管理（決定的）
```

AI は創造的な作業が得意だが、正確性の保証は苦手である。逆にコードは創造できないが、一度書けば同じ入力に対して常に同じ結果を返す。ACCD はこの補完関係を設計の中核に据えている。この原理は軸 B（専念の委譲）を直接導出し、軸 A〜E の全てに通底する。

#### 原理 2: Markdown は表現、YAML は定義、JSON は中間データ

```text
YAML の役割:     正本（人間/AI が編集、システムが検証）
Markdown の役割: 表現（コードが生成、人間/AI が読む）
JSON の役割:     中間データ（コードが生成、コードが消費）
```

この分離により、AI は「値を埋める」ことに集中でき、構造の正当性はスキーマが、表現の生成は `render.py` が担う。JSON は Gate 結果・Pydantic 出力・外部ツール設定など、人間が直接編集しない機械間データに限定する。詳細は [05 — YAML 正本と Markdown ビュー](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842090) で扱う。

#### 原理 3: コンテキストウィンドウは揮発的で有限、情報は永続化し選択して収める

```text
永続化:      全情報を YAML 正本に書き残す → 05 YAML 正本
選択して収める: 何を読み何を読まないかを宣言する → 15 Context Loading
```

AI の記憶はセッションで消え、容量にも限りがある。チャット上で報告しただけでは、次のセッションには存在しない。この原理が 5 軸の設計動機そのものである。軸 A（制約の補完）は揮発性・容量上限・断崖性への直接対処、軸 D（段階的圧縮）は「選択して収める」の構造化手法であり、この原理なくして ACCD は成立しない。詳細は [05 — YAML 正本](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842090) と [15 — Context Loading](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005949) で扱う。

### ACCD の 5 軸

ACCD は 5 つの独立した設計軸から成る。初期は C0（コンテキスト制約）からの一本導出だったが、品質ゲートや Deterministic Guard の位置づけを分析した結果、C0 への対処だけでは説明できない設計動機が存在することが判明した。「C0 が解消しても品質ゲートは必要か？」— 答えが Yes であるなら、それは制約補完とは別の設計軸に属する。

| 軸 | 名称 | 問い | C0 が解消しても必要か |
| --- | --- | --- | --- |
| **A** | 制約の補完 | AI の構造的限界をコードと仕組みでどう補うか | — |
| **B** | 専念の委譲 | AI が生成と推論に集中できるよう、何をコードに委譲するか | Yes |
| **C** | 認知的多様性 | 同一モデルの確証バイアスをどう排除するか | Yes |
| **D** | 段階的圧縮 | 情報をどう構造化して引き継ぐか | 部分的に Yes |
| **E** | 自律的進化 | AI が自らの規律を強化する仕組みをどう作るか | Yes |

**軸 A（制約の補完）** は C0 への直接対処であり、ACCD の出発点。Context Loading Table はウィンドウの容量上限に対処し、YAML 正本は揮発性に対処し、Lifecycle Contract は断崖性に対処する。軸 A は「AI の弱点を埋める」守りの設計である。

**軸 B（専念の委譲）** は「AI にやらせないことで AI のポテンシャルを解放する」という設計。品質ゲートによる機械的検証、Deterministic Guard による数値判定、Finding Code による統一エラー体系 — これらはいずれも「AI が正確性の検証に認知資源を使わなくて済む」ための仕組みである。C0 が無限大になっても、AI に検証させるより、コードに検証させる方が信頼性は高い。軸 A が守りなら、軸 B は「AI の強みを伸ばす」攻めの設計である。

**軸 C（認知的多様性）** は、同一のモデルが生成と批判を兼ねると確証バイアスが生じるという問題への対処。異なるモデルファミリーによるクロスレビュー、Hypothesis Challenge（仮説への批判的検証）がこの軸に属する。

**軸 D（段階的圧縮）** は、セッション間・ステップ間の情報引き継ぎを構造化する設計。Handover テンプレート、Context Loading の優先度制御、YAML → Markdown の表現分離。C0 制約の直接対処（軸 A）の側面もあるが、「推論の質を高めるための情報構造化」は C0 が解消しても有効。

**軸 E（自律的進化）** は、AI が自身の行動を観察し、規律を強化していく仕組み。現在の実装は最小構成（違反の手動記録 → ルール化 → Hook 化の昇格パス）だが、BAS が目指す方向は AI が自律的にこのサイクルを回すこと。他の 4 軸が「現在の設計」であるのに対し、軸 E は「目指す方向」であり、性質が異なる。詳細は [04 — ビジョン](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842070) で扱う。

### なぜ 5 つなのか

4 つでも 6 つでもなく 5 つになった論理:

1. **軸 A は出発点**: C0（コンテキスト制約）への直接対処。これがなければ BAS は始まらない
2. **軸 B は「C0 が解消しても必要か」テストで分離**: 品質ゲートは制約補完ではなく役割分担。設計動機が A と根本的に異なる
3. **軸 C も同テストで分離**: 確証バイアスは C0 とは独立した問題
4. **軸 D は A と重複するが独立性あり**: 情報構造化は制約対処と推論品質向上の両面を持つ。A に吸収するとこの二面性が失われる
5. **軸 E は PO の意図**: A〜D が「現在の設計」なら E は「目指す方向」。性質が異なるが BAS の設計体系に含める必要がある

5 軸は「C0 一本からの演繹的展開」ではなく、各機構の設計動機を分析した結果の **帰納的な分類** である。

### 導出マップ

5 軸から各章（機構・パイプライン・運用）への導出関係:

<!-- Confluence 上ではここに導出マップ画像があります。MCP 取得結果では一時 blob URL のため、Markdown では画像実体を安定参照できません。 -->

| 軸 | 導出先 | 関係 |
| --- | --- | --- |
| A | 05 YAML正本 | 揮発性への対処（状態の永続化） |
| A | 06 ライフサイクル | 断崖性への対処（状態遷移の機械管理） |
| A | 11 サブエージェント | コンテキスト分離 |
| A | 15 Context Loading | 容量上限の制御 |
| **B** | **05 YAML正本** | **状態管理をコードに委譲** |
| B | 07 品質ゲート | 検証の委譲 |
| B | 08 Guard | 判定の決定化 |
| B | 09 Finding Code | エラー分類の統一化 |
| B | 10 エンジン | 実行の委譲（engine_resolver） |
| C | 10 エンジン | モデルファミリー分散 |
| C | 11 サブエージェント | 独立した視点での分析 |
| C | 13 仮説 | 仮説への批判的検証 |
| C | 14 壁打ち | 異なる視点での合成 |
| D | 12 提案書 | 情報の構造化引き継ぎ |
| D | 15 Context Loading | 読み制御（優先度による段階圧縮） |
| E | 07 品質ゲート | 規律の機械的強制 |
| E | 17 スキル | 違反の昇格パス |

### BAS での実装（What）

ACCD は BAS の全モジュールに浸透している。以下は各軸の代表的な実装箇所:

### 軸 A: 制約の補完

| 実装 | 対処する制約 | モジュール |
| --- | --- | --- |
| Context Loading Table | 容量上限 | `bas/planning/scaffold.py` |
| YAML 正本 + Markdown ビュー | 揮発性 | `bas/planning/render.py`, `bas/planning/state.py` |
| Lifecycle Contract | 断崖性 | `bas/planning/cli.py`, `bas/planning/validators/` |
| トークン予算計算 | 容量上限 | `bas/planning/scaffold.py` |

### 軸 B: 専念の委譲

| 実装 | AI から委譲される処理 | モジュール |
| --- | --- | --- |
| Entry / Exit Gate | セッションの開始・終了条件の検証 | `bas/planning/validators/` |
| Deterministic Guard | 出力品質の数値判定 | `bas/guards/`, `bas/gates/` |
| Finding Code 体系 | エラーの統一分類 | [09 — Finding Code](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842151)、[付録 B](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842287) |
| Schema 検証 | YAML 構造の正当性チェック | `bas/planning/schema.py` |

### 軸 C: 認知的多様性

| 実装 | 担保する多様性 | 参照 |
| --- | --- | --- |
| モデルファミリー分散 | 生成と批判で異なるモデルファミリー（[FC-430 CRITICAL_REVIEW_SAME_ENGINE](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842151) で機械的に強制） | `bas/guards/workflow_engine.py` |
| Hypothesis Challenge | 仮説への独立した批判的検証 | `skills/critical-review/` |
| エンジン切替可能設計 | 障害時のフォールバック経路を確保 | `bas/runner/`, `workflows/proposal_mvp.yaml` |

### 軸 D: 段階的圧縮

| 実装 | 圧縮の形態 | 参照 |
| --- | --- | --- |
| Handover テンプレート | ステップ間の構造化引き継ぎ | `skills/proposal-strategy/templates/handover.md`（現在配置済み。他スキルはワークフロー YAML の `handover_template` で参照） |
| Context Loading 優先度 | must_read / reference / not_needed の 3 段階 | `sessions/*.yaml` |
| Review Packet | 全出力の集約ビュー | `skills/review-packet/` |

### 軸 E: 自律的進化（現在の最小構成）

| 実装 | 進化の段階 | 参照 |
| --- | --- | --- |
| `issues.yaml` | 違反の記録 | `.session/context/issues.yaml` |
| `.cursor/rules/` | ルールへの昇格 | `.cursor/rules/bas-*.mdc` |
| `.cursor/hooks.json` | Hook への昇格（機械的強制） | `.cursor/hooks.json` |

### 自プロジェクトへの適用

### Step 1: 問題を定式化する

自分のプロジェクトで AI がどの障害を起こしているかを観察する。典型的な症状:

- 同じミスが繰り返される → 軸 E（違反の記録と昇格）
- 前セッションの判断が失われる → 軸 A（揮発性への対処）
- AI の出力にミスが多い → 軸 B（検証の委譲）
- AI が自分の出力を批判できない → 軸 C（認知的多様性）

### Step 2: 1 つの軸から始める

全軸を同時に導入する必要はない。推奨順序:

1. **軸 A（制約の補完）** — Context Loading Table だけで作業品質が向上する
2. **軸 B（専念の委譲）** — 品質ゲートで検証を機械化する
3. **軸 E（自律的進化）** — 違反を記録してルール化するサイクルを回す
4. **軸 D（段階的圧縮）** — セッション間引き継ぎを構造化する
5. **軸 C（認知的多様性）** — 複数モデルによるクロスレビュー

### Step 3: 導出マップを描く

自分のプロジェクトの仕組みが ACCD のどの軸に対応するかをマッピングする。「なぜこの仕組みが必要か」を軸に紐づけて説明できれば、チームメンバーへの説明コストが下がる。

---


---


<a id="2-agent-conduct--ai-の行動規律"></a>

## Agent Conduct — AI の行動規律

### 解く問題（Why）

AI エージェントは強力な推論能力と実行能力を持つが、その能力を「正しく使う」ための規律がなければ、以下の問題が構造的に発生する:

1. **Sycophancy（追従）**: ユーザーの発言に無批判に同意し、問題を指摘しない
2. **手順スキップ**: 「不要」「自明」と自己判断し、検証ステップを省略する
3. **完了の偽装**: 80% 完了の状態で「完了」と報告する
4. **対症療法**: 根本原因ではなく症状を隠す修正をする
5. **先送り**: 「スコープ外」と自己判断して問題を無視する

これらは AI の「悪意」ではなく、**構造的な傾向** である。明示的に規律を定義しなければ、どのモデルでも再現する。この章は ACCD の軸 B（専念の委譲）と軸 E（自律的進化）に位置づけられる。行動規律を明文化してコードで強制することで、AI が生成と推論のポテンシャルに集中できる環境を作る。

### 設計原理（How）

### 4 つの行動原則

AI の全行動を制約する 4 つの原則:

| 原則 | 意味 | 対処する問題 |
| --- | --- | --- |
| **Humble（謙虚）** | 自分の判断は間違いうる。手順は AI の判断ミスから成果物を守る仕組み | 手順スキップ、過信 |
| **Cautious（慎重）** | 不可逆な行動の前に必ず立ち止まる | 早まった変更、確認漏れ |
| **Thorough（確実）** | 全検証項目を実行し、結果を記録する。記録されていない作業は存在しない | 完了の偽装、検証漏れ |
| **Selective（本質）** | 出力前に読み手の目で自分の出力を見る。「記憶のない AI がこれを読んで正しく理解・判断できるか」を問う | 冗長な出力、情報過多 |

これらは AGENTS.md の Agent Conduct セクションで定義される SoT であり、全セッションに適用される。

### Anti-Sycophancy（追従防止）

AI が陥りやすい最も危険な傾向。追従は AI の「好意」ではなく、判断の放棄である。

**許容される応答パターン:**

| パターン | 例 |
| --- | --- |
| 事実に基づく肯定 | 「はい、そのアプローチは X の理由で適切です」 |
| 部分的肯定 + 改善提案 | 「A は良いですが、B は Y のリスクがあります」 |
| 率直な否定 | 「その方法は Z の問題があるため、代わりに W を推奨します」 |

**禁止される応答パターン:**

| パターン | なぜダメか |
| --- | --- |
| 「素晴らしい質問です！」 | 空虚な賞賛。判断の先送り |
| 「はい、その通りです！」（根拠なし） | 無条件の同意。問題の見逃し |
| 「小さな問題ですが…」（実際は重大） | 問題の矮小化 |

### デバッグ規律

AI がバグ修正を行う際の構造的な規律。対症療法を構造的に防止する:

1. **証拠収集が最優先**: 修正の前にエラーログ・stderr・コンソール出力を収集
2. **パイプライン分解**: どの段階で失敗しているかを証拠で示す
3. **対症療法の禁止**: 入力/出力の書き換えで問題を回避してはならない
4. **最小再現**: 問題を最小のケースで再現し、原因を分離
5. **自己チェック**: 「根本原因に対処しているか、症状を隠しているか」を自問

### スキップ禁止

スキル・手順の Step は番号順に全て実行する。AI が「不要」「自明」「小規模だから」と自己判断してスキップすることを明示的に禁止する。

| スキップの自己正当化 | 正しい対応 |
| --- | --- |
| 「不要だと思う」 | スキル本文にスキップ条件が明記されているか確認 → No なら実行 |
| 「自明だから」 | 自明でも実行する。結果が自明であることの確認になる |
| 「小規模だから」 | 規模は省略の理由にならない |

唯一の例外: スキル本文に明示的なスキップ条件が書かれている場合。

### 振り返りフォーマット

PO から是正を求められた場合、言い訳ではなく構造分析で回答する:

1. **As-Is**: 実際に起こったことを時系列整理
2. **根本原因**: 構造的な原因（個人の不注意ではなく仕組みの欠陥）
3. **To-Be**: あるべきだった行動
4. **構造的対策案**: 再発防止の仕組み（ルール追加・テンプレート改善等）

### BAS での実装（What）

### Cursor Rules による強制

BAS ではこれらの規律を `.cursor/rules/` に配置し、AI セッション開始時に自動注入する:

| ルール | 役割 | 対応する原則 |
| --- | --- | --- |
| `bas-anti-sycophancy.mdc` | 追従防止 + 提案後行動規約 | Humble, Selective |
| `bas-no-step-skip.mdc` | スキル手順のスキップ禁止 | Humble, Thorough |
| `bas-debugging-protocol.mdc` | デバッグ規律 | Cautious, Thorough |
| `bas-no-handwritten-data.mdc` | 構造化データの転写禁止 | Thorough |
| `bas-subagent-wait.mdc` | サブエージェント完了待ち | Cautious |
| `bas-git-workflow.mdc` | Git ワークフロー強制 | Cautious |
| `bas-issue-capture.mdc` | 問題の即時記録 | Thorough |

### 昇格メカニズム（軸 E: 自律的進化 の現在の実装）

同じ違反が繰り返し観測された場合、段階的に強制度を高める:

```
観察（チャットで指摘）
  ↓ 3 回以上
ルール化（.cursor/rules/*.mdc に明文化）
  ↓ ルールでも再発
Hook 化（.cursor/hooks.json で機械的に強制）
  ↓ Hook でも対処不十分
Validator 化（bas/planning/validators/ でコードとして強制）
```

各段階の違い:

| 段階 | 強制力 | 例 |
| --- | --- | --- |
| 観察 | なし（記憶に依存） | 「サブエージェント結果を待ってから進めて」 |
| ルール | 弱（AI が従うかは保証なし） | `bas-subagent-wait.mdc` |
| Hook | 中（ターン終了時に自動チェック） | `.cursor/hooks.json` の stop hook |
| Validator | 強（Gate を通過しなければ先に進めない） | `bas/planning/validators/` |

### 構造化データの転写禁止

AI が Markdown レポートを書く際、URL・ID・数値をメモリから書くとハルシネーションが発生する。BAS ではこれを構造的に防止する:

1. AI がレポートの骨格を作成（データ部分はプレースホルダー）
2. Python スクリプトでソースデータからテーブル行を生成
3. プレースホルダーをプログラム生成のテーブルで置換
4. 突合チェックスクリプトで検証

これは軸 B（専念の委譲）の典型例: AI は文章と分析を担い、正確性が要求されるデータ転写をコードに委譲する。

### 自プロジェクトへの適用

### Step 1: Anti-Sycophancy ルールを配置する

```markdown
# .cursor/rules/anti-sycophancy.mdc

### 絶対ルール
1. 事実に基づく応答: ユーザーの発言が事実と異なる場合、同意せず正確な情報を提供する
2. 問題点の指摘: コード・設計に問題がある場合、褒める前に問題を指摘する
3. 不確実性の表明: 確信がない場合は「わかりません」と正直に答える
4. 過剰な褒め言葉の禁止: 「素晴らしい質問です」等の空虚な賞賛を使わない
5. 代替案の提示: より良い代替案がある場合は提示する

### 提案後の行動規約
対策案を提示した後は:
1. 推奨を明示する（根拠付き）
2. 「進めますか？」と判断を求める
```

### Step 2: デバッグ規律を追加する

```markdown
# .cursor/rules/debugging.mdc

バグ修正の前に:
1. エラーログ・stderr を収集する
2. どの段階で失敗しているかを特定する
3. 対症療法（入力/出力の書き換え）ではなく根本原因に対処する
4. 修正前に「根本原因に対処しているか」を自問する
```

### Step 3: 違反の追跡と昇格

1. AI の行動で問題が起きたら、具体的な事実を記録する

* `issues.yaml`: プロジェクトの設計・運用上のイシュー（Open/Resolved で管理）
* `gotchas.yaml`: スキル実行時の失敗パターン・注意点（次回以降の同種作業への申し送り）

1. 同種の違反が 3 回蓄積したら `.cursor/rules/` にルール化する
2. ルールでも再発する場合は `.cursor/hooks.json` に Hook 化する
3. 少数のルールから始める: Anti-Sycophancy + デバッグ規律の 2 つだけで大きな効果がある
4. 具体例を含める: 「禁止」だけでなく「こう答えるべき」の具体例があると AI が従いやすい


---


<a id="3-interaction-principles--po-との対話原則"></a>

## Interaction Principles — PO との対話原則

### 解く問題（Why）

AI エージェントの能力が高くなるほど、PO（Product Owner / 意思決定者）との対話の質が成果物の品質を左右する。しかし、対話には以下の構造的な問題がある:

1. **判断の先送り**: 選択肢を並べるだけで推奨を示さない。PO に認知負荷を転嫁している
2. **スコープの暗黙変更**: PO に確認せず、スコープを拡大または縮小する
3. **コスト主張の根拠不足**: 「工数がかかる」と言うだけで、具体的な変更対象やファイル数を示さない
4. **確認の無限ループ**: 自律的に判断すべき事項まで PO に確認を求め、作業が進まない
5. **操作の転嫁**: 「Agent モードに切り替えてください」のように、AI 側の制約を PO の操作で解決しようとする

Agent Conduct（[02](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483907615)）が AI の「内面の規律」であるのに対し、Interaction Principles は AI と PO の「対話のプロトコル」を定義する。ACCD の軸 B（専念の委譲）に属する — PO が判断に集中できるよう、AI が情報の整理と推奨の提示を担う。

### 設計原理（How）

### 提案→推奨→承認プロトコル

AI が対策案や選択肢を提示する場合、以下の 3 ステップで完結する:

```
1. 選択肢を根拠付きで提示する
2. 推奨を明示する（「A を推奨します。理由は X です」）
3. PO に判断を求める（「進めますか？」）
```

**禁止パターン:**

* 選択肢を並べて終わる（推奨なし）→ 判断の先送り
* 「Agent モードに切り替えれば実装できます」→ 操作の転嫁
* 推奨なしに「どちらがいいですか？」→ PO への認知負荷の転嫁

### スコープの明示的管理

スコープの拡大も縮小も、理由を述べて PO に判断を求める。勝手に広げず、勝手に切り捨てない。

| パターン | 正しい行動 |
| --- | --- |
| 作業中に追加課題を発見 | 「X を発見しました。スコープに含めますか？ 含める場合は Y ファイルの変更が必要で、推定 Z 行です」 |
| 依頼が大きすぎる | 「依頼を A と B に分割することを推奨します。理由: 一度にやるとレビュー品質が下がります」 |
| タスクが不要と判断 | 「T3 は X の理由で不要と考えますが、スキップしてよいですか？」 |

### 先送り・コスト主張の根拠要件

「後でやる」「工数がかかる」と述べる場合は、必ず根拠を添える:

| 主張 | 不十分 | 十分 |
| --- | --- | --- |
| 「後でやります」 | 理由なし | 「今やると X の依存関係で Y も変更が必要になり、推定 20 ファイル。次セッションで X 解消後にやる方が変更 5 ファイルで済みます」 |
| 「コストが大きい」 | 感覚的 | 「変更対象: bas/planning/ 配下 8 ファイル + tests/ 4 ファイル。推定 200 行の変更」 |

### 選択肢の評価規律（deterministic-first）

実装の選択肢を提示する際、「AI の動的判断に依存する案」と「コードが決定的に強制する案」が両方ある場合:

* **推奨は必ず決定的な案にする**
* AI 判断の案は参考として併記は許容するが、推奨にしてはならない
* コストが大きい場合は変更対象ファイル数・推定行数を根拠として添えて PO に判断を求める

これは ACCD の根本原理「AI は動的、コードは決定的」の直接的な帰結。

### 情報の永続化義務

チャットは次のセッションに引き継がれない。AI がチャットで報告した内容は、同一ターンで追跡ドキュメントに書き戻す義務がある。

| パターン | 問題 | 正しい行動 |
| --- | --- | --- |
| チャットで方針を説明して終わり | 次の AI はその方針を知らない | 方針を追跡ドキュメントに記録する |
| 「前セッションで確認済み」 | 次の AI はその記憶を持たない | 確認結果を追跡ドキュメントに記録する |
| 「詳細は省略するが○○の方針で」 | 何の方針か次の AI にはわからない | 方針の内容を明記するか参照先を正確に示す |

### BAS での実装（What）

### AGENTS.md での定義

Interaction Principles は AGENTS.md の一部として定義される。AI セッション開始時に自動的にロードされ、全ての対話に適用される。

### Boundaries による具体化

AGENTS.md の Boundaries セクションで、具体的な許可/禁止リストを定義:

| 区分 | 内容 | 例 |
| --- | --- | --- |
| **Always** | PO に確認せず実行する | Agent Conduct に従う、ルールをリポ内に配置する |
| **Ask First** | PO の承認を得てから実行する | セッション終了、コミット、新規スキル追加 |
| **Never** | いかなる状況でも実行しない | credentials のコミット、`--dangerously-skip-permissions` |

### ルールによる強制

| ルール | 対応する原則 |
| --- | --- |
| `bas-anti-sycophancy.mdc` | 提案後行動規約（推奨必須・判断の先送り禁止） |
| `bas-deterministic-first.mdc` | 選択肢の評価規律 |
| `bas-session-render.mdc` | render 結果のチャット本文展開（情報の永続化義務の一例） |
| `bas-issue-capture.mdc` | 問題の即記録（先送り禁止の機械的強制） |

### 実際の対話例

BAS 開発中に観測された典型的な対話パターン:

**良い例:**

> AI: 「`validators.py` が 660 行で C2 閾値を超えています。分割を推奨します。対象: 16 チェック関数を `validators/` パッケージに分離。推定変更: 3 ファイル新規作成 + 既存 2 ファイル修正。進めますか？」

**悪い例:**

> AI: 「`validators.py` が大きいですね。分割する方法もありますし、このままでも動きます。どちらがいいですか？」

前者は推奨と根拠を示している。後者は判断を PO に丸投げしている。

### 自プロジェクトへの適用

### Step 1: 提案→推奨→承認ルールを配置する

```markdown
# .cursor/rules/interaction.mdc

### 提案後の行動規約
対策案・選択肢を提示した後は:
1. 推奨を明示する（根拠付き）
2. 「進めますか？」と判断を求める
3. 推奨なしに選択肢を並べて終わることは禁止
```

### Step 2: Boundaries を定義する

自分のプロジェクトで AI が「自律的にやるべきこと」「確認すべきこと」「絶対にやってはいけないこと」を AGENTS.md に明記する。

### Step 3: 永続化ルールを追加する

```markdown
# .cursor/rules/persistence.mdc

チャットで報告した内容は、同一ターンで追跡ドキュメントに書き戻すこと。
チャット上でのみ共有された方針・判断・課題は、次セッションに引き継がれない。
```

### 導入の効果

* PO の判断負荷が減る（AI が整理して推奨を提示するため）
* 「言った/言わない」がなくなる（追跡ドキュメントに永続化されるため）
* AI の暴走が防がれる（Boundaries で明示的に制限されるため）


---


<a id="4-ビジョン--bas-が目指す先"></a>

## ビジョン — BAS が目指す先

> **出典**: [04. BAS（Confluence）](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842070/04.+BAS)（page id: `4483842070`, v5）

### 解く問題（Why）

BAS が解決しようとしている問題の本質は、「AI のコストが劇的に下がったことで、従来は人的資源の制約から不可能だったアプローチが可能になった」という環境変化にある。

### 人的資源の制約が強制していた意思決定構造

従来のコンサルティングや提案書作成では:

* **仮説は 1 つに絞る**: 人間が検証できるリソース（時間・人員・コスト）に限りがあるため、早期に仮説を 1 つに絞り込んで深掘りする。検証リソースが足りない以上、これは半ばギャンブルだった
* **批判は限定的**: レビューは人間のレビュアーの可用性に依存し、全ての仮説に独立した批判的検証を行うことは現実的でない
* **知見の統合は属人的**: 異なる分野の知見を統合するには、それぞれの分野に精通した人間が必要

AI のコスト構造はこの前提を覆す:

* **仮説を並列生成できる**: 複数の仮説を同時に生成し、それぞれをシミュレーションするコストが極めて低い
* **独立した批判が可能**: 異なるモデルファミリーで生成した仮説に、別のモデルが批判的レビューを行える
* **知見の横断が自動化できる**: 書籍ライブラリや過去事例からの知見統合を AI が担える


### 2 つのビジョン

この環境変化から、BAS は 2 つの方向性を追求する:

1. **仮説駆動アプローチ**: 「1 つに絞って深掘り」から「並列生成して競わせる」へ
2. **自律的進化**: 「人間が AI のルールを書く」から「AI が自らの規律を強化する」へ

どちらも ACCD の軸に紐づく: 仮説駆動は軸 C（認知的多様性）の応用、自律的進化は軸 E（自律的進化）の追求。

BAS は単なる「提案書生成ツール」ではない。**AI が自分自身の規律を学習し強化するための足場** — それが BAS の本質的な位置づけである。提案書生成はこの足場の上で最初に検証するユースケースであり、BAS が目指しているのは AI の自律的進化を促すための構造そのものの構築にある。

> **現在の位置づけ**: BAS は現在、仮説駆動パイプラインの最小構成（7 ステップの直線実行）と、自律的進化の最小構成（人間主導の違反記録 → ルール化）を実装している。本章はこの最小構成の設計意図と、BAS が目指す発展の方向を描く。

### 設計原理（How）

### 仮説駆動アプローチ

従来の直線的なプロセスと仮説駆動の対比:

```
【従来】
  課題分析 → 仮説選定(1つ) → 深掘り → 提案書
  
【仮説駆動】
  課題分析 → 仮説並列生成(N個) → シミュレーション(N個)
           → 批判的検証(独立モデル) → 統合・優先順位付け → 提案書
```

仮説駆動の設計原則:

1. **並列生成**: 1 つに絞らず、複数の仮説を同時に生成する。コストが低いからこそ可能
2. **独立した批判**: 生成と批判を異なるモデルファミリーで行い、確証バイアスを排除する（軸 C: 認知的多様性）
3. **シミュレーション**: 各仮説の実現可能性・リスク・期待効果を事前にシミュレーションする
4. **優先順位付け**: シミュレーション結果に基づいて仮説を順位付けし、最終的な提案に統合する

> **現在の実装と目指す方向**: 現在の BAS では `proposal_mvp.yaml` ワークフローの strategy → simulation → hypothesis_challenge → drafting の 4 ステップで仮説駆動を実装している。仮説の並列生成は strategy ステップ内で行われ、hypothesis_challenge で異なるモデルによる批判的検証を実施する。目指す方向は、仮説の生成数・シミュレーションの深度・批判の多角性をスケーリングし、より高品質な提案を自動生成すること。

### 自律的進化

AI が自身の行動を観察し、規律を自ら強化していくメカニズム:

```
【現在の昇格パス】
  人間が違反を観察 → issues.yaml に記録 → .cursor/rules/ にルール化
  → .cursor/hooks.json に Hook 化 → bas/planning/validators/ にコード化

【目指す方向】
  AI が違反を自己検知 → 自動で issues に記録 → パターンを分析
  → ルール案を提案 → PO 承認後に自動配置
```

自律的進化の設計原則:

1. **観察**: AI が自身の出力と PO のフィードバックを構造的に記録する
2. **パターン認識**: 繰り返される違反パターンを検知する
3. **対策の提案**: ルール・Hook・Validator の形で対策を自動生成する
4. **段階的強化**: 観察 → ルール → Hook → Validator と強制度を段階的に高める

> **現在の実装と目指す方向**: 現在の BAS では、違反の観察と記録は人間（PO）が行い、AI はルール化や Hook 化の実装を支援する。`bas-issue-capture.mdc` ルールにより AI が問題を `issues.yaml` に即座に記録する仕組みはあるが、パターン認識と対策提案は人間が主導している。目指す方向は、AI が自律的に違反パターンを分析し、ルール案を生成して PO に承認を求めるサイクルを実現すること。PO は「ルールを書く人」ではなく「ルールを承認する人」になる。

### 2 つのビジョンの接続

仮説駆動と自律的進化は独立したビジョンではなく、同じテーゼの表裏:

| 観点 | 仮説駆動 | 自律的進化 |
| --- | --- | --- |
| 活用する変化 | AI コストの低下 | AI コストの低下 |
| 適用先 | プロダクト（提案書の品質） | プロセス（開発ワークフローの品質） |
| 軸 | C（認知的多様性）の応用 | E（自律的進化）の追求 |
| 人間の役割 | 仮説の最終判断 | ルールの承認 |

どちらも「AI のコストが下がったことで、従来は人間のリソース制約から不可能だったアプローチが可能になった」という共通の基盤に立つ。

### BAS での実装（What）

### 仮説駆動パイプライン

`workflows/proposal_mvp.yaml` の 7 ステップ構成:

> **図**: 7 ステップのワークフロー図は [Confluence 原本](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842070/04.+BAS) で参照してください（API エクスポート時の画像リンクは再利用不可のため省略）。

* **オレンジ（S3, S7）**: 軸 C（認知的多様性）— 異なるモデルファミリーによる批判的検証
* **青（S6）**: 軸 B（専念の委譲）— コードによる決定的検証

> **現在の実装と目指す方向**: 現在のパイプラインは 7 ステップの直線構成。仮説の並列生成は strategy ステップ内で AI が行う。目指す方向は、仮説ごとに独立したシミュレーションを並列実行し、結果を統合するアーキテクチャへの進化。

### 自律的進化の実装

現在の最小構成:

| コンポーネント | 役割 | 自動化レベル |
| --- | --- | --- |
| `bas-issue-capture.mdc` | AI が問題を即座に記録 | 半自動（AI がルールに従って記録） |
| `issues.yaml` | 問題の蓄積と追跡 | 手動（人間がパターンを分析） |
| `.cursor/rules/` | 違反パターンのルール化 | 半自動（AI が実装、人間が承認） |
| `.cursor/hooks.json` | ルール違反の機械的検知 | 自動（ターン終了時に自動実行） |
| `bas/planning/validators/` | Gate での強制 | 完全自動（通過しなければ先に進めない） |

> **現在の実装と目指す方向**: 上記の 5 段階のうち、issues.yaml → rules への昇格判断は人間が行っている。目指す方向は、issues.yaml のパターン分析と rules の案の自動生成。最終的な承認は人間（PO）が行うが、提案の主体を AI に移行する。

### 自プロジェクトへの適用

> **現在 BAS でできること**: 7 ステップパイプラインの実行、`issues.yaml` での違反記録、手動でのルール・Hook 昇格。**これからの方向**: AI が違反パターンを自動検知し、ルール化を提案する自律的フィードバックループ。

### 仮説駆動の導入

仮説駆動は提案書作成に限らず、技術選定やアーキテクチャ設計にも応用できる:

1. **問題の定義**: 解くべき問題を明確にする
2. **仮説の並列生成**: AI に複数の解決策を生成させる（「3 つの選択肢を出して」）
3. **シミュレーション**: 各選択肢のメリット・デメリット・リスクを分析させる
4. **独立した批判**: 別のモデル（または別のプロンプト）で批判的レビューを行う
5. **統合と判断**: 結果を比較し、人間が最終判断する


### 自律的進化の導入

1. **問題の記録から始める**: AI の行動で問題が起きたら、具体的な事実を記録する
2. **パターンを探す**: 3 回以上繰り返される問題はパターンとして認識する
3. **ルール化する**: パターンを `.cursor/rules/` にルール化する
4. **効果を測定する**: ルール化後も同じ問題が起きるかを観察する
5. **強化する**: ルールで不十分なら Hook や Validator に昇格する

重要なのは「最初から完璧な仕組みを作ろうとしない」こと。観察 → 記録 → ルール化のサイクルを回すことで、プロジェクト固有の規律が自然に蓄積されていく。


---


# Part 2: データ管理と品質保証


<a id="5-yaml-正本--markdown-ビュー"></a>

> **出典**: [05. YAML 正本と Markdown ビュー](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842090/05.+YAML+Markdown)（Confluence。Markdown として取得・整理）

## YAML 正本 + Markdown ビュー

### 解く問題（Why）

AI エージェントにセッション計画や進捗を管理させると、自然言語のフリーテキストで記述する。しかしフリーテキストには致命的な問題がある:

1. **検証不能**: 「タスク T1 は完了」と書かれていても、機械的に検証できない
2. **構造の崩壊**: セッションを重ねるうちにフォーマットが崩れ、情報が散逸する
3. **変換コスト**: 人間が読む Markdown と機械が検証するデータ構造が一致しない

この章は ACCD の 2 つの軸に位置づけられる。軸 A（制約の補完）— YAML を正本とすることで、AI セッションが揮発しても構造化データが永続化される。軸 B（専念の委譲）— 状態管理と構造検証をコード（スキーマバリデーション、`render.py`）に委譲することで、AI は値を埋めることに集中できる。

### 設計原理（How）

### Markdown は表現、YAML は定義

```
YAML（正本）         Markdown（ビュー）
┌──────────────┐    ┌──────────────────┐
│ tasks:       │    │ ## タスク一覧     │
│   - id: T1   │───→│ | ID | 内容 | …  │
│     status:  │    │ | T1 | …   | …  │
│       done   │    └──────────────────┘
└──────────────┘
      ↑                    ↑
  機械が検証           人間/AI が読む
  スキーマで制約       render.py が生成
```

原則:

* **YAML が唯一の正本**。AI は YAML の値を編集する
* **Markdown は YAML から決定的に生成される**。手書きしない
* **スキーマがテンプレートとして存在する**。キー構造・enum 値を機械検証する


### JSON は中間データ

YAML と Markdown の 2 層に加え、BAS では **JSON を機械間の中間データ形式** として位置づけている:

| 形式 | 誰が書くか | 誰が読むか | 用途 |
| --- | --- | --- | --- |
| **YAML** | 人間 / AI | 人間 / AI / コード | 正本（セッション計画、設定、スキーマ） |
| **Markdown** | コードが生成 | 人間 / AI | ビュー（レンダリング結果、ドキュメント） |
| **JSON** | コードが生成 | コードが消費 | 中間データ（Gate 結果、Pydantic 出力、外部ツール設定） |

JSON が使われる典型的な場面:

* **Gate 結果**: バリデーター実行結果の構造化出力（Pass/Fail、エラー詳細）
* **Pydantic 出力**: Python コードが生成するスキーマ検証済みのデータ
* **外部ツール設定**: MCP サーバー設定（`.cursor/mcp.json`）、Hook 定義（`.cursor/hooks.json`）

JSON は人間が直接編集するものではなく、コードが生成しコードが消費する。人間や AI が編集する必要がある構造化データは YAML に、人間が読むための表現は Markdown に、という役割分担を徹底することで、各形式の責務が明確になる。

### 3 層のデータ管理

| 層 | 役割 | ファイル |
| --- | --- | --- |
| **テンプレート** | YAML の雛形。キー構造と初期値を定義 | `templates/session.yaml` |
| **スキーマ + i18n** | enum 値の許容リスト + ラベルの多言語定義 | `templates/schema.yaml`, `templates/i18n.yaml` |
| **インスタンス** | AI が値を埋めた実データ | `.session/sessions/*.yaml` |

### enum による値の制約

フリーテキストではなく、許容される値を事前定義する:

```yaml
# schema.yaml
enums:
  task_status:
    values:
      - id: planned      # 予定
      - id: in_progress   # 進行中
      - id: done          # 完了
      - id: blocked       # ブロック

  context_loading_priority:
    values:
      - id: must_read     # 必読
      - id: edit_target   # 編集対象
      - id: reference     # 詳細参照
      - id: not_needed    # 参照不要
```

AI が `status: finished`（定義外の値）と書くと、バリデーターがエラーを返す。

### SoT Hierarchy

AGENTS.md が Root SoT として各 Domain SoT へのルーティングを持つ:

| SoT | ファイル | 管理対象 |
| --- | --- | --- |
| Root SoT | `AGENTS.md` | プロジェクト境界・実行原則 |
| Development Workflow SoT | `CONTRIBUTING.md` | Git 規約・ブランチ戦略 |
| Architecture Decision SoT | `design/decisions/` | ADR |
| Context SoT | `.session/context/*.yaml` | プロジェクト背景・原則・スコープ |
| Session SoT | `.session/sessions/*.yaml` | セッション計画・タスク・QG |
| State SoT | `.session/state.yaml` | アクティブ/完了セッション |

### BAS での実装（What）

### テンプレート → スキャフォールド

```shell
bas planning init s01 s02 s03
```

このコマンドは:

1. `templates/context/*.yaml` を `.session/context/` にコピー
2. `templates/session.yaml` をベースに各セッション YAML を生成
3. `review_criteria.yaml` の `ai_judgment` 項目を QG 行として自動注入
4. `state.yaml` を初期化


### PO 向けレンダリング

```shell
bas planning render s01        # 単一セッション
bas planning render --context  # コンテキスト YAML のみ
bas planning render            # 全体（context + 全 session）
```

AI は YAML を編集するだけで、人間向けのビューは常に最新の正本から生成される。

### Gate での自動検証

Entry Gate と Exit Gate の両方で YAML スキーマを検証する:

```shell
bas planning validate s01 --gate entry
# Gate PASS: s01 の entry

bas planning validate s01 --gate exit
# Gate FAIL: s01 の exit
#   [error] yaml_schema_match: 必須キー 'records' が不足
```

### 自プロジェクトへの適用

### Step 1: セッション YAML のテンプレートを作る

```yaml
# templates/session.yaml
session_id: ""
purpose: ""
tasks:
  - id: T1
    content: ""
    status: planned
quality_gates:
  - id: QG-1
    content: ""
    method: ""
    status: not_done
records: ""
```

### Step 2: AI にテンプレートを埋めさせる

「テンプレートの構造を変えずに、値を埋めてください」と指示する。`status` の許容値を Cursor Rule で明示する:

```markdown
# .cursor/rules/session-yaml.mdc
tasks[].status は以下のみ許容: planned, in_progress, done, blocked
quality_gates[].status は以下のみ許容: not_done, pass, fail
```

### Step 3: 検証スクリプトを追加する（オプション）

```python
import yaml
from pathlib import Path

ALLOWED_STATUS = {"planned", "in_progress", "done", "blocked"}

with open(".session/sessions/s01.yaml") as f:
    data = yaml.safe_load(f)

for task in data.get("tasks", []):
    assert task["status"] in ALLOWED_STATUS, (
        f"Task {task['id']}: invalid status '{task['status']}'"
    )
```


---


<a id="6-セッションライフサイクル"></a>

> **出典**: [06. セッションライフサイクル](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874821/06)（Confluence。Markdown として取得・整理）

## セッションライフサイクル

### 解く問題（Why）

AI エージェントを使った開発では、作業が大きくなると複数セッションに分割する必要がある。しかし分割した瞬間に以下の問題が発生する:

1. **状態の散逸**: どのセッションが完了し、どのセッションが未着手か、追跡する仕組みがない
2. **依存関係の無視**: セッション B はセッション A の成果物に依存するのに、A が未完了のまま B を開始する
3. **完了の曖昧さ**: 「だいたい終わった」と「全条件を満たした」の区別がつかない

この章は ACCD の軸 A（制約の補完 — 揮発性と断崖性への対処）に位置づけられる。Lifecycle Contract により、セッション間の状態遷移を決定的に管理する。

### 設計原理（How）

### 3 層モデルに統一契約を適用する

```
Campaign（目標達成に必要な全作業）
├── Session 1（1 回の AI セッションで実行する作業）
│   ├── Task 1-1
│   └── Task 1-2
├── Session 2
│   └── Task 2-1
└── Session 3
    ├── Task 3-1
    └── Task 3-2
```

全階層に同一の **Lifecycle Contract** を適用する:

```
Prepare → Start Gate → Execute → End Gate → Close / Handover
```

| フェーズ | 目的 | 検証 |
| --- | --- | --- |
| Prepare | 計画の作成・レビュー・承認 | plan_review + po_approval レシート |
| Start Gate | 開始条件の充足を検証 | Entry Gate |
| Execute | 作業の実行 | — |
| End Gate | 完了条件の充足を検証 | Exit Gate |
| Close | 状態遷移 + アーカイブ | state.yaml の更新 |

### 状態管理: state.yaml

```yaml
active: s02
completed:
  - s01
accepted: false
start_commits:
  s01: "abc123..."
  s02: "def456..."
```

状態遷移: `null → active → completed → (全完了) → accepted → archive`

全ての状態遷移操作は冪等。同じコマンドを 2 回実行しても状態が壊れることはない。

### start_commit による変更追跡

`activate` 時に `git rev-parse HEAD` の結果を `start_commits` に記録する。Exit Gate の `records_coverage`（V9: 実施記録カバレッジ）はこの commit hash を使って `git diff --name-only {start_commit}` を実行し、変更されたファイルが実施記録で言及されているかを検証する。

### 受け入れテスト + アーカイブ

全セッション完了後:

1. `bas planning accept` — `acceptance.yaml` の `after: all` テストを実行
2. 全 PASS → `accepted: true`
3. `bas planning archive campaign-name` — 全ファイルをアーカイブディレクトリに移動し、事後検証を実行


### BAS での実装（What）

### CLI コマンド

> 注: Confluence 原本では以下の表の前に CLI 一覧のスクリーンショットが挿入されていました。API 経由の Markdown 変換では画像をローカル資産として取得できないため、表のみ転記しています。

| コマンド | フェーズ | 役割 |
| --- | --- | --- |
| `init` | Prepare | context/ + sessions/*.yaml を生成 |
| `render` | Prepare | YAML → Markdown 変換 |
| `mark-reviewed` | Prepare | plan_review レシート作成 |
| `mark-approved` | Prepare | po_approval レシート作成 |
| `activate` | Start | active 設定 + start_commit 記録 |
| `validate` | Gate | Entry/Exit Gate 検証 |
| `load-context` | Start | 必読ファイル出力 + レシート記録 |
| `complete` | Close | completed に移行 |
| `accept` | Close | 受け入れテスト実行 |
| `archive` | Close | 全ファイルをアーカイブ |

### 典型的なフロー

```shell
# 1. 計画
bas planning init s01 s02 s03
# AI が YAML を編集
bas planning render
bas planning mark-reviewed s01 --result "PASS"
bas planning mark-approved s01 --checklist "render_displayed=yes,content_approved=yes"

# 2. セッション開始
bas planning activate s01
bas planning validate s01 --gate entry
bas planning load-context s01

# 3. 作業実行 → 4. セッション終了
bas planning mark-cross-reviewed s01 --result "PASS" --transcript /path/to/transcript.jsonl
bas planning validate s01 --gate exit
bas planning complete s01

# 5. 全完了後
bas planning accept
bas planning archive my-campaign
```

### 自プロジェクトへの適用

### Step 1: state.yaml を導入する

```yaml
active: null
completed: []
```

### Step 2: 最小限の状態遷移スクリプトを作る

```python
import yaml
from pathlib import Path

STATE_PATH = Path(".session/state.yaml")

def activate(session_id):
    state = yaml.safe_load(STATE_PATH.read_text()) or {}
    if state.get("active") == session_id:
        return
    state["active"] = session_id
    STATE_PATH.write_text(yaml.dump(state, allow_unicode=True))
```

### Step 3: Cursor Rule でライフサイクルを強制する

```markdown
# .cursor/rules/session-lifecycle.mdc
セッション作業を開始する前に .session/state.yaml の active を確認してください。
active が null の場合は activate を、別のセッションの場合は先に complete してください。
```


---


<a id="7-品質ゲートシステム--receipt-driven-gates--criteria-first-review"></a>

> **出典**: [07. 品質ゲートシステム](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874841/07.)（Confluence。Markdown として取得・整理。page id: `4483874841`, v3）

## 品質ゲートシステム — Receipt-driven Gates + Criteria-first Review

### 解く問題（Why）

AI エージェントの品質保証には 2 つの構造的な問題がある:

**事実の揮発**: 「レビューした」「PO が承認した」といった事実は、チャット履歴に埋もれ、次のセッションからアクセスできない。AI が「承認済み」と主張しても、それが事実かは検証できない。

**観点の揺れ**: 「品質チェックしてください」と言うと、AI はその場で思いついた観点でレビューする。セッションごとにチェック項目が変わり、前回見つけた問題カテゴリを次回は見逃す。

この章は ACCD の軸 B（専念の委譲）に位置づけられる。品質の検証をコードに委譲することで、AI は生成と推論に集中できる。Receipt-driven Gates と Criteria-first Review を 1 つのシステムとして統合的に解説する。

### 設計原理（How）

### Receipt: ファイルシステム上の事実マーカー

「何かが起きた」という事実を、ファイルシステム上のマーカーファイル（レシート）として永続化する:

```
.session/receipts/
├── s01_plan_review       # プランレビュー実施の証拠
├── s01_po_approval       # PO 承認の証拠
├── s01_entry             # コンテキストローディング実施の証拠
└── s01_cross_review      # クロスレビュー実施の証拠
```

AI がどんなに「レビュー済みです」と主張しても、レシートファイルが存在しなければ Gate は FAIL する。

### PO 承認の鮮度検証

レシートの mtime とセッション YAML の mtime を比較し、承認後の変更を検知する:

```
po_approval レシートの mtime < session YAML の mtime
→ stale（陳腐化）→ Gate FAIL
```

### Criteria-first: 検証観点をコードの外に定義する

検証項目を YAML ファイルに外部定義し、`type` フィールドで二分する:

| 基準 | machine | ai_judgment |
| --- | --- | --- |
| 入力 | 構造化データ（YAML, ファイルパス, Git diff） | 自然言語、コードの意味 |
| 出力 | PASS / FAIL（二値） | 判断 + 根拠 |
| 再現性 | 同一入力 → 同一結果 | モデル・プロンプトで揺れる |

原則: **機械的に検証できるものは全て machine にする**。ai_judgment は「意味」の判断にのみ使う。

### Gate による統合

Entry Gate と Exit Gate が Receipt の存在と Criteria の検証を統合実行する:

```
Entry Gate
├── V1:  context_files_exist      (machine)
├── V2:  not_needed_row_exists    (machine)
├── V6:  yaml_schema_match        (machine)
├── V7:  plan_review_receipt      (receipt)
├── V12: impact_coverage          (machine)
├── V14: po_approval_receipt      (receipt)
└── V15: context_loaded_receipt   (receipt)

Exit Gate
├── V3:  qg_methods_filled        (machine)
├── V4:  all_qg_pass              (machine)
├── V5:  records_nonempty         (machine)
├── V8:  path_id_exist            (machine)
├── V9:  records_coverage         (machine)
├── V10: cross_review_receipt     (receipt)
├── V11: acceptance_tests_pass    (machine)
├── V13: pytest_pass              (machine)
├── V16: pyright_pass             (machine)
├── V17: findings_triage_clean    (machine)
├── V18: triage_approval_receipt  (receipt)
├── V20: cross_review_clean       (machine)
└── V25: code_changes_have_tests  (machine)
```

### 新しいチェックの追加フロー

1. `review_criteria.yaml` に 1 行追加
2. `validators/` にチェック関数を 1 つ追加
3. 全セッションの Gate 検証に自動追加される


### BAS での実装（What）

### レシートの作成

```shell
bas planning mark-reviewed s01 --result "PASS"
bas planning mark-approved s01 --checklist "render_displayed=yes,content_approved=yes"
bas planning load-context s01
bas planning mark-cross-reviewed s01 --result "PASS" --transcript /path/to/transcript.jsonl
```

### review_criteria.yaml

```yaml
criteria:
  - id: V1
    name: コンテキストファイル実在
    type: machine
    gate: entry
    check: context_files_exist

  - id: R1
    name: 設計原則との整合性
    type: ai_judgment
    question: セッション計画は設計原則と整合しているか？
```

machine 項目は Gate が自動実行し、ai_judgment 項目はセッション YAML の QG 行として自動注入される。

### QG 自動注入

`scaffold.py` がセッション YAML を生成する際、`review_criteria.yaml` の `ai_judgment` 項目を QG 行として注入する:

```yaml
quality_gates:
  - id: QG-R1
    content: 設計原則との整合性
    method: ai_judgment
    status: not_done    # AI が作業後に pass/fail に更新
```

### 自プロジェクトへの適用

### Step 1: レシートディレクトリを作る

```shell
mkdir -p .session/receipts
```

### Step 2: 検証観点を YAML で定義する

```yaml
# standards/review_criteria.yaml
criteria:
  - id: V1
    name: テストが通る
    type: machine
    gate: exit
    check: tests_pass

  - id: R1
    name: コード可読性
    type: ai_judgment
    question: コードは第三者が理解できる可読性を持つか？
```

### Step 3: Cursor Rule でレシート確認を強制する

```markdown
# .cursor/rules/receipt-check.mdc
セッション YAML の編集を開始する前に:
- .session/receipts/{session_id}_plan_review の存在を確認
- .session/receipts/{session_id}_po_approval の存在を確認
レシートが存在しない場合は、作業を開始せず PO に報告
```


---


<a id="8-deterministic-guard--ai-出力の決定的判定"></a>

> **出典**: [08. Deterministic Guard](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005889/08.+Deterministic+Guard)（Confluence。Markdown として取得・整理。page id: `4484005889`, v5）

## Deterministic Guard — AI 出力の決定的判定

### 解く問題（Why）

AI エージェントが生成した成果物の品質を AI 自身に評価させると信頼性が低い:

1. **自己評価バイアス**: 自分が書いたものを高く評価する傾向がある
2. **判定の揺れ**: 同じ成果物でも、プロンプトやモデルによって判定が変わる
3. **数値化できない**: 「まあまあ良い」では後工程の判断基準にならない

この章は ACCD の軸 B（専念の委譲 — 判定の決定化）に位置づけられる。AI にスコアリングさせず、コードが数値で決定的に判定する。

### 設計原理（How）

### Finding Code による数値判定

AI の出力に対する問題を **Finding Code**（数値コード）で分類し、最大コードの数値レンジで判定を決定的に算出する:

```
Finding Code の数値レンジ:
  2xx: INFO       → 情報提供のみ
  3xx: WARNING    → 注意（許容範囲内）
  4xx: ERROR      → 要修正
  5xx: CRITICAL   → ブロック（進行不可）
```

判定の算出:

```
全 Finding の最大コード → Decision
  コードなし         → PASS
  max < 300          → PASS
  300 ≤ max < 400    → PASS_WITH_WARNINGS
  400 ≤ max < 500    → NEEDS_REVISION
  500 ≤ max          → BLOCKED
```

この算出は純粋な関数であり、同じ Finding セットに対して常に同じ Decision を返す。

### Guard の分離と統合

個別の検証ロジック（Guard）を独立したクラスとして実装し、フレームワーク（DeterministicGuard）が統合実行する:

```
DeterministicGuard（フレームワーク）
├── WorkflowStepsGuard    → ワークフロー step の整合性
├── FindingCodesGuard     → Finding Code の妥当性
├── ArtifactPathsGuard    → 成果物パスの実在チェック
├── MetadataRefsGuard     → メタデータ参照の検証
├── LifecycleGuard        → ライフサイクル状態の検証
└── WorkflowEngineGuard   → エンジン・モデルの多様性検証
```

### 3 層の分離

| 層 | 責務 | 変更頻度 |
| --- | --- | --- |
| BaseGuard | 契約の定義 | ほぼ不変 |
| 個別 Guard | ドメイン固有の検証 | 機能追加時 |
| DeterministicGuard | 統合と判定 | ほぼ不変 |

新しい検証を追加するとき、`BaseGuard` を継承した新クラスを作り登録するだけでよい。

### BAS での実装（What）

### BaseGuard

```python
class BaseGuard(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def run(self, context: dict[str, Any]) -> GuardOutput: ...
```

### DeterministicGuard

```python
class DeterministicGuard:
    def run(self, context, *, target="") -> GuardResult:
        all_checks, all_findings = [], []
        for guard in self._guards:
            output = guard.run(context)
            all_checks.extend(output.checks)
            all_findings.extend(output.findings)
        decision = compute_decision(all_findings)
        return GuardResult(target=target, decision=decision,
                           checks=all_checks, findings=all_findings)
```

### Finding Code レジストリ

[付録 B](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842287) に全コードを定義（[09 — Finding Code](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842151) で体系を解説）:

```yaml
- code: 201
  name: metadata_info
  severity: info
- code: 401
  name: missing_required_output
  severity: error
- code: 430
  name: same_engine_generation_review
  severity: critical
  message: 生成とレビューが同一エンジン・モデルファミリー
```

FC-430 CRITICAL_REVIEW_SAME_ENGINE はワークフロー内で生成ステップとレビューステップが同一エンジン・同一モデルファミリーで実行される場合に発火する。これは軸 C（認知的多様性）の機械的強制。

### 自プロジェクトへの適用

### Step 1: Finding Code 体系を定義する

```yaml
codes:
  - code: 201
    name: info_note
    severity: info
  - code: 401
    name: missing_test
    severity: error
  - code: 501
    name: security_violation
    severity: critical
```

### Step 2: 判定ロジックを実装する

```python
def compute_decision(findings):
    if not findings:
        return "PASS"
    max_code = max(f["code"] for f in findings)
    if max_code >= 500: return "BLOCKED"
    elif max_code >= 400: return "NEEDS_REVISION"
    elif max_code >= 300: return "PASS_WITH_WARNINGS"
    return "PASS"
```

### Step 3: Guard を作って登録する

新しい検証 = 新しい Guard クラス。既存コードの変更は不要。


---


<a id="9-finding-code--ai-エージェント開発のエラー体系"></a>

> **出典**: [09. Finding Code — AI エージェント開発のエラー体系](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842151/09.+Finding+Code+AI)（Confluence。Markdown として取得・整理）

## Finding Code — AI エージェント開発のエラー体系

### 解く問題（Why）

AI エージェントの出力に対する品質チェックでは、問題の種類と深刻度を統一的に記述する仕組みが必要になる。しかし以下の問題がある:

1. **分類の揺れ**: AI がその場で「問題あり」と判断しても、深刻度の基準がセッションごとに異なる
2. **アクションの曖昧さ**: 問題を検知しても「何をすべきか」（差し戻し？ブロック？警告のみ？）が不明確
3. **蓄積と分析の困難**: 自然言語のエラーメッセージでは、パターンの検知や統計的な品質分析ができない

この章は ACCD の軸 B（専念の委譲）に位置づけられる。AI にエラーの分類と対応判断をさせず、コードが Finding Code で機械的に分類・処理する。

### 設計原理（How）

### HTTP ステータスコードの着想

Finding Code の番号体系は HTTP ステータスコードとコンパイラエラーコードから着想を得ている:

| HTTP | Finding Code | 意味 |
| --- | --- | --- |
| 2xx Success | 2xx Info | 肯定的所見。処理続行 |
| 3xx Redirection | 3xx Warn | 改善推奨。処理は続行するが警告を記録 |
| 4xx Client Error | 4xx Error | 問題あり。ステップを差し戻して再実行 |
| 5xx Server Error | 5xx Critical | 重大問題。タスク全体をブロック |
| — | 6xx Human | 人間の判断が必要。AI では解決不能 |

HTTP と同様に、番号の先頭桁で深刻度が決まる。コードを見ただけでアクションがわかる設計。

### severity × action の 2 軸分類

各 Finding Code は **深刻度（severity）** と **アクション（action）** の 2 つの属性を持つ:

| 深刻度 | アクション | 意味 |
| --- | --- | --- |
| Info | `continue` | 肯定的所見。何もしない |
| Warn | `continue_with_warning` | 処理を続行するが、警告を記録する |
| Error | `retry_step` | 該当ステップを差し戻し、再実行する |
| Critical | `block_task` | タスク全体をブロック。人間の介入なしに続行不可 |
| Human | `human_decision` | 人間が判断する。AI は待機する |

原則として番号帯のデフォルト severity に従うが、例外は `severity_override: true` で明示する（例: FC-430 CRITICAL_REVIEW_SAME_ENGINE は 4xx 番号帯だが severity は Critical）。

### Gate との統合

Finding Code は単独では機能しない。[08 — Deterministic Guard](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005889) と [07 — 品質ゲート](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874841) が Finding Code を発行し、Gate が action に基づいて制御フローを決定する:

```
Guard が出力を検査
  → Finding Code を発行（例: FC-416 UNVERIFIED_REFERENCE）
  → severity: error, action: retry_step
  → Gate がステップを差し戻し
  → AI がステップを再実行
```

### コードの命名規則

```
FC-{番号} {UPPER_SNAKE_CASE_NAME}

例: FC-430 CRITICAL_REVIEW_SAME_ENGINE
    FC-506 HALLUCINATED_SOURCE_OR_FACT
```

名前はコードの意味を簡潔に表す英語の UPPER_SNAKE_CASE。番号は一度割り当てたら変更しない（後方互換性）。

### BAS での実装（What）

### 番号帯の概要

| 番号帯 | 深刻度 | アクション | コード数 |
| --- | --- | --- | --- |
| 2xx | Info | 続行 | 1 |
| 3xx | Warn | 警告付き続行 | 18 |
| 4xx | Error | ステップ差し戻し | 36 |
| 5xx | Critical | タスクブロック | 19 |
| 6xx | Human | 人間判断 | 5 |

合計: 79 コード（全一覧: [付録 B](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842287)）

### 代表的な Finding Code

#### 提案書品質（3xx〜4xx）

| Code | Name | 説明 |
| --- | --- | --- |
| 301 | SOURCE_RECENCY_WEAK | 出典の鮮度が弱い |
| 402 | SOURCE_MISSING | 必要な出典が存在しない |
| 404 | HYPOTHESIS_NOT_SUPPORTED | 仮説を支持するエビデンスがない |
| 409 | DRAFT_OVERCLAIMS | ドラフトが過大な主張をしている |

#### AI 出力の決定的検証（4xx）

| Code | Name | 説明 |
| --- | --- | --- |
| 416 | UNVERIFIED_REFERENCE | 参照が検証されていない |
| 417 | INVALID_ARTIFACT_PATH | artifact パスが無効 |
| 421 | URL_NOT_VERIFIED | URL が検証されていない |
| 430 | CRITICAL_REVIEW_SAME_ENGINE | 生成と批判が同一エンジン（Critical に昇格） |

#### ハルシネーション検知（5xx）

| Code | Name | 説明 |
| --- | --- | --- |
| 506 | HALLUCINATED_SOURCE_OR_FACT | 出典・事実が AI の捏造 |
| 512 | FABRICATED_REFERENCE_IN_OUTPUT | 出力に捏造された参照 |
| 513 | FABRICATED_ID_OR_PATH | 捏造された ID・パス |
| 514 | UNVERIFIED_CALCULATION_USED_AS_FACT | 未検証の計算結果を事実として使用 |

#### 人間判断（6xx）

| Code | Name | 説明 |
| --- | --- | --- |
| 601 | HUMAN_APPROVED | 人間が承認 |
| 604 | HUMAN_REQUESTED_MAJOR_REVISION | 大幅な修正を要求 |
| 612 | HUMAN_BLOCKED_UNTIL_INPUT | 人間の入力待ち |

全 79 コードの完全な定義は [付録 B — Finding Code 全一覧](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842287) を参照。

### 段階的な深刻度昇格

同じ問題でも、パイプラインの段階によって深刻度が変わる:

```
Hypothesis Exploration Gate:
  FC-322 HYPOTHESIS_NOT_TESTABLE → Warn（探索段階では許容）

後段 Gate:
  FC-405 HYPOTHESIS_NOT_TESTABLE → Error（後段では差し戻し）
```

早い段階では警告に留め、後段で未解消なら差し戻す。パイプライン全体で品質を段階的に高める設計。

### finding_codes.yaml の構造

```yaml
- code: 430
  name: CRITICAL_REVIEW_SAME_ENGINE
  severity: critical
  severity_override: true    # 4xx だが Critical に昇格
  action: block_task
  gate: WorkflowRunner（pre-flight check）
  description: >
    critical-review step の engine が主生成 step と
    同一 engine で実行された。モデル固有バイアスの
    相殺が無効化されるため、workflow 実行を拒否する。
  source: session
  related_ac: [AC-23]
  related_adr: [ADR-011]
```

### 自プロジェクトへの適用

### Step 1: 番号体系を決める

HTTP ステータスコードの体系をそのまま借用するのが最も簡単:

```yaml
# standards/finding_codes.yaml
- code: 401
  name: TEST_NOT_PASSING
  severity: error
  action: retry_step
  description: テストが通っていない
```

### Step 2: Guard から Finding Code を発行する

```python
def check_tests(output_dir):
    result = subprocess.run(["pytest", output_dir], capture_output=True)
    if result.returncode != 0:
        return Finding(code=401, name="TEST_NOT_PASSING")
    return None
```

### Step 3: アクションを Gate に接続する

```python
findings = run_all_guards(output_dir)
critical = [f for f in findings if f.severity == "critical"]
if critical:
    block_task(critical)
errors = [f for f in findings if f.severity == "error"]
if errors:
    retry_step(errors)
```


---


# Part 3: 実行基盤とパイプライン


<a id="10-エンジンとモデル選択"></a>

> **出典**: [10. エンジンとモデル選択](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874861/10)（Confluence。Markdown として取得・整理）

## エンジンとモデル選択

### 解く問題（Why）

AI エージェント開発では、実行エンジン（Cursor CLI, Claude Code CLI, Codex CLI 等）とモデル（Claude, GPT 等）の選択が成果物の品質に直接影響する。しかし以下の問題がある:

1. **エンジンロックイン**: 1 つのエンジンに依存すると、そのエンジンの障害や制約がプロジェクト全体をブロックする
2. **確証バイアス**: 同じモデルが生成と批判を兼ねると、自分の出力を批判的に検証できない
3. **暗黙的な選択**: AI にエンジンやモデルを自由に選ばせると、選択理由が記録されず再現できない

この章は ACCD の 2 つの軸に位置づけられる。軸 C（認知的多様性）— 異なるモデルファミリーを使い分けることで確証バイアスを排除する。軸 B（専念の委譲）— ワークフロー YAML に宣言したモデルを CLI 引数として機械的に渡すことで、AI にモデル選択を判断させない。

### 設計原理（How）

### 統一インターフェースによるエンジン抽象化

BAS は `AgentRunner` 抽象基底クラスで全エンジンを統一インターフェース化している。各エンジンは `AgentRunner` を実装するだけで差し替え・追加が可能:

```python
class AgentRunner(ABC):
    @abstractmethod
    def run(self, engine, prompt, workspace, expected_outputs,
            *, model=None, max_turns=30, ...) -> AgentRunResult:
```

ワークフロー YAML に宣言された `model` は、このインターフェースを通じて各エンジンの **CLI 引数に機械的に渡される**。AI が実行時にモデルを選ぶのではなく、コードが決定的に強制する。

### 実装済みの 3 エンジン

BAS は現在 3 つのエンジンを実装済みで、ワークフロー YAML の `engine` フィールドを変えるだけで差し替えできる:

| エンジン | CLI コマンド | model の渡し方 | 特徴 |
| --- | --- | --- | --- |
| CursorEngine | `cursor agent --model ` | `--model` 引数 | 主実行エンジン。IDE ではなく CLI（subprocess）として起動 |
| ClaudeCodeEngine | `claude --model ` | `--model` 引数 + `--settings`, `--mcp-config`, `--agents` 明示指定 | 再現可能性のため全パラメータを明示。`--bare` は OAuth 非互換のため不使用 |
| CodexEngine | `codex exec --model  --json --full-auto` | `--model` 引数 | `--ephemeral --ignore-user-config` でユーザー設定に依存しない |

3 エンジン全てが同じ `AgentRunner` インターフェースを実装しているため、将来新しい CLI エンジンが登場した場合も `AgentRunner` を実装するだけで統合できる。ワークフロー YAML の変更は `engine` フィールドの値を変えるだけで済む。

### エンジン統一とモデルファミリー分散

現時点の `proposal_mvp.yaml` は `engine: cursor`（Cursor CLI）に統一し、認知的多様性は**モデルファミリーの分散**で確保する設計:

| 多様性の確保手段 | 方法 | 機械的強制 |
| --- | --- | --- |
| モデルファミリー分散 | 生成（Claude）と批判（GPT）で異なるファミリー | FC-430 CRITICAL_REVIEW_SAME_ENGINE |
| エンジン切替可能設計 | 障害時に別エンジンへ自動フォールバック | engine_resolver |

Cursor CLI は `--model` 引数で任意のモデルを指定できるため、**1 つのエンジンで複数のモデルファミリーを使い分けられる**。認知的多様性の中核はモデルファミリーの分散であり、エンジンの違いは補助的な効果。

### モデルファミリー分散

ワークフロー内で生成ステップとレビューステップに異なるモデルファミリーを指定する:

```yaml
steps:
  - id: strategy
    model: claude-opus-4-7-thinking-high     # Claude ファミリー（生成）
  - id: hypothesis_challenge
    model: gpt-5.5-high                       # GPT ファミリー（批判）
  - id: critical_review
    model: gpt-5.5-extra-high                 # GPT ファミリー（最終レビュー）
```

生成と批判で同一モデルファミリーを使うと、Finding Code [FC-430 CRITICAL_REVIEW_SAME_ENGINE](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483842151) が発火する（[08 — Deterministic Guard](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005889)）。

### Preflight + engine_resolver による動的解決

パイプライン実行時、2 段階のプロセスでエンジンとモデルを決定する:

**1. Preflight（事前検出）**: `run_preflight()` が各エンジンの CLI が利用可能かを検出する。

**2. resolve_engines（動的解決）**: 各ステップのエンジンを以下の優先順位で解決し、利用不可なら自動フォールバックする:

```
1. step.engine が明示指定かつ利用可能 → そのエンジンを使用
2. step.engine が利用不可 → cursor にフォールバック
3. step.engine 未指定 → workflow.default_engine を使用
```

フォールバック時も元のモデルファミリーに近いモデルを自動選定する:

| 元のエンジン | フォールバック先 | 自動選定モデル |
| --- | --- | --- |
| claude-code | cursor | claude-4.6-sonnet-medium-thinking |
| codex | cursor | gpt-5.3-codex |

### モデル選択ポリシー

モデルの選択は以下の基準で行う:

| 基準 | 説明 |
| --- | --- |
| タスクの性質 | 生成（創造性重視）vs 検証（正確性重視） |
| モデルファミリーの分散 | 生成と批判で同一ファミリーを避ける |
| コスト | 重要度に応じてモデルのグレードを選択 |
| thinking モード | 複雑な推論が必要な場合は thinking-high/extra-high |

### BAS での実装（What）

### ワークフロー YAML

```yaml
# workflows/proposal_mvp.yaml
default_engine: cursor

steps:
  - id: strategy
    engine: cursor
    model: claude-opus-4-7-thinking-high
  - id: hypothesis_challenge
    engine: cursor
    model: gpt-5.5-high
  - id: deterministic_guard
    engine: none           # コード実行のみ。AI 不要
```

`engine` と `model` はワークフロー YAML に宣言され、実行時に `AgentRunner.run()` の引数として渡される。AI が動的に判断する余地はない。

### 3 エンジンの起動パターン

```python
# CursorEngine: cursor agent --model <model> --trust --force --print
class CursorEngine(AgentRunner):
    def run(self, engine, prompt, workspace, expected_outputs, *, model=None, ...):
        args = ["agent", "--model", model, "--trust", "--force", "--print",
                "--output-format", "stream-json", "-p", prompt]
        subprocess.run(["cursor"] + args, cwd=workspace)

# ClaudeCodeEngine: claude --model <model> --settings ... --mcp-config ...
class ClaudeCodeEngine(AgentRunner):
    def run(self, engine, prompt, workspace, expected_outputs, *, model=None, ...):
        args = ["--model", model, "--settings", self._settings_path,
                "--mcp-config", self._mcp_config_path, "--agents", self._agents_path,
                "--max-turns", str(max_turns), "-p", prompt]
        subprocess.run(["claude"] + args, cwd=workspace)

# CodexEngine: codex exec --model <model> --json --full-auto --ephemeral
class CodexEngine(AgentRunner):
    def run(self, engine, prompt, workspace, expected_outputs, *, model=None, ...):
        args = ["exec", "--model", model, "--json", "--full-auto",
                "--ephemeral", "--ignore-user-config"]
        subprocess.run(["codex"] + args, cwd=workspace, input=prompt)
```

### WorkflowEngineGuard（FC-430 CRITICAL_REVIEW_SAME_ENGINE）

生成ステップとレビューステップが同一モデルファミリーで実行される場合に Critical Finding を発行:

```python
def _model_family(model_name: str) -> str:
    if "claude" in model_name: return "claude"
    if "gpt" in model_name or "codex" in model_name: return "gpt"
    return "unknown"
```

### 自プロジェクトへの適用

### Step 1: モデルファミリーの分散を意識する

生成と批判に同じモデルを使わない。最小構成:

* 生成: Claude
* レビュー: GPT（または別バージョンの Claude）


### Step 2: ワークフロー YAML でモデルを宣言する

```yaml
steps:
  - id: generate
    model: claude-sonnet
  - id: review
    model: gpt-4
```

モデルを YAML に宣言することで、AI の実行時判断を排除し再現可能にする。

### Step 3: エンジンの抽象化と差し替え

エンジンを抽象インターフェースで統一し、CLI コマンドの差異を隠蔽する。新しいエンジンが登場した場合も、インターフェースを実装するだけで既存のワークフロー YAML をそのまま使える。

### Step 4: エンジン障害時のフォールバック

利用可能なエンジンを事前検出し、障害時は自動フォールバックする仕組みを設ける。フォールバック時も元のモデルファミリーに近いモデルを自動選定することで、認知的多様性を維持する。


---


<a id="11-サブエージェントアーキテクチャ"></a>

## サブエージェントアーキテクチャ

> **出典**: [11 — サブエージェントアーキテクチャ](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005909/11.)（page id: `4484005909`, v3）

### 解く問題（Why）

AI エージェントのコンテキストウィンドウは有限であり、1 つのセッションで全ての作業を行うと以下の問題が起きる:

1. **コンテキスト汚染**: レビュー結果や分析データが作業コンテキストを圧迫し、本来の作業に使える容量が減る
2. **確証バイアス**: 自分が書いたコードを自分でレビューしても、批判的な視点が不足する
3. **並列性の欠如**: 複数の独立した分析を逐次実行すると、時間がかかる

この章は ACCD の軸 A（制約の補完 — 容量上限への対処）と軸 C（認知的多様性）に位置づけられる。サブエージェントによるコンテキスト分離は軸 A、異なる視点での分析は軸 C の実装。

### 設計原理（How）

### 2 つの用途

サブエージェントには大きく分けて 2 つの用途がある:

#### 用途 1: 開発支援（レビュー・分析）

メインの作業コンテキストを汚染せずに、独立した分析やレビューを実行する:

* **plan-reviewer / plan-reviewer-deep**: セッション計画の整合性レビュー
* **explore**: コードベースの探索・影響調査
* **ci-investigator**: CI 失敗の原因調査

#### 用途 2: プロダクト生成（壁打ち・批判的検証）

提案書パイプライン内で、異なる視点からの批判的検証を行う:

* **hypothesis-simulation**: 仮説のシミュレーションと優先順位付け
* **critical-review**: 仮説や提案への批判的レビュー
* **book-advisor**: 書籍ライブラリの知見に基づく壁打ち

### コンテキスト分離の原則

サブエージェントはメインエージェントのコンテキストウィンドウとは独立した空間で動作する:

```
メインエージェント（コンテキスト: 作業 + 計画）
├── サブエージェント A（コンテキスト: レビュー対象のみ）
├── サブエージェント B（コンテキスト: 分析対象のみ）
└── サブエージェント C（コンテキスト: 探索対象のみ）
```

利点:

* メインの作業コンテキストが圧迫されない
* 各サブエージェントは自分のタスクに集中できる
* 並列実行が可能

### 結果の合成

サブエージェントの結果をメインエージェントが合成する際の規律:

1. **完了待ち**: サブエージェントの結果を確認するまで、その結果に依存する作業に着手しない
2. **全件確認**: サマリーだけで判断せず、詳細結果（full response）を確認する
3. **全 findings 対応**: Critical/Major のみ対応して Minor/Info を後回しにしない

### readonly モードの活用

分析・レビュー系のサブエージェントは `readonly: true` で実行し、意図しないファイル変更を防止する。

### BAS での実装（What）

### 開発支援サブエージェント

| サブエージェント | 用途 | readonly |
| --- | --- | --- |
| `plan-reviewer` | 計画の整合性チェック | Yes |
| `plan-reviewer-deep` | 詳細なプランレビュー（findings 付き） | Yes |
| `explore` | コードベース探索・影響調査 | Yes |
| `ci-investigator` | CI 失敗の原因調査 | Yes |

### プロダクト生成サブエージェント

| サブエージェント | 用途 | readonly |
| --- | --- | --- |
| `critical-review` | 仮説・提案への批判的レビュー | Yes |
| `hypothesis-simulation` | 仮説のシミュレーション | Yes |
| `proposal-strategy` | 戦略立案 | No |
| `book-advisor` | 書籍知見に基づく壁打ち | Yes |

### 規律のルール化

サブエージェント完了待ちの規律は `bas-subagent-wait.mdc` で強制:

* サブエージェントの結果を確認するまで実装行為を開始しない
* `AwaitShell` でサブエージェントをポーリングしない（完了通知を待つ）
* サマリーのみで後続処理に着手しない

### --transcript による監査

クロスレビューの `mark-cross-reviewed` コマンドは `--transcript` オプションでサブエージェントの transcript パスを受け取り、transcript 内の finding 件数と YAML の `cross_review_findings` 件数を機械的に突合する。

### 自プロジェクトへの適用

### Step 1: レビューをサブエージェントに委譲する

コードレビューや設計レビューを、メインの作業コンテキストから分離する:

```
# Cursor の Task ツールを使用
Task(subagent_type="explore", prompt="X の影響範囲を調査して")
```

### Step 2: readonly を活用する

分析・レビュー系のタスクには `readonly: true` を指定し、意図しない変更を防止する。

### Step 3: 結果待ちルールを配置する

```markdown
# .cursor/rules/subagent-wait.mdc
サブエージェントに分析を委譲した場合、結果を確認するまで
その結果に依存する作業に着手してはならない。
```


---


<a id="12-提案書生成パイプライン--7-ステップの全体像"></a>

> **出典**: [12. 提案書生成パイプライン](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483940374/12)（Confluence。Markdown として取得・整理）

## 提案書生成パイプライン — 7 ステップの全体像

### 解く問題（Why）

提案書を AI に書かせると「良さそうな文章」は生成されるが、以下の問題がある:

1. **仮説の不在**: いきなり提案書を書き始め、「なぜその提案なのか」の根拠が薄い
2. **批判の不在**: 生成したモデルが自分の出力を肯定する確証バイアス
3. **品質の不確定**: 提案書が「十分か」を判断する定量的な基準がない

BAS の提案書生成パイプラインは、この問題に ACCD の 5 軸を適用した実装例。仮説駆動（軸 C: 認知的多様性）、段階的圧縮（軸 D: 段階的圧縮）、決定的検証（軸 B: 専念の委譲）を統合する。

### 設計原理（How）

### 7 ステップの構成

> **図（フロー）**: 7 ステップの全体像ダイアグラムは [Confluence の該当ページ](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483940374/12) で表示されます。API 経由の Markdown 変換ではメディアが blob URL となるため、ここでは省略しています。

| ステップ | 軸 | 役割 |
| --- | --- | --- |
| strategy | C（認知的多様性） | 複数の仮説を並列生成 |
| simulation | D（段階的圧縮） | 各仮説をシミュレーションし優先順位付け |
| hypothesis_challenge | C（認知的多様性） | 異なるモデルによる批判的検証 |
| drafting | D（段階的圧縮） | 強化された仮説から提案書を起案 |
| packet | D（段階的圧縮） | 全出力を 1 つのレビューパケットに集約 |
| deterministic_guard | B（専念の委譲） | コードによる決定的判定 |
| critical_review | C（認知的多様性） | 異なるモデルによる最終レビュー |

### 段階的情報圧縮（軸 D: 段階的圧縮）

各ステップは前ステップの出力を圧縮して受け取る:

```
brief.md (入力)
  → 01_hypotheses.md + 01_argument_map.md (strategy で展開)
    → 02_hypothesis_simulation.md + 02_prioritized_hypotheses.md (simulation で精査)
      → 03_strengthened_hypotheses.md (challenge で強化)
        → 04_proposal_outline.md + 04_executive_summary.md (drafting で統合)
          → 05_review_packet.md (packet で集約)
```

出力ファイル名の `NN_` プレフィックスはステップ番号で、PO が読む順序を明示する。`_handover/` サブディレクトリはステップ間引き継ぎ用（PO は読まない）。

### rerun_from_step

ステップ N で失敗した場合、ステップ 1 からやり直す必要はない。`rerun_from_step` で途中から再実行:

```shell
bas worker run proposal_mvp --project hotel-breakfast --rerun-from simulation
```

### BAS での実装（What）

### ワークフロー YAML

```yaml
# workflows/proposal_mvp.yaml
name: proposal_mvp
version: "0.5"
default_engine: cursor

steps:
  - id: strategy
    skill: proposal-strategy
    engine: cursor
    model: claude-opus-4-7-thinking-high
  - id: simulation
    skill: hypothesis-simulation
    engine: cursor
    model: claude-4.6-sonnet-medium-thinking
  # ... (7 steps)
```

### Handover テンプレート

各スキルは `templates/handover.md` を持ち、次ステップへの引き継ぎ情報の構造を定義:

```markdown
### 前提条件
### 主要な判断
### 次ステップへの申し送り
```

### 出力ファイル構造

```
projects/<slug>/outputs/
├── 01_hypotheses.md
├── 01_argument_map.md
├── 01_book_advisor_strategy.md
├── 02_hypothesis_simulation.md
├── 02_prioritized_hypotheses.md
├── 03_strengthened_hypotheses.md
├── 04_proposal_outline.md
├── 04_executive_summary.md
├── 05_review_packet.md
└── _handover/
    ├── strategy.md
    ├── simulation.md
    └── drafting.md
```

### 自プロジェクトへの適用

### Step 1: ワークフローを YAML で定義する

パイプラインの全ステップを宣言的に記述する。各ステップに入力・出力・使用するスキルを明示。

### Step 2: Handover テンプレートを設計する

ステップ間の情報引き継ぎを構造化する。「何を引き継ぐか」を事前に定義することで、情報の欠落を防ぐ。

### Step 3: 段階的に検証ステップを追加する

生成だけでは不十分。批判（hypothesis_challenge）→ 数値検証（deterministic_guard）→ 最終レビュー（critical_review）の 3 段階を推奨。


---


<a id="13-仮説生成とシミュレーション"></a>

> **出典**: [13. 仮説生成とシミュレーション](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005929/13.)（Confluence。Markdown として取得・整理）

## 仮説生成とシミュレーション

### 解く問題（Why）

従来のコンサルティングでは、人的資源の制約から仮説を早期に 1 つに絞り込んで深掘りするのが合理的だった。しかし AI のコストが劇的に下がった今、この制約は解消されている:

1. **仮説の単線化**: 1 つの仮説に賭けて外れた場合、やり直しコストが大きい
2. **シミュレーション不在**: 仮説の実現可能性を事前に検証しない
3. **優先順位の恣意性**: どの仮説を採用するかの基準が明確でない

この章は ACCD の軸 C（認知的多様性）の応用。並列生成により複数の視点を確保し、シミュレーションにより実現可能性を事前検証する。

### 設計原理（How）

### 仮説並列生成

strategy ステップで複数の仮説を同時に生成する:

1. **ブリーフの分析**: 顧客課題・市場環境・制約条件を構造化
2. **仮説の生成**: 3〜10 個の独立した仮説を並列で生成
3. **論拠マップの構築**: 各仮説の根拠・反論・前提を構造化

各仮説は strategy ステップで初期の Confidence（信頼度）と Impact if true（真の場合の影響度）を付与される。この段階では仮説の根拠と証拠ニーズの明確化が目的であり、優先順位は仮のもの。

### Handover による段階的圧縮

strategy から simulation への引き継ぎは Handover テンプレートで構造化される:

| 引き継ぎ内容 | ファイル | 役割 |
| --- | --- | --- |
| 仮説一覧 | `01_hypotheses.md` | N 個の仮説とその根拠 |
| 論拠マップ | `01_argument_map.md` | 各仮説の支持/反論の構造 |
| 書籍知見 | `01_book_advisor_strategy.md` | ライブラリからの統合知見 |
| Handover | `_handover/strategy.md` | 判断の経緯と申し送り |

simulation は全出力を入力として受け取り、各仮説のシミュレーション結果を `02_hypothesis_simulation.md` に圧縮する。Handover ファイルにより strategy 内での判断の経緯が失われない。

### シミュレーション（ストレステスト）

simulation ステップの核心は各仮説へのストレステスト。仮説を「正しいと仮定して進める」のではなく、「壊そうとして耐えたものだけを残す」という設計思想。

各仮説に対して以下の 3 軸で分析する:

#### Counter-arguments（反論）

仮説を無効化しうる最も強い反論を複数挙げる。straw-man（藁人形論法）ではなく、仮説が本当に崩れる可能性のある実質的な反論であることが制約条件。

#### Reinforcements（補強）

反論を踏まえてもなお仮説を支持する根拠。理論的裏付け、他業種での再現性、ブリーフ内の事実等。

#### Stress-test result（結果判定）

| 項目 | 値域 | 判定基準 |
| --- | --- | --- |
| **Survives?** | Yes / Partial / No | 反論に耐えたか。Partial は条件付きで生存 |
| **Revised confidence** | High / Medium-High / Medium / Low-Medium / Low | ストレステスト後の信頼度。strategy の初期値から上下しうる |
| **Key risk** | 自由記述 | 実践で仮説を無効化しうる最大のリスク |

### Book Advisor 壁打ち（反論強化）

ストレステスト実施後、書籍ライブラリの知見で反論を強化する（ADR-046）。book-advisor サブエージェントを呼び出し、以下を問う:

1. これらの反論は書籍の事例でどう裏付けられるか？
2. 書籍が示す失敗パターンで見落としている反論はないか？
3. この優先度判定の理論的妥当性はどうか？

この壁打ちにより:

* 見落としていた反論が追加される（例: 事前オーダーの「Anxiety」反論）
* 仮説間の構造的依存関係が発見される（例: 2 つの仮説が独立ではなく統合設計が必要）
* Confidence が修正される（例: 「設計の基盤」→「前提条件として格上げ」で Medium → Medium-High）

Round 1 の省略は禁止。書籍引用は書名・章・ページ番号を必須とする。

### 優先順位付け

ストレステストと Book Advisor 壁打ちの結果に基づいて、仮説をランク付けする。

#### スコアリング式

```
ランク = (Confidence × Impact) × Feasibility
```

| 評価軸 | 値域 | 何を見ているか |
| --- | --- | --- |
| **Confidence（信頼度）** | High / Medium-High / Medium / Low-Medium / Low | 仮説の証拠基盤の強さ。反論に耐えたか |
| **Impact（影響度）** | High / Medium / Conditional | 仮説が真の場合、提案全体への貢献度 |
| **Feasibility（実現可能性）** | 暗黙評価 | Recommendation 欄で「低コスト・短期実装」等の形で反映 |

Confidence と Impact は定性評価（High / Medium / Low）の掛け合わせ。ブリーフの段階では定量データが未取得であるため、数値スコアではなく定性レベルを採用している。

#### タイブレーク規則

Confidence × Impact が同等の仮説が複数ある場合、以下の順序で優先する:

1. **因果的前提依存関係**: 他の仮説の入力（前提条件）になっている仮説を優先する。例: 「ジョブ分解調査」（H2）は「制約特定」（H3）と「予約設計」（H6）の両方の前提条件であるため、スコアが同等なら H2 が上位
2. **Feasibility**: 実現可能性が高い方を優先

この規則により、単純なスコア順ではなく**仮説間の因果構造**がランキングに反映される。

#### Cut line（ドラフティング対象外の判定）

ランク表の下部に Cut line を引き、それ以下の仮説はドラフティングステップに進まない。Cut line の判断基準:

* **Survives? が No**: ストレステストで生存できなかった仮説
* **提案コアではなく実装詳細**: 提案書で主張すべき仮説ではなく、実装フェーズで決定すべき事項（例: 「予約枠は 5 つ以下」→ 提案では「枠数は AB テストで決定」と記載するにとどめる）
* **Conditional Impact**: 前提条件が確認されない限り影響度が不確定


### 三段階の精錬プロセス

優先度は 1 回で確定するのではなく、パイプラインの 3 つのステップで段階的に精度を上げる:

> **注**: Confluence 上では本節に「三段階の精錬プロセス」を示す図が埋め込まれています。このエクスポートでは blob URL により外部から参照できないため、詳細は[出典ページ](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005929/13.)を参照してください。

| ステップ | 操作 | 優先度への影響 |
| --- | --- | --- |
| **strategy** | 各仮説に初期 Confidence・Impact を付与 | 仮の順序（根拠の質に基づく初期判定） |
| **simulation** | ストレステスト + Book Advisor Round 1 | Confidence の上下修正、依存関係の発見、Cut line の決定 |
| **hypothesis_challenge** | 異なるモデルファミリー（GPT）が優先度判定自体を批判 | ランキングの矛盾・過大評価の修正 |

#### hypothesis_challenge による優先度の批判

simulation ステップで Claude が付けた優先順位を、hypothesis_challenge ステップで GPT が批判的に検証する（[14 — 壁打ちと結果合成](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874881)）。検証の焦点:

* **ランキングの内部矛盾**: 「H2 は H3 の前提条件」と simulation 内で述べながら、H3 を H2 より上位にランクしている等の矛盾
* **Confidence の過大評価**: 実装の摩擦（フロント業務負荷、no-show 率等）を考慮せずに High と判定している等
* **依存関係の見落とし**: 独立した施策として扱っているが、実際には統合設計が必須である等

この異モデル検証により、生成モデルの確証バイアスが構造的に排除される。

### 提案構造への反映

優先順位が確定した仮説群は、提案書の Phase 構造に反映される:

| Phase | 内容 | 対応する仮説の特性 |
| --- | --- | --- |
| **Phase 0（先行調査）** | 他の仮説の前提条件を確認する調査 | 因果的前提依存関係で上位の仮説 |
| **Phase 1（最優先実施）** | 提案の柱。制約解消やボトルネック対処 | Confidence: High, Impact: High |
| **Phase 2（並行施策）** | Phase 1 と並行可能な補助施策 | Impact: Medium-High, Phase 1 との統合設計が必要 |
| **Phase 3（段階展開）** | Phase 2 稼働後の体験設計・ロールアウト | Conditional Impact, 前段の結果に依存 |
| **除外** | 提案スコープから外す要素 | Cut line 以下、または反論で否定された施策 |

### BAS での実装（What）

### strategy ステップ

```yaml
- id: strategy
  skill: proposal-strategy
  model: claude-opus-4-7-thinking-high
  output:
    - ${project_dir}/outputs/01_hypotheses.md
    - ${project_dir}/outputs/01_argument_map.md
    - ${project_dir}/outputs/01_book_advisor_strategy.md
```

book-advisor スキルにより書籍ライブラリの知見を統合。

### simulation ステップ

```yaml
- id: simulation
  skill: hypothesis-simulation
  model: claude-4.6-sonnet-medium-thinking
  output:
    - ${project_dir}/outputs/02_hypothesis_simulation.md
    - ${project_dir}/outputs/02_prioritized_hypotheses.md
```

### 出力例: ストレステスト結果

`02_hypothesis_simulation.md` の各仮説セクション構造:

```markdown
### H3: 処理能力ボトルネック

### Counter-arguments
- C3-a: 制約が席数の場合、補充・動線改善だけでは不十分
- C3-b: 制約強化のみでは不十分で、分散を並行実施する必要がある
- C3-c（最重要）: DBR は非製造業・非定常フローへの過剰適用の可能性

### Reinforcements
- Brief 自体が「配膳・片付けが追いつかない」と明記
- 他業種（飲食・病院・空港）でも DBR の基本原則は再現性が高い

### Book Advisor Round 1 補強
- C3-c への精緻化:「DBR 全体が無効」ではなく「ドラム特定方法の修正が必要」
- 隠れた失敗パターン: 稼働率最大化 → バッファなし → 滞留増大の悪循環
- H3 と H6 の構造的依存関係: DBR の「ロープ」機能が H6 に対応

### Stress-test result
- **Survives?**: Yes
- **Revised confidence**: High
- **Key risk**: 制約が席数の場合に強化策の有効性が限定される
```

### 出力例: ランク表

`02_prioritized_hypotheses.md` の構造:

```markdown
ランク付け基準: (信頼度 × 影響) × 実現可能性。同点は因果的前提依存関係を優先。

| Rank | ID | Title | Confidence | Impact | Survives? | Recommendation |
|------|----|-------|-----------|--------|-----------|----------------|
| 1 | H3 | 処理能力ボトルネック | High | High | Yes | 提案の柱①: Phase 1 の最優先実施項目 |
| 2 | H2 | 朝食ジョブは4タイプ | Medium-High | High | Yes | 提案の柱②: H3/H6 の設計入力として先行調査必須 |
| ... | | | | | | |

### Cut line
Rank 10（H9）以下はドラフティング対象外。
H9 は提案コアではなく実装フェーズの詳細設計事項。
```

### 出力例: hypothesis_challenge による優先度修正

GPT による批判（`gates/hypothesis_challenge.md`）で、simulation の優先度判定が修正される:

```markdown
| ID | 対象 | 指摘 | Severity | 修正案 |
|----|------|------|----------|--------|
| HC-1 | H3/H2 | ランク表で H3 > H2 だが、simulation 内で H2 は H3 の入力前提条件と明記。順序の矛盾 | major | H2 を Phase 0 の診断作業として Rank 1 に移動 |
| HC-3 | H6 | フロント業務負荷・no-show リスクを指摘しながら Medium-High を維持。甘い判定 | major | 運用検証前は Medium に降格 |
```

### 自プロジェクトへの適用

### Step 1: 仮説の並列生成を試す

「この課題に対して 3 つの異なるアプローチを提案してください」— これだけで仮説駆動の第一歩。各仮説には必ず Confidence（信頼度）と Evidence needed（必要な証拠）を付与させる。

### Step 2: ストレステストを追加する

各仮説に対して「最も強い反論を 2〜3 個挙げ、それでも生存するか判定してください」と依頼する。「実現可能性・期待効果・リスクを分析」よりも、**反論→生存判定**のフレームの方が批判の深度が上がる。

### Step 3: 依存関係を可視化する

仮説間の因果的依存関係（「A は B の前提条件」「C と D は統合設計が必要」）を明示させる。これにより、スコアだけでは見えない実装順序の制約が浮かび上がる。

### Step 4: 異なるモデルで優先度を批判させる

生成モデルと異なるファミリーのモデル（例: Claude で生成 → GPT でレビュー）に「このランキングの矛盾を指摘してください」と依頼する。同一モデルでは確証バイアスにより批判が浅くなる。

### Step 5: 人間が最終判断する

AI にスコアリングと Cut line の提案までさせるが、最終的にどの仮説を採用するかは人間が判断する。AI の優先度は「判断の素材」であり「判断そのもの」ではない。


---


<a id="14-エージェント間の壁打ちと結果合成"></a>

## エージェント間の壁打ちと結果合成

> **出典**: [14 — エージェント間の壁打ちと結果合成](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483874881/14.)（page id: `4483874881`, v6）

### 解く問題（Why）

AI エージェントが生成した仮説や提案を、同じモデルにレビューさせると意味のある批判が得られない:

1. **確証バイアス**: 生成モデルと同じ学習データ・推論パターンを持つモデルは、同じ盲点を共有する
2. **批判の深度不足**: 「概ね良い」という浅い評価で終わり、構造的な弱点を指摘できない
3. **結果の統合困難**: 複数のレビュー結果をどう統合するかの基準がない

この章は ACCD の軸 C（認知的多様性）の中核的な実装。異なるモデルファミリーによる壁打ちで確証バイアスを排除する。

### 設計原理（How）

### 壁打ちの 3 つの層

BAS の壁打ちは 3 つの層で構成される。参加者とタイミングが異なるが、**批判的検証 → 結果合成**という構造は共通:

| 層 | 参加者 | 実行方法 | タイミング |
| --- | --- | --- | --- |
| パイプライン壁打ち | AI ↔ AI | ワークフロー YAML のステップとして `bas worker` が順次実行。ファイルベースの入出力 | パイプライン実行中（自動） |
| IDE 壁打ち | 人間 ↔ AI | Cursor の `Task` ツールでサブエージェントを起動。チャットベース | 計画・開発時（随時） |
| Human Review | 人間 → AI | `bas review` で人間がフィードバック。Finding Code 6xx で AI に指示が戻る | パイプライン完了後 |

### パイプライン壁打ち（AI ↔ AI）

パイプライン内の壁打ちは**リアルタイムの対話ではなく、ファイルを介した非同期の批判的検証**。`bas worker` がワークフロー YAML のステップを順次実行し、前のステップの出力ファイルを次のステップの入力として渡す:

<!-- 図: Confluence 原文にパイプライン／ステップ間連携のスクリーンショットまたはダイアグラムあり。ローカル blob URL のためこのリポジトリでは画像を同梱していない。上記 Confluence ページを参照。 -->

各ステップの AI は、前のステップの AI が何を考えたか（中間推論）を見ることはできない。**最終出力ファイルだけが引き継がれる**。これにより、独立した視点が構造的に保証される。

#### system-prompt による役割注入

壁打ちステップの AI には `critical-review` スキルの system-prompt テンプレートで批判的な役割が注入される:

> "You are an independent critical reviewer executing on a DIFFERENT engine from the primary generation. Your purpose is to catch blind spots, logical gaps, and unjustified claims."

「レビューして」ではなく、**何をどの観点で批判すべきか**が構造化されたプロンプトとして渡される。

#### 2 つのモード

同一の `critical-review` スキルが `mode` パラメータで挙動を変える:

| モード | タイミング | 入力 | 出力 | 批判の焦点 |
| --- | --- | --- | --- | --- |
| `hypothesis_challenge` | 仮説生成後・起草前 | 仮説 + シミュレーション結果 | 強化済み仮説 + Gate レポート | 仮説の論拠・前提条件・差別化 |
| `final` | 提案書完成後 | 提案書 + Guard 結果 + hypothesis_challenge 結果 | Cross Review + final_gate.json | 内部整合性・過大な主張・missing elements |

### IDE 壁打ち（人間 ↔ AI）

計画段階や開発中に、人間が Cursor の `Task` ツールでサブエージェントを起動し、壁打ちを行う（[11 — サブエージェントアーキテクチャ](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005909)）:

```
人間: 「この仮説の弱点を指摘して」
  → Task(subagent_type="book-advisor", prompt="...")
    → サブエージェントが書籍知見に基づいて批判
  → 人間が結果を判断して作業に反映
```

パイプライン壁打ちとの違い:

* **対話的**: 人間がリアルタイムに介入し、方向を修正できる
* **コンテキスト分離**: サブエージェントはメインの作業コンテキストを汚染しない
* **柔軟性**: `book-advisor`（書籍知見）、`explore`（コード探索）等、目的に応じたサブエージェントを使い分ける


### Human Review（人間 → AI）

パイプライン完了後、PO が最終判断を行う。`gates/final_gate.json` と `gates/cross_review.md` を確認し、Finding Code 6xx で AI にフィードバックを返す:

| Finding Code | 意味 | AI の行動 |
| --- | --- | --- |
| FC-601 HUMAN_APPROVED | 承認 | 完了 |
| FC-604 HUMAN_REQUESTED_MAJOR_REVISION | 大幅修正要求 | 指摘箇所を修正して再実行 |
| FC-609 HUMAN_REQUESTED_RESEARCH | 追加調査要求 | 調査を実施して再提出 |
| FC-610 HUMAN_REQUESTED_REWRITE | リライト要求 | 該当セクションを書き直して再実行 |

### 結果の合成

複数の壁打ち結果を統合する際の規律:

| 原則 | 内容 |
| --- | --- |
| 矛盾する指摘 | 両方の論拠を提示し、PO に判断を委ねる |
| 共通する指摘 | 高い確度で対処が必要 |
| 一方のみの指摘 | 指摘されたモデルの専門性を考慮して判断 |

### BAS での実装（What）

### ワークフロー YAML のステップ定義

```yaml
# hypothesis_challenge: 仮説段階の壁打ち
- id: hypothesis_challenge
  skill: critical-review
  mode: hypothesis_challenge
  engine: cursor
  model: gpt-5.5-high          # GPT ファミリー（生成は Claude）
  input:
    - ${project_dir}/outputs/01_hypotheses.md
    - ${project_dir}/outputs/02_hypothesis_simulation.md
    - ${project_dir}/outputs/02_prioritized_hypotheses.md
  output:
    - ${project_dir}/gates/hypothesis_challenge.md
    - ${project_dir}/outputs/03_strengthened_hypotheses.md

# critical_review: 最終レビュー
- id: critical_review
  skill: critical-review
  mode: final
  engine: cursor
  model: gpt-5.5-extra-high    # GPT ファミリー（生成は Claude）
  input:
    - ${project_dir}/outputs/05_review_packet.md
    - ${project_dir}/outputs/04_proposal_outline.md
    - ${project_dir}/gates/deterministic_guard.json
    - ${project_dir}/gates/hypothesis_challenge.md
  output:
    - ${project_dir}/gates/cross_review.md
    - ${project_dir}/gates/final_gate.json
```

`input` / `output` フィールドにより、ステップ間のデータフローが YAML で宣言的に定義される。`bas worker` はこの宣言に従ってファイルを渡し、AI は宣言されたファイルだけを読み書きする。

### FC-430 CRITICAL_REVIEW_SAME_ENGINE による多様性の機械的強制

`WorkflowEngineGuard` が生成ステップとレビューステップのモデルファミリーを比較し、同一ファミリーの場合に Critical Finding を発行する（[08 — Deterministic Guard](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005889)）。

### 自プロジェクトへの適用

### Step 1: 生成とレビューでモデルを変える

最小構成: 生成を Claude、レビューを GPT（またはその逆）。

### Step 2: 批判の観点を事前定義する

「レビューしてください」ではなく、system-prompt で批判の観点（論理的整合性・実現可能性・独自性等）を構造化する。自由記述のレビューは深度が不足する。

### Step 3: ファイルベースの入出力を定義する

壁打ちステップの入力と出力をワークフロー YAML で宣言する。前のステップの出力ファイルだけが次のステップに渡されることで、独立した視点が構造的に保証される。

### Step 4: 人間の介入ポイントを設計する

パイプラインの最終段に Human Review Gate を配置し、Finding Code 6xx で人間のフィードバックを構造化する。「承認 / 修正要求 / リライト要求」等の定型化された応答で、AI が次のアクションを機械的に判断できるようにする。


---


<a id="15-context-loading-と読み制御"></a>

> **出典**: [15. Context Loading と読み制御](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005949/15.+Context+Loading)（Confluence。Markdown として取得・整理）

## Context Loading と読み制御

### 解く問題（Why）

AI エージェントのコンテキストウィンドウには物理的な上限がある。プロジェクトが成長すると、全ファイルを読み込むことは不可能になる。

この状況で AI に「必要なファイルを自分で探して読め」と任せると:

1. **読み漏れ**: 関連ファイルの存在を知らず、不整合な変更をする
2. **読み過ぎ**: 不要なファイルまで読んでウィンドウを浪費する
3. **再現不能**: 別セッションで同じタスクを実行したとき、違うファイルを読んで違う結果になる

この章は ACCD の軸 A（制約の補完 — 容量上限への対処）と軸 D（段階的圧縮 — 読み制御）に位置づけられる。

### 設計原理（How）

### 「読まない」を明示する

Context Loading Table は、セッション開始時に **AI が何を読み、何を読まないかを宣言する YAML 構造**:

```yaml
context_loading:
  - priority: must_read
    file: context/principles.yaml
    reason: 設計原則

  - priority: edit_target
    file: bas/planning/validators.py
    reason: 新しい検証チェックを追加

  - priority: reference
    file: design/gate_design.md
    reason: Gate 仕様の確認用

  - priority: not_needed
    file: bas/drive/sync.py
    reason: Drive 同期は今回のスコープ外
```

| 優先度 | 意味 | AI の行動 |
| --- | --- | --- |
| `must_read` | 必読。全文読み込む | `load-context` で自動出力 |
| `edit_target` | 編集対象 | `load-context` で自動出力 |
| `reference` | 詳細参照。部分的に読む | 必要時に部分読み込み |
| `not_needed` | 参照不要 | Gate が存在を強制検証 |

### なぜ `not_needed` が重要か

1. **暗黙の依存を排除**: 理由を書くことで「本当に不要か」を計画段階で検証する
2. **引き継ぎ**: 「なぜ読まなかったか」が残るので、次の AI が同じ判断を再現できる

Entry Gate が `not_needed` 行の存在を機械検証する（V2: 参照不要行の存在）。`not_needed` が 1 行もないセッションは Gate を通過できない。

### トークン予算の事前計算

```
推定トークン数 = must_read + edit_target の合計バイト数 ÷ 4
```

セッション開始前にこの数値を確認し、コンテキストウィンドウのオーバーフローを防止する。

### V12: 影響範囲カバレッジ

`edit_target` に指定したファイルを `import` している他のファイルが `context_loading` に登録されていない場合に警告を出す。変更の影響範囲が計画段階で可視化される。

### BAS での実装（What）

### コンテキストローディングの実行

```shell
bas planning load-context s01
```

1. `must_read` と `edit_target` のファイル内容を標準出力に出力
2. レシートファイルを記録
3. 推定トークン数を表示


### Gate での自動検証

| チェック | ID | 内容 |
| --- | --- | --- |
| `context_files_exist` | V1: ファイル実在 | `must_read` / `edit_target` のファイルが実在するか |
| `not_needed_row_exists` | V2: 参照不要行 | `not_needed` 行が最低 1 つ存在するか |
| `impact_coverage` | V12: 影響範囲 | 影響範囲がカバーされているか |

### 自プロジェクトへの適用

### Step 1: セッション YAML に Context Loading Table を追加する

```yaml
context_loading:
  - priority: must_read
    file: README.md
    reason: プロジェクト概要
  - priority: edit_target
    file: src/auth/login.py
    reason: ログイン機能の修正
  - priority: not_needed
    file: src/payment/stripe.py
    reason: 決済機能は今回のスコープ外
```

### Step 2: セッション開始時のルールを配置する

```markdown
# .cursor/rules/context-loading.mdc
セッション開始時に context_loading に従ってファイルを読んでから作業を開始してください。
```

### Step 3: 機械検証を追加する（オプション）

```python
import yaml
from pathlib import Path

with open(".session/sessions/s01.yaml") as f:
    data = yaml.safe_load(f)

for item in data.get("context_loading", []):
    if item["priority"] in ("must_read", "edit_target"):
        assert Path(item["file"]).exists(), f"File not found: {item['file']}"

has_not_needed = any(
    item["priority"] == "not_needed"
    for item in data.get("context_loading", [])
)
assert has_not_needed, "not_needed 行が必要"
```


---


# Part 4: 運用と拡張体系


<a id="16-git-ワークフローとコミット規約"></a>

> **出典**: [16. Git ワークフローとコミット規約](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4484005969/16.+Git)（Confluence。Markdown として取得・整理）

## Git ワークフローとコミット規約

### 解く問題（Why）

AI エージェントに Git 操作を任せると:

1. **main への直接コミット**: ブランチ戦略を無視して main に直接 push する
2. **コミットメッセージの不統一**: 毎回異なるフォーマットで、変更履歴が追跡しにくい
3. **機密情報の漏洩**: `.env` や `credentials.yaml` を無意識にコミットする
4. **破壊的操作**: `--force` push や hard reset を軽率に実行する

この章は ACCD の軸 A（制約の補完 — 揮発性への対処）に位置づけられる。Git の規約を明文化することで、セッション間で一貫した操作を保証する。

### 設計原理（How）

### ブランチ戦略

```
main（リリース）
 ↑ PR（CODEOWNERS review 必須）
dev（統合）
 ↑ squash merge
feature/<topic>（作業）
```

* `main` / `dev` への直接コミット禁止
* 全ての変更は feature ブランチで行う
* `dev` からブランチを切り、`dev` にマージ
* `main` へのマージはリリース時のみ（PR 必須）


### ブランチ命名

`/` 形式:

| prefix | 用途 |
| --- | --- |
| `feature/` | 新機能 |
| `fix/` | バグ修正 |
| `docs/` | ドキュメント |
| `chore/` | 雑務 |
| `refactor/` | リファクタリング |

### Conventional Commits（日本語版）

```
<type>(<scope>): <要約>

例:
feat(planning): Entry Gate に V25 コード変更テスト付随チェックを追加
fix(guards): FC-430 のモデルファミリー多様性チェックを修正
docs(guide): ACCD 5 軸体系の導出マップを追加
```

### squash merge

feature ブランチのコミット粒度は作業の都合。`dev` へのマージ時に squash して 1 コミットに集約する:

```shell
git checkout dev
git merge --squash feature/my-topic
git commit -m "feat(planning): ..."
git branch -d feature/my-topic
```

### Never リスト

| 操作 | 理由 |
| --- | --- |
| credentials のコミット | セキュリティ |
| `--force` push to main | 不可逆 |
| `--dangerously-skip-permissions` | 安全機構の迂回 |
| `git rebase -i`（インタラクティブ） | AI は対話入力を扱えない |

### BAS での実装（What）

### CONTRIBUTING.md が SoT

Git 規約の SoT は `CONTRIBUTING.md`。`bas-git-workflow.mdc` ルールが最小限の強制ルールを AI セッションに注入し、`bas-git-ops` スキルが具体的な操作テンプレートを提供する。

### リリース時の三点セット

```shell
# pyproject.toml の version を更新
# CHANGELOG.md にエントリを追加
# Git タグを作成
git tag v{VERSION}
```

三点の version が一致しなければ CI で検出される。

### 自プロジェクトへの適用

### Step 1: ブランチ保護を設定する

GitHub の Branch Protection で `main` / `dev` への直接 push を禁止する。

### Step 2: コミット規約をルール化する

```markdown
# .cursor/rules/git-workflow.mdc
main / dev への直接コミット禁止。
コミットメッセージ: <type>(<scope>): <要約>
credentials（.env 等）は絶対にコミットしない。
```

### Step 3: squash merge をデフォルトにする

GitHub の Merge Settings で「Squash and merge」をデフォルトに設定する。


---


<a id="17-スキル・ルール・hook・サブエージェント--4-層の拡張体系"></a>

> **出典**: [17. スキル・ルール・Hook・サブエージェント](https://showcasegig.atlassian.net/wiki/spaces/~588498106/pages/4483907635/17.+Hook)（Confluence。Markdown として取得・整理）

## スキル・ルール・Hook・サブエージェント — 4 層の拡張体系

### 解く問題（Why）

AI エージェントの振る舞いを制御する仕組みが増えると、「どの仕組みを使うべきか」が不明確になる:

1. **配置先の混乱**: スキル・ルール・Hook・サブエージェントのどこに置くべきかがわからない
2. **強制度の不一致**: ルールで書いても AI が無視するケースがある
3. **重複と矛盾**: 同じ制約が複数箇所に散在し、更新漏れが起きる

この章は ACCD の軸 E（自律的進化）に位置づけられる。4 層の拡張体系は、違反の観察から段階的に強制度を高める昇格パスの受け皿。

### 設計原理（How）

### 4 層の体系

| 層 | 形式 | 強制力 | 発火タイミング |
| --- | --- | --- | --- |
| **スキル** | `.agents/skills/*/SKILL.md` | なし（AI が選択） | AI が発火条件を検知 |
| **ルール** | `.cursor/rules/*.mdc` | 弱（AI に注入されるが従うかは保証なし） | セッション開始時に自動注入 |
| **Hook** | `.cursor/hooks.json` | 中（ターン終了時に自動実行） | afterFileEdit, stop 等 |
| **Validator** | `bas/planning/validators/` | 強（Gate を通過しなければ進めない） | validate コマンド実行時 |

### 配置判断フロー

```
「AI にこう振る舞ってほしい」
  ↓
Q: 手順（ステップ実行）が必要？
  → Yes → スキル（.agents/skills/）
  ↓ No
Q: 常に適用したい？
  → Yes → ルール（.cursor/rules/）
  ↓ No
Q: 特定のイベントで自動チェックしたい？
  → Yes → Hook（.cursor/hooks.json）
  ↓ No
Q: Gate で機械的にブロックしたい？
  → Yes → Validator（bas/planning/validators/）
```

### 昇格パス

同じ違反が繰り返された場合、段階的に強制度を高める:

```
観察（チャットで指摘）
  ↓ 3 回以上
ルール化（.cursor/rules/*.mdc）
  ↓ ルールでも再発
Hook 化（.cursor/hooks.json）
  ↓ Hook でも対処不十分
Validator 化（bas/planning/validators/）
```

### スキルの設計原則

* **Progressive Disclosure**: 最初に概要、詳細は Step で段階的に展開
* **発火条件の明確化**: SKILL.md のフロントマター `Use when:` / `Do NOT use for:` で明示
* **品質ゲート内蔵**: スキル自体に QG を定義可能


### リポ内スキル vs ユーザーレベルスキル

| 配置 | 用途 | 優先度 |
| --- | --- | --- |
| `.agents/skills/bas-*` | BAS プロジェクト固有 | 高（優先） |
| `~/.cursor/skills/` | ユーザーレベル共有 | 低 |

リポ内の `bas-*` スキルはユーザーレベルの同機能スキルに優先する。clone した別ユーザーにも同じスキルが適用される（再現可能性）。

AGENTS.md §Skill Precedence で定義される対応表:

| `bas-*` スキル | 優先される汎用スキル |
| --- | --- |
| `bas-session` | `session-planning` / `session-handover` |
| `bas-git-ops` | `git-ops` |
| `bas-decisions-record` | `decisions-record` |
| `bas-quality-gate` | `quality-gate` |
| `bas-create-skill` | `create-skill-rule` |
| `bas-create-rule` | `create-skill-rule` |
| `bas-create-hook` | `create-hook` |
| `bas-create-subagent` | `create-skill-rule` |
| `bas-scg-handbook` | `scg-handbook` |

### BAS での実装（What）

### スキルの例

| スキル | 用途 |
| --- | --- |
| `bas-session` | セッションライフサイクル管理 |
| `bas-git-ops` | Git 操作テンプレート |
| `bas-tdd` | TDD 開発ワークフロー |
| `bas-create-skill` | 新スキルの作成 |

### ルールの例

| ルール | 用途 |
| --- | --- |
| `bas-anti-sycophancy.mdc` | 追従防止 |
| `bas-no-step-skip.mdc` | スキップ禁止 |
| `bas-debugging-protocol.mdc` | デバッグ規律 |
| `bas-subagent-wait.mdc` | サブエージェント完了待ち |

### Hook の例

`.cursor/hooks.json` で定義される自動チェック。ターン終了時（stop）やファイル編集後（afterFileEdit）に発火する。

### 自プロジェクトへの適用

### Step 1: ルールから始める

Anti-Sycophancy + デバッグ規律の 2 つだけで大きな効果がある。

### Step 2: 繰り返す違反をルール化する

AI の行動で 3 回以上繰り返される問題を `.cursor/rules/` にルール化する。

### Step 3: スキルで手順を標準化する

「毎回同じ手順で実行してほしいタスク」をスキルとして定義する。

### Step 4: Hook で自動チェックを追加する

ルールで対処しきれない違反を Hook で機械的に検知する。


---