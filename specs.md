# GPTKit — Specification du module WHOIS

Ce document définit **la version propre et finale** du module WHOIS de **GPTKit**, en repartant de zéro.  
Aucun code, aucune technologie imposée : uniquement le **contrat**, le **comportement**, et les **contraintes**.

GPTKit est destiné **exclusivement** à être utilisé via un **Custom GPT web** (Actions HTTP / OpenAPI).

---

# 1. Concept global — GPTKit

GPTKit est un **backend unique**, organisé en *namespaces*, destiné à regrouper plusieurs outils consommables par un Custom GPT via des Actions HTTP.

Namespaces prévus :
- `/domain/*` — outils liés aux domaines (WHOIS, DNS, HTTP check, SSL…)
- `/seo/*` — outils SEO (futur)
- `/utils/*` — utilitaires divers (futur)

## Contraintes générales
- Un **seul service HTTP**, un seul host/port.
- **JSON uniquement** en réponse.
- Pas de HTML, pas de streaming, pas de WebSocket.
- Endpoints **idempotents** pour les lectures (GET).
- Chaque endpoint doit être **simple à décrire dans OpenAPI**.

---

# 2. Module WHOIS — Aperçu

Le module WHOIS fournit **un seul endpoint** permettant :
- une lookup WHOIS fiable
- une détermination simple de disponibilité
- un cache persistant
- un contrôle du rate limiting
- un comportement déterministe pour GPT

Ce module est exposé sous :
```
GET /domain/whois
```

---

# 3. API WHOIS — Détails complets

## 3.1. Paramètres (query)

### `domain` (string, requis)
- Doit contenir un domaine complet : `example.com`, `monsite.fr`, etc.
- Doit contenir au moins un `.`.
- Exemples invalides : `habitatleger`, `domain`, `test`.

### `force` (integer, optionnel, défaut = 0)
- `0` : utiliser le cache si existant.
- `1` : ignorer le cache et exécuter un WHOIS frais.

---

## 3.2. Logique interne

### Étape 1 — Validation
- Vérifier la présence de `domain`.
- Vérifier qu’il contient au moins un `.`.
- Extraire le TLD comme la sous-chaîne après le dernier `.`.

### Étape 2 — Cache persistant
- Si `domain` est dans le cache ET `force != 1` :
  - Retourner immédiatement le contenu du cache.
  - **Aucun rate limiting appliqué**.
  - **Aucun WHOIS exécuté**.

### Étape 3 — Rate limiting (si WHOIS requis)
- Appliquer un **rate limit global** (ex : par minute / par heure).
- Appliquer un **rate limit par domaine** (anti-spam via `force=1`).
- En cas de dépassement : renvoyer **HTTP 429**.

### Étape 4 — Exécution WHOIS
- Exécuter **une seule** commande WHOIS système.
- Timeout strict recommandé (ex : 5s).
- Ne jamais re-tenter automatiquement.

### Étape 5 — Détermination disponibilité
Patterns minimaux :
- `.com` : "No match", "NOT FOUND"
- `.fr` : "Status: FREE", "No entries found"
- autres TLD : variantes similaires ("NOT FOUND", etc.)

Si match → `available = true`
Sinon → `available = false`

### Étape 6 — Mise à jour du cache
- Écraser l’entrée précédente.
- Stocker `domain`, `tld`, `available`, `checked_at`, `raw`.

### Étape 7 — Réponse JSON
- Retourner la réponse formelle décrite ci-dessous.

---

# 4. Réponse (succès)

```json
{
  "domain": "example.com",
  "tld": "com",
  "available": true,
  "checked_at": "2025-01-01T12:00:00Z",
  "raw": "raw whois output here..."
}
```

Signification :
- `domain` : domaine demandé
- `tld` : TLD extrait
- `available` : booléen basé sur patterns
- `checked_at` : timestamp ISO-8601 UTC
- `raw` : WHOIS brut (tronqué si nécessaire)

---

# 5. Réponses d’erreur

## 400 — domaine invalide
```json
{
  "error": "invalid_domain",
  "message": "Domain must include a TLD (example: site.com)."
}
```

## 429 — rate limit
```json
{
  "error": "rate_limited",
  "message": "WHOIS rate limit exceeded."
}
```

## 500 — WHOIS / interne
```json
{
  "error": "whois_error",
  "message": "WHOIS lookup failed or timed out."
}
```

---

# 6. Cache — Spécification

Propriétés :
- **Persistant** entre redémarrages.
- Pas d’expiration automatique.
- **Jamais** utilisé si `force = 1`.
- Format interne suggéré :

```
{
  "domain": "example.com",
  "tld": "com",
  "available": true,
  "checked_at": "...",
  "raw": "..."
}
```

- Les lectures depuis le cache **n’utilisent pas le rate limit**.

---

# 7. Rate Limiting — Spécification

S’applique **uniquement** lorsqu’un WHOIS doit être exécuté.

## Deux niveaux :

### 1. Rate limit global
- Ex : nombre max WHOIS/minute ou WHOIS/heure.
- Valeurs exactes à définir côté implémentation.

### 2. Rate limit par domaine
- Empêche l’abus de `force=1`.

## En cas de dépassement :
- Retourner HTTP `429` + JSON.
- Ne pas exécuter WHOIS.

---

# 8. Intégration dans GPTKit

WHOIS devient l’un des modules de :
```
/domain/whois
/domain/dns      (futur)
/domain/http     (futur)
/domain/ssl      (futur)
```

Les Custom GPT web pourront déclarer **plusieurs Actions HTTP**, chacune ciblant une partie des endpoints de GPTKit.

---

# 9. Non-objectifs

Ne pas implémenter dans ce module :

- résolution DNS
- batch WHOIS
- scan multi-TLD
- UI / HTML
- streaming / websockets
- jobs automatiques
- authentification
- interactions registrar

---

# 10. Résumé final

- Endpoint : `GET /domain/whois`
- Params : `domain` (requis), `force` (optionnel)
- Cache persistant + rate limiting seulement si WHOIS exécuté
- JSON propre et stable
- Compatible OpenAPI / Actions Custom GPT
- Module strictement délimité, prêt à être implémenté

