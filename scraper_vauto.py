"""
scraper_vauto.py
Scrape vAuto Service Appointments et les valeurs d'évaluation.
Tourne sur Railway via scheduler.py

Variables d'environnement requises:
  VAUTO_USER  = votre username vAuto
  VAUTO_PASS  = votre mot de passe vAuto
  DATABASE_URL = (optionnel, défaut: hyundai_prospect.db)
"""

import os, re, time, sqlite3, logging, json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── Config ──────────────────────────────────────────────────────────────────
VAUTO_USER = os.environ.get('VAUTO_USER', '')
VAUTO_PASS = os.environ.get('VAUTO_PASS', '')
VAUTO_COOKIES_JSON = os.environ.get('VAUTO_COOKIES', '')  # Cookies exportés de Chrome
DB_PATH    = os.environ.get('DB_PATH', 'hyundai_prospect.db')

VAUTO_URL  = 'https://provision.vauto.app.coxautoinc.com'
SA_URL     = 'https://provision.vauto.app.coxautoinc.com/Va/Inventory/Stocking/ServiceAppointments/ServiceAppointmentsGrid.aspx'

# Filtre: exclure les véhicules trop récents (≤ N ans)
ANNEE_MIN_OPPORTUNITE = datetime.now().year - 2  # ex: 2024 → exclure 2025+

# Cookies d'authentification (convertis au format Playwright)
def charger_cookies_depuis_env() -> list:
    """
    Charge les cookies depuis la variable d'env VAUTO_COOKIES.
    Format: JSON exporté par Cookie-Editor Chrome.
    """
    if not VAUTO_COOKIES_JSON:
        return []
    try:
        raw = json.loads(VAUTO_COOKIES_JSON)
        cookies_playwright = []
        for c in raw:
            # Playwright utilise 'sameSite' avec majuscules spécifiques
            same_site = c.get('sameSite', 'None')
            if same_site in ['no_restriction', 'unspecified', None, '']:
                same_site = 'None'
            elif same_site == 'lax':
                same_site = 'Lax'
            elif same_site == 'strict':
                same_site = 'Strict'

            cookie = {
                'name': c['name'],
                'value': c['value'],
                'domain': c['domain'],
                'path': c.get('path', '/'),
                'secure': c.get('secure', False),
                'httpOnly': c.get('httpOnly', False),
                'sameSite': same_site,
            }
            # Ajouter expiration si présente (pas pour les cookies session)
            if 'expirationDate' in c:
                cookie['expires'] = int(c['expirationDate'])
            cookies_playwright.append(cookie)
        log.info(f"🍪 {len(cookies_playwright)} cookies chargés depuis VAUTO_COOKIES")
        return cookies_playwright
    except Exception as e:
        log.error(f"❌ Erreur chargement cookies: {e}")
        return []

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('scraper_vauto')


# ─── Helpers DB ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS clients_service (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_rdv TEXT, heure_rdv TEXT,
        nom TEXT, telephone TEXT, email TEXT, adresse TEXT,
        annee_veh INTEGER, marque TEXT, modele TEXT, version TEXT,
        vin TEXT UNIQUE, km INTEGER,
        valeur_vauto REAL DEFAULT 0,
        solde_financement REAL DEFAULT 0,
        type_contrat TEXT DEFAULT 'financement',
        fin_contrat TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        statut TEXT DEFAULT 'nouveau',
        modele_propose TEXT DEFAULT '',
        version_proposee TEXT DEFAULT '',
        date_import TEXT,
        source TEXT DEFAULT 'vauto',
        lien_evaluation TEXT DEFAULT '',
        date_evaluation TEXT DEFAULT ''
    )''')
    # Ajouter colonnes si elles n'existent pas (migration)
    for col, definition in [
        ('lien_evaluation', 'TEXT DEFAULT ""'),
        ('date_evaluation', 'TEXT DEFAULT ""'),
    ]:
        try:
            conn.execute(f'ALTER TABLE clients_service ADD COLUMN {col} {definition}')
        except:
            pass
    conn.commit()
    conn.close()

def upsert_client(data: dict):
    """Insère ou met à jour un client par VIN."""
    conn = get_db()
    existing = conn.execute(
        'SELECT id, valeur_vauto, statut FROM clients_service WHERE vin=?',
        (data.get('vin',''),)
    ).fetchone()

    if existing:
        # Mettre à jour seulement les champs de base (pas écraser statut/notes)
        conn.execute('''UPDATE clients_service SET
            date_rdv=?, heure_rdv=?, nom=?, telephone=?, email=?,
            annee_veh=?, marque=?, modele=?, version=?, km=?,
            date_import=?, source=?
            WHERE vin=?''', (
            data['date_rdv'], data['heure_rdv'], data['nom'],
            data['telephone'], data['email'],
            data['annee_veh'], data['marque'], data['modele'],
            data['version'], data['km'],
            datetime.now().strftime('%Y-%m-%d'), 'vauto',
            data['vin']
        ))
        log.info(f"  ↻ Mis à jour: {data['nom']} — {data['annee_veh']} {data['modele']}")
        result = 'updated'
    else:
        conn.execute('''INSERT INTO clients_service
            (date_rdv, heure_rdv, nom, telephone, email,
             annee_veh, marque, modele, version, vin, km,
             date_import, source, statut)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            data['date_rdv'], data['heure_rdv'], data['nom'],
            data['telephone'], data['email'],
            data['annee_veh'], data['marque'], data['modele'],
            data['version'], data['vin'], data['km'],
            datetime.now().strftime('%Y-%m-%d'), 'vauto', 'nouveau'
        ))
        log.info(f"  ✚ Nouveau: {data['nom']} — {data['annee_veh']} {data['modele']}")
        result = 'inserted'

    conn.commit()
    conn.close()
    return result

def sauvegarder_evaluation(vin: str, valeur: float, lien: str = ''):
    conn = get_db()
    conn.execute('''UPDATE clients_service SET
        valeur_vauto=?, lien_evaluation=?, date_evaluation=?
        WHERE vin=?''', (
        valeur, lien, datetime.now().strftime('%Y-%m-%d %H:%M'), vin
    ))
    conn.commit()
    conn.close()


# ─── Parser des données brutes ───────────────────────────────────────────────
def parser_vehicule(texte: str):
    """
    Parse '2021 Hyundai Palisade' ou '2021 Hyundai Palisade Luxury' 
    → (2021, 'Hyundai', 'Palisade', 'Luxury')
    """
    texte = texte.strip()
    m = re.match(r'(\d{4})\s+(\w+)\s+(.+)', texte)
    if not m:
        return None, 'Hyundai', texte, ''
    annee = int(m.group(1))
    marque = m.group(2)
    reste = m.group(3).strip()
    # Modèles multi-mots connus
    for modele_long in ['Santa Fe', 'Kona Electric', 'Elantra HEV', 'Tucson PHEV',
                         'Palisade HEV', 'Ioniq 5', 'Ioniq 6', 'Ioniq 9']:
        if reste.startswith(modele_long):
            version = reste[len(modele_long):].strip()
            return annee, marque, modele_long, version
    # Modèle = premier mot, version = reste
    parts = reste.split(' ', 1)
    modele = parts[0]
    version = parts[1] if len(parts) > 1 else ''
    return annee, marque, modele, version

def parser_km(texte: str) -> int:
    """'123,152' → 123152"""
    try:
        return int(str(texte).replace(',', '').replace(' ', '').strip())
    except:
        return 0

def parser_date(texte: str):
    """'05/22/2026' → ('2026-05-22', '')  ou  '05/22/2026 7:30 AM' → ('2026-05-22', '07:30')"""
    texte = texte.strip()
    # Format MM/DD/YYYY HH:MM AM/PM
    m = re.match(r'(\d{2}/\d{2}/\d{4})\s+(\d+:\d+\s*[AP]M)', texte)
    if m:
        try:
            d = datetime.strptime(m.group(1), '%m/%d/%Y')
            t = datetime.strptime(m.group(2).strip(), '%I:%M %p')
            return d.strftime('%Y-%m-%d'), t.strftime('%H:%M')
        except:
            pass
    # Format MM/DD/YYYY seulement
    m2 = re.match(r'(\d{2}/\d{2}/\d{4})', texte)
    if m2:
        try:
            d = datetime.strptime(m2.group(1), '%m/%d/%Y')
            return d.strftime('%Y-%m-%d'), ''
        except:
            pass
    return texte, ''


# ─── Scraper principal ────────────────────────────────────────────────────────
class ScraperVAuto:

    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None

    def demarrer(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled']
        )
        context = self.browser.new_context(
            viewport={'width': 1400, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        # Injecter les cookies de session si disponibles
        cookies = charger_cookies_depuis_env()
        if cookies:
            try:
                context.add_cookies(cookies)
                log.info(f"🍪 {len(cookies)} cookies injectés dans le navigateur")
            except Exception as e:
                log.warning(f"⚠️ Erreur injection cookies: {e}")

        self.page = context.new_page()
        log.info("🌐 Navigateur démarré")

    def arreter(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        log.info("🔒 Navigateur fermé")

    def login(self) -> bool:
        """Se connecte à vAuto via Cox Automotive SSO."""
        if not VAUTO_USER or not VAUTO_PASS:
            log.error("❌ VAUTO_USER et VAUTO_PASS non définis dans les variables d'environnement")
            return False

        log.info(f"🔑 Connexion à vAuto ({VAUTO_USER})...")
        try:
            # 1. Aller sur la page Service Appointments directement
            # Cox redirige automatiquement vers le SSO si non connecté
            log.info(f"   → Chargement: {SA_URL[:60]}")
            self.page.goto(SA_URL, wait_until='domcontentloaded', timeout=60000)
            time.sleep(3)
            log.info(f"   → Redirigé vers: {self.page.url[:80]}")
            log.info(f"   → Titre: {self.page.title()}")

            # 2. Gérer la page de login Cox Automotive SSO
            # L'URL contiendra 'login', 'sso', 'idp', 'signin' ou 'coxautoinc'
            url_actuelle = self.page.url.lower()
            tentatives = 0

            while any(mot in url_actuelle for mot in ['login', 'sso', 'signin', 'idp', 'auth']) and tentatives < 3:
                tentatives += 1
                log.info(f"   → Page login détectée (tentative {tentatives})")

                # Chercher champ username/email
                champ_user = None
                for sel in ['input[name="username"]', 'input[name="email"]',
                            'input[type="email"]', '#username', '#email',
                            'input[placeholder*="user" i]', 'input[placeholder*="email" i]',
                            'input[id*="user" i]', 'input[id*="email" i]']:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        champ_user = sel
                        break

                if champ_user:
                    log.info(f"   → Champ username trouvé: {champ_user}")
                    self.page.fill(champ_user, VAUTO_USER)
                    time.sleep(0.5)

                    # Parfois Cox sépare username et password en 2 étapes
                    # Chercher bouton 'Next' ou 'Continue' d'abord
                    for sel_next in ['button:has-text("Next")', 'button:has-text("Continue")',
                                     'button:has-text("Suivant")', 'input[type="submit"]']:
                        el = self.page.query_selector(sel_next)
                        if el and el.is_visible():
                            # Vérifier si le champ password est déjà visible
                            pass_visible = self.page.query_selector('input[type="password"]')
                            if not pass_visible:
                                log.info(f"   → Clic Next pour accéder au mot de passe")
                                el.click()
                                self.page.wait_for_load_state('domcontentloaded', timeout=15000)
                                time.sleep(2)
                                break

                # Chercher champ password
                champ_pass = None
                for sel in ['input[name="password"]', 'input[type="password"]',
                            '#password', 'input[id*="pass" i]',
                            'input[placeholder*="pass" i]', 'input[placeholder*="mot" i]']:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        champ_pass = sel
                        break

                if champ_pass:
                    log.info(f"   → Champ password trouvé: {champ_pass}")
                    self.page.fill(champ_pass, VAUTO_PASS)
                    time.sleep(0.5)

                    # Cliquer le bouton de soumission
                    for sel_btn in ['button[type="submit"]', 'input[type="submit"]',
                                    'button:has-text("Sign in")', 'button:has-text("Login")',
                                    'button:has-text("Se connecter")', 'button:has-text("Submit")',
                                    'button[id*="login" i]', 'button[id*="submit" i]']:
                        el = self.page.query_selector(sel_btn)
                        if el and el.is_visible():
                            log.info(f"   → Clic submit: {sel_btn}")
                            el.click()
                            break
                else:
                    log.warning("   → Champ password non trouvé")
                    # Prendre screenshot pour debug
                    self.page.screenshot(path='/tmp/login_debug.png')
                    log.info("   → Screenshot sauvegardé: /tmp/login_debug.png")

                # Attendre la navigation
                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=30000)
                except:
                    pass
                time.sleep(3)
                url_actuelle = self.page.url.lower()
                log.info(f"   → URL après soumission: {self.page.url[:80]}")

            # 3. Vérifier qu'on est sur vAuto
            url_finale = self.page.url.lower()
            if 'vauto' in url_finale or 'coxautoinc' in url_finale:
                if not any(mot in url_finale for mot in ['login', 'signin', 'sso', 'auth']):
                    log.info(f"✅ Connecté — {self.page.url[:80]}")
                    return True

            # 4. Pas encore connecté — afficher ce qu'on voit
            log.error(f"❌ Login échoué — URL finale: {self.page.url}")
            log.error(f"   Titre: {self.page.title()}")
            return False

        except PWTimeout:
            log.error(f"❌ Timeout — URL: {self.page.url}")
            return False
        except Exception as e:
            log.error(f"❌ Erreur login: {e}")
            import traceback
            traceback.print_exc()
            return False

    def naviguer_service_appointments(self) -> bool:
        """Navigue vers la page Service Appointments."""
        log.info("📋 Navigation vers Service Appointments...")
        try:
            # Après login, on est déjà sur SA — vérifier d'abord
            url = self.page.url.lower()
            if 'serviceappointments' in url:
                log.info(f"✅ Déjà sur SA: {self.page.url[:80]}")
                return True

            # Sinon naviguer explicitement vers l'URL exacte
            log.info(f"   → Goto SA URL...")
            self.page.goto(SA_URL, wait_until='domcontentloaded', timeout=60000)
            time.sleep(3)
            log.info(f"   → URL: {self.page.url[:80]}")
            log.info(f"   → Titre: {self.page.title()}")

            if 'login' in self.page.url.lower() or 'signin' in self.page.url.lower():
                log.warning("Session expirée")
                return False

            return True

        except Exception as e:
            log.error(f"❌ Navigation échouée: {e}")
            return False

    def extraire_rdv_page(self) -> list[dict]:
        """Extrait tous les RDV de la page courante."""
        rdvs = []
        time.sleep(2)

        try:
            # Attendre que le tableau soit chargé
            self.page.wait_for_selector('table, .appointment-row, [class*="appointment"]',
                                         timeout=10000)
        except:
            log.warning("⚠️ Tableau non trouvé sur cette page")
            return rdvs

        # Stratégie 1: tableau HTML standard
        rows = self.page.query_selector_all('table tbody tr')
        if rows:
            log.info(f"  📊 {len(rows)} lignes trouvées dans le tableau")
            for row in rows:
                try:
                    cells = row.query_selector_all('td')
                    if len(cells) < 4:
                        continue
                    rdv = self._parser_ligne_tableau(cells)
                    if rdv:
                        rdvs.append(rdv)
                except Exception as e:
                    log.debug(f"  Ligne ignorée: {e}")

        # Stratégie 2: si pas de tableau, essayer les cards/rows
        if not rdvs:
            cards = self.page.query_selector_all('[class*="appointment"], [class*="service-row"]')
            for card in cards:
                try:
                    rdv = self._parser_carte(card)
                    if rdv:
                        rdvs.append(rdv)
                except:
                    pass

        return rdvs

    def _parser_ligne_tableau(self, cells) -> dict | None:
        """Parse une ligne du tableau Service Appointments de vAuto."""
        try:
            # Structure typique vAuto:
            # Col 0: icône statut
            # Col 1: Date/Heure RDV
            # Col 2: Véhicule (lien cliquable) + NIV + Odomètre
            # Col 3: Inventaire
            # Col 4: Client (nom, adresse, email, téléphone)

            if len(cells) < 4:
                return None

            # Date/Heure
            date_txt = cells[1].inner_text().strip() if len(cells) > 1 else ''
            date_rdv, heure_rdv = parser_date(date_txt)

            # Véhicule
            veh_cell = cells[2] if len(cells) > 2 else None
            if not veh_cell:
                return None

            veh_texte = veh_cell.inner_text().strip()
            # Extraire les lignes: ligne 1 = "2021 Hyundai Palisade Luxury"
            # ligne 2 = "NIV: KM8R..."
            # ligne 3 = "Odomètre: 123,152"
            lignes = [l.strip() for l in veh_texte.split('\n') if l.strip()]
            if not lignes:
                return None

            annee, marque, modele, version = parser_vehicule(lignes[0])
            if not annee:
                return None

            # VIN et KM
            vin, km = '', 0
            for ligne in lignes[1:]:
                if 'NIV' in ligne or 'VIN' in ligne or len(ligne) == 17:
                    vin = re.sub(r'(NIV|VIN)\s*:', '', ligne).strip()
                elif re.search(r'\d{3,}', ligne):
                    km = parser_km(re.search(r'[\d,]+', ligne).group())

            # Client
            client_cell = cells[4] if len(cells) > 4 else cells[-1]
            client_txt = client_cell.inner_text().strip()
            client_lignes = [l.strip() for l in client_txt.split('\n') if l.strip()]

            nom = client_lignes[0] if client_lignes else 'Inconnu'
            telephone, email, adresse = '', '', ''
            for cl in client_lignes[1:]:
                if '@' in cl:
                    email = cl
                elif re.search(r'\d{3}.*\d{4}', cl):
                    telephone = cl
                elif cl.lower() not in ['unknown', 'inconnu', '']:
                    adresse = adresse + ' ' + cl if adresse else cl

            # Lien évaluation (sur le véhicule)
            lien_eval = ''
            lien_el = veh_cell.query_selector('a')
            if lien_el:
                lien_eval = lien_el.get_attribute('href') or ''
                if lien_eval and not lien_eval.startswith('http'):
                    lien_eval = VAUTO_URL + lien_eval

            return {
                'date_rdv': date_rdv,
                'heure_rdv': heure_rdv,
                'nom': nom,
                'telephone': telephone,
                'email': email,
                'adresse': adresse.strip(),
                'annee_veh': annee,
                'marque': marque,
                'modele': modele,
                'version': version,
                'vin': vin,
                'km': km,
                'lien_evaluation': lien_eval,
            }

        except Exception as e:
            log.debug(f"  Parse erreur: {e}")
            return None

    def _parser_carte(self, card) -> dict | None:
        """Parse une carte/div d'appointment (format alternatif)."""
        try:
            txt = card.inner_text()
            lignes = [l.strip() for l in txt.split('\n') if l.strip()]
            if len(lignes) < 3:
                return None

            # Chercher année dans les lignes
            annee, marque, modele, version = None, 'Hyundai', '', ''
            for ligne in lignes:
                m = re.match(r'(20\d{2})\s+(\w+)\s+(.+)', ligne)
                if m:
                    annee = int(m.group(1))
                    marque = m.group(2)
                    reste = m.group(3)
                    parts = reste.split(' ', 1)
                    modele = parts[0]
                    version = parts[1] if len(parts) > 1 else ''
                    break

            if not annee:
                return None

            vin = ''
            for ligne in lignes:
                if len(re.sub(r'\s', '', ligne)) == 17:
                    vin = ligne.strip()

            return {
                'date_rdv': '', 'heure_rdv': '',
                'nom': lignes[0], 'telephone': '', 'email': '',
                'adresse': '', 'annee_veh': annee, 'marque': marque,
                'modele': modele, 'version': version,
                'vin': vin, 'km': 0, 'lien_evaluation': '',
            }
        except:
            return None

    def paginer(self) -> bool:
        """Passe à la page suivante. Retourne False si dernière page."""
        try:
            # Chercher bouton "suivant" ou ">"
            for sel in ['button:has-text("Next")', 'a:has-text("Next")',
                        '[aria-label="Next page"]', '.pagination-next',
                        'button:has-text(">")', 'a[rel="next"]']:
                btn = self.page.query_selector(sel)
                if btn:
                    disabled = btn.get_attribute('disabled') or btn.get_attribute('aria-disabled')
                    if disabled and disabled != 'false':
                        return False
                    btn.click()
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                    time.sleep(2)
                    return True
            return False
        except:
            return False

    def scraper_evaluations(self, limite=20):
        """
        Pour les clients sans valeur vAuto, ouvre leur lien évaluation
        et récupère la valeur estimée.
        """
        conn = get_db()
        clients = conn.execute('''
            SELECT id, nom, vin, lien_evaluation
            FROM clients_service
            WHERE (valeur_vauto IS NULL OR valeur_vauto = 0)
            AND lien_evaluation != ''
            AND vin != ''
            ORDER BY date_rdv ASC
            LIMIT ?
        ''', (limite,)).fetchall()
        conn.close()

        log.info(f"🔍 {len(clients)} véhicules à évaluer...")

        for client in clients:
            try:
                log.info(f"  → {client['nom']} ({client['vin'][:8]}...)")
                self.page.goto(client['lien_evaluation'],
                               wait_until='networkidle', timeout=20000)
                time.sleep(3)

                valeur = self._extraire_valeur_evaluation()
                if valeur and valeur > 0:
                    sauvegarder_evaluation(client['vin'], valeur,
                                           client['lien_evaluation'])
                    log.info(f"    ✅ Valeur: ${valeur:,.0f}")
                else:
                    log.info(f"    ⚠️ Valeur non trouvée")

                time.sleep(1)  # Pause entre requêtes

            except Exception as e:
                log.warning(f"    ❌ Erreur évaluation {client['nom']}: {e}")

    def _extraire_valeur_evaluation(self) -> float:
        """Extrait la valeur d'évaluation depuis la page vAuto."""
        # vAuto affiche la valeur dans plusieurs formats possibles
        for sel in [
            '[class*="appraisal-value"]',
            '[class*="trade-value"]',
            '[class*="evaluation-value"]',
            '.market-value',
            '[data-testid*="value"]',
        ]:
            el = self.page.query_selector(sel)
            if el:
                txt = el.inner_text()
                m = re.search(r'\$?([\d,]+)', txt)
                if m:
                    try:
                        return float(m.group(1).replace(',', ''))
                    except:
                        pass

        # Chercher dans tout le texte de la page un montant significatif
        # (valeur de véhicule entre $2,000 et $80,000)
        page_txt = self.page.inner_text('body')
        montants = re.findall(r'\$\s*([\d,]+)', page_txt)
        for m in montants:
            try:
                val = float(m.replace(',', ''))
                if 2000 < val < 80000:
                    return val
            except:
                pass

        return 0.0

    def scraper_tous_rdv(self) -> dict:
        """Scrape toutes les pages de Service Appointments."""
        stats = {'inseres': 0, 'mis_a_jour': 0, 'filtres': 0, 'erreurs': 0}
        page_num = 1

        while True:
            log.info(f"📄 Page {page_num}...")
            rdvs = self.extraire_rdv_page()

            if not rdvs:
                log.info(f"  Aucun RDV sur cette page, arrêt")
                break

            for rdv in rdvs:
                # Filtre: ignorer véhicules trop récents
                if rdv.get('annee_veh') and rdv['annee_veh'] > ANNEE_MIN_OPPORTUNITE:
                    log.debug(f"  ⏭ Filtré (trop récent): {rdv['annee_veh']} {rdv['modele']}")
                    stats['filtres'] += 1
                    continue

                # Sauvegarder lien évaluation séparément
                if rdv.get('lien_evaluation') and rdv.get('vin'):
                    conn = get_db()
                    conn.execute(
                        'UPDATE clients_service SET lien_evaluation=? WHERE vin=?',
                        (rdv['lien_evaluation'], rdv['vin'])
                    )
                    conn.commit()
                    conn.close()

                result = upsert_client(rdv)
                stats[result + 's'] += 1

            # Page suivante?
            if not self.paginer():
                log.info(f"✅ Dernière page atteinte")
                break
            page_num += 1
            if page_num > 50:  # Sécurité
                break

        return stats


# ─── Fonction principale ─────────────────────────────────────────────────────
def run_scraper(headless=True, evaluer=True):
    """Lance le scraper complet."""
    log.info("=" * 50)
    log.info(f"🚀 Scraper vAuto — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 50)

    if not VAUTO_USER:
        log.error("❌ VAUTO_USER non défini. Ajoutez-le dans Railway → Variables")
        return False

    init_db()
    scraper = ScraperVAuto(headless=headless)

    try:
        scraper.demarrer()

        # Si cookies disponibles → aller directement sur SA sans login
        cookies_dispo = bool(VAUTO_COOKIES_JSON)
        if cookies_dispo:
            log.info("🍪 Mode cookies — pas de login nécessaire")
            if not scraper.naviguer_service_appointments():
                log.warning("⚠️ Cookies expirés? Tentative login...")
                if not scraper.login():
                    return False
                if not scraper.naviguer_service_appointments():
                    return False
        else:
            log.info("🔑 Mode login classique")
            if not scraper.login():
                return False
            if not scraper.naviguer_service_appointments():
                return False

        stats = scraper.scraper_tous_rdv()
        log.info(f"\n📊 Résultats import RDV:")
        log.info(f"  ✚ Nouveaux:    {stats['inseres']}")
        log.info(f"  ↻ Mis à jour:  {stats['mis_a_jour']}")
        log.info(f"  ⏭ Filtrés:     {stats['filtres']}")

        if evaluer and stats['inseres'] > 0:
            log.info(f"\n🔍 Récupération des évaluations...")
            scraper.scraper_evaluations(limite=30)

        log.info("\n✅ Scraper terminé avec succès")
        return True

    except Exception as e:
        log.error(f"❌ Erreur critique: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        scraper.arreter()


if __name__ == '__main__':
    import sys
    headless = '--visible' not in sys.argv
    run_scraper(headless=headless)
