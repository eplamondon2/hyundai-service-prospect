"""
parser_programme.py — Version 3 finale avec corrections métier
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

MODELES_CONNUS = ['Elantra','Kona','Tucson','Santa Fe','Palisade',
                  'Sonata','Venue','Ioniq','IONIQ']

# Corrections: (version, pdsf_int) → (annee, modele_correct)
# Nécessaires car le PDF place le label du groupe sur la 2e ligne (pas la 1ère)
CORRECTIONS_MODELE = {
    # AM2026
    ('Preferred-Trend AWD', 36099): (2026, 'Sonata'),
    ('N Line', 40699): (2026, 'Sonata'),
    ('Hybrid Preferred-Trend HEV', 36199): (2026, 'Sonata'),
    ('Essential', 21999): (2026, 'Venue'),
    ('Essential (Two-tone)', 22349): (2026, 'Venue'),
    ('Preferred', 24099): (2026, 'Venue'),
    ('Preferred (Two-tone)', 24449): (2026, 'Venue'),
    ('Ultimate - Black interior', 26599): (2026, 'Venue'),
    ('Ultimate - Denim interior', 26599): (2026, 'Venue'),
    ('2.0L Essential FWD', 26749): (2026, 'Kona'),
    ('2.0L Essential AWD', 28749): (2026, 'Kona'),
    ('2.0L Preferred FWD', 29249): (2026, 'Kona'),
    ('1.6T N Line AWD w/ Two-tone', 37149): (2026, 'Kona'),
    ('1.6T N Line Ultimate AWD', 39399): (2026, 'Kona'),
    ('1.6T N Line Ultimate AWD w/ Two-tone', 39849): (2026, 'Kona'),
    ('1.6T Preferred Hybrid AWD 7-Pass', 43799): (2026, 'Santa Fe'),
    ('1.6T Preferred Hybrid w/Trend Pkg AWD 7-Pass', 47799): (2026, 'Santa Fe'),
    ('Preferred Trend ICE 8P', 53699): (2026, 'Palisade'),
    ('XRT PRO ICE 7P', 57799): (2026, 'Palisade'),
    ('Ultimate Calligraphy 7P', 62499): (2026, 'Palisade'),
    ('2.5T Luxury HEV 7-Pass', 60999): (2026, 'Palisade HEV'),
    ('2.5T Ultimate Calligraphy HEV 7-Pass', 65699): (2026, 'Palisade HEV'),
    ('2.5T Ultimate Calligraphy HEV 7-Pass NHL Edition', 68899): (2026, 'Palisade HEV'),
    # AM2025
    ('N M/T', 40199): (2025, 'Elantra N'),
    ('N DCT', 41799): (2025, 'Elantra N'),
    ('HEV Luxury (Two-Tone Interior)', 31099): (2025, 'Elantra HEV'),
    ('1.6T Ultimate PHEV AWD', 52899): (2025, 'Tucson PHEV'),
    ('Preferred-Trend FWD', 33099): (2025, 'Sonata'),
    ('Preferred-Trend AWD', 35099): (2025, 'Sonata'),
    ('N-Line', 39699): (2025, 'Sonata'),
    ('1.6T Preferred Hybrid AWD 7-Pass', 42499): (2025, 'Santa Fe'),
    ('1.6T Preferred Hybrid w/Trend Pkg AWD 7-Pass', 46499): (2025, 'Santa Fe'),
    ('2.5T XRT AWD 7-Pass', 47999): (2025, 'Santa Fe'),
    ('2.5T Luxury AWD 7-pass', 50999): (2025, 'Santa Fe'),
    ('2.5T Ultimate Calligraphy AWD 6-Pass', 54799): (2025, 'Santa Fe'),
    ('2.5T Ultimate Calligraphy AWD 6-Pass Beige', 54799): (2025, 'Santa Fe'),
    ('Preferred', 50499): (2025, 'Palisade'),
    ('Urban 8 Passenger', 55699): (2025, 'Palisade'),
    ('Urban 7 Passenger', 56199): (2025, 'Palisade'),
    ('Ultimate Calligraphy', 59299): (2025, 'Palisade'),
    ('Ultimate Calligraphy (Beige Interior)', 59299): (2025, 'Palisade'),
    ('Calligraphy Night', 60799): (2025, 'Palisade'),
    ('Preferred RWD Long Range', 54999): (2025, 'Ioniq 6'),
    ('Preferred AWD Long Range', 58399): (2025, 'Ioniq 6'),
    ('Preferred AWD Long Range with Ultimate Package', 64999): (2025, 'Ioniq 6'),
}

def extraire_am_modele(val):
    if not val: return None, None
    val = val.split('\n')[0].strip()
    m = re.search(r'(20\d{2})', val)
    annee = int(m.group(1)) if m else None
    modele = re.sub(r'20\d{2}(AM|MY)?\s*', '', val).strip()
    if any(k in modele for k in MODELES_CONNUS):
        return annee, modele
    return None, None

def extraire_tableau_taux(pdf_path):
    all_items = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            for table in page.extract_tables():
                if len(table) < 5: continue
                header = ' '.join(str(c) for row in table[:6] for c in row if c)
                if 'P.D.S.F' not in header: continue
                if not any(len(r) >= 25 for r in table): continue

                # Construire les segments: (label_row_idx, annee, modele)
                labels = []
                for row_idx, row in enumerate(table):
                    mod_val = nettoyer(row[1]) if len(row) > 1 else None
                    annee, modele = extraire_am_modele(mod_val)
                    if annee and modele:
                        labels.append((row_idx, annee, modele))

                # Pour chaque data row, assigner le label dont la plage contient ce row
                for row_idx, row in enumerate(table):
                    if len(row) < 25: continue
                    version = nettoyer(row[2])
                    pdsf = parse_dollar(row[3])
                    if not version or not pdsf: continue

                    # Trouver le segment: label précédent le plus proche
                    assigned_annee, assigned_modele = None, None
                    for label_idx, annee, modele in reversed(labels):
                        if label_idx <= row_idx:
                            assigned_annee, assigned_modele = annee, modele
                            break
                    # Si pas de label avant, prendre le premier label après
                    if not assigned_modele and labels:
                        assigned_annee, assigned_modele = labels[0][1], labels[0][2]

                    all_items.append({
                        'row': row, 'annee': assigned_annee, 'modele': assigned_modele,
                        'version': version, 'pdsf': pdsf,
                    })

    # Fallback forward pour les None restants
    annee_cur, modele_cur = None, None
    for item in all_items:
        if item['annee']: annee_cur = item['annee']
        if item['modele']: modele_cur = item['modele']
        if not item['annee']: item['annee'] = annee_cur
        if not item['modele']: item['modele'] = modele_cur

    # Appliquer les corrections métier
    for item in all_items:
        key = (item['version'], int(item['pdsf']))
        if key in CORRECTIONS_MODELE:
            item['annee'], item['modele'] = CORRECTIONS_MODELE[key]

    # Construire les records finaux
    records = []
    for item in all_items:
        row = item['row']
        records.append({
            'annee_modele': item['annee'],
            'modele': item['modele'],
            'version': item['version'],
            'pdsf': item['pdsf'],
            'rabais_comptant':      parse_dollar(row[4]),
            'rabais_fidelite':      parse_dollar(row[5]),
            'comptant_financement': parse_dollar(row[6]),
            'reduc_fid_fin':        parse_pct(row[7]),
            'taux_fin_24': parse_pct(row[8]),  'taux_fin_36': parse_pct(row[9]),
            'taux_fin_48': parse_pct(row[10]), 'taux_fin_60': parse_pct(row[11]),
            'taux_fin_72': parse_pct(row[12]), 'taux_fin_84': parse_pct(row[13]),
            'taux_fin_96': parse_pct(row[14]),
            'comptant_location': parse_dollar(row[15]),
            'reduc_fid_loc':     parse_pct(row[16]),
            'taux_loc_24': parse_pct(row[17]), 'taux_loc_33': parse_pct(row[18]),
            'taux_loc_36': parse_pct(row[19]), 'taux_loc_39': parse_pct(row[20]),
            'taux_loc_48': parse_pct(row[21]), 'taux_loc_60': parse_pct(row[22]),
            'resid_24': parse_pct(row[23]), 'resid_33': parse_pct(row[24]),
            'resid_36': parse_pct(row[25]), 'resid_39': parse_pct(row[26]),
            'resid_48': parse_pct(row[27]), 'resid_60': parse_pct(row[28]),
            'page_source': 0,
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
        c.execute('''INSERT INTO programmes VALUES
            (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
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
    print(f"   {len(records)} entrées extraites\n")

    # Affichage groupé pour validation
    modele_cur = None
    for r in records:
        if r['modele'] != modele_cur:
            modele_cur = r['modele']
            print(f"\n--- {r['annee_modele']} {r['modele']} ---")
        print(f"  {r['version']:42} ${r['pdsf']:,.0f}")

    print()
    sauvegarder_sqlite(records, 'hyundai_prospect.db', mois)
    with open(f'programme_{mois}.json','w',encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"📁 JSON: programme_{mois}.json")
