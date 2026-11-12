# 比賽雷達：幫高中生找比賽

每 3 天自動從獎金獵人（bhuntr.com）抓取比賽，篩出高中生能參加的，
再用網頁依「興趣關鍵字、類型、難易度」幫每位學生挑。全部免費，用 GitHub 就能跑。

## 檔案
- `scraper/scrape.py`：爬蟲，結果寫進 `docs/data.json`
- `.github/workflows/update.yml`：每 3 天自動執行爬蟲
- `docs/index.html`：篩選與推薦網站（會用 GitHub Pages 發布）

## 設定步驟（約 15 分鐘）
1. 到 github.com 註冊帳號，按右上角「+」→ New repository，取個名字（例如 `competition-radar`），選 **Public**，建立。
2. 在 repo 頁面按「uploading an existing file」，把這個資料夾裡的所有檔案拖進去（包含 `.github` 資料夾）→ Commit。
   - 如果 `.github` 資料夾傳不上去：按 Add file → Create new file，檔名輸入 `.github/workflows/update.yml`，貼上內容。
3. Settings → Actions → General → 最下面 Workflow permissions 選 **Read and write permissions** → Save。
4. Settings → Secrets and variables → Actions → Variables 分頁 → New repository variable：
   名稱 `CONTACT_EMAIL`，值填你的 email（會放在爬蟲的識別資訊裡，讓對方網站知道怎麼聯絡你）。
5. Actions 分頁 → 左邊點「更新比賽資料」→ Run workflow，等 3–10 分鐘跑完。
6. Settings → Pages → Branch 選 `main`、資料夾選 `/docs` → Save。
   幾分鐘後網址會出現在同一頁，例如 `https://你的帳號.github.io/competition-radar/`。

## 如果抓到 0 筆
打開 Actions 裡那次執行的紀錄，看「抓取比賽」步驟的訊息：
- 「列表頁一個連結都沒抓到」：原站網址或結構和程式預設不同，調整 `scrape.py` 上方的 `LIST_URL` 和 `DETAIL_RE`。
- 「robots.txt 不允許」：對方不希望被自動抓取，請停止或直接聯絡獎金獵人詢問。
把紀錄貼給 Claude 就能幫你改。

## 注意
- 使用前請讀獎金獵人的使用條款；若條款禁止自動抓取，請先徵得同意。
- 程式只存標題、連結、截止日、獎金和短摘要，學生要點連結回原站看完整辦法。
- 難易度和「高中能否參加」是用關鍵字推估的，報名前請再確認原頁面。
- 學生名字與設定只存在你自己電腦的瀏覽器，不會上傳；但網站本身是公開的。
