"""
parser_programme.py
Extrait le tableau des taux Hyundai depuis le PDF du programme mensuel.
Usage: python parser_programme.py Programme.pdf [2026-05]
"""
import pdfplumber, sqlite3, json, re, sys

def nettoyer(val):
    if val is None: return None
    v = str(val).strip()
    v = re.sub(r'^[0-9a-zA-Z]\n', '', v)
    v = re.sub(r'^[:/\-]\n', '', v)
    return v.strip() or None

def parse_pct(val):
    v = nettoyer(val)
    if not v or v == '-': return None
    try: return float(v.replace('%','').replace(',','.').strip())
    except: return None

def parse_dollar(val):
    v = nettoyer(val)
    if not v or v == '-': return None
    try: return float(v.replace('$','').replace(',','').strip())
    except: return None

def extraire_tableau_taux(pdf_path):
    records, modele_courant, annee_courant = [], None, None
    MODELES_CONNUS = ['Elantra','Kona','Tucson','Santa Fe','Palisade',
                      'Sonata','Venue','Ioniq','IONIQ']

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            for table in page.extract_tables():
                if len(table) < 5: continue
                header = ' '.join(str(c) for row in table[:6] for c in row if c)
                if 'P.D.S.F' not in header: continue
                if not any(len(r) >= 25 for r in table): continue

                for row in table:
                    if len(row) < 25: continue
                    mod_val = nettoyer(row[1])
                    if mod_val and any(m in mod_val for m in MODELES_CONNUS):
                        m = re.search(r'(20\d{2})', mod_val)
                        annee_courant = int(m.group(1)) if m else annee_courant
                        modele_courant = re.sub(r'20\d{2}(AM|MY)?\s*', '', mod_val).strip()

                    version = nettoyer(row[2])
                    pdsf = parse_dollar(row[3])
                    if not version or not pdsf: continue

                    records.append({
                        'annee_modele': annee_courant,
                        'modele': modele_courant,
                        'version': version,
                        'pdsf': pdsf,
                        'rabais_comptant': parse_dollar(row[4]),
                        'rabais_fidelite': parse_dollar(row[5]),
                        'comptant_financement': parse_dollar(row[6]),
                        'reduc_fid_fin': parse_pct(row[7]),
                        'taux_fin_24': parse_pct(row[8]),
                        'taux_fin_36': parse_pct(row[9]),
                        'taux_fin_48': parse_pct(row[10]),
                        'taux_fin_60': parse_pct(row[11]),
                        'taux_fin_72': parse_pct(row[12]),
                        'taux_fin_84': parse_pct(row[13]),
                        'taux_fin_96': parse_pct(row[14]),
                        'comptant_location': parse_dollar(row[15]),
                        'reduc_fid_loc': parse_pct(row[16]),
                        'taux_loc_24': parse_pct(row[17]),
                        'taux_loc_33': parse_pct(row[18]),
                        'taux_loc_36': parse_pct(row[19]),
                        'taux_loc_39': parse_pct(row[20]),
                        'taux_loc_48': parse_pct(row[21]),
                        'taux_loc_60': parse_pct(row[22]),
                        'resid_24': parse_pct(row[23]),
                        'resid_33': parse_pct(row[24]),
                        'resid_36': parse_pct(row[25]),
                        'resid_39': parse_pct(row[26]),
                        'resid_48': parse_pct(row[27]),
                        'resid_60': parse_pct(row[28]),
                        'page_source': page_num + 1,
                    })
    return records

def sauvegarder_sqlite(records, db_path, mois):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS programmes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, mois TEXT,
        annee_modele INTEGER, modele TEXT, version TEXT, pdsf REAL,
        rabais_comptant REAL, rabais_fidelite REAL, comptant_financement REAL, reduc_fid_fin REAL,
        taux_fin_24 REAL, taux_fin_36 REAL, taux_fin_48 REAL, taux_fin_60 REAL,
        taux_fin_72 REAL, taux_fin_84 REAL, taux_fin_96 REAL,
        comptant_location REAL, reduc_fid_loc REAL,
        taux_loc_24 REAL, taux_loc_33 REAL, taux_loc_36 REAL,
        taux_loc_39 REAL, taux_loc_48 REAL, taux_loc_60 REAL,
        resid_24 REAL, resid_33 REAL, resid_36 REAL,
        resid_39 REAL, resid_48 REAL, resid_60 REAL, page_source INTEGER)''')
    c.execute("DELETE FROM programmes WHERE mois=?", (mois,))
    for r in records:
        c.execute('''INSERT INTO programmes VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (mois, r['annee_modele'], r['modele'], r['version'], r['pdsf'],
             r['rabais_comptant'], r['rabais_fidelite'], r['comptant_financement'], r['reduc_fid_fin'],
             r['taux_fin_24'], r['taux_fin_36'], r['taux_fin_48'], r['taux_fin_60'],
             r['taux_fin_72'], r['taux_fin_84'], r['taux_fin_96'],
             r['comptant_location'], r['reduc_fid_loc'],
             r['taux_loc_24'], r['taux_loc_33'], r['taux_loc_36'], r['taux_loc_39'],
             r['taux_loc_48'], r['taux_loc_60'],
             r['resid_24'], r['resid_33'], r['resid_36'], r['resid_39'],
             r['resid_48'], r['resid_60'], r['page_source']))
    conn.commit(); conn.close()
    print(f"✅ {len(records)} versions sauvegardées (mois: {mois})")

if __name__ == '__main__':
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else 'Programme.pdf'
    mois = sys.argv[2] if len(sys.argv) > 2 else '2026-05'
    print(f"📄 Extraction: {pdf_file}")
    records = extraire_tableau_taux(pdf_file)
    print(f"   {len(records)} entrées extraites")
    for r in records[:3]:
        print(f"   {r['annee_modele']} {r['modele']} | {r['version'][:30]} | PDSF: ${r['pdsf']:,.0f}")
    sauvegarder_sqlite(records, 'hyundai_prospect.db', mois)
    with open(f'programme_{mois}.json','w',encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"📁 JSON: programme_{mois}.json")
