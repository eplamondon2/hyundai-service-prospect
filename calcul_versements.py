"""
calcul_versements.py
Moteur de calcul des versements mensuels pour financement et location.
Inclut le calcul d'équité et le score d'opportunité client.

Taxes Québec: TPS 5% + TVQ 9.975% = 14.975%
"""

import sqlite3
import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Constantes Québec ───────────────────────────────────────────────────────
TPS  = 0.05
TVQ  = 0.09975
TAXE_TOTALE = TPS + TVQ          # 14.975%
FRAIS_ADMIN_STANDARD = 799.00    # max concessionnaire (ICE/HEV)
FRAIS_ADMIN_VE       = 599.00    # max concessionnaire (VÉ/PHEV)
TAXE_CLIMATISEUR     = 100.00    # Taxe fédérale fixe sur climatiseur (avant taxes de vente)
TAXE_PNEUS_NEUFS     = 22.50     # Taxe provinciale sur pneus neufs (avant taxes de vente)
FRAIS_LIVRAISON = {              # AM26 par défaut (incluent déjà livraison + destination)
    'Elantra': 1900, 'Elantra HEV': 1900, 'Elantra N': 1900,
    'Sonata': 1975,
    'Venue': 2050, 'Kona': 2050, 'Kona EV': 2050,
    'Tucson': 2050, 'Tucson HEV': 2050, 'Tucson PHEV': 2050,
    'Santa Fe': 2100, 'Palisade': 2100, 'Palisade HEV': 2100,
    'Ioniq 5': 2050, 'Ioniq 6': 2050, 'Ioniq 9': 2050,
    'default': 2050
}


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class VehiculeClient:
    """Véhicule actuel du client en service."""
    annee: int
    marque: str
    modele: str
    version: str = ''
    km: int = 0
    vin: str = ''
    valeur_vauto: float = 0.0         # Valeur évaluation vAuto
    solde_financement: float = 0.0    # Solde restant (0 si payé/loué)
    type_contrat: str = 'financement' # 'financement', 'location', 'comptant'
    fin_contrat: str = ''             # 'AAAA-MM' optionnel


@dataclass
class ScenarioFinancement:
    modele_propose: str
    version_propose: str
    pdsf: float
    rabais: float
    comptant_fin: float
    taux_annuel: float     # ex: 3.49
    terme_mois: int        # ex: 60
    mise_de_fonds: float = 0.0
    fidelisation: bool = False
    frais_admin: float = FRAIS_ADMIN_STANDARD
    frais_livraison: float = 2050.0
    # Calculé
    versement_mensuel: float = field(init=False, default=0.0)
    montant_finance: float = field(init=False, default=0.0)
    prix_avant_taxe: float = field(init=False, default=0.0)
    prix_total: float = field(init=False, default=0.0)

    def __post_init__(self):
        self.calculer()

    def calculer(self):
        # Pour financement subventionné: utiliser comptant_financement seulement
        # rabais est le rabais cash (non subventionné), non applicable ici
        rabais_total = self.comptant_fin
        self.prix_avant_taxe = (self.pdsf - rabais_total + self.frais_admin
                                + self.frais_livraison + TAXE_CLIMATISEUR + TAXE_PNEUS_NEUFS)
        self.prix_total = self.prix_avant_taxe * (1 + TAXE_TOTALE)
        self.montant_finance = self.prix_total - self.mise_de_fonds
        if self.montant_finance <= 0:
            self.versement_mensuel = 0.0
            return
        taux_m = (self.taux_annuel / 100) / 12
        n = self.terme_mois
        if taux_m == 0:
            self.versement_mensuel = self.montant_finance / n
        else:
            self.versement_mensuel = self.montant_finance * (taux_m / (1 - (1 + taux_m) ** -n))


@dataclass
class ScenarioLocation:
    modele_propose: str
    version_propose: str
    pdsf: float
    rabais: float
    comptant_loc: float
    taux_annuel: float       # ex: 4.49
    terme_mois: int          # 24, 36, 48, 60
    residu_pct: float        # ex: 57.0 → 57%
    km_annuel: int = 20000
    mise_de_fonds: float = 0.0
    fidelisation: bool = False
    frais_admin: float = FRAIS_ADMIN_STANDARD
    frais_livraison: float = 2050.0
    # Calculé
    versement_mensuel: float = field(init=False, default=0.0)
    valeur_residuelle: float = field(init=False, default=0.0)
    prix_avant_taxe: float = field(init=False, default=0.0)

    def __post_init__(self):
        self.calculer()

    def calculer(self):
        """
        Formule location SFHM standard:
        Versement = (Valeur_financement - Résiduel_actualisé) × Facteur_location + Taxe
        """
        # Pour location subventionnée: utiliser comptant_location seulement
        rabais_total = self.comptant_loc
        self.prix_avant_taxe = (self.pdsf - rabais_total + self.frais_admin
                                + self.frais_livraison + TAXE_CLIMATISEUR + TAXE_PNEUS_NEUFS)

        # Ajustement kilométrage (base 16,000 km/an)
        # +2% pour 20,000 km/an, +3% pour 24,000 km/an selon le programme
        if self.km_annuel == 20000:
            adj_km = 0.02
        elif self.km_annuel == 24000:
            adj_km = 0.03
        else:
            adj_km = 0.0

        residu_pct_ajuste = max(0, self.residu_pct - adj_km * 100)
        self.valeur_residuelle = self.pdsf * (residu_pct_ajuste / 100)

        valeur_financement = self.prix_avant_taxe - self.mise_de_fonds
        taux_m = (self.taux_annuel / 100) / 12
        n = self.terme_mois

        # Actualiser le résiduel
        if taux_m > 0:
            residu_actualise = self.valeur_residuelle / ((1 + taux_m) ** n)
        else:
            residu_actualise = self.valeur_residuelle

        montant_amorti = valeur_financement - residu_actualise
        if montant_amorti <= 0:
            self.versement_mensuel = 0.0
            return

        if taux_m == 0:
            versement_avant_taxe = montant_amorti / n
        else:
            versement_avant_taxe = montant_amorti * (taux_m / (1 - (1 + taux_m) ** -n))

        self.versement_mensuel = versement_avant_taxe * (1 + TAXE_TOTALE)


# ─── Moteur principal ─────────────────────────────────────────────────────────
class MoteurVersements:

    def __init__(self, db_path: str = 'hyundai_prospect.db'):
        self.db_path = db_path

    def chercher_programme(self, modele: str, version: str = None, annee: int = None) -> Optional[dict]:
        """Trouve le programme le plus récent pour un modèle/version."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        params = [f'%{modele.lower()}%']
        q = "SELECT * FROM programmes WHERE LOWER(modele) LIKE ?"
        if annee:
            q += " AND annee_modele=?"; params.append(annee)
        if version:
            q += " AND LOWER(version) LIKE ?"; params.append(f'%{version.lower()}%')
        q += " ORDER BY mois DESC, pdsf ASC LIMIT 1"
        c.execute(q, params)
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def lister_modeles(self) -> list[str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT DISTINCT annee_modele||' '||modele FROM programmes ORDER BY annee_modele DESC, modele")
        result = [r[0] for r in c.fetchall()]
        conn.close()
        return result

    def lister_versions(self, modele: str, annee: int = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        params = [f'%{modele.lower()}%']
        q = "SELECT * FROM programmes WHERE LOWER(modele) LIKE ?"
        if annee:
            q += " AND annee_modele=?"; params.append(annee)
        q += " ORDER BY mois DESC, pdsf ASC"
        c.execute(q, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def calculer_scenarios(self, prog: dict, terme_fin: int = 84,
                            terme_loc: int = 48, km_annuel: int = 20000,
                            mise_de_fonds: float = 0, fidelisation: bool = False) -> dict:
        """
        Calcule les scénarios financement et location pour un programme donné.
        Retourne un dict avec les deux scénarios.
        """
        modele_str = f"{prog.get('annee_modele','')} {prog.get('modele','')} {prog.get('version','')}"

        # Frais livraison
        frais_liv = FRAIS_LIVRAISON.get(prog.get('modele',''), FRAIS_LIVRAISON['default'])
        # Frais admin (VÉ si Ioniq ou Kona EV)
        est_ve = any(x in (prog.get('modele') or '') for x in ['Ioniq','IONIQ','Kona EV'])
        frais_admin = FRAIS_ADMIN_VE if est_ve else FRAIS_ADMIN_STANDARD

        # Taux financement selon terme
        taux_fin_map = {
            24: prog.get('taux_fin_24'), 36: prog.get('taux_fin_36'),
            48: prog.get('taux_fin_48'), 60: prog.get('taux_fin_60'),
            72: prog.get('taux_fin_72'), 84: prog.get('taux_fin_84'),
            96: prog.get('taux_fin_96'),
        }
        taux_fin = taux_fin_map.get(terme_fin) or prog.get('taux_fin_60') or 5.68

        # Taux location et résiduel selon terme
        taux_loc_map = {
            24: prog.get('taux_loc_24'), 33: prog.get('taux_loc_33'),
            36: prog.get('taux_loc_36'), 39: prog.get('taux_loc_39'),
            48: prog.get('taux_loc_48'), 60: prog.get('taux_loc_60'),
        }
        resid_map = {
            24: prog.get('resid_24'), 33: prog.get('resid_33'),
            36: prog.get('resid_36'), 39: prog.get('resid_39'),
            48: prog.get('resid_48'), 60: prog.get('resid_60'),
        }
        taux_loc = taux_loc_map.get(terme_loc) or prog.get('taux_loc_48') or 5.99
        resid = resid_map.get(terme_loc) or prog.get('resid_48') or 50.0

        rabais = (prog.get('rabais_comptant') or 0)
        if fidelisation:
            rabais += (prog.get('rabais_fidelite') or 0)

        sc_fin = ScenarioFinancement(
            modele_propose=modele_str,
            version_propose=prog.get('version',''),
            pdsf=prog.get('pdsf', 0),
            rabais=rabais,
            comptant_fin=prog.get('comptant_financement') or 0,
            taux_annuel=taux_fin,
            terme_mois=terme_fin,
            mise_de_fonds=mise_de_fonds,
            fidelisation=fidelisation,
            frais_admin=frais_admin,
            frais_livraison=frais_liv,
        )

        sc_loc = None
        if taux_loc and resid:
            sc_loc = ScenarioLocation(
                modele_propose=modele_str,
                version_propose=prog.get('version',''),
                pdsf=prog.get('pdsf', 0),
                rabais=rabais,
                comptant_loc=prog.get('comptant_location') or 0,
                taux_annuel=taux_loc,
                terme_mois=terme_loc,
                residu_pct=resid,
                km_annuel=km_annuel,
                mise_de_fonds=mise_de_fonds,
                fidelisation=fidelisation,
                frais_admin=frais_admin,
                frais_livraison=frais_liv,
            )

        return {'financement': sc_fin, 'location': sc_loc}

    def calculer_equite(self, client: VehiculeClient) -> dict:
        """
        Calcule l'équité du client (valeur vAuto - solde).
        Détermine le score d'opportunité (1-5).
        """
        equite = client.valeur_vauto - client.solde_financement
        annee_courante = 2026

        # Score d'opportunité (0-100)
        score = 0
        raisons = []

        # Age du véhicule
        age = annee_courante - client.annee
        if age >= 5:
            score += 30; raisons.append(f"Véhicule de {age} ans")
        elif age >= 3:
            score += 15; raisons.append(f"Véhicule de {age} ans")

        # Kilométrage
        if client.km >= 120000:
            score += 25; raisons.append(f"{client.km:,} km")
        elif client.km >= 80000:
            score += 15; raisons.append(f"{client.km:,} km")
        elif client.km >= 60000:
            score += 5

        # Équité positive
        if equite >= 5000:
            score += 30; raisons.append(f"Équité positive +${equite:,.0f}")
        elif equite >= 0:
            score += 15; raisons.append(f"Équité ~${equite:,.0f}")
        elif equite >= -3000:
            score += 5

        # Client Hyundai (fidélisation possible)
        if 'hyundai' in client.marque.lower():
            score += 10; raisons.append("Client Hyundai fidélisation possible")

        # Fin de contrat proche (si fourni)
        if client.fin_contrat:
            try:
                from datetime import datetime
                fin = datetime.strptime(client.fin_contrat, '%Y-%m')
                mois_restants = (fin.year - 2026) * 12 + (fin.month - 5)
                if 0 <= mois_restants <= 6:
                    score += 20; raisons.append(f"Contrat se termine dans {mois_restants} mois!")
                elif mois_restants < 0:
                    score += 25; raisons.append("Contrat terminé!")
            except:
                pass

        # Étoile (1-5)
        if score >= 80: etoiles = 5
        elif score >= 60: etoiles = 4
        elif score >= 40: etoiles = 3
        elif score >= 20: etoiles = 2
        else: etoiles = 1

        return {
            'equite': equite,
            'valeur_vauto': client.valeur_vauto,
            'solde': client.solde_financement,
            'score': score,
            'etoiles': etoiles,
            'raisons': raisons,
        }


# ─── Test rapide ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    moteur = MoteurVersements('hyundai_prospect.db')

    print("📋 Modèles disponibles:")
    for m in moteur.lister_modeles()[:10]:
        print(f"   {m}")

    # Test Elantra 2026
    prog = moteur.chercher_programme('Elantra', annee=2026)
    if prog:
        print(f"\n🚗 Test: {prog['annee_modele']} {prog['modele']} {prog['version']}")
        print(f"   PDSF: ${prog['pdsf']:,.0f} | Rabais: ${prog['rabais_comptant']:,.0f}")
        scenarios = moteur.calculer_scenarios(prog, terme_fin=84, terme_loc=48, km_annuel=20000)
        fin = scenarios['financement']
        loc = scenarios['location']
        print(f"   Financement 84m @ {fin.taux_annuel}%: ${fin.versement_mensuel:,.0f}/mois")
        if loc:
            print(f"   Location 48m @ {loc.taux_annuel}% (résid {loc.resid_pct}%): ${loc.versement_mensuel:,.0f}/mois")

    # Test équité client
    client = VehiculeClient(
        annee=2021, marque='Hyundai', modele='Elantra',
        km=85000, valeur_vauto=12500, solde_financement=8000,
        type_contrat='financement'
    )
    equite = moteur.calculer_equite(client)
    print(f"\n👤 Test client 2021 Elantra 85,000 km:")
    print(f"   Équité: ${equite['equite']:,.0f} | Score: {equite['score']}/100 | ⭐ {equite['etoiles']}/5")
    print(f"   Raisons: {', '.join(equite['raisons'])}")
