"""
app.py  –  Dashboard Service Prospect Hyundai St-Raymond
Lancer: python app.py
Accès:  http://localhost:5000
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import sqlite3, json, os, csv, io, re, re
from datetime import datetime
from calcul_versements import MoteurVersements, VehiculeClient
try:
    import xlrd
    XLRD_OK = True
except ImportError:
    XLRD_OK = False

app = Flask(__name__)
DB = 'hyundai_prospect.db'
moteur = MoteurVersements(DB)

# ─── Helpers DB ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clients_service (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_rdv TEXT, heure_rdv TEXT,
        nom TEXT, telephone TEXT, email TEXT, adresse TEXT,
        annee_veh INTEGER, marque TEXT, modele TEXT, version TEXT,
        vin TEXT, km INTEGER,
        valeur_vauto REAL DEFAULT 0,
        solde_financement REAL DEFAULT 0,
        type_contrat TEXT DEFAULT 'financement',
        fin_contrat TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        statut TEXT DEFAULT 'nouveau',  -- nouveau, contacté, vendu, pas_interesse
        modele_propose TEXT DEFAULT '',
        version_proposee TEXT DEFAULT '',
        date_import TEXT,
        source TEXT DEFAULT 'manuel'
    )''')
    conn.commit(); conn.close()

init_db()

# ─── Templates HTML ──────────────────────────────────────────────────────────
BASE_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Service Prospect — Hyundai St-Raymond</title>
<style>
  :root { --bleu:#002c5f; --rouge:#c00; --vert:#1a8a1a; --jaune:#f5a623; --gris:#f5f5f5; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; background:#f0f2f5; color:#222; }
  header { background:var(--bleu); color:white; padding:14px 24px; display:flex; align-items:center; gap:16px; }
  header h1 { font-size:1.3rem; font-weight:700; }
  header span { font-size:.9rem; opacity:.7; }
  nav { background:white; border-bottom:3px solid var(--bleu); display:flex; padding:0 24px; }
  nav a { display:block; padding:12px 18px; text-decoration:none; color:var(--bleu); font-weight:600;
          border-bottom:3px solid transparent; margin-bottom:-3px; font-size:.95rem; }
  nav a:hover, nav a.active { border-bottom-color:var(--rouge); color:var(--rouge); }
  .container { max-width:1400px; margin:0 auto; padding:20px; }
  .card { background:white; border-radius:10px; padding:20px; margin-bottom:16px;
          box-shadow:0 2px 8px rgba(0,0,0,.08); }
  .card h2 { font-size:1.1rem; color:var(--bleu); margin-bottom:14px; border-bottom:2px solid #eee; padding-bottom:8px; }
  table { width:100%; border-collapse:collapse; font-size:.88rem; }
  th { background:var(--bleu); color:white; padding:10px 8px; text-align:left; }
  td { padding:9px 8px; border-bottom:1px solid #eee; vertical-align:middle; }
  tr:hover td { background:#f0f4ff; }
  .badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:.78rem; font-weight:700; }
  .badge-5 { background:#1a8a1a; color:white; }
  .badge-4 { background:#5cb85c; color:white; }
  .badge-3 { background:var(--jaune); color:#333; }
  .badge-2 { background:#f0ad4e; color:#333; }
  .badge-1 { background:#ccc; color:#555; }
  .badge-vendu { background:var(--bleu); color:white; }
  .badge-contacte { background:var(--jaune); color:#333; }
  .btn { display:inline-block; padding:8px 16px; border-radius:6px; border:none; cursor:pointer;
         font-weight:600; font-size:.88rem; text-decoration:none; }
  .btn-primary { background:var(--bleu); color:white; }
  .btn-success { background:var(--vert); color:white; }
  .btn-danger { background:var(--rouge); color:white; }
  .btn-sm { padding:4px 10px; font-size:.8rem; }
  input, select, textarea { width:100%; padding:8px 10px; border:1px solid #ccc; border-radius:6px;
                              font-size:.9rem; margin-top:3px; }
  label { font-size:.85rem; font-weight:600; color:#555; display:block; margin-top:10px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }
  .equite-pos { color:var(--vert); font-weight:700; }
  .equite-neg { color:var(--rouge); font-weight:700; }
  .stat-box { background:var(--bleu); color:white; border-radius:10px; padding:16px; text-align:center; }
  .stat-box .num { font-size:2rem; font-weight:900; }
  .stat-box .lbl { font-size:.82rem; opacity:.8; margin-top:4px; }
  .stars { color:var(--jaune); font-size:1rem; }
  .versement-box { background:#f0f8ff; border:1px solid #b3d4f0; border-radius:8px; padding:12px; margin:6px 0; }
  .versement-box .montant { font-size:1.4rem; font-weight:900; color:var(--bleu); }
  .filtre-bar { display:flex; gap:10px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
  .filtre-bar input, .filtre-bar select { width:auto; flex:1; min-width:150px; }
  .alert { padding:10px 16px; border-radius:6px; margin-bottom:12px; }
  .alert-success { background:#d4edda; color:#155724; border:1px solid #c3e6cb; }
  .alert-info { background:#d1ecf1; color:#0c5460; border:1px solid #bee5eb; }
</style>
</head>
<body>
<header>
  <div>🔵</div>
  <div>
    <h1>Service Prospect — Hyundai St-Raymond</h1>
    <span>Gestion des opportunités de vente via le service</span>
  </div>
</header>
<nav>
  <a href="/" class="{{ 'active' if page=='dashboard' }}">📊 Tableau de bord</a>
  <a href="/clients" class="{{ 'active' if page=='clients' }}">👥 Clients RDV</a>
  <a href="/calculateur" class="{{ 'active' if page=='calc' }}">🧮 Calculateur</a>
  <a href="/import" class="{{ 'active' if page=='import' }}">📂 Import</a>
  <a href="/programme" class="{{ 'active' if page=='prog' }}">📋 Programme</a>
</nav>
<div class="container">
{% block content %}{% endblock %}
</div>
</body></html>'''

# ─── Page Dashboard ───────────────────────────────────────────────────────────
DASHBOARD_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px">
  <div class="stat-box"><div class="num">{{ stats.total }}</div><div class="lbl">Clients RDV à venir</div></div>
  <div class="stat-box" style="background:#c00"><div class="num">{{ stats.chauds }}</div><div class="lbl">⭐⭐⭐⭐⭐ Très chauds</div></div>
  <div class="stat-box" style="background:#1a8a1a"><div class="num">{{ stats.contactes }}</div><div class="lbl">Contactés</div></div>
  <div class="stat-box" style="background:#f5a623;color:#333"><div class="num">{{ stats.vendus }}</div><div class="lbl">Vendus ce mois</div></div>
</div>

<div class="card">
  <h2>🔥 Opportunités prioritaires (Score ≥ 60)</h2>
  <table>
    <tr><th>RDV</th><th>Client</th><th>Véhicule actuel</th><th>KM</th><th>Valeur vAuto</th><th>Équité</th><th>Score</th><th>Actions</th></tr>
    {% for c in top_clients %}
    <tr>
      <td>{{ c.date_rdv }}<br><small>{{ c.heure_rdv }}</small></td>
      <td><strong>{{ c.nom }}</strong><br><small style="color:#666">{{ c.telephone }}</small></td>
      <td>{{ c.annee_veh }} {{ c.marque }} {{ c.modele }}<br><small>{{ c.version or '' }}</small></td>
      <td>{{ "{:,}".format(c.km) if c.km else '—' }}</td>
      <td>{% if c.valeur_vauto %}<strong>${{ "{:,.0f}".format(c.valeur_vauto) }}</strong>{% else %}<span style="color:#aaa">—</span>{% endif %}</td>
      <td>
        {% if c.valeur_vauto %}
          {% set eq = c.valeur_vauto - (c.solde_financement or 0) %}
          <span class="{{ 'equite-pos' if eq >= 0 else 'equite-neg' }}">${{ "{:,.0f}".format(eq) }}</span>
        {% else %}—{% endif %}
      </td>
      <td>
        <span class="stars">{{ '⭐' * c.etoiles }}</span>
        <span class="badge badge-{{ c.etoiles }}">{{ c.score }}/100</span>
      </td>
      <td>
        <a href="/client/{{ c.id }}" class="btn btn-primary btn-sm">Fiche</a>
      </td>
    </tr>
    {% endfor %}
    {% if not top_clients %}<tr><td colspan="8" style="text-align:center;color:#aaa;padding:20px">Aucun client importé — allez sur Import pour commencer</td></tr>{% endif %}
  </table>
</div>
{% endblock %}''')

# ─── Page Clients ─────────────────────────────────────────────────────────────
CLIENTS_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <h2 style="border:none;margin:0">👥 Tous les clients RDV service</h2>
    <div style="display:flex;gap:8px">
      <a href="/import" class="btn btn-primary">📂 Importer</a>
      <a href="/export_csv" class="btn" style="background:#eee;color:#333">⬇ Export CSV</a>
    </div>
  </div>
  <div class="filtre-bar">
    <input type="text" id="recherche" placeholder="🔍 Rechercher nom, véhicule..." oninput="filtrer()">
    <select id="filtre_statut" onchange="filtrer()">
      <option value="">Tous statuts</option>
      <option value="nouveau">Nouveaux</option>
      <option value="contacte">Contactés</option>
      <option value="vendu">Vendus</option>
    </select>
    <select id="filtre_score" onchange="filtrer()">
      <option value="">Tous scores</option>
      <option value="5">⭐⭐⭐⭐⭐ Très chaud</option>
      <option value="4">⭐⭐⭐⭐ Chaud</option>
      <option value="3">⭐⭐⭐ Moyen</option>
    </select>
  </div>
  <table id="table_clients">
    <tr><th>RDV</th><th>Client</th><th>Véhicule</th><th>KM</th><th>Valeur</th><th>Équité</th><th>Score</th><th>Statut</th><th></th></tr>
    {% for c in clients %}
    <tr data-statut="{{ c.statut }}" data-score="{{ c.etoiles }}"
        data-search="{{ c.nom|lower }} {{ c.modele|lower }} {{ c.annee_veh }}">
      <td>{{ c.date_rdv }}<br><small>{{ c.heure_rdv }}</small></td>
      <td><strong>{{ c.nom }}</strong><br><small style="color:#666">{{ c.telephone }}</small></td>
      <td>{{ c.annee_veh }} {{ c.marque }} {{ c.modele }}</td>
      <td>{{ "{:,}".format(c.km) if c.km else '—' }}</td>
      <td>{% if c.valeur_vauto %}<strong>${{ "{:,.0f}".format(c.valeur_vauto) }}</strong>{% else %}—{% endif %}</td>
      <td>
        {% if c.valeur_vauto %}
          {% set eq = c.valeur_vauto - (c.solde_financement or 0) %}
          <span class="{{ 'equite-pos' if eq >= 0 else 'equite-neg' }}">${{ "{:,.0f}".format(eq) }}</span>
        {% else %}—{% endif %}
      </td>
      <td><span class="badge badge-{{ c.etoiles }}">{{ '⭐' * c.etoiles }}</span></td>
      <td>
        <span class="badge badge-{{ c.statut }}">{{ c.statut }}</span>
      </td>
      <td><a href="/client/{{ c.id }}" class="btn btn-primary btn-sm">Voir</a></td>
    </tr>
    {% endfor %}
  </table>
</div>
<script>
function filtrer() {
  const q = document.getElementById('recherche').value.toLowerCase();
  const s = document.getElementById('filtre_statut').value;
  const sc = document.getElementById('filtre_score').value;
  document.querySelectorAll('#table_clients tr[data-search]').forEach(tr => {
    const ok_q = !q || tr.dataset.search.includes(q);
    const ok_s = !s || tr.dataset.statut === s;
    const ok_sc = !sc || tr.dataset.score === sc;
    tr.style.display = (ok_q && ok_s && ok_sc) ? '' : 'none';
  });
}
</script>
{% endblock %}''')

# ─── Fiche client ─────────────────────────────────────────────────────────────
FICHE_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div style="display:flex;gap:8px;margin-bottom:14px;align-items:center">
  <a href="/clients" style="color:var(--bleu);text-decoration:none">← Retour</a>
  <h2 style="color:var(--bleu)">Fiche client: {{ client.nom }}</h2>
</div>
{% if msg %}<div class="alert alert-success">{{ msg }}</div>{% endif %}
<div class="grid2">
  <div class="card">
    <h2>👤 Informations client</h2>
    <p><strong>RDV:</strong> {{ client.date_rdv }} {{ client.heure_rdv }}</p>
    <p><strong>Téléphone:</strong> {{ client.telephone }}</p>
    <p><strong>Email:</strong> {{ client.email or '—' }}</p>
    <p><strong>Adresse:</strong> {{ client.adresse or '—' }}</p>
    <hr style="margin:12px 0">
    <p><strong>Véhicule:</strong> {{ client.annee_veh }} {{ client.marque }} {{ client.modele }}</p>
    <p><strong>Version:</strong> {{ client.version or '—' }}</p>
    <p><strong>VIN:</strong> <code>{{ client.vin or '—' }}</code></p>
    <p><strong>Kilométrage:</strong> {{ "{:,}".format(client.km) if client.km else '—' }} km</p>
    <hr style="margin:12px 0">
    <p><strong>Valeur vAuto:</strong>
      {% if client.valeur_vauto %}<strong class="equite-pos">${{ "{:,.0f}".format(client.valeur_vauto) }}</strong>{% else %}<em>non évalué</em>{% endif %}
    </p>
    <p><strong>Solde financement:</strong>
      {% if client.solde_financement %}<span class="equite-neg">${{ "{:,.0f}".format(client.solde_financement) }}</span>{% else %}Payé / N/A{% endif %}
    </p>
    {% if client.valeur_vauto %}
      {% set eq = client.valeur_vauto - (client.solde_financement or 0) %}
      <p><strong>Équité estimée:</strong>
        <span class="{{ 'equite-pos' if eq >= 0 else 'equite-neg' }}" style="font-size:1.2rem">${{ "{:,.0f}".format(eq) }}</span>
      </p>
    {% endif %}
    <p style="margin-top:8px"><span class="badge badge-{{ equite.etoiles }}">⭐ {{ equite.etoiles }}/5 — Score {{ equite.score }}/100</span></p>
    <p style="color:#666;font-size:.85rem;margin-top:4px">{{ equite.raisons | join(' · ') }}</p>
  </div>

  <div class="card">
    <h2>✏️ Mise à jour</h2>
    <form method="POST" action="/client/{{ client.id }}/update">
      <label>Valeur vAuto ($)</label>
      <input type="number" name="valeur_vauto" value="{{ client.valeur_vauto or '' }}" placeholder="ex: 14500">
      <label>Solde financement ($)</label>
      <input type="number" name="solde_financement" value="{{ client.solde_financement or '' }}" placeholder="ex: 9000">
      <label>Type de contrat</label>
      <select name="type_contrat">
        <option value="financement" {{ 'selected' if client.type_contrat=='financement' }}>Financement</option>
        <option value="location" {{ 'selected' if client.type_contrat=='location' }}>Location</option>
        <option value="comptant" {{ 'selected' if client.type_contrat=='comptant' }}>Comptant</option>
      </select>
      <label>Fin de contrat (AAAA-MM)</label>
      <input type="text" name="fin_contrat" value="{{ client.fin_contrat or '' }}" placeholder="ex: 2026-09">
      <label>Statut</label>
      <select name="statut">
        <option value="nouveau" {{ 'selected' if client.statut=='nouveau' }}>Nouveau</option>
        <option value="contacte" {{ 'selected' if client.statut=='contacte' }}>Contacté</option>
        <option value="vendu" {{ 'selected' if client.statut=='vendu' }}>Vendu</option>
        <option value="pas_interesse" {{ 'selected' if client.statut=='pas_interesse' }}>Pas intéressé</option>
      </select>
      <label>Modèle proposé</label>
      <input type="text" name="modele_propose" value="{{ client.modele_propose or '' }}" placeholder="ex: 2026 Elantra Preferred">
      <label>Notes</label>
      <textarea name="notes" rows="3" placeholder="Notes de suivi...">{{ client.notes or '' }}</textarea>
      <button type="submit" class="btn btn-success" style="margin-top:12px;width:100%">💾 Sauvegarder</button>
    </form>
  </div>
</div>

<div class="card">
  <h2>🧮 Calculateur de versements</h2>
  <form method="GET" action="/client/{{ client.id }}" style="margin-bottom:16px">
    <div class="grid3">
      <div>
        <label>Modèle à proposer</label>
        <select name="calc_modele" onchange="this.form.submit()">
          <option value="">-- Choisir --</option>
          {% for m in modeles %}
          <option value="{{ m }}" {{ 'selected' if calc_modele == m }}>{{ m }}</option>
          {% endfor %}
        </select>
      </div>
      {% if versions %}
      <div>
        <label>Version</label>
        <select name="calc_version" onchange="this.form.submit()">
          {% for v in versions %}
          <option value="{{ v.id }}" {{ 'selected' if calc_version == v.id|string }}>{{ v.version }} — ${{ "{:,.0f}".format(v.pdsf) }}</option>
          {% endfor %}
        </select>
      </div>
      {% endif %}
      <div>
        <label>Terme financement</label>
        <select name="terme_fin" onchange="this.form.submit()">
          {% for t in [48, 60, 72, 84, 96] %}
          <option value="{{ t }}" {{ 'selected' if terme_fin == t }}>{{ t }} mois</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label>Terme location</label>
        <select name="terme_loc" onchange="this.form.submit()">
          {% for t in [24, 36, 48, 60] %}
          <option value="{{ t }}" {{ 'selected' if terme_loc == t }}>{{ t }} mois</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label>Km/année (location)</label>
        <select name="km_annuel" onchange="this.form.submit()">
          <option value="16000" {{ 'selected' if km_annuel == 16000 }}>16 000 km</option>
          <option value="20000" {{ 'selected' if km_annuel == 20000 }}>20 000 km</option>
          <option value="24000" {{ 'selected' if km_annuel == 24000 }}>24 000 km</option>
        </select>
      </div>
      <div>
        <label>Client fidélisation?</label>
        <select name="fidelisation" onchange="this.form.submit()">
          <option value="0">Non</option>
          <option value="1" {{ 'selected' if fidelisation }}>Oui (+rabais)</option>
        </select>
      </div>
    </div>
  </form>

  {% if scenarios %}
  <div class="grid2">
    <div class="versement-box">
      <div style="font-weight:700;color:var(--bleu);margin-bottom:8px">💳 FINANCEMENT {{ scenarios.fin.terme_mois }} mois @ {{ scenarios.fin.taux_annuel }}%</div>
      <div class="montant">${{ "{:,.0f}".format(scenarios.fin.versement_mensuel) }}/mois</div>
      <div style="margin-top:8px;font-size:.85rem;color:#555">
        PDSF: ${{ "{:,.0f}".format(scenarios.fin.pdsf) }}<br>
        Rabais Hyundai: -${{ "{:,.0f}".format(scenarios.fin.comptant_fin) }}<br>
        Prix avant taxe: ${{ "{:,.0f}".format(scenarios.fin.prix_avant_taxe) }}<br>
        Montant financé (avec taxe): ${{ "{:,.0f}".format(scenarios.fin.montant_finance) }}
      </div>
    </div>
    {% if scenarios.loc %}
    <div class="versement-box">
      <div style="font-weight:700;color:#c00;margin-bottom:8px">🔑 LOCATION {{ scenarios.loc.terme_mois }} mois @ {{ scenarios.loc.taux_annuel }}% — {{ km_annuel|int // 1000 }}k km/an</div>
      <div class="montant" style="color:#c00">${{ "{:,.0f}".format(scenarios.loc.versement_mensuel) }}/mois</div>
      <div style="margin-top:8px;font-size:.85rem;color:#555">
        PDSF: ${{ "{:,.0f}".format(scenarios.loc.pdsf) }}<br>
        Rabais: -${{ "{:,.0f}".format(scenarios.loc.rabais + scenarios.loc.comptant_loc) }}<br>
        Valeur résiduelle ({{ scenarios.loc.resid_pct }}%): ${{ "{:,.0f}".format(scenarios.loc.valeur_residuelle) }}<br>
        Versement <em>taxes incluses</em>
      </div>
    </div>
    {% endif %}
  </div>
  <div class="alert alert-info" style="margin-top:10px;font-size:.83rem">
    ⚠️ Calcul estimatif — taxes QC incluses (TPS 5% + TVQ 9.975%). Frais d'administration et livraison inclus.
    Le versement réel peut varier selon le crédit, le solde repris et les options.
  </div>
  {% endif %}
</div>
{% endblock %}''')

# ─── Page Import ──────────────────────────────────────────────────────────────
IMPORT_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
{% if msg %}<div class="alert alert-success">{{ msg }}</div>{% endif %}
<div class="grid2">
  <div class="card">
    <h2>📋 Saisie manuelle (1 client)</h2>
    <form method="POST" action="/import/manuel">
      <div class="grid2">
        <div>
          <label>Date RDV</label>
          <input type="date" name="date_rdv" required>
          <label>Heure</label>
          <input type="time" name="heure_rdv" value="08:00">
        </div>
        <div>
          <label>Nom client</label>
          <input type="text" name="nom" required placeholder="Prénom Nom">
          <label>Téléphone</label>
          <input type="text" name="telephone" placeholder="(418) 000-0000">
        </div>
      </div>
      <label>Email</label>
      <input type="email" name="email" placeholder="client@email.com">
      <label>Année véhicule</label>
      <input type="number" name="annee_veh" placeholder="ex: 2021" min="2010" max="2026">
      <label>Marque</label>
      <input type="text" name="marque" value="Hyundai">
      <label>Modèle</label>
      <input type="text" name="modele" placeholder="ex: Elantra">
      <label>Version</label>
      <input type="text" name="version" placeholder="ex: Preferred IVT">
      <label>VIN</label>
      <input type="text" name="vin" placeholder="17 caractères">
      <label>Kilométrage</label>
      <input type="number" name="km" placeholder="ex: 75000">
      <button type="submit" class="btn btn-success" style="margin-top:14px;width:100%">➕ Ajouter ce client</button>
    </form>
  </div>

  <div class="card" style="border:2px solid var(--bleu)">
    <h2>📊 Import XLS — vAuto Service Appointments <span style="background:#1a8a1a;color:white;font-size:.75rem;padding:2px 8px;border-radius:10px;margin-left:8px">RECOMMANDÉ</span></h2>
    <p style="color:#666;font-size:.88rem;margin-bottom:12px">
      Dans vAuto → Stock → Service Appointments → cliquez l'icône <strong>Export XLS</strong> en haut à droite → uploadez le fichier ici.
    </p>
    <form method="POST" action="/import/xls" enctype="multipart/form-data">
      <div style="border:2px dashed #b3d4f0;border-radius:8px;padding:20px;text-align:center;margin-bottom:12px;background:#f8fbff">
        <div style="font-size:2rem;margin-bottom:8px">📁</div>
        <label style="display:block;cursor:pointer;color:var(--bleu);font-weight:700">
          Cliquer pour sélectionner le fichier XLS
          <input type="file" name="xls_file" accept=".xls,.xlsx" style="display:none" onchange="document.getElementById('nom_fichier').textContent=this.files[0]?.name||''">
        </label>
        <div id="nom_fichier" style="margin-top:6px;color:#888;font-size:.85rem"></div>
      </div>
      <button type="submit" class="btn btn-success" style="width:100%;font-size:1rem;padding:12px">
        📥 Importer les RDV vAuto
      </button>
    </form>
  </div>
</div>

<div class="card">
  <h2>📌 Format CSV vAuto — Guide rapide</h2>
  <p style="font-size:.87rem;color:#555;line-height:1.7">
    Dans vAuto → Stock → Service Appointments → cliquer l'icône export (CSV/Excel en haut à droite).<br>
    Les colonnes minimales requises : <strong>Date RDV, Nom, Téléphone, Année, Modèle, VIN, KM</strong>.<br>
    La valeur vAuto et le solde de financement peuvent être ajoutés manuellement dans la fiche client après l'import.
  </p>
</div>
{% endblock %}''')

# ─── Page Programme ───────────────────────────────────────────────────────────
PROG_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div class="card">
  <h2>📋 Programme Hyundai en vigueur</h2>
  <div class="filtre-bar">
    <input type="text" id="rech_prog" placeholder="🔍 Modèle ou version..." oninput="filtrerProg()">
    <select id="filt_am" onchange="filtrerProg()">
      <option value="">Toutes les années-modèles</option>
      <option value="2026">AM 2026</option>
      <option value="2025">AM 2025</option>
    </select>
  </div>
  <table id="table_prog">
    <tr>
      <th>AM</th><th>Modèle</th><th>Version</th><th>PDSF</th>
      <th>Rabais</th>
      <th>Fin 60m</th><th>Fin 84m</th>
      <th>Loc 48m</th><th>Résid 48m</th>
      <th>Loc 36m</th><th>Résid 36m</th>
    </tr>
    {% for p in programmes %}
    <tr data-am="{{ p.annee_modele }}" data-search="{{ (p.modele or '')|lower }} {{ (p.version or '')|lower }}">
      <td>{{ p.annee_modele or '—' }}</td>
      <td>{{ p.modele or '—' }}</td>
      <td>{{ p.version }}</td>
      <td>${{ "{:,.0f}".format(p.pdsf) }}</td>
      <td>{% if p.rabais_comptant and p.rabais_comptant > 0 %}<span style="color:green">-${{ "{:,.0f}".format(p.rabais_comptant) }}</span>{% else %}—{% endif %}</td>
      <td>{{ p.taux_fin_60 }}%</td>
      <td>{{ p.taux_fin_84 or '—' }}%</td>
      <td>{{ p.taux_loc_48 or '—' }}%</td>
      <td>{{ p.resid_48 or '—' }}%</td>
      <td>{{ p.taux_loc_36 or '—' }}%</td>
      <td>{{ p.resid_36 or '—' }}%</td>
    </tr>
    {% endfor %}
  </table>
</div>
<script>
function filtrerProg() {
  const q = document.getElementById('rech_prog').value.toLowerCase();
  const am = document.getElementById('filt_am').value;
  document.querySelectorAll('#table_prog tr[data-search]').forEach(tr => {
    const ok_q = !q || tr.dataset.search.includes(q);
    const ok_am = !am || tr.dataset.am === am;
    tr.style.display = (ok_q && ok_am) ? '' : 'none';
  });
}
</script>
{% endblock %}''')

# ─── Calculateur standalone ───────────────────────────────────────────────────
CALC_HTML = BASE_HTML.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div class="grid2">
  <div class="card">
    <h2>🧮 Calculateur de versements</h2>
    <form method="GET" action="/calculateur">
      <label>Modèle</label>
      <select name="calc_modele" onchange="this.form.submit()">
        <option value="">-- Choisir un modèle --</option>
        {% for m in modeles %}
        <option value="{{ m }}" {{ 'selected' if calc_modele == m }}>{{ m }}</option>
        {% endfor %}
      </select>
      {% if versions %}
      <label>Version</label>
      <select name="calc_version" onchange="this.form.submit()">
        {% for v in versions %}
        <option value="{{ v.id }}" {{ 'selected' if calc_version == v.id|string }}>{{ v.version }} — ${{ "{:,.0f}".format(v.pdsf) }}</option>
        {% endfor %}
      </select>
      {% endif %}
      <label>Terme financement (mois)</label>
      <select name="terme_fin" onchange="this.form.submit()">
        {% for t in [48, 60, 72, 84, 96] %}
        <option value="{{ t }}" {{ 'selected' if terme_fin == t }}>{{ t }} mois</option>
        {% endfor %}
      </select>
      <label>Terme location (mois)</label>
      <select name="terme_loc" onchange="this.form.submit()">
        {% for t in [24, 36, 48, 60] %}
        <option value="{{ t }}" {{ 'selected' if terme_loc == t }}>{{ t }} mois</option>
        {% endfor %}
      </select>
      <label>Km/année (location)</label>
      <select name="km_annuel" onchange="this.form.submit()">
        <option value="16000">16 000 km</option>
        <option value="20000" selected>20 000 km</option>
        <option value="24000">24 000 km</option>
      </select>
      <label>Mise de fonds ($)</label>
      <input type="number" name="mise_de_fonds" value="{{ mise_de_fonds or 0 }}" min="0" placeholder="0">
      <label>Client fidélisation?</label>
      <select name="fidelisation" onchange="this.form.submit()">
        <option value="0">Non</option>
        <option value="1" {{ 'selected' if fidelisation }}>Oui (+rabais fidélité)</option>
      </select>
      <button type="submit" class="btn btn-primary" style="margin-top:14px;width:100%">Calculer</button>
    </form>
  </div>

  <div>
  {% if scenarios %}
    <div class="card">
      <h2>💳 Financement {{ scenarios.fin.terme_mois }} mois</h2>
      <div class="versement-box">
        <div class="montant">${{ "{:,.0f}".format(scenarios.fin.versement_mensuel) }}/mois</div>
        <div style="font-size:.85rem;color:#555;margin-top:8px">
          Taux: {{ scenarios.fin.taux_annuel }}% | Terme: {{ scenarios.fin.terme_mois }} mois<br>
          PDSF: ${{ "{:,.0f}".format(scenarios.fin.pdsf) }}<br>
          Rabais Hyundai: -${{ "{:,.0f}".format(scenarios.fin.comptant_fin) }}<br>
          Livraison ${{ "{:,.0f}".format(scenarios.fin.frais_livraison) }} + admin ${{ "{:,.0f}".format(scenarios.fin.frais_admin) }} + clim $100 + pneus $22.50<br>
          Prix avant taxe: ${{ "{:,.0f}".format(scenarios.fin.prix_avant_taxe) }}<br>
          <strong>Montant financé TTC: ${{ "{:,.0f}".format(scenarios.fin.montant_finance) }}</strong>
        </div>
      </div>
    </div>
    {% if scenarios.loc %}
    <div class="card">
      <h2>🔑 Location {{ scenarios.loc.terme_mois }} mois</h2>
      <div class="versement-box">
        <div class="montant" style="color:var(--rouge)">${{ "{:,.0f}".format(scenarios.loc.versement_mensuel) }}/mois <small style="font-size:.7rem">taxes incl.</small></div>
        <div style="font-size:.85rem;color:#555;margin-top:8px">
          Taux: {{ scenarios.loc.taux_annuel }}% | Terme: {{ scenarios.loc.terme_mois }} mois<br>
          Résiduel {{ scenarios.loc.resid_pct }}%: ${{ "{:,.0f}".format(scenarios.loc.valeur_residuelle) }}<br>
          {{ km_annuel|int // 1000 }} 000 km/an | Comptant loc: ${{ "{:,.0f}".format(scenarios.loc.comptant_loc) }}
        </div>
      </div>
    </div>
    {% endif %}
    <div class="alert alert-info" style="font-size:.82rem">
      ⚠️ Estimatif — TPS 5% + TVQ 9.975% + frais admin + livraison inclus.
    </div>
  {% elif calc_modele %}
    <div class="card"><p style="color:#888">Aucun programme trouvé pour ce modèle/version.</p></div>
  {% else %}
    <div class="card"><p style="color:#888">Sélectionnez un modèle pour voir les versements.</p></div>
  {% endif %}
  </div>
</div>
{% endblock %}''')


# ─── Routes ───────────────────────────────────────────────────────────────────

def calculer_score_client(c):
    """Calcule score et étoiles pour un Row client."""
    client_obj = VehiculeClient(
        annee=c['annee_veh'] or 2020,
        marque=c['marque'] or 'Hyundai',
        modele=c['modele'] or '',
        km=c['km'] or 0,
        valeur_vauto=c['valeur_vauto'] or 0,
        solde_financement=c['solde_financement'] or 0,
        type_contrat=c['type_contrat'] or 'financement',
        fin_contrat=c['fin_contrat'] or '',
    )
    return moteur.calculer_equite(client_obj)

@app.route('/')
def dashboard():
    conn = get_db()
    clients = [dict(r) for r in conn.execute("SELECT * FROM clients_service ORDER BY date_rdv").fetchall()]
    conn.close()
    for c in clients:
        eq = calculer_score_client(c)
        c['score'] = eq['score']
        c['etoiles'] = eq['etoiles']
    top = sorted([c for c in clients if c['score'] >= 40], key=lambda x: -x['score'])[:20]
    stats = {
        'total': len(clients),
        'chauds': sum(1 for c in clients if c.get('etoiles', 0) >= 5),
        'contactes': sum(1 for c in clients if c.get('statut') == 'contacte'),
        'vendus': sum(1 for c in clients if c.get('statut') == 'vendu'),
    }
    from jinja2 import Template
    return Template(DASHBOARD_HTML).render(page='dashboard', stats=stats, top_clients=top)

@app.route('/clients')
def clients():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM clients_service ORDER BY date_rdv, heure_rdv").fetchall()]
    conn.close()
    for c in rows:
        eq = calculer_score_client(c)
        c['score'] = eq['score']
        c['etoiles'] = eq['etoiles']
    rows.sort(key=lambda x: (-x['score'], x['date_rdv'] or ''))
    from jinja2 import Template
    return Template(CLIENTS_HTML).render(page='clients', clients=rows)

@app.route('/client/<int:cid>', methods=['GET'])
def fiche_client(cid):
    conn = get_db()
    client = dict(conn.execute("SELECT * FROM clients_service WHERE id=?", (cid,)).fetchone())
    conn.close()

    equite = calculer_score_client(client)
    modeles = moteur.lister_modeles()
    calc_modele = request.args.get('calc_modele', '')
    calc_version = request.args.get('calc_version', '')
    terme_fin = int(request.args.get('terme_fin', 84))
    terme_loc = int(request.args.get('terme_loc', 48))
    km_annuel = int(request.args.get('km_annuel', 20000))
    fidelisation = request.args.get('fidelisation', '0') == '1'
    msg = request.args.get('msg', '')

    versions, scenarios = [], None
    if calc_modele:
        parts = calc_modele.split(' ', 1)
        annee = int(parts[0]) if parts[0].isdigit() else None
        modele_nom = parts[1] if len(parts) > 1 else calc_modele
        versions = moteur.lister_versions(modele_nom, annee)
        prog = None
        if calc_version:
            for v in versions:
                if str(v['id']) == calc_version:
                    prog = v; break
        if not prog and versions:
            prog = versions[0]
            calc_version = str(prog['id'])
        if prog:
            sc = moteur.calculer_scenarios(prog, terme_fin, terme_loc, km_annuel, 0, fidelisation)
            scenarios = {'fin': sc['financement'], 'loc': sc['location']}

    from jinja2 import Template
    return Template(FICHE_HTML).render(
        page='clients', client=client, equite=equite, modeles=modeles,
        versions=versions, calc_modele=calc_modele, calc_version=calc_version,
        terme_fin=terme_fin, terme_loc=terme_loc, km_annuel=km_annuel,
        fidelisation=fidelisation, scenarios=scenarios, msg=msg)

@app.route('/client/<int:cid>/update', methods=['POST'])
def update_client(cid):
    data = request.form
    conn = get_db()
    conn.execute('''UPDATE clients_service SET
        valeur_vauto=?, solde_financement=?, type_contrat=?, fin_contrat=?,
        statut=?, modele_propose=?, notes=? WHERE id=?''', (
        data.get('valeur_vauto') or None,
        data.get('solde_financement') or None,
        data.get('type_contrat'), data.get('fin_contrat'),
        data.get('statut'), data.get('modele_propose'), data.get('notes'), cid))
    conn.commit(); conn.close()
    return redirect(f'/client/{cid}?msg=Sauvegardé+avec+succès')

@app.route('/calculateur')
def calculateur():
    modeles = moteur.lister_modeles()
    calc_modele = request.args.get('calc_modele', '')
    calc_version = request.args.get('calc_version', '')
    terme_fin = int(request.args.get('terme_fin', 84))
    terme_loc = int(request.args.get('terme_loc', 48))
    km_annuel = int(request.args.get('km_annuel', 20000))
    mise_de_fonds = float(request.args.get('mise_de_fonds', 0))
    fidelisation = request.args.get('fidelisation', '0') == '1'

    versions, scenarios = [], None
    if calc_modele:
        parts = calc_modele.split(' ', 1)
        annee = int(parts[0]) if parts[0].isdigit() else None
        modele_nom = parts[1] if len(parts) > 1 else calc_modele
        versions = moteur.lister_versions(modele_nom, annee)
        prog = None
        if calc_version:
            for v in versions:
                if str(v['id']) == calc_version:
                    prog = v; break
        if not prog and versions:
            prog = versions[0]; calc_version = str(prog['id'])
        if prog:
            sc = moteur.calculer_scenarios(prog, terme_fin, terme_loc, km_annuel, mise_de_fonds, fidelisation)
            scenarios = {'fin': sc['financement'], 'loc': sc['location']}

    from jinja2 import Template
    return Template(CALC_HTML).render(
        page='calc', modeles=modeles, versions=versions,
        calc_modele=calc_modele, calc_version=calc_version,
        terme_fin=terme_fin, terme_loc=terme_loc, km_annuel=km_annuel,
        mise_de_fonds=mise_de_fonds, fidelisation=fidelisation, scenarios=scenarios)

@app.route('/import')
def import_page():
    msg = request.args.get('msg', '')
    from jinja2 import Template
    return Template(IMPORT_HTML).render(page='import', msg=msg)

@app.route('/import/manuel', methods=['POST'])
def import_manuel():
    d = request.form
    conn = get_db()
    conn.execute('''INSERT INTO clients_service 
        (date_rdv, heure_rdv, nom, telephone, email, annee_veh, marque, modele, version, vin, km, date_import, source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        d.get('date_rdv'), d.get('heure_rdv'), d.get('nom'), d.get('telephone'),
        d.get('email'), d.get('annee_veh') or None, d.get('marque'), d.get('modele'),
        d.get('version'), d.get('vin'), d.get('km') or None,
        datetime.now().strftime('%Y-%m-%d'), 'manuel'))
    conn.commit(); conn.close()
    return redirect('/import?msg=Client+ajouté+avec+succès')


def parser_xls_vauto(contenu_bytes):
    """Parse le fichier XLS exporté de vAuto Service Appointments."""
    if not XLRD_OK:
        return [], "xlrd non installé — ajoutez xlrd dans requirements.txt"
    try:
        wb = xlrd.open_workbook(file_contents=contenu_bytes)
        ws = wb.sheet_by_index(0)
    except Exception as e:
        return [], str(e)

    records = []
    for row_idx in range(1, ws.nrows):
        try:
            date_str    = str(ws.cell_value(row_idx, 1)).strip()
            veh_titre   = str(ws.cell_value(row_idx, 2)).strip()
            vin         = str(ws.cell_value(row_idx, 3)).strip()
            km_raw      = ws.cell_value(row_idx, 4)
            prenom      = str(ws.cell_value(row_idx, 12)).strip()
            nom_famille = str(ws.cell_value(row_idx, 13)).strip()
            adresse     = str(ws.cell_value(row_idx, 14)).strip()
            ville       = str(ws.cell_value(row_idx, 15)).strip()
            code_postal = str(ws.cell_value(row_idx, 16)).strip()
            email       = str(ws.cell_value(row_idx, 17)).strip()
            telephone   = str(ws.cell_value(row_idx, 18)).strip()

            m = re.match(r'(\d{2}/\d{2}/\d{4})\s+(\d+:\d+:\d+\s*[AP]M)', date_str)
            if m:
                d = datetime.strptime(m.group(1), '%m/%d/%Y')
                t = datetime.strptime(m.group(2).strip(), '%I:%M:%S %p')
                date_rdv  = d.strftime('%Y-%m-%d')
                heure_rdv = t.strftime('%H:%M')
            else:
                date_rdv, heure_rdv = date_str[:10], ''

            m_veh = re.match(r'(\d{4})\s+(\w+)\s+(.+)', veh_titre)
            if not m_veh:
                continue
            annee_veh = int(m_veh.group(1))
            marque    = m_veh.group(2)
            reste     = m_veh.group(3).strip()
            modele, version = reste, ''
            for ml in ['IONIQ 5','IONIQ 6','IONIQ 9','Santa Fe','Elantra HEV',
                       'Kona Electric','Tucson PHEV','Palisade HEV']:
                if reste.upper().startswith(ml.upper()):
                    modele, version = ml, reste[len(ml):].strip()
                    break
            else:
                parts_v = reste.split(' ', 1)
                modele  = parts_v[0]
                version = parts_v[1] if len(parts_v) > 1 else ''

            records.append({
                'date_rdv': date_rdv, 'heure_rdv': heure_rdv,
                'nom': f"{prenom} {nom_famille}".strip(),
                'telephone': telephone.replace('+1','').strip(),
                'email': email,
                'adresse': f"{adresse}, {ville} {code_postal}".strip(', '),
                'annee_veh': annee_veh, 'marque': marque,
                'modele': modele, 'version': version,
                'vin': vin, 'km': int(km_raw) if km_raw else 0,
            })
        except:
            continue
    return records, None

@app.route('/import/xls', methods=['POST'])
def import_xls():
    f = request.files.get('xls_file')
    if not f or not f.filename:
        return redirect('/import?msg=Aucun+fichier+reçu')
    records, erreur = parser_xls_vauto(f.read())
    if erreur:
        return redirect(f'/import?msg=Erreur:+{erreur}')
    inseres, maj = 0, 0
    conn = get_db()
    for r in records:
        ex = conn.execute('SELECT id FROM clients_service WHERE vin=?', (r['vin'],)).fetchone()
        if ex:
            conn.execute('''UPDATE clients_service SET
                date_rdv=?,heure_rdv=?,nom=?,telephone=?,email=?,adresse=?,
                annee_veh=?,marque=?,modele=?,version=?,km=?,date_import=?,source=?
                WHERE vin=?''', (
                r['date_rdv'],r['heure_rdv'],r['nom'],r['telephone'],r['email'],
                r['adresse'],r['annee_veh'],r['marque'],r['modele'],r['version'],
                r['km'],datetime.now().strftime('%Y-%m-%d'),'vauto_xls',r['vin']))
            maj += 1
        else:
            conn.execute('''INSERT INTO clients_service
                (date_rdv,heure_rdv,nom,telephone,email,adresse,
                 annee_veh,marque,modele,version,vin,km,date_import,source,statut)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                r['date_rdv'],r['heure_rdv'],r['nom'],r['telephone'],r['email'],
                r['adresse'],r['annee_veh'],r['marque'],r['modele'],r['version'],
                r['vin'],r['km'],datetime.now().strftime('%Y-%m-%d'),'vauto_xls','nouveau'))
            inseres += 1
    conn.commit(); conn.close()
    return redirect(f'/clients?msg={inseres}+nouveaux,+{maj}+mis+à+jour')

@app.route('/import/csv', methods=['POST'])
def import_csv():
    csv_data = request.form.get('csv_data', '').strip()
    f = request.files.get('csv_file')
    if f and f.filename:
        csv_data = f.read().decode('utf-8', errors='replace')

    if not csv_data:
        return redirect('/import?msg=Aucune+donnée+reçue')

    lines = csv_data.strip().splitlines()
    inserted = 0
    conn = get_db()
    for line in lines[1:]:  # Sauter l'en-tête
        if not line.strip(): continue
        parts = [p.strip().strip('"') for p in line.split(',')]
        if len(parts) < 4: continue
        try:
            conn.execute('''INSERT INTO clients_service
                (date_rdv, heure_rdv, nom, telephone, email, annee_veh, marque, modele, version, vin, km, date_import, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                parts[0] if len(parts)>0 else '',
                parts[1] if len(parts)>1 else '',
                parts[2] if len(parts)>2 else '',
                parts[3] if len(parts)>3 else '',
                parts[4] if len(parts)>4 else '',
                int(parts[5]) if len(parts)>5 and parts[5].isdigit() else None,
                parts[6] if len(parts)>6 else 'Hyundai',
                parts[7] if len(parts)>7 else '',
                parts[8] if len(parts)>8 else '',
                parts[9] if len(parts)>9 else '',
                int(parts[10]) if len(parts)>10 and parts[10].replace(',','').isdigit() else None,
                datetime.now().strftime('%Y-%m-%d'), 'csv'))
            inserted += 1
        except Exception as e:
            print(f"Ligne ignorée: {e}")
    conn.commit(); conn.close()
    return redirect(f'/import?msg={inserted}+clients+importés')

@app.route('/programme')
def programme():
    conn = get_db()
    progs = [dict(r) for r in conn.execute(
        "SELECT * FROM programmes ORDER BY annee_modele DESC, modele, pdsf").fetchall()]
    conn.close()
    from jinja2 import Template
    return Template(PROG_HTML).render(page='prog', programmes=progs)

@app.route('/export_csv')
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM clients_service").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID','Date RDV','Heure','Nom','Téléphone','Email','Année','Marque','Modèle',
                     'VIN','KM','Valeur vAuto','Solde','Type contrat','Statut','Modèle proposé','Notes'])
    for r in rows:
        writer.writerow([r['id'], r['date_rdv'], r['heure_rdv'], r['nom'], r['telephone'],
                         r['email'], r['annee_veh'], r['marque'], r['modele'],
                         r['vin'], r['km'], r['valeur_vauto'], r['solde_financement'],
                         r['type_contrat'], r['statut'], r['modele_propose'], r['notes']])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=service_prospect.csv'})

if __name__ == '__main__':
    print("🚀 Démarrage du dashboard Service Prospect")
    print("   → http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
