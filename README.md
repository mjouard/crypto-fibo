# Plan Fibonacci crypto

Application locale qui affiche, pour BTC, ETH, SOL, LINK, AAVE et TAO :
- les zones d'achat Fibonacci (−50 %, −61,8 %, −78,6 % sous l'ATH) et de vente (retour à l'ATH, extensions 1,272, 1,618, 2,618), passées et à venir ;
- les « points d'or » (entrées et sorties exceptionnelles du radar d'opportunités) ;
- le résultat de la stratégie Fibonacci appliquée avec 10 000 $.

À chaque ouverture (au plus toutes les 6 heures), l'application récupère les dernières clôtures journalières
sur l'API publique de Binance (Kraken en secours), les ajoute aux fichiers `data/*.csv`, puis recalcule tout.
Aucune clé d'API n'est nécessaire.

## Installation (une seule fois)

Il faut Python 3.10 ou plus récent.

**Mac / Linux**
```
cd crypto-fibo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows**
```
cd crypto-fibo
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Lancement

```
streamlit run app.py
```
L'application s'ouvre dans le navigateur (http://localhost:8501).
Sur Mac, tu peux aussi double-cliquer sur `lancer.command` ; sur Windows, sur `lancer.bat`.

## Mettre à jour les données sans ouvrir l'application

```
python data_update.py
```

## Fichiers

- `app.py` : interface Streamlit.
- `core.py` : calculs (cycles, stratégie, radar BTC, points d'or des altcoins).
- `data_update.py` : récupération des cours récents.
- `data/` : historique des clôtures journalières (BTC depuis 2010) et données on-chain BTC.

## Limites

- Les données on-chain BTC (MVRV, Puell) viennent de Coin Metrics et s'arrêtent au 23 mai 2026 ;
  au-delà, la capitalisation réalisée est prolongée par sa tendance. Le score BTC perd donc un peu en précision avec le temps.
- Les cours récents sont en USDT (Binance) : écart négligeable avec l'USD.
- Les seuils des points d'or ont été calés sur l'historique : les résultats passés sont optimistes.
- Ce n'est pas un conseil d'investissement.

## Mise en production sur Railway

Streamlit a besoin d'un serveur qui tourne en continu : Railway convient, Vercel non.

1. Mets le dossier `crypto-fibo` dans un dépôt GitHub (privé de préférence).
2. Sur Railway : **New Project → Deploy from GitHub repo**, choisis le dépôt.
   Railway détecte Python via `requirements.txt` et utilise la commande de `railway.json`.
3. Dans **Settings → Deploy → Region**, choisis une région **Europe** : l'API de Binance refuse les requêtes venant des États-Unis
   (l'app basculerait alors sur Kraken, qui fonctionne partout, mais c'est plus lent).
4. Dans **Variables**, ajoute `APP_PASSWORD` avec le mot de passe de ton choix : l'app demandera ce mot de passe à l'ouverture.
5. Dans **Settings → Networking**, clique sur **Generate Domain** pour obtenir l'adresse publique.

Les fichiers `data/*.csv` du dépôt servent de point de départ. À chaque redéploiement, l'app repart de ces fichiers
et récupère tout seule les jours manquants. Pas besoin de volume. Pour éviter un rattrapage trop long,
tu peux de temps en temps lancer `python data_update.py` en local et pousser les CSV mis à jour sur GitHub.

## Alertes e-mail (GitHub Actions, gratuit)

`alerts.py` tourne chaque jour vers 8 h (heure de Paris) grâce à `.github/workflows/alerts.yml`. Il :
1. récupère les derniers cours et recalcule tout ;
2. envoie un e-mail si, depuis la veille, une zone d'achat ou de vente Fibonacci a été touchée,
   si le prix est à moins de 5 % d'un niveau (une seule fois par niveau), si un nouvel ATH démarre un cycle,
   ou si un point d'or (entrée ou sortie) s'allume ;
3. enregistre les données à jour dans le dépôt (ce qui redéploie aussi l'app Streamlit avec des données fraîches).

Configuration, dans le dépôt GitHub → **Settings → Secrets and variables → Actions** :
- Secrets : `SMTP_USER` (ton adresse Gmail), `SMTP_PASSWORD` (un **mot de passe d'application** Gmail, pas ton mot de passe habituel),
  `MAIL_TO` (l'adresse qui reçoit les alertes). Optionnel : `SMTP_HOST`, `SMTP_PORT` pour un autre fournisseur (défaut Gmail, port 465).
- Variable (onglet Variables) : `APP_URL` = l'adresse de ton app Streamlit, pour avoir un lien dans l'e-mail.

Le premier passage envoie un e-mail « Alertes activées » avec l'état actuel. Pour le lancer tout de suite :
onglet **Actions → Alertes Plan Fibonacci → Run workflow**.

Test en local sans envoyer d'e-mail : `DRY_RUN=1 python alerts.py`.
