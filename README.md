# kindle-panel

Pannello e-ink a basso consumo per Home Assistant su un **Kindle 4 Non-Touch** jailbroken.

Il Kindle esce a intervalli dalla sospensione in RAM e scarica in HTTPS autenticato un PNG generato da un gateway sulla LAN. Ridisegna lo schermo solo se l'immagine è cambiata, poi torna a dormire.

```
Kindle 4 NT (fork kindle-dash, shell + xh)
   │  HTTPS (cert self-signed, CA fissata sul Kindle) + Bearer token del Kindle
   │  solo LAN, via nome host
   ▼
kindle-gateway (container Python sull'home server)
   │  REST API di HA (solo GET /api/states/<id>) con token di un utente HA non admin
   ▼
Home Assistant (container)
```

- Il gateway legge **solo** le entità elencate in `config.yaml` e disegna l'immagine da sé con Pillow. Non usa browser headless né screenshot di Lovelace.
- Il token di HA non lascia mai il server.
- `/kindle.png` risponde solo con il token del Kindle. `/healthz` non è autenticato e restituisce solo `ok`. Non c'è nessun altro endpoint, nemmeno `/docs` o `/openapi.json`.
- **Il servizio NON va aggiunto alla configurazione di cloudflared** né esposto fuori dalla LAN in altro modo.

Struttura del repo:
- `gateway/`: il gateway (FastAPI, Pillow, httpx);
- `kindle/`: fork vendorizzato di [pascalw/kindle-dash](https://github.com/pascalw/kindle-dash). Le modifiche sono descritte in [`kindle/UPSTREAM.md`](kindle/UPSTREAM.md).

---

## Perché un nome host e non l'IP

Lo `xh` incluso in kindle-dash (0.16.1, rustls) **non riesce a fare HTTPS verso un indirizzo IP**. L'errore è `invalid dnsname`; i dettagli sono in [`kindle/UPSTREAM.md`](kindle/UPSTREAM.md). Serve quindi un **nome host** che il DNS della tua LAN (router, Pi-hole, …) risolva nell'IP del server, per esempio `homeserver.lan`.

- I nomi mDNS `.local` non funzionano: `xh` è un binario statico musl, che risolve solo tramite DNS e `/etc/hosts`.
- Prima di iniziare, verifica da un PC sulla LAN: `nslookup <NOME_HOST>` deve restituire l'IP del server.

---

## 1. Gateway (home server)

### Utente e token di Home Assistant

1. In HA crea un utente dedicato **non amministratore**: *Impostazioni → Persone → Aggiungi persona*, con l'accesso abilitato e "Amministratore" disattivato.
2. Accedi a HA con quell'utente e crea un token: *Profilo → Token di accesso a lunga durata → Crea token*.

### Configurazione

Tutti i comandi partono da `gateway/`:

```sh
cd gateway

# Entità da mostrare (quelle di esempio sono segnaposto)
cp config.example.yaml config.yaml
$EDITOR config.yaml

# Secrets: mai nel repo (secrets/ è in .gitignore)
(umask 077 && mkdir -p secrets)
$EDITOR secrets/ha_token                       # incolla il token HA su una riga
openssl rand -hex 32 > secrets/kindle_token    # KINDLE_TOKEN
chmod 644 secrets/ha_token secrets/kindle_token

# CA + certificato server (SAN=DNS:<NOME_HOST>, più IP:<IP_LAN> se indicato)
./scripts/gen-certs.sh <NOME_HOST> <IP_LAN>

# Compose: indica la rete Docker del container di HA
cp compose.example.yaml compose.yaml
$EDITOR compose.yaml
docker compose up -d --build
```

Dettagli:
- **`config.yaml`:**
  - l'ordine di `rows` è l'ordine sullo schermo;
  - `ha_url` è `http://homeassistant:8123` se il gateway sta sulla rete Docker di HA, altrimenti `http://<IP_LAN>:8123`. Se HA usa `network_mode: host`, segui il commento in `compose.example.yaml`.
- **`secrets/` e `certs/`:**
  - le cartelle sono private (700);
  - i file montati nel container sono 644, perché il container gira con un utente non root (UID 10001). `ca.key` resta 600 e non viene mai montata;
  - i secrets si possono passare anche come variabili d'ambiente (`HA_TOKEN`, `KINDLE_TOKEN`) invece che come file (`HA_TOKEN_FILE`, `KINDLE_TOKEN_FILE`), ma non entrambi.
- **`gen-certs.sh`:**
  - genera `ca.key`/`ca.pem` e `server.key`/`server.pem`, entrambi validi 10 anni;
  - se `ca.key`/`ca.pem` esistono già li riusa e rigenera solo il certificato server, così il Kindle continua a funzionare senza ricopiare `ca.pem`.
- **Porta 8443:** `compose.example.yaml` la pubblica su tutte le interfacce del server. Per ascoltare solo sull'IP LAN usa `"<IP_LAN>:8443:8443"`.
- **Modifiche a `config.yaml`:** dopo ogni modifica esegui `docker compose restart`.

### Prova locale

Con `T=$(cat secrets/kindle_token)`:

```sh
# Con CA e token: 200 e un PNG 600x800 in scala di grigi
curl --cacert certs/ca.pem -H "Authorization: Bearer $T" https://<NOME_HOST>:8443/kindle.png -o out.png
# Senza token: 401
curl --cacert certs/ca.pem -o /dev/null -w '%{http_code}\n' https://<NOME_HOST>:8443/kindle.png
# Con -k (senza CA) ma con token: funziona comunque. Il pinning si verifica sul Kindle
curl -k -H "Authorization: Bearer $T" https://<NOME_HOST>:8443/kindle.png -o /dev/null -w '%{http_code}\n'
```

Apri `out.png` e controlla a occhio il risultato. Se hai passato `<IP_LAN>` a `gen-certs.sh`, curl funziona anche con `https://<IP_LAN>:8443`, ma il Kindle deve usare il nome host.

Se HA è irraggiungibile, o rifiuta il token, il gateway risponde **503** e il Kindle mantiene l'immagine precedente.

---

## 2. Kindle

Prerequisiti:
- Kindle 4 NT jailbroken con KUAL;
- Wi-Fi **già configurato e attivo** (WPA2, 2,4 GHz) prima dell'avvio;
- facoltativo: SSH (USBNetwork) per il debug.

### Preparazione dei file

```sh
cd kindle

# File per dispositivo (in .gitignore): CA del gateway e token del Kindle
cp ../gateway/certs/ca.pem src/local/ca.pem
cp ../gateway/secrets/kindle_token src/local/token

# Obbligatori: IP del server (per il ping Wi-Fi) e URL del gateway con il NOME HOST
$EDITOR src/local/env.sh     # WIFI_TEST_IP="<IP_LAN>"  GATEWAY_URL="https://<NOME_HOST>:8443"

make dist
```

`make dist` scarica il tarball della release upstream `v1.0.0-beta.4` e ne estrae `xh` e `next-wakeup`, già compilati per ARM, verificandone gli sha256. Richiede `curl`, `tar` e `sha256sum`; su macOS usa `make dist SHA256SUM="shasum -a 256"`.

Gli altri default in `env.sh`:
- `TIMEZONE="Europe/Rome"`;
- `REFRESH_SCHEDULE="*/15 7-23 * * *"`, cioè ogni 15 minuti dalle 7 alle 23. Di notte appare la schermata "sleeping";
- `FULL_DISPLAY_REFRESH_RATE=4`.

### Installazione

1. Collega il Kindle via USB (modalità archivio di massa).
2. Copia il **contenuto** di `kindle/dist/` in `dashboard/` sul Kindle, cioè `/mnt/us/dashboard/`.
3. Copia `kindle/KUAL/kindle-dash/` in `extensions/kindle-dash/` sul Kindle, cioè `/mnt/us/extensions/kindle-dash/`.
4. Scollega il Kindle e avvia da KUAL: *Kindle dashboard → Avvia dashboard*.
5. Il dispositivo va in sospensione dopo circa 10–15 secondi.

Per aggiornare, ricopia `dist/`.

### Uscire dal dashboard

Il dashboard ferma il framework Amazon. Finché è attivo, quindi, **non funzionano né la modalità USB né KOReader**.

- **Hard reboot:** tieni premuto il tasto di accensione per circa 20 secondi. Al riavvio il Kindle torna normale.
- **Via SSH:** `/mnt/us/dashboard/stop.sh` seguito da `reboot`.
- **Voce KUAL "Ferma dashboard e riavvia":** funziona solo mentre il framework è attivo. Dopo un avvio normale il framework è fermo e KUAL non è raggiungibile.

### Log

`/mnt/us/dashboard/logs/dash.log` riporta a ogni ciclo data e livello batteria: serve a stimare l'autonomia.

| Messaggio | Significato |
|---|---|
| `Partial screen refresh` / `Full screen refresh` | Nuova immagine disegnata |
| `Dashboard image unchanged` + `Not updating screen, fetch-dashboard returned 2` | Dati invariati, schermo non ridisegnato |
| `Fetch failed, xh returned N` + `... returned 1` | Download fallito, resta l'immagine precedente. `N`: 1 = connessione/TLS/DNS, 2 = timeout, 4 = HTTP 4xx (401: token errato), 5 = HTTP 5xx (503: il gateway non raggiunge HA) |
| `Missing configuration: ...` | Mancano `GATEWAY_URL`, `local/token` o `local/ca.pem` |
| `Couldn't connect to Wi-Fi` / `No test ip specified` | Il ping verso `WIFI_TEST_IP` fallisce, oppure `WIFI_TEST_IP` è vuoto |

Errori di `xh` da riconoscere:

| Errore | Causa |
|---|---|
| `invalid dnsname` | In `GATEWAY_URL` c'è un IP: va usato il nome host |
| `failed to lookup address information` | Il DNS della LAN non risolve il nome host |
| `UnknownIssuer` | `local/ca.pem` non è la CA che ha firmato il certificato del gateway |
| `CertNotValidForName` | Il nome in `GATEWAY_URL` non è nel SAN del certificato |
| `CertNotValidYet` / `CertExpired` | Probabilmente l'orologio del Kindle è sbagliato (vedi sotto) |

### Orologio

Dopo la fine del supporto Amazon l'ora del Kindle potrebbe non sincronizzarsi più. Verificala con le date nel log. L'ora conta per due motivi:
- la pianificazione `REFRESH_SCHEDULE` dipende dall'ora;
- la validazione TLS fallisce se l'orologio è fuori dal periodo di validità del certificato.

Se l'ora deriva, il passo previsto per la v1.1 è impostarla dall'header `Date` del gateway; per ora la cosa è solo documentata.

### Debug

Via SSH: `DEBUG=true /mnt/us/dashboard/start.sh`. Gira in primo piano con `set -x` e usa `sleep` al posto della sospensione.

---

## 3. Verifica sul dispositivo

- [ ] Copia via USB e avvio da KUAL.
- [ ] Un ciclo con `DEBUG=true`, se c'è SSH; altrimenti leggere il log dopo un ciclo.
- [ ] Il primo disegno avviene.
- [ ] Un ciclo successivo con dati invariati non ridisegna (`Not updating screen` nel log).
- [ ] Cambiando un'entità in HA, lo schermo si aggiorna al ciclo successivo.
- [ ] Sospensione e risveglio RTC funzionano.
- [ ] Livello batteria registrato per 24 ore.
- [ ] L'ora del Kindle è corretta (`date` nel log).

---

## Sviluppo

```sh
# Test del gateway (HA simulato con respx)
cd gateway
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Script del Kindle: shellcheck -s ash + shfmt -i 2, come nella CI upstream
cd kindle && make lint
```

## Note sul rendering

- **Immagine:** 600×800, modalità `L` (8 bit, scala di grigi, senza alpha), font DejaVu Sans, nero su bianco. Il testo è antialiasato, quindi ci sono grigi solo sui bordi dei caratteri.
- **Determinismo:** l'immagine dipende solo dai dati, così il Kindle può saltare il refresh:
  - non riporta l'ora di render: "dati del HH:MM" è il `last_changed` più recente tra le entità, nel `timezone` configurato;
  - la batteria è arrotondata a passi del 5%.
- **Valori:** formato grezzo di HA:
  - numeri sempre a 1 decimale con il punto (`45` diventa `45.0`), con unità `unit_of_measurement`. `display_precision` non è disponibile da `GET /api/states/<id>`: sta nel registro entità, non negli attributi;
  - `weather.*`: mostra lo stato come arriva da HA (es. `cloudy`) più l'attributo `temperature`;
  - entità mancanti, in errore, `unavailable` o `unknown` appaiono come `—`.
- **`last_changed` e meteo:** `last_changed` cambia solo quando cambia lo stato. Per un'entità `weather` che aggiorna solo la temperatura (un attributo), l'ora "dati del" non si sposta.
