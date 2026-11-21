# gaikou — 盛岡 小児科ナビ

岩手県盛岡市周辺（盛岡市・滝沢市・矢巾町・紫波町）の小児科について、

1. **公式HP・順番受付ページから受付状況（受付中／終了、呼出番号、待ち人数）を自動で読み取り**
2. **口コミ評価（Googleマップ・Caloo・EPARK）を集め**
3. **3歳児連れで行きやすいかを点数化して、おすすめ順・今行きやすい順のリストにする**

ツールです。何度実行しても最新の状態に更新されます。

## 出力

| ファイル | 内容 |
|---|---|
| `docs/index.html` | スマホで見やすい一覧ページ（おすすめ順 / 今行きやすい順 / エリア絞り込み） |
| `docs/ranking.md` | Markdown のランキング表 |
| `data/latest.json` | 取得結果の全データ |

## スマホで使う

一覧ページ（GitHub Pages）はスマホ向けに作ってあり、ホーム画面に追加するとアプリのように開けます。

- **iPhone（Safari）**: ページを開く → 下の共有ボタン（□に↑）→「ホーム画面に追加」
- **Android（Chrome）**: ページを開く → 右上の︙ →「ホーム画面に追加」（または「アプリをインストール」）

画面の機能:
- 「おすすめ」/「今行きやすい」の並び替え、エリア絞り込み、「受付中のみ」表示（選んだ条件は次回も残ります）
- 各医院に **受付ページ / 電話する / 地図 / 公式HP** の大きなボタン
- 右上の **最新にする** で最新データを確認。アプリに戻ってきたときも自動で確認します
- 診療時間中にデータが75分以上古いと、警告を表示します
- 電波が無いときは、最後に開いた一覧を表示します
- 下部に #8000（こども医療電話相談）と夜間急患診療所への発信ボタン

**スマホだけで今すぐ更新したいとき**: スマホのブラウザで GitHub を開き、Actions →「小児科リスト更新」→ Run workflow
（ブラウザのメニューで「PC版サイトを表示」にすると押しやすいです）。数分後に「最新にする」を押すと反映されます。

## 使い方（手元のPC）

```bash
pip install -r requirements.txt
python update.py                  # 全医院を更新
python update.py --render         # JSで描画される受付ページにも対応（初回のみ: python -m playwright install chromium）
python update.py --only miura-kids,saito-ped
python update.py --refresh-reviews  # 口コミキャッシュ（1週間）を無視して再取得
```

### Googleマップの口コミを使う（任意）

Google Cloud で Places API (New) を有効にし、APIキーを環境変数に設定します。

```bash
export GOOGLE_MAPS_API_KEY=xxxxx
python update.py
```

キーが無い場合は Caloo / EPARK の評価と `clinics.yaml` の `manual_rating` だけで計算します。

## 自動更新（GitHub Actions + GitHub Pages）

`.github/workflows/update.yml` が診療時間帯（平日・土曜 8:00〜18:30 JST）に30分ごとに実行し、結果をコミットします。

1. リポジトリの Settings → Pages で `Deploy from a branch`、ブランチ `main` / フォルダ `/docs` を選ぶ
2. （任意）Settings → Secrets and variables → Actions に `GOOGLE_MAPS_API_KEY` を登録
3. 今すぐ更新したいときは Actions タブ → 「小児科リスト更新」→ **Run workflow**

## 医院の追加・修正

`clinics.yaml` を編集します。順番受付ページのURLが分かっている場合は `reservation_url` に書くと確実です
（未指定ならHP内のリンクから自動検出します）。口コミを手入力する場合は:

```yaml
    manual_rating: {rating: 4.1, count: 25, source: Googleマップ, url: https://maps.google.com/...}
```

公式HPが見つからなかった医院（`homepage: null`）は、HPのURLを追記すると次回から受付状況を取得します。

## おすすめ度の計算（100点満点）

| 項目 | 配点 |
|---|---|
| 口コミ（件数の少なさを補正したベイズ平均。★1〜5 → 0〜60点） | 60 |
| Web順番受付あり（院内の待ち時間を短くできる） | 15 |
| 小児科専門 | 10 |
| 土曜診療 | 10 |
| 受付状況を自動で確認できる | 5 |

重みは `pediatrics/score.py` で変更できます。「今行きやすい順」は 受付中 → 待ち人数が少ない → おすすめ度 の順に並べます。

## 仕組み

- `pediatrics/status.py` — HP内のリンク/iframe から順番受付システム（ドクターキューブ、アットリンク、EPARK、Airウェイト等）を検出し、受付ページの文言（「現在◯番」「待ち◯人」「本日の受付は終了」など）を正規表現で抽出
- `pediatrics/reviews.py` — Places API、口コミサイトの JSON-LD `aggregateRating` から評価を取得
- `pediatrics/score.py` — スコア計算
- `pediatrics/render.py` — HTML / Markdown / JSON 出力

テスト: `python -m pytest -q`

## 注意

- 受付状況は自動で読み取った推定値です。読み取りに失敗したり、表示が古かったりすることがあります。**受診前に必ず受付ページか電話で確認してください。**
- `clinics.yaml` の医院情報は2026年11月時点の公開情報をもとにしています。住所・診療時間・予約方法は変わることがあります。
- 各サイトへの負荷を抑えるため、1回の実行で1ページあたり1リクエスト、間隔1秒にしています。
- 夜間・休日: 盛岡市夜間急患診療所 019-654-1080 / こども医療電話相談 **#8000**
