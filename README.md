# Financial Dashboard Starter

This repository:

1. Downloads historical market prices from Yahoo Finance through `yfinance`.
2. Downloads economic series through the official FRED API.
3. Writes the results to CSV files in `data/`.
4. Refreshes the files every day at **6:00 a.m. America/New_York** through GitHub Actions.
5. Hosts `index.html` as a static GitHub Pages dashboard.

## Repository structure

```text
.
├── .github/workflows/daily_refresh.yml
├── data/
│   ├── fred_data.csv
│   ├── latest_snapshot.csv
│   ├── last_updated.json
│   └── market_data.csv
├── scripts/update_data.py
├── config.json
├── index.html
└── requirements.txt
```

## 1. Create the GitHub repository

Create a new GitHub repository and upload every file and folder in this starter package.

A public repository is the simplest option for GitHub Pages. The FRED API key is not stored in the repository; it is stored as an Actions secret.

## 2. Add your FRED API key

Create a FRED account and request an API key.

In the GitHub repository:

1. Open **Settings**.
2. Open **Secrets and variables → Actions**.
3. Select **New repository secret**.
4. Name the secret exactly `FRED_API_KEY`.
5. Paste the API key and save it.

Never put the API key in `index.html`, `config.json`, or a CSV file.

## 3. Run the first refresh manually

1. Open the repository's **Actions** tab.
2. Select **Daily financial data refresh**.
3. Select **Run workflow**.

The workflow downloads the data, creates the CSV files, and commits the refreshed files back to the repository.

## 4. Turn on GitHub Pages

1. Open **Settings → Pages**.
2. Under **Build and deployment**, select **Deploy from a branch**.
3. Select the `main` branch and the `/ (root)` folder.
4. Save.

The project URL will normally use this pattern:

```text
https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/
```

## 5. Customize the dashboard data

Edit `config.json`.

### Add a Yahoo Finance ticker

```json
{"symbol": "AAPL", "name": "Apple"}
```

Yahoo symbols must use Yahoo Finance's ticker format. For example, market indices often begin with `^`.

### Add a FRED series

```json
{"id": "MORTGAGE30US", "name": "30-Year Mortgage Rate"}
```

Use the FRED series ID shown on the series page.

## CSV schemas

### `data/market_data.csv`

```text
Date,Ticker,Open,High,Low,Close,AdjClose,Volume
```

### `data/fred_data.csv`

```text
Date,SeriesID,SeriesName,Value
```

### `data/latest_snapshot.csv`

```text
Source,SeriesID,Name,LatestDate,LatestValue,PreviousValue,Change,ChangePct
```

## Local test

Create and activate a Python virtual environment, install the packages, and set the key.

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FRED_API_KEY="YOUR_KEY"
python scripts/update_data.py
python -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

Do not open `index.html` directly from File Explorer because browsers commonly block local CSV fetches from `file://` pages.

## Scheduling note

The workflow is configured for 6:00 a.m. in the `America/New_York` timezone. GitHub scheduled workflows are not guaranteed to begin at the exact second requested and may occasionally be delayed. The workflow can also be run manually from the Actions tab.

## Data-use note

`yfinance` is an open-source package and is not an official Yahoo product. Review Yahoo's terms before redistributing or using the downloaded data commercially.
