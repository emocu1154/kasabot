"""
🏆 KASANIN KRALI - İddia Analiz Telegram Botu
===============================================
Geçmiş oran verilerini kullanarak futbol maçları için
akıllı bahis analizi yapan Telegram botu.

Veri Kaynakları:
- football-data.co.uk (geçmiş maç sonuçları + oranlar, 20+ yıl)
- The Odds API (güncel oranlar, tüm oran sağlayıcılar)

Kullanım: Kullanıcı maç linkini veya takım isimlerini gönderir,
bot otomatik analiz yapar.
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import re
import io
import csv
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
import urllib.request
import urllib.parse

# --- Telegram Bot ---
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, filters, ContextTypes
    )
except ImportError:
    print("python-telegram-bot yükleniyor...")
    os.system("pip install python-telegram-bot --break-system-packages -q")
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, filters, ContextTypes
    )

# --- Ayarlar ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================
# YAPILANDIRMA - Bu değerleri kendi API anahtarlarınızla doldurun
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "YOUR_ODDS_API_KEY")

# The Odds API endpoint
ODDS_API_BASE = "https://the-odds-api.com/v4"

# football-data.co.uk CSV URL şablonu
FOOTBALL_DATA_BASE = "https://www.football-data.co.uk"

# Database dosyası
DB_PATH = "betting_analysis.db"

# ============================================================
# LİG KODLARI - football-data.co.uk formatı
# ============================================================
LEAGUE_CODES = {
    # İngiltere
    "E0": {"name": "Premier League", "country": "İngiltere", "odds_api": "soccer_epl"},
    "E1": {"name": "Championship", "country": "İngiltere", "odds_api": "soccer_efl_champ"},
    "E2": {"name": "League One", "country": "İngiltere", "odds_api": None},
    "E3": {"name": "League Two", "country": "İngiltere", "odds_api": None},
    # İspanya
    "SP1": {"name": "La Liga", "country": "İspanya", "odds_api": "soccer_spain_la_liga"},
    "SP2": {"name": "La Liga 2", "country": "İspanya", "odds_api": "soccer_spain_segunda_division"},
    # Almanya
    "D1": {"name": "Bundesliga", "country": "Almanya", "odds_api": "soccer_germany_bundesliga"},
    "D2": {"name": "Bundesliga 2", "country": "Almanya", "odds_api": "soccer_germany_bundesliga2"},
    # İtalya
    "I1": {"name": "Serie A", "country": "İtalya", "odds_api": "soccer_italy_serie_a"},
    "I2": {"name": "Serie B", "country": "İtalya", "odds_api": "soccer_italy_serie_b"},
    # Fransa
    "F1": {"name": "Ligue 1", "country": "Fransa", "odds_api": "soccer_france_ligue_one"},
    "F2": {"name": "Ligue 2", "country": "Fransa", "odds_api": "soccer_france_ligue_two"},
    # Hollanda
    "N1": {"name": "Eredivisie", "country": "Hollanda", "odds_api": "soccer_netherlands_eredivisie"},
    # Belçika
    "B1": {"name": "Pro League", "country": "Belçika", "odds_api": "soccer_belgium_first_div"},
    # Portekiz
    "P1": {"name": "Primeira Liga", "country": "Portekiz", "odds_api": "soccer_portugal_primeira_liga"},
    # Türkiye
    "T1": {"name": "Süper Lig", "country": "Türkiye", "odds_api": "soccer_turkey_super_league"},
    # Yunanistan
    "G1": {"name": "Super League", "country": "Yunanistan", "odds_api": "soccer_greece_super_league"},
    # İskoçya
    "SC0": {"name": "Premiership", "country": "İskoçya", "odds_api": "soccer_spl"},
    # Avusturya
    "AUT": {"name": "Bundesliga", "country": "Avusturya", "odds_api": None},
    # İsviçre
    "SWZ": {"name": "Super League", "country": "İsviçre", "odds_api": "soccer_switzerland_superleague"},
    # Danimarka
    "DNK": {"name": "Superligaen", "country": "Danimarka", "odds_api": None},
    # Norveç
    "NOR": {"name": "Eliteserien", "country": "Norveç", "odds_api": "soccer_norway_eliteserien"},
    # İsveç
    "SWE": {"name": "Allsvenskan", "country": "İsveç", "odds_api": "soccer_sweden_allsvenskan"},
    # Polonya
    "POL": {"name": "Ekstraklasa", "country": "Polonya", "odds_api": "soccer_poland_ekstraklasa"},
    # Rusya (tarihsel)
    "RUS": {"name": "Premier Liga", "country": "Rusya", "odds_api": None},
    # Brezilya
    "BRA": {"name": "Serie A", "country": "Brezilya", "odds_api": "soccer_brazil_campeonato"},
    # Arjantin
    "ARG": {"name": "Primera Division", "country": "Arjantin", "odds_api": "soccer_argentina_primera_division"},
    # Japonya
    "JPN": {"name": "J-League", "country": "Japonya", "odds_api": "soccer_japan_j_league"},
    # Çin
    "CHN": {"name": "Super League", "country": "Çin", "odds_api": None},
    # Meksika
    "MEX": {"name": "Liga MX", "country": "Meksika", "odds_api": "soccer_mexico_ligamx"},
    # ABD
    "USA": {"name": "MLS", "country": "ABD", "odds_api": "soccer_usa_mls"},
}

# Sezon listesi (tarihsel veri indirmek için)
SEASONS = [
    "9394", "9495", "9596", "9697", "9798", "9899", "9900",
    "0001", "0102", "0203", "0304", "0405", "0506", "0607",
    "0708", "0809", "0910", "1011", "1112", "1213", "1314",
    "1415", "1516", "1617", "1718", "1819", "1920", "2021",
    "2122", "2223", "2324", "2425", "2526"
]

# ============================================================
# DATABASE
# ============================================================
class Database:
    """SQLite database for storing historical match & odds data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_code TEXT NOT NULL,
                season TEXT NOT NULL,
                match_date TEXT,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                ft_home_goals INTEGER,
                ft_away_goals INTEGER,
                ft_result TEXT,  -- H/D/A
                ht_home_goals INTEGER,
                ht_away_goals INTEGER,
                ht_result TEXT,
                -- Bahisçi oranları (ortalama/max)
                avg_h REAL, avg_d REAL, avg_a REAL,
                max_h REAL, max_d REAL, max_a REAL,
                -- Bet365 oranları
                b365_h REAL, b365_d REAL, b365_a REAL,
                -- Alt/Üst oranları
                avg_over25 REAL, avg_under25 REAL,
                b365_over25 REAL, b365_under25 REAL,
                -- Asian Handicap
                avg_ahh REAL, avg_aha REAL, avg_ah_line REAL,
                -- İstatistikler
                home_shots INTEGER, away_shots INTEGER,
                home_corners INTEGER, away_corners INTEGER,
                home_fouls INTEGER, away_fouls INTEGER,
                home_yellows INTEGER, away_yellows INTEGER,
                home_reds INTEGER, away_reds INTEGER,
                UNIQUE(league_code, season, match_date, home_team, away_team)
            );

            CREATE TABLE IF NOT EXISTS data_updates (
                league_code TEXT NOT NULL,
                season TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                row_count INTEGER DEFAULT 0,
                PRIMARY KEY (league_code, season)
            );

            CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code);
            CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
            CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(ft_result);
            CREATE INDEX IF NOT EXISTS idx_matches_odds ON matches(avg_h, avg_d, avg_a);
        """)
        self.conn.commit()

    def insert_match(self, data: dict):
        """Insert a single match record."""
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT OR IGNORE INTO matches ({cols}) VALUES ({placeholders})"
        self.conn.execute(sql, list(data.values()))

    def bulk_insert(self, records: list):
        """Insert multiple match records."""
        if not records:
            return
        for rec in records:
            self.insert_match(rec)
        self.conn.commit()

    def get_similar_odds_matches(
        self,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
        tolerance: float = 0.15,
        league_code: str = None,
        limit: int = 5000
    ) -> list:
        """
        Verilen oranlarla benzer geçmiş maçları bul.
        Yalnızca iki takım arasındaki maçlara değil,
        tüm ligdeki benzer oranlı maçlara bakar.
        """
        sql = """
            SELECT * FROM matches
            WHERE avg_h IS NOT NULL AND avg_d IS NOT NULL AND avg_a IS NOT NULL
              AND ABS(avg_h - ?) <= ?
              AND ABS(avg_d - ?) <= ?
              AND ABS(avg_a - ?) <= ?
        """
        params = [home_odds, tolerance, draw_odds, tolerance, away_odds, tolerance]

        if league_code:
            sql += " AND league_code = ?"
            params.append(league_code)

        sql += f" ORDER BY match_date DESC LIMIT {limit}"
        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_league_stats(self, league_code: str) -> dict:
        """Lig genelinde istatistikler."""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN ft_result='H' THEN 1 ELSE 0 END) as home_wins,
                SUM(CASE WHEN ft_result='D' THEN 1 ELSE 0 END) as draws,
                SUM(CASE WHEN ft_result='A' THEN 1 ELSE 0 END) as away_wins,
                AVG(ft_home_goals + ft_away_goals) as avg_goals,
                SUM(CASE WHEN ft_home_goals + ft_away_goals > 2.5 THEN 1 ELSE 0 END) as over25,
                SUM(CASE WHEN ft_home_goals > 0 AND ft_away_goals > 0 THEN 1 ELSE 0 END) as btts
            FROM matches
            WHERE league_code = ? AND ft_result IS NOT NULL
        """, [league_code])
        row = cursor.fetchone()
        if row and row["total"] > 0:
            return dict(row)
        return {}

    def get_total_matches(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) as cnt FROM matches")
        return cursor.fetchone()["cnt"]

    def close(self):
        self.conn.close()


# ============================================================
# VERİ İNDİRME - football-data.co.uk
# ============================================================
class DataDownloader:
    """football-data.co.uk'dan geçmiş maç verilerini indirir."""

    # CSV sütun eşlemeleri
    COLUMN_MAP = {
        "Div": "league_code",
        "Date": "match_date",
        "HomeTeam": "home_team", "Home": "home_team",
        "AwayTeam": "away_team", "Away": "away_team",
        "FTHG": "ft_home_goals", "HG": "ft_home_goals",
        "FTAG": "ft_away_goals", "AG": "ft_away_goals",
        "FTR": "ft_result", "Res": "ft_result",
        "HTHG": "ht_home_goals",
        "HTAG": "ht_away_goals",
        "HTR": "ht_result",
        # Oranlar
        "AvgH": "avg_h", "AvgD": "avg_d", "AvgA": "avg_a",
        "MaxH": "max_h", "MaxD": "max_d", "MaxA": "max_a",
        "B365H": "b365_h", "B365D": "b365_d", "B365A": "b365_a",
        "Avg>2.5": "avg_over25", "Avg<2.5": "avg_under25",
        "B365>2.5": "b365_over25", "B365<2.5": "b365_under25",
        "AvgAHH": "avg_ahh", "AvgAHA": "avg_aha", "AvgAH": "avg_ah_line",
        # İstatistikler
        "HS": "home_shots", "AS": "away_shots",
        "HC": "home_corners", "AC": "away_corners",
        "HF": "home_fouls", "AF": "away_fouls",
        "HY": "home_yellows", "AY": "away_yellows",
        "HR": "home_reds", "AR": "away_reds",
    }

    def __init__(self, db: Database):
        self.db = db

    def download_csv(self, url: str) -> str:
        """URL'den CSV indir."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                # Windows-1252 encoding dene, sonra utf-8
                for enc in ["utf-8", "latin-1", "windows-1252"]:
                    try:
                        return data.decode(enc)
                    except:
                        continue
                return data.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"CSV indirilemedi: {url} - {e}")
            return ""

    def parse_csv(self, csv_text: str, season: str, league_code: str) -> list:
        """CSV metnini parse et ve kayıt listesi döndür."""
        records = []
        if not csv_text.strip():
            return records

        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            record = {"season": season, "league_code": league_code}
            for csv_col, db_col in self.COLUMN_MAP.items():
                val = row.get(csv_col, "")
                if val and val.strip():
                    val = val.strip()
                    # Sayısal alanlar
                    if db_col in [
                        "ft_home_goals", "ft_away_goals",
                        "ht_home_goals", "ht_away_goals",
                        "home_shots", "away_shots",
                        "home_corners", "away_corners",
                        "home_fouls", "away_fouls",
                        "home_yellows", "away_yellows",
                        "home_reds", "away_reds"
                    ]:
                        try:
                            record[db_col] = int(val)
                        except:
                            pass
                    elif db_col.startswith("avg_") or db_col.startswith("max_") or db_col.startswith("b365_"):
                        try:
                            record[db_col] = float(val)
                        except:
                            pass
                    else:
                        record[db_col] = val

            # En az takım isimleri olmalı
            if record.get("home_team") and record.get("away_team"):
                records.append(record)

        return records

    def download_league_season(self, league_code: str, season: str) -> int:
        """Tek bir lig + sezon verisini indir."""
        # Ana ligler: mmyy/league.csv
        # Ek ligler: mmyy/league.csv (farklı URL yapısı)
        if len(season) == 4:
            url = f"{FOOTBALL_DATA_BASE}/mmz4281/{season}/{league_code}.csv"
        else:
            url = f"{FOOTBALL_DATA_BASE}/mmz4281/{season}/{league_code}.csv"

        csv_text = self.download_csv(url)
        records = self.parse_csv(csv_text, season, league_code)
        if records:
            self.db.bulk_insert(records)
            self.db.conn.execute(
                "INSERT OR REPLACE INTO data_updates VALUES (?, ?, ?, ?)",
                [league_code, season, datetime.now().isoformat(), len(records)]
            )
            self.db.conn.commit()
        return len(records)

    def download_all(self, progress_callback=None):
        """Tüm liglerin tüm sezon verilerini indir."""
        total = 0
        for league_code in LEAGUE_CODES:
            for season in SEASONS:
                count = self.download_league_season(league_code, season)
                total += count
                if count > 0 and progress_callback:
                    progress_callback(league_code, season, count, total)
        return total

    def download_league(self, league_code: str, progress_callback=None):
        """Tek bir ligin tüm sezon verilerini indir."""
        total = 0
        for season in SEASONS:
            count = self.download_league_season(league_code, season)
            total += count
            if count > 0 and progress_callback:
                progress_callback(league_code, season, count, total)
        return total


# ============================================================
# GÜNCEL ORANLAR - The Odds API
# ============================================================
class OddsAPI:
    """The Odds API ile güncel maç oranlarını çeker."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _request(self, endpoint: str, params: dict = None) -> dict:
        """API isteği gönder."""
        if not params:
            params = {}
        params["apiKey"] = self.api_key
        url = f"{ODDS_API_BASE}{endpoint}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Odds API hatası: {e}")
            return {}

    def get_sports(self) -> list:
        """Mevcut sporları listele."""
        return self._request("/sports") or []

    def get_odds(self, sport_key: str, regions: str = "eu,uk",
                 markets: str = "h2h,totals,spreads") -> list:
        """Bir spor için güncel oranları al."""
        return self._request(f"/sports/{sport_key}/odds", {
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }) or []

    def get_match_odds(self, sport_key: str, event_id: str,
                       regions: str = "eu,uk",
                       markets: str = "h2h,totals") -> dict:
        """Tek bir maçın oranlarını al."""
        result = self._request(f"/sports/{sport_key}/events/{event_id}/odds", {
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        })
        return result or {}

    def find_match(self, sport_key: str, home_team: str = None,
                   away_team: str = None) -> Optional[dict]:
        """Takım isimlerine göre maç bul."""
        events = self.get_odds(sport_key)
        if not events:
            return None

        for event in events:
            h = event.get("home_team", "").lower()
            a = event.get("away_team", "").lower()

            if home_team and away_team:
                ht = home_team.lower()
                at = away_team.lower()
                if (ht in h or h in ht) and (at in a or a in at):
                    return event
            elif home_team:
                ht = home_team.lower()
                if ht in h or h in ht or ht in a or a in ht:
                    return event
            elif away_team:
                at = away_team.lower()
                if at in h or h in at or at in a or a in at:
                    return event
        return None


# ============================================================
# ANALİZ MOTORU
# ============================================================
@dataclass
class AnalysisResult:
    """Analiz sonucu."""
    match_info: str = ""
    league_info: str = ""
    total_compared: int = 0
    # Maç Sonucu
    home_win_pct: float = 0
    draw_pct: float = 0
    away_win_pct: float = 0
    # Çifte Şans
    home_or_draw_pct: float = 0
    home_or_away_pct: float = 0
    draw_or_away_pct: float = 0
    # İlk Yarı / Maç Sonucu (en olası senaryolar)
    iy_ms_stats: Dict[str, float] = field(default_factory=dict)
    # Alt/Üst
    over25_pct: float = 0
    over15_pct: float = 0
    over35_pct: float = 0
    # KG (Karşılıklı Gol)
    btts_yes_pct: float = 0
    # Skor tahminleri
    score_predictions: List[Tuple[str, float]] = field(default_factory=list)
    # En iyi tercih
    best_pick: str = ""
    best_pick_reason: str = ""
    best_pick_odds: float = 0
    best_pick_confidence: float = 0
    # Alternatif tercih
    alt_pick: str = ""
    alt_pick_reason: str = ""
    alt_pick_odds: float = 0
    alt_pick_confidence: float = 0
    # Oranlar
    bookmaker_odds: Dict[str, Dict] = field(default_factory=dict)
    # Ham veri
    confidence_level: str = ""  # Düşük/Orta/Yüksek


class AnalysisEngine:
    """Oran bazlı maç analizi motoru."""

    def __init__(self, db: Database):
        self.db = db

    def analyze(
        self,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
        league_code: str = None,
        home_team: str = "",
        away_team: str = "",
        over25_odds: float = None,
        under25_odds: float = None,
        bookmaker_data: dict = None
    ) -> AnalysisResult:
        """Ana analiz fonksiyonu."""
        result = AnalysisResult()
        result.match_info = f"{home_team} vs {away_team}"
        result.bookmaker_odds = bookmaker_data or {}

        if league_code and league_code in LEAGUE_CODES:
            league = LEAGUE_CODES[league_code]
            result.league_info = f"{league['country']} - {league['name']}"

        # 1) Benzer oranlarla geçmiş maçları bul
        # Önce aynı ligde ara
        similar = self.db.get_similar_odds_matches(
            home_odds, draw_odds, away_odds,
            tolerance=0.15, league_code=league_code
        )

        # Yeterli veri yoksa toleransı artır
        if len(similar) < 50:
            similar = self.db.get_similar_odds_matches(
                home_odds, draw_odds, away_odds,
                tolerance=0.25, league_code=league_code
            )

        # Hala az ise tüm liglerde ara
        if len(similar) < 50:
            similar = self.db.get_similar_odds_matches(
                home_odds, draw_odds, away_odds,
                tolerance=0.20, league_code=None
            )

        if len(similar) < 10:
            similar = self.db.get_similar_odds_matches(
                home_odds, draw_odds, away_odds,
                tolerance=0.35, league_code=None
            )

        result.total_compared = len(similar)

        if not similar:
            result.best_pick = "Yetersiz Veri"
            result.best_pick_reason = "Veritabanında benzer oranlı maç bulunamadı."
            result.confidence_level = "Düşük"
            return result

        # 2) Maç sonucu istatistikleri
        total = len(similar)
        home_wins = sum(1 for m in similar if m.get("ft_result") == "H")
        draws = sum(1 for m in similar if m.get("ft_result") == "D")
        away_wins = sum(1 for m in similar if m.get("ft_result") == "A")

        result.home_win_pct = round(home_wins / total * 100, 1)
        result.draw_pct = round(draws / total * 100, 1)
        result.away_win_pct = round(away_wins / total * 100, 1)

        # 3) Çifte Şans
        result.home_or_draw_pct = round((home_wins + draws) / total * 100, 1)
        result.home_or_away_pct = round((home_wins + away_wins) / total * 100, 1)
        result.draw_or_away_pct = round((draws + away_wins) / total * 100, 1)

        # 4) Alt/Üst
        goals_data = [
            (m.get("ft_home_goals", 0) or 0) + (m.get("ft_away_goals", 0) or 0)
            for m in similar
            if m.get("ft_home_goals") is not None
        ]
        if goals_data:
            result.over15_pct = round(sum(1 for g in goals_data if g > 1.5) / len(goals_data) * 100, 1)
            result.over25_pct = round(sum(1 for g in goals_data if g > 2.5) / len(goals_data) * 100, 1)
            result.over35_pct = round(sum(1 for g in goals_data if g > 3.5) / len(goals_data) * 100, 1)

        # 5) KG (Karşılıklı Gol)
        btts_data = [
            m for m in similar
            if m.get("ft_home_goals") is not None and m.get("ft_away_goals") is not None
        ]
        if btts_data:
            btts_yes = sum(
                1 for m in btts_data
                if m["ft_home_goals"] > 0 and m["ft_away_goals"] > 0
            )
            result.btts_yes_pct = round(btts_yes / len(btts_data) * 100, 1)

        # 6) İY/MS
        iy_ms_counts = {}
        for m in similar:
            ht = m.get("ht_result")
            ft = m.get("ft_result")
            if ht and ft:
                key = f"{ht}/{ft}"
                iy_ms_counts[key] = iy_ms_counts.get(key, 0) + 1

        if iy_ms_counts:
            iy_ms_total = sum(iy_ms_counts.values())
            result.iy_ms_stats = {
                k: round(v / iy_ms_total * 100, 1)
                for k, v in sorted(iy_ms_counts.items(), key=lambda x: -x[1])[:5]
            }

        # 7) Skor tahminleri
        score_counts = {}
        for m in similar:
            hg = m.get("ft_home_goals")
            ag = m.get("ft_away_goals")
            if hg is not None and ag is not None:
                score = f"{hg}-{ag}"
                score_counts[score] = score_counts.get(score, 0) + 1

        if score_counts:
            score_total = sum(score_counts.values())
            result.score_predictions = [
                (score, round(cnt / score_total * 100, 1))
                for score, cnt in sorted(score_counts.items(), key=lambda x: -x[1])[:5]
            ]

        # 8) En iyi ve alternatif tercih belirleme
        self._determine_best_picks(result, home_odds, draw_odds, away_odds)

        # 9) Güven seviyesi
        if total >= 200:
            result.confidence_level = "Yüksek"
        elif total >= 50:
            result.confidence_level = "Orta"
        else:
            result.confidence_level = "Düşük"

        return result

    def _determine_best_picks(
        self, result: AnalysisResult,
        home_odds: float, draw_odds: float, away_odds: float
    ):
        """En iyi ve alternatif tercihi belirle."""
        # Value bet hesapla: gerçek oluşma oranı vs bahis oranı
        options = []

        # MS 1
        implied_home = 100 / home_odds if home_odds else 0
        if result.home_win_pct > implied_home:
            edge = result.home_win_pct - implied_home
            options.append({
                "name": f"MS 1 (Ev Sahibi) @ {home_odds:.2f}",
                "pct": result.home_win_pct,
                "edge": edge,
                "odds": home_odds,
                "type": "ms1"
            })

        # MS X
        implied_draw = 100 / draw_odds if draw_odds else 0
        if result.draw_pct > implied_draw:
            edge = result.draw_pct - implied_draw
            options.append({
                "name": f"MS X (Beraberlik) @ {draw_odds:.2f}",
                "pct": result.draw_pct,
                "edge": edge,
                "odds": draw_odds,
                "type": "msx"
            })

        # MS 2
        implied_away = 100 / away_odds if away_odds else 0
        if result.away_win_pct > implied_away:
            edge = result.away_win_pct - implied_away
            options.append({
                "name": f"MS 2 (Deplasman) @ {away_odds:.2f}",
                "pct": result.away_win_pct,
                "edge": edge,
                "odds": away_odds,
                "type": "ms2"
            })

        # Çifte Şans 1X
        cs1x_odds = 1 / (1/home_odds + 1/draw_odds) if home_odds and draw_odds else 0
        if cs1x_odds > 0:
            implied_1x = 100 / cs1x_odds
            if result.home_or_draw_pct > implied_1x:
                options.append({
                    "name": f"Çifte Şans 1X @ ~{cs1x_odds:.2f}",
                    "pct": result.home_or_draw_pct,
                    "edge": result.home_or_draw_pct - implied_1x,
                    "odds": cs1x_odds,
                    "type": "cs1x"
                })

        # Çifte Şans X2
        csx2_odds = 1 / (1/draw_odds + 1/away_odds) if draw_odds and away_odds else 0
        if csx2_odds > 0:
            implied_x2 = 100 / csx2_odds
            if result.draw_or_away_pct > implied_x2:
                options.append({
                    "name": f"Çifte Şans X2 @ ~{csx2_odds:.2f}",
                    "pct": result.draw_or_away_pct,
                    "edge": result.draw_or_away_pct - implied_x2,
                    "odds": csx2_odds,
                    "type": "csx2"
                })

        # Alt/Üst 2.5
        if result.over25_pct > 55:
            options.append({
                "name": "Üst 2.5 Gol",
                "pct": result.over25_pct,
                "edge": result.over25_pct - 50,
                "odds": 0,
                "type": "over25"
            })
        elif result.over25_pct < 45:
            options.append({
                "name": "Alt 2.5 Gol",
                "pct": 100 - result.over25_pct,
                "edge": (100 - result.over25_pct) - 50,
                "odds": 0,
                "type": "under25"
            })

        # KG Var/Yok
        if result.btts_yes_pct > 55:
            options.append({
                "name": "KG Var",
                "pct": result.btts_yes_pct,
                "edge": result.btts_yes_pct - 50,
                "odds": 0,
                "type": "btts_yes"
            })
        elif result.btts_yes_pct < 40:
            options.append({
                "name": "KG Yok",
                "pct": 100 - result.btts_yes_pct,
                "edge": (100 - result.btts_yes_pct) - 50,
                "odds": 0,
                "type": "btts_no"
            })

        # Edge'e göre sırala
        options.sort(key=lambda x: -x["edge"])

        if options:
            best = options[0]
            result.best_pick = best["name"]
            result.best_pick_confidence = round(best["pct"], 1)
            result.best_pick_odds = best.get("odds", 0)
            result.best_pick_reason = (
                f"Benzer oranlı {result.total_compared} maçta %{best['pct']:.1f} gerçekleşme"
            )

        if len(options) > 1:
            alt = options[1]
            result.alt_pick = alt["name"]
            result.alt_pick_confidence = round(alt["pct"], 1)
            result.alt_pick_odds = alt.get("odds", 0)
            result.alt_pick_reason = (
                f"Benzer oranlı maçlarda %{alt['pct']:.1f} gerçekleşme"
            )

        # Eğer hiç value bet yoksa en yüksek olasılığı seç
        if not result.best_pick:
            if result.home_win_pct >= result.draw_pct and result.home_win_pct >= result.away_win_pct:
                result.best_pick = f"MS 1 (Ev Sahibi) @ {home_odds:.2f}"
                result.best_pick_confidence = result.home_win_pct
            elif result.away_win_pct > result.home_win_pct:
                result.best_pick = f"MS 2 (Deplasman) @ {away_odds:.2f}"
                result.best_pick_confidence = result.away_win_pct
            else:
                result.best_pick = f"Çifte Şans 1X"
                result.best_pick_confidence = result.home_or_draw_pct
            result.best_pick_reason = "En yüksek olasılıklı seçenek"


# ============================================================
# MESAJ FORMATLAMA
# ============================================================
def format_analysis_message(result: AnalysisResult) -> str:
    """Analiz sonucunu Telegram mesajı olarak formatla."""
    # İY/MS label çevirisi
    iy_ms_labels = {
        "H/H": "1/1", "H/D": "1/X", "H/A": "1/2",
        "D/H": "X/1", "D/D": "X/X", "D/A": "X/2",
        "A/H": "2/1", "A/D": "2/X", "A/A": "2/2",
    }

    conf_emoji = {
        "Yüksek": "🟢", "Orta": "🟡", "Düşük": "🔴"
    }
    ce = conf_emoji.get(result.confidence_level, "⚪")

    msg = f"""🏆 <b>ANALİZ SONUCU</b> 🏆

⚽ <b>{result.match_info}</b>
🏟 {result.league_info}
📊 <i>{result.total_compared} benzer oranlı maç analiz edildi</i>

━━━━━━━━━━━━━━━━━━━

✅ <b>EN İYİ TERCİH:</b> {result.best_pick}
{ce} Güven: %{result.best_pick_confidence} ({result.confidence_level})
📝 {result.best_pick_reason}
"""

    if result.alt_pick:
        msg += f"""
🔄 <b>ALTERNATİF:</b> {result.alt_pick}
📝 {result.alt_pick_reason}
"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━

📊 <b>MAÇ SONUCU:</b>
  1: %{result.home_win_pct}  |  X: %{result.draw_pct}  |  2: %{result.away_win_pct}

🎯 <b>ÇİFTE ŞANS:</b>
  1X: %{result.home_or_draw_pct}  |  12: %{result.home_or_away_pct}  |  X2: %{result.draw_or_away_pct}

⚽ <b>ALT/ÜST:</b>
  1.5Ü: %{result.over15_pct}  |  2.5Ü: %{result.over25_pct}  |  3.5Ü: %{result.over35_pct}

🔀 <b>KG:</b> Var %{result.btts_yes_pct}  |  Yok %{round(100 - result.btts_yes_pct, 1)}
"""

    # İY/MS (sadece ilk 3)
    if result.iy_ms_stats:
        msg += "\n📋 <b>İY/MS (En Olası):</b>\n"
        for key, pct in list(result.iy_ms_stats.items())[:3]:
            label = iy_ms_labels.get(key, key)
            msg += f"  {label}: %{pct}\n"

    # Skor tahminleri (ilk 3)
    if result.score_predictions:
        msg += "\n🎲 <b>SKOR (En Olası):</b>\n"
        for score, pct in result.score_predictions[:3]:
            msg += f"  {score}: %{pct}\n"

    # Bookmaker oranları
    if result.bookmaker_odds:
        msg += "\n📈 <b>ORANLAR (Seçili Bahisçiler):</b>\n"
        count = 0
        for bm_name, odds in result.bookmaker_odds.items():
            if count >= 4:
                break
            h = odds.get("h2h", {})
            if h:
                home_o = h.get("home", "-")
                draw_o = h.get("draw", "-")
                away_o = h.get("away", "-")
                msg += f"  {bm_name}: {home_o} / {draw_o} / {away_o}\n"
                count += 1

    msg += f"""
━━━━━━━━━━━━━━━━━━━
⚠️ <i>Bu analiz geçmiş verilere dayalıdır, garanti değildir.</i>"""

    return msg


# ============================================================
# TELEGRAM BOT HANDLERS
# ============================================================
# Global instances
db = Database(DB_PATH)
downloader = DataDownloader(db)
odds_api = OddsAPI(ODDS_API_KEY)
engine = AnalysisEngine(db)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlatma mesajı."""
    total = db.get_total_matches()
    msg = f"""🏆 <b>KASANIN KRALI - İddia Analiz Botu</b> 🏆

Hoş geldin! Bu bot geçmiş yılların oran verilerini kullanarak futbol maçlarını analiz eder.

📊 Veritabanında <b>{total:,}</b> maç kaydı var.

<b>Nasıl Kullanılır:</b>
Maç linkini veya takım isimlerini gönder:

📝 Örnekler:
• <code>Galatasaray Fenerbahçe</code>
• <code>Barcelona Real Madrid</code>
• <code>Liverpool Arsenal</code>

<b>Komutlar:</b>
/ligler - Desteklenen ligler
/veriindir - Geçmiş veri indir
/istatistik - Veritabanı istatistikleri
/yardim - Yardım

⚡ <i>İlk kullanımda /veriindir komutuyla geçmiş verileri indirin.</i>"""

    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım mesajı."""
    msg = """🔍 <b>YARDIM</b>

<b>Maç Analizi:</b>
Takım isimlerini göndermeniz yeterli:
<code>Ev Takımı Deplasman Takımı</code>

Bot otomatik olarak:
1. Güncel oranları çeker
2. Geçmiş benzer oranlı maçları bulur
3. Tüm bahis seçeneklerini analiz eder
4. En iyi tercihi ve alternatifi gösterir

<b>Önemli:</b>
• Bot sadece iki takım arasındaki maçlara değil, tüm ligdeki benzer oranlı TÜM maçlara bakar
• Ne kadar çok geçmiş veri varsa analiz o kadar güvenilir
• İlk kullanımda /veriindir komutunu çalıştırın

<b>Oran Sağlayıcılar:</b>
Bet365, Pinnacle, 1xBet, Betfair ve daha fazlası"""

    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desteklenen ligleri göster."""
    msg = "🌍 <b>DESTEKLENEN LİGLER</b>\n\n"
    current_country = ""
    for code, info in sorted(LEAGUE_CODES.items(), key=lambda x: x[1]["country"]):
        if info["country"] != current_country:
            current_country = info["country"]
            msg += f"\n🏴 <b>{current_country}</b>\n"
        api_status = "✅" if info.get("odds_api") else "📊"
        msg += f"  {api_status} {info['name']} ({code})\n"

    msg += "\n✅ = Güncel oran + geçmiş veri\n📊 = Sadece geçmiş veri"
    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Veritabanı istatistikleri."""
    total = db.get_total_matches()
    cursor = db.conn.execute("""
        SELECT league_code, COUNT(*) as cnt
        FROM matches
        GROUP BY league_code
        ORDER BY cnt DESC
        LIMIT 15
    """)
    rows = cursor.fetchall()

    msg = f"📊 <b>VERİTABANI İSTATİSTİKLERİ</b>\n\n"
    msg += f"Toplam Maç: <b>{total:,}</b>\n\n"

    if rows:
        msg += "<b>En Fazla Veri Olan Ligler:</b>\n"
        for row in rows:
            league = LEAGUE_CODES.get(row["league_code"], {})
            name = league.get("name", row["league_code"])
            country = league.get("country", "?")
            msg += f"  {country} {name}: {row['cnt']:,}\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Geçmiş verileri indir."""
    await update.message.reply_text(
        "⏳ <b>Veri indirme başlıyor...</b>\n"
        "Bu işlem birkaç dakika sürebilir.\n"
        "Tüm liglerin 1993'ten bugüne verisi indirilecek.",
        parse_mode="HTML"
    )

    status_msg = await update.message.reply_text("📥 İndiriliyor...")
    downloaded = 0
    last_update_time = datetime.now()

    def progress(league, season, count, total):
        nonlocal downloaded, last_update_time
        downloaded = total
        # Her 5 saniyede bir güncelle (rate limit'e takılmamak için)
        now = datetime.now()
        if (now - last_update_time).seconds >= 5:
            last_update_time = now
            league_info = LEAGUE_CODES.get(league, {})
            name = league_info.get("name", league)
            asyncio.get_event_loop().create_task(
                status_msg.edit_text(
                    f"📥 İndiriliyor...\n"
                    f"Lig: {name} | Sezon: {season}\n"
                    f"Toplam: {total:,} maç"
                )
            )

    # Senkron indirme (async wrapper ile)
    loop = asyncio.get_event_loop()
    total = await loop.run_in_executor(None, downloader.download_all, progress)

    await status_msg.edit_text(
        f"✅ <b>İndirme tamamlandı!</b>\n"
        f"Toplam <b>{total:,}</b> yeni maç kaydı eklendi.\n"
        f"Veritabanında toplam <b>{db.get_total_matches():,}</b> maç var.",
        parse_mode="HTML"
    )


async def cmd_download_league(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tek lig verisi indir."""
    if not context.args:
        await update.message.reply_text(
            "Kullanım: /ligindir <lig_kodu>\n"
            "Örnek: /ligindir T1 (Süper Lig)\n"
            "Lig kodları için: /ligler"
        )
        return

    code = context.args[0].upper()
    if code not in LEAGUE_CODES:
        await update.message.reply_text(f"❌ Bilinmeyen lig kodu: {code}\nLig kodları için: /ligler")
        return

    league = LEAGUE_CODES[code]
    await update.message.reply_text(
        f"📥 {league['country']} {league['name']} verisi indiriliyor..."
    )

    loop = asyncio.get_event_loop()
    total = await loop.run_in_executor(None, downloader.download_league, code, None)

    await update.message.reply_text(
        f"✅ {league['name']}: <b>{total:,}</b> maç indirildi.",
        parse_mode="HTML"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı mesajını işle - maç analizi yap."""
    text = update.message.text.strip()
    if not text or text.startswith("/"):
        return

    # Bekleme mesajı
    wait_msg = await update.message.reply_text(
        "🔍 <b>Analiz yapılıyor...</b>\n⏳ Lütfen bekleyin (10-15 saniye)",
        parse_mode="HTML"
    )

    try:
        # Takım isimlerini ayır
        # Kullanıcı "Galatasaray Fenerbahce" veya "Galatasaray - Fenerbahce" yazabilir
        teams = re.split(r'\s*[-–—vs\.]+\s*|\s{2,}', text, maxsplit=1)
        if len(teams) < 2:
            # Tek kelime ise ortadan böl
            words = text.split()
            if len(words) >= 2:
                mid = len(words) // 2
                teams = [" ".join(words[:mid]), " ".join(words[mid:])]
            else:
                await wait_msg.edit_text("❌ Lütfen iki takım ismi girin.\nÖrnek: Galatasaray Fenerbahce")
                return

        home_team = teams[0].strip()
        away_team = teams[1].strip()

        # Güncel oranları çekmeye çalış
        home_odds, draw_odds, away_odds = 0, 0, 0
        bookmaker_data = {}
        league_code = None
        match_found = False

        # Tüm futbol sporlarını dene
        soccer_sports = [v["odds_api"] for v in LEAGUE_CODES.values() if v.get("odds_api")]
        soccer_sports = list(set(soccer_sports))  # unique

        for sport_key in soccer_sports:
            try:
                match = odds_api.find_match(sport_key, home_team, away_team)
                if match:
                    match_found = True
                    home_team = match.get("home_team", home_team)
                    away_team = match.get("away_team", away_team)

                    # Lig kodunu bul
                    for code, info in LEAGUE_CODES.items():
                        if info.get("odds_api") == sport_key:
                            league_code = code
                            break

                    # Oranları çıkar
                    for bm in match.get("bookmakers", []):
                        bm_name = bm.get("title", "Unknown")
                        bm_odds = {}
                        for market in bm.get("markets", []):
                            if market["key"] == "h2h":
                                outcomes = market.get("outcomes", [])
                                h2h = {}
                                for o in outcomes:
                                    if o["name"] == match["home_team"]:
                                        h2h["home"] = o["price"]
                                    elif o["name"] == match["away_team"]:
                                        h2h["away"] = o["price"]
                                    else:
                                        h2h["draw"] = o["price"]
                                bm_odds["h2h"] = h2h
                            elif market["key"] == "totals":
                                totals = {}
                                for o in market.get("outcomes", []):
                                    totals[o["name"].lower()] = o["price"]
                                    totals["point"] = o.get("point", 2.5)
                                bm_odds["totals"] = totals
                        bookmaker_data[bm_name] = bm_odds

                    # Ortalama oranları hesapla
                    home_list, draw_list, away_list = [], [], []
                    for bm_odds in bookmaker_data.values():
                        h2h = bm_odds.get("h2h", {})
                        if h2h.get("home"):
                            home_list.append(h2h["home"])
                        if h2h.get("draw"):
                            draw_list.append(h2h["draw"])
                        if h2h.get("away"):
                            away_list.append(h2h["away"])

                    if home_list:
                        home_odds = sum(home_list) / len(home_list)
                    if draw_list:
                        draw_odds = sum(draw_list) / len(draw_list)
                    if away_list:
                        away_odds = sum(away_list) / len(away_list)

                    break
            except Exception as e:
                logger.warning(f"Sport {sport_key} hatası: {e}")
                continue

        # Eğer güncel oran bulunamadıysa
        if not home_odds:
            # Lig istatistiklerinden yaklaşık oran tahmin et
            await wait_msg.edit_text(
                f"⚠️ <b>{home_team} vs {away_team}</b> için güncel oran bulunamadı.\n\n"
                f"Bu durum şu nedenlerle olabilir:\n"
                f"• Maç henüz programda değil\n"
                f"• Odds API key eksik veya geçersiz\n"
                f"• Takım isimleri farklı yazılmış olabilir\n\n"
                f"💡 Lütfen takım isimlerini İngilizce tam adlarıyla yazın.\n"
                f"Örnek: <code>Galatasaray Fenerbahce</code>",
                parse_mode="HTML"
            )
            return

        # Analiz yap
        result = engine.analyze(
            home_odds=home_odds,
            draw_odds=draw_odds,
            away_odds=away_odds,
            league_code=league_code,
            home_team=home_team,
            away_team=away_team,
            bookmaker_data=bookmaker_data
        )

        # Sonucu gönder
        msg = format_analysis_message(result)
        await wait_msg.edit_text(msg, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Analiz hatası: {e}", exc_info=True)
        await wait_msg.edit_text(
            f"❌ Bir hata oluştu: {str(e)[:200]}\n"
            f"Lütfen tekrar deneyin."
        )


# ============================================================
# ANA FONKSİYON
# ============================================================
def main():
    """Botu başlat."""
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("=" * 60)
        print("HATA: Telegram Bot Token'ı ayarlanmamış!")
        print()
        print("1. @BotFather'dan yeni bot oluşturun")
        print("2. Token'ı BOT_TOKEN olarak ayarlayın:")
        print("   export BOT_TOKEN='your_token_here'")
        print()
        print("Odds API Key için:")
        print("   https://the-odds-api.com adresinden ücretsiz key alın")
        print("   export ODDS_API_KEY='your_key_here'")
        print("=" * 60)
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Komut handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("baslat", cmd_start))
    app.add_handler(CommandHandler("yardim", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ligler", cmd_leagues))
    app.add_handler(CommandHandler("veriindir", cmd_download))
    app.add_handler(CommandHandler("ligindir", cmd_download_league))
    app.add_handler(CommandHandler("istatistik", cmd_stats))

    # Mesaj handler (maç analizi)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🏆 KASANIN KRALI Bot başlatıldı!")
    print(f"Veritabanı: {db.get_total_matches():,} maç")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
