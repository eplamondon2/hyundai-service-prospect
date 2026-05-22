"""
scheduler.py
Lance le scraper vAuto automatiquement selon un horaire.
Tourne en parallèle avec app.py sur Railway.

Démarrage: python scheduler.py
"""

import schedule, time, logging, threading, os
from datetime import datetime
from scraper_vauto import run_scraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SCHEDULER] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('scheduler')

# Heure de scraping (format 24h, heure locale du serveur Railway = UTC)
# 7h00 AM heure de Montréal = 11h00 UTC (heure d'été) ou 12h00 UTC (heure standard)
HEURE_SCRAPING = os.environ.get('SCRAPING_HEURE', '11:00')
HEURE_SCRAPING_2 = os.environ.get('SCRAPING_HEURE_2', '14:00')  # 2e passage optionnel


def job_scraping():
    """Job de scraping lancé par le scheduler."""
    log.info(f"⏰ Démarrage du scraping automatique — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        succes = run_scraper(headless=True, evaluer=True)
        if succes:
            log.info("✅ Scraping terminé avec succès")
        else:
            log.warning("⚠️ Scraping terminé avec des erreurs")
    except Exception as e:
        log.error(f"❌ Erreur dans le job: {e}")


def demarrer_scheduler():
    """Configure et démarre le scheduler."""
    log.info(f"📅 Scheduler démarré")
    log.info(f"   Scraping automatique à {HEURE_SCRAPING} UTC et {HEURE_SCRAPING_2} UTC")

    schedule.every().day.at(HEURE_SCRAPING).do(job_scraping)
    schedule.every().day.at(HEURE_SCRAPING_2).do(job_scraping)

    # Optionnel: scraper au démarrage si variable définie
    if os.environ.get('SCRAPING_AU_DEMARRAGE', '').lower() == 'true':
        log.info("🚀 Scraping au démarrage activé...")
        threading.Thread(target=job_scraping, daemon=True).start()

    while True:
        schedule.run_pending()
        time.sleep(60)  # Vérifier toutes les minutes


if __name__ == '__main__':
    demarrer_scheduler()
