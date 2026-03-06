"""
AdRipper - Google Ads Data Extraction Tool
------------------------------------------
Entwickelt für den headless Einsatz auf macOS (M4) via Cron.
Extrahiert Kampagnendaten, Keywords und Anzeigenperformance.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import yaml
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# --- KONSTANTEN & ENUMS ---
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"


class ReportType:
    """Konstanten für die verschiedenen Report-Typen."""

    CAMPAIGNS = "campaigns"
    KEYWORDS = "keywords"
    ADS = "ads"
    SUMMARY = "summary"


# Globaler Logger (wird in setup_logging konfiguriert)
logger = logging.getLogger("AdRipper")


def setup_logging() -> None:
    """Initialisiert das Logging, ohne Side-Effects beim Import."""
    if logger.hasHandlers():
        return

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(LOG_DIR / "adripper.log")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


class AdRipperEngine:
    """Core Engine für die Google Ads Datenextraktion."""

    def __init__(
        self, google_ads_path: Path, customers_path: Path, base_config_path: Path
    ):
        self.customers_config: Dict[str, Any] = {}
        self.base_config: Dict[str, Any] = {}
        self.output_base = Path(".")
        self.default_date_range = "LAST_30_DAYS"
        self.csv_sep = ";"

        self._load_configs(customers_path, base_config_path)

        try:
            self.client = GoogleAdsClient.load_from_storage(str(google_ads_path))
            self.service = self.client.get_service("GoogleAdsService")
            with open(google_ads_path, "r", encoding="utf-8") as f:
                ga_config = yaml.safe_load(f)
                self.login_customer_id = str(
                    ga_config.get("login_customer_id", "")
                ).replace("-", "")
        except Exception as e:
            raise ValueError(f"Fehler beim Laden der Google Ads Config: {e}") from e

    def _load_configs(self, customers_path: Path, base_config_path: Path) -> None:
        try:
            with open(customers_path, "r", encoding="utf-8") as f:
                self.customers_config = yaml.safe_load(f) or {}

            with open(base_config_path, "r", encoding="utf-8") as f:
                self.base_config = json.load(f)

            out_path_str = self.base_config.get("base_output_path", "~/Analysen")
            self.output_base = Path(out_path_str).expanduser()
            self.default_date_range = self.base_config.get(
                "default_date_range", "LAST_30_DAYS"
            )
            self.csv_sep = self.base_config.get("csv_separator", ";")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Konfigurationsdatei fehlt: {e}") from e

    def _calc_ctr(self, clicks: float, impressions: float) -> float:
        if impressions == 0:
            return 0.0
        return round((clicks / impressions) * 100, 2)

    def get_query(self, report_type: str) -> str:
        """Erzeugt die GAQL Query je nach Report-Typ."""
        base_metrics = """
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        """

        if report_type == ReportType.CAMPAIGNS:
            return f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    {base_metrics}
                FROM campaign
                WHERE segments.date DURING {self.default_date_range}
            """
        if report_type == ReportType.KEYWORDS:
            return f"""
                SELECT
                    campaign.name,
                    ad_group.name,
                    ad_group_criterion.criterion_id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    {base_metrics}
                FROM keyword_view
                WHERE segments.date DURING {self.default_date_range}
            """
        if report_type == ReportType.ADS:
            return f"""
                SELECT
                    campaign.name,
                    ad_group.name,
                    ad_group_ad.ad.id,
                    ad_group_ad.status,
                    ad_group_ad.ad.type,
                    {base_metrics}
                FROM ad_group_ad
                WHERE segments.date DURING {self.default_date_range}
            """

        raise ValueError(f"Unbekannter ReportType: {report_type}")

    def run_report(
        self, customer_id: str, report_type: str, max_retries: int = 3
    ) -> pd.DataFrame:
        """Führt einen API-Call aus inkl. Retry-Logik."""
        query = self.get_query(report_type)
        retries = 0

        while retries < max_retries:
            try:
                request = self.client.get_type("SearchGoogleAdsRequest")
                request.customer_id = customer_id
                request.query = query

                rows = []
                response = self.service.search(request=request)

                for row in response:
                    data: Dict[str, Any] = {
                        "CampaignName": (
                            row.campaign.name if hasattr(row.campaign, "name") else ""
                        ),
                        "Impressions": row.metrics.impressions,
                        "Clicks": row.metrics.clicks,
                        "Cost": row.metrics.cost_micros / 1000000.0,
                        "Conversions": row.metrics.conversions,
                        "ConversionValue": row.metrics.conversions_value,
                    }

                    data["CTR"] = self._calc_ctr(data["Clicks"], data["Impressions"])
                    data["ConversionRate"] = (
                        round((data["Conversions"] / data["Clicks"]) * 100, 2)
                        if data["Clicks"] > 0
                        else 0.0
                    )

                    if report_type == ReportType.CAMPAIGNS:
                        data["Campaign ID"] = row.campaign.id
                        data["Campaign Status"] = row.campaign.status.name
                    elif report_type == ReportType.KEYWORDS:
                        data["AdGroup"] = row.ad_group.name
                        data["Keyword ID"] = row.ad_group_criterion.criterion_id
                        data["Keyword Text"] = row.ad_group_criterion.keyword.text
                        data["Match Type"] = (
                            row.ad_group_criterion.keyword.match_type.name
                        )
                    elif report_type == ReportType.ADS:
                        data["AdGroup"] = row.ad_group.name
                        data["Ad ID"] = row.ad_group_ad.ad.id
                        data["Ad Status"] = row.ad_group_ad.status.name
                        data["Ad Type"] = row.ad_group_ad.ad.type_.name

                    rows.append(data)

                return pd.DataFrame(rows)

            except GoogleAdsException as ex:
                logger.error(
                    "API Fehler (Attempt %s/%s): %s",
                    retries + 1,
                    max_retries,
                    ex.error.code().name,
                )
                retries += 1
                time.sleep(2**retries)

        logger.error(
            "Fehler bei %s für %s nach %s versuchen.",
            report_type,
            customer_id,
            max_retries,
        )
        return pd.DataFrame()

    def create_summary_report(self, df_campaigns: pd.DataFrame) -> pd.DataFrame:
        """Erzeugt basierend auf Kampagnen-Dataframe die Gesamtmetriken."""
        if df_campaigns.empty:
            return df_campaigns

        summary = {
            "Impressions": df_campaigns["Impressions"].sum(),
            "Clicks": df_campaigns["Clicks"].sum(),
            "Cost": df_campaigns["Cost"].sum(),
            "Conversions": df_campaigns["Conversions"].sum(),
            "ConversionValue": df_campaigns["ConversionValue"].sum(),
        }
        summary["CTR"] = self._calc_ctr(summary["Clicks"], summary["Impressions"])
        summary["ConversionRate"] = (
            round((summary["Conversions"] / summary["Clicks"]) * 100, 2)
            if summary["Clicks"] > 0
            else 0.0
        )

        return pd.DataFrame([summary])

    def execute(self, specific_customer: Optional[str] = None) -> None:
        """Schleife über definierte Targets in customers.yaml"""
        targets = self.customers_config

        if specific_customer:
            if specific_customer not in targets:
                logger.error("Kunde '%s' unbekannt.", specific_customer)
                return
            targets = {specific_customer: targets[specific_customer]}

        for name, conf in targets.items():
            if not conf.get("enabled", True):
                continue

            cust_id = str(conf["customer_id"]).replace("-", "")
            folder = conf["folder"]
            logger.info("=== Report Start: %s (CID: %s) ===", name, cust_id)

            campaign_df = pd.DataFrame()
            reports = conf.get("reports", [])

            for r_type in reports:
                if r_type == ReportType.SUMMARY:
                    continue

                logger.info("Führe %s Extrahierung aus...", r_type)
                df = self.run_report(cust_id, r_type)
                if df.empty:
                    continue

                if r_type == ReportType.CAMPAIGNS:
                    campaign_df = df

                out_path = self.output_base / folder / "01_Daten"
                out_path.mkdir(parents=True, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d")
                file_path = out_path / f"{timestamp}_{r_type}.csv"
                df.to_csv(file_path, sep=self.csv_sep, index=False)
                logger.info("Gespeichert: %s", file_path)

            if ReportType.SUMMARY in reports and not campaign_df.empty:
                logger.info("Erstelle Summary Report...")
                summary_df = self.create_summary_report(campaign_df)
                timestamp = datetime.now().strftime("%Y%m%d")
                file_path = (
                    self.output_base / folder / "01_Daten" / f"{timestamp}_summary.csv"
                )
                summary_df.to_csv(file_path, sep=self.csv_sep, index=False)
                logger.info("Gespeichert: %s", file_path)


def main() -> None:
    """Einstiegspunkt für CLI-Aufruf."""
    setup_logging()

    parser = argparse.ArgumentParser(description="AdRipper")
    parser.add_argument("--customer", type=str, help="Spezifischer Kunde zum Ausführen")
    args = parser.parse_args()

    try:
        engine = AdRipperEngine(
            google_ads_path=CONFIG_DIR / "google_ads.yaml",
            customers_path=CONFIG_DIR / "customers.yaml",
            base_config_path=CONFIG_DIR / "base_config.json",
        )
        engine.execute(args.customer)
        logger.info("Erfolgreich beendet.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.critical("FATAL ERROR: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
