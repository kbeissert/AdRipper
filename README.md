# AdRipper 🚀

**AdRipper** ist ein headless ETL-Tool, das wöchentlich oder monatlich Performance-Daten von der Google Ads API zieht, aggregiert und als CSV speichert. Entwickelt für den lokalen Einsatz auf macOS (M4) via Cron.

## 📁 Struktur

```text
~/Projekte/AdRipper/
├── src/
│   └── adripper.py      # Core Logic (Python 3.12+)
├── config/
│   ├── base_config.json # Pfade, Datumsbereiche
│   ├── customers.yaml   # Kunden-Liste & Report-Definitionen
│   └── google_ads.yaml  # API Credentials (NICHT im Repo!)
├── logs/                # Logs (Datei + Konsole)
├── run.sh               # Bash Wrapper für Cron
└── requirements.txt     # Dependencies
```

## 🛠️ Setup

### 1. Umgebung
Python 3.12+ empfohlen.

```bash
cd ~/Projekte/AdRipper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run.sh
```

### 2. Konfiguration

1.  **Credentials**: Lege deine `google_ads.yaml` (mit developer_token, client_id, etc.) in den Ordner `config/`.
2.  **Kunden**: Bearbeite `config/customers.yaml`:
    ```yaml
    mein-kunde:
      customer_id: "123-456-7890"
      folder: "MeinKunde/01_Daten"
      enabled: true
      reports:
        - campaigns
        - keywords
        - ads
        - summary
    ```

## 🏃‍♂️ Ausführung

### Manuell (Test)
```bash
# Einzelner Kunde
python src/adripper.py --customer cerdo-fachwerkhaus

# Alle aktiven Kunden ausführen
python src/adripper.py --all
```

### Cron (Automatisch)
Um den Job z.B. jeden Montag um 06:00 Uhr laufen zu lassen:

1.  `crontab -e` öffnen.
2.  Zeile hinzufügen:
    ```bash
    0 6 * * 1 /Users/kbeissert/_PROJEKTE/Entwicklung/AdRipper/run.sh --all
    ```

## 📊 Outputs
Die Dateien landen standardmäßig in `/Data/Analysen/{kunde}/{pfad}`.
Format: `YYYY-MM-DD_{report_type}.csv`

**Beispiel:**
- `2026-02-20_campaigns.csv`: Rohe Kampagnen-Performance.
- `2026-02-20_summary.csv`: Aggregation pro Kampagne + Total (KPIs wie CTR/CPC berechnet).

## 💡 Erweiterung
Neue Reports in `src/adripper.py` -> `get_query()` hinzufügen.
