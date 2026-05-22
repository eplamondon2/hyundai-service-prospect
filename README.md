# 🚗 Service Prospect — Hyundai St-Raymond

Outil de prospection service-ventes pour identifier les clients en position avantageuse pour changer de véhicule.

---

## 📦 Structure du projet

```
hyundai_service_prospect/
├── app.py                    ← Dashboard web (Flask)
├── parser_programme.py       ← Extraction PDF programme Hyundai
├── calcul_versements.py      ← Moteur de calcul financement/location
├── hyundai_prospect.db       ← Base de données SQLite (créée automatiquement)
└── README.md
```

---

## 🚀 Installation & démarrage

### 1. Installer les dépendances
```bash
pip install flask pdfplumber
```

### 2. Importer le programme Hyundai du mois
```bash
python parser_programme.py Programme.pdf 2026-05
```
→ Extrait les 90+ versions (PDSF, rabais, taux, résiduels) dans la base SQLite.
→ À refaire chaque 1er du mois avec le nouveau PDF.

### 3. Lancer le dashboard
```bash
python app.py
```
→ Accès: http://localhost:5000

---

## 📋 Workflow mensuel

### Début du mois
1. Recevoir le nouveau PDF programme Hyundai
2. `python parser_programme.py Programme_AAAA-MM.pdf AAAA-MM`

### Chaque semaine (ou quotidiennement)
1. Dans vAuto → Stock → Service Appointments → Export CSV
2. Dashboard → Import → Coller ou uploader le CSV
3. Les clients sont automatiquement scorés (⭐ 1-5)

### Avant chaque journée de service
1. Dashboard → Tableau de bord → voir les ⭐⭐⭐⭐⭐
2. Cliquer sur chaque fiche → entrer la valeur vAuto (après évaluation)
3. Entrer le solde de financement (DealerTrack ou portail Hyundai)
4. Le calculateur génère les versements financement ET location
5. Mettre à jour le statut (contacté / vendu / pas intéressé)

---

## 🧮 Calculs

### Financement
```
Prix avant taxe = PDSF - Rabais - Comptant fin + Frais admin + Livraison
Montant financé = Prix avant taxe × 1.14975 (TPS+TVQ)
Versement = Montant × (i / (1 - (1+i)^-n))
```

### Location
```
Valeur résiduelle = PDSF × Résiduel%
Versement avant taxe = (Prix - Résid actualisé) × facteur_location
Versement TTC = Versement avant taxe × 1.14975
```

### Équité estimée
```
Équité = Valeur vAuto - Solde de financement
```

### Score d'opportunité (0-100 → ⭐ 1-5)
| Critère | Points |
|---------|--------|
| Véhicule ≥ 5 ans | +30 |
| Véhicule 3-4 ans | +15 |
| KM ≥ 120,000 | +25 |
| KM 80-120k | +15 |
| Équité ≥ 5,000$ | +30 |
| Équité ≥ 0$ | +15 |
| Client Hyundai (fidélisation) | +10 |
| Contrat se termine ≤ 6 mois | +20 |
| Contrat terminé | +25 |

---

## 📂 Format CSV Import

```csv
Date,Heure,Nom,Telephone,Email,Annee,Marque,Modele,Version,VIN,KM
05/22/2026,08:30,Jean Tremblay,(418) 555-1234,,2021,Hyundai,Elantra,Preferred,KM8ABC123456,78000
```

---

## 🔜 Prochaines étapes suggérées

- [ ] Scraping automatique vAuto (Playwright) pour récupérer les évaluations
- [ ] Intégration DealerTrack (solde financement)
- [ ] Portail Hyundai SFHM (fin de location)
- [ ] Export liste d'appels pour BDC
- [ ] Envoi SMS/email automatique aux clients ciblés
- [ ] Lier l'inventaire disponible aux fiches clients

---

## ⚠️ Notes importantes

- Les versements sont **estimatifs** — le F&I confirme les chiffres exacts
- Taxes Québec: TPS 5% + TVQ 9.975% = **14.975%**
- Frais admin max: **799$** (ICE/HEV) | **599$** (VÉ/PHEV)
- Programme Hyundai valide: **1 mai 2026 au 1 juin 2026**
- Le financement 60/84 mois n'est **pas offert au Québec**
