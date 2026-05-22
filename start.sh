#!/bin/bash
echo "📦 Installation de Chromium..."
playwright install chromium
playwright install-deps chromium
echo "✅ Chromium installé"
echo "🚀 Démarrage de l'application..."
python app.py &
python scheduler.py
