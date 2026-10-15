# kindle-panel

Pannello e-ink a basso consumo per Home Assistant su un **Kindle 4 Non-Touch** jailbroken.

Il Kindle esce a intervalli dalla sospensione in RAM e scarica in HTTPS autenticato un PNG generato da un gateway sulla LAN. Ridisegna lo schermo solo se l'immagine è cambiata, poi torna a dormire.

Il PNG mostra una **plancia di Home Assistant** scelta per URL (modalità `dashboard`) oppure un elenco fisso di entità (modalità `rows`).

```
Kindle 4 NT (fork kindle-dash, shell + xh)
   │  HTTPS (cert self-signed, CA fissata sul Kindle) + Bearer token del Kindle
   │  solo LAN, via nome host (mappato in /etc/hosts del Kindle)
   ▼
kindle-gateway (container Python sull'home server)
   │  token di un utente HA non admin, solo letture:
   │   - dashboard: WebSocket API (lovelace/config, home_tasks/get_lists, home_tasks/get_tasks)
   │                + GET /api/states/person.* per i nomi delle persone assegnate
   │   - rows:      GET /api/states/<id> delle entità elencate
   ▼
Home Assistant (container)
```

- Il gateway disegna l'immagine da sé con Pillow, a partire dai dati. Non usa browser headless né screenshot di Lovelace.
- In modalità `dashboard` legge la configurazione della plancia e i dati delle sole card supportate (vedi [Modalità dashboard](#modalità-dashboard)). In modalità `rows` legge **solo** le entità elencate in `config.yaml`.
- Il token di HA non lascia mai il server.
- `/kindle.png` risponde solo con il token del Kindle. `/healthz` non è autenticato e restituisce solo `ok`. Non c'è nessun altro endpoint, nemmeno `/docs` o `/openapi.json`.
- **Il servizio NON va aggiunto alla configurazione di cloudflared** né esposto fuori dalla LAN in altro modo.

Struttura del repo:
- `gateway/`: il gateway (FastAPI, Pillow, httpx);
- `kindle/`: fork vendorizzato di [pascalw/kindle-dash](https://github.com/pascalw/kindle-dash). Le modifiche sono descritte in [`kindle/UPSTREAM.md`](kindle/UPSTREAM.md).

---

## Dove stanno i file

Il repo contiene solo codice ed esempi. I file del singolo impianto (certificati, token, configurazione, IP) sono **ignorati da git** e vivono in un **repo separato dei secret**, per esempio `kindle-panel-secrets`. Quel repo ricalca gli stessi percorsi relativi di questo, come descritto in [Repo dei secret](#repo-dei-secret).

| File (percorso nel repo) | Contenuto | Serve su |
|---|---|---|
| `gateway/config.yaml` | Plancia (o entità) da mostrare, `ha_url`, lingua, fuso orario | server |
| `gateway/compose.yaml` | Compose dell'impianto (rete, porte) | server |
| `gateway/secrets/ha_token` | Token di HA dell'utente dedicato | server |
| `gateway/secrets/kindle_token` | Token con cui il Kindle si autentica | server |
| `gateway/certs/server.pem`, `server.key` | Certificato TLS del gateway | server |
| `gateway/certs/ca.pem`, `ca.key` | CA privata che firma il certificato | dove si generano i certificati (`ca.key` non va mai montata) |
| `kindle/src/local/ca.pem` | Copia di `gateway/certs/ca.pem` | build del Kindle |
| `kindle/src/local/token` | Copia di `gateway/secrets/kindle_token` | build del Kindle |
| `kindle/src/local/device.sh` | `WIFI_TEST_IP` e `GATEWAY_URL` | build del Kindle |

---

## Perché un nome host e non l'IP

Lo `xh` incluso in kindle-dash (0.16.1, rustls) **non riesce a fare HTTPS verso un indirizzo IP** (errore `invalid dnsname`) e non ha l'opzione `--resolve`; i dettagli sono in [`kindle/UPSTREAM.md`](kindle/UPSTREAM.md). Serve quindi un **nome host**, e `xh` è un binario statico musl che lo risolve solo tramite DNS o `/etc/hosts`, senza mDNS.

Non serve alcun record DNS. All'avvio del dashboard, `setup-hosts.sh` aggiunge al Kindle la voce `<WIFI_TEST_IP> <nome host di GATEWAY_URL>` in `/etc/hosts`:
- riapre in scrittura il filesystem di sistema, che è in sola lettura, solo se la voce manca o è diversa;
- scrive l'esito in `logs/dash.log`;
- usa solo costrutti di shell base, perché il busybox del K4 è molto vecchio (per esempio non supporta `grep -x`).

Il nome può quindi essere qualsiasi, anche `.local` (per esempio `kindle-gateway.local`), purché coincida con quello passato a `gen-certs.sh`. Va bene anche un nome già risolto dal DNS della LAN: la voce in `/etc/hosts` punterà comunque a `WIFI_TEST_IP`.

---

## Installazione

Le istruzioni usano questi segnaposto, da sostituire con i tuoi valori:

| Segnaposto | Significato | Esempio |
|---|---|---|
| `<IP_SERVER>` | IP LAN dell'home server, meglio se statico o riservato nel DHCP | `192.168.1.4` |
| `<NOME_HOST>` | Nome con cui il Kindle raggiunge il gateway | `kindle-gateway.local` |
| `<SERVER>` | Destinazione SSH del server | `utente@192.168.1.4` |

### 0. Prerequisiti

**Kindle 4 NT jailbroken con KUAL funzionante.** Su un K4 con firmware 4.1.4 l'ordine che ha funzionato è questo. Tutti i pacchetti sono di NiLuJe, nel thread [Snapshots](https://www.mobileread.com/forums/showthread.php?t=225030) su MobileRead.
1. **Jailbreak:** `kindle-k4-jailbreak-1.8.N`. Copia `data.tar.gz`, `ENABLE_DIAGS` e `diagnostic_logs/` nella radice del Kindle e riavvia. In modalità diagnostica scegli *D) Exit, Reboot or Disable Diags → R) Reboot System → Q) To continue*. Al riavvio compare la schermata del jailbreak.
2. **MKK:** `kindle-mkk-20141129`, file `Update_mkk-20141129-k4-ALL_install.bin`. Copialo nella radice e vai su *Menu → Impostazioni → Menu → Aggiorna il Kindle*.
3. **DevCerts 2025:** il certificato con cui è firmato KUAL è scaduto ad aprile 2025. Installa `Update_mkk-20250419-k4-ALL_keystore-install.bin` dal [post di NiLuJe](https://www.mobileread.com/forums/showpost.php?p=4506164) (`DevCerts-20250419-KeyStore.zip`), sempre con *Aggiorna il Kindle*. Senza questo passo KUAL dà "Elemento non firmato da uno sviluppatore autorizzato".
4. **KUAL:** copia `KUAL-KDK-1.0.azw2` in `documents/`. Sul K4 non va usata la versione "Booklet".

Se un aggiornamento fallisce subito e KUAL dice "Mobileread Kindlet Kit is not installed", controlla che `/var/local/java/keystore/developer.keystore` non sia immutabile (`lsattr`, poi `chattr -i`). Un tentativo di jailbreak precedente può averlo bloccato.

**Kindle in rete:** Wi-Fi configurato e attivo (WPA2, 2,4 GHz). Il Kindle deve poter raggiungere `<IP_SERVER>`.

**Server:** Docker con il plugin compose, Home Assistant raggiungibile dal server e la porta 8443 libera.

**PC per la build:** `git`, `make`, `curl`, `tar`, `sha256sum`, `openssl` e `rsync`. Su macOS usa `make dist SHA256SUM="shasum -a 256"`.

### 1. Utente e token di Home Assistant

1. In HA crea un utente dedicato **non amministratore**: *Impostazioni → Persone → Aggiungi persona*, con l'accesso abilitato e "Amministratore" disattivato.
2. Esci, accedi con quell'utente e crea un token: *Profilo → Sicurezza → Token di accesso a lunga durata → Crea token*. Copialo subito, HA non lo mostra più.

I token di HA danno tutti i permessi dell'utente: per questo l'utente è dedicato e non admin, e il token resta sul server.

Cosa può fare questo token, verificato su HA 2026.6.0:
- **può** leggere la configurazione di **tutte** le plance, anche quelle con "Solo amministratori": `require_admin` nasconde la plancia solo dalla barra laterale, non la protegge da `lovelace/config`;
- **non può** modificare le plance: `lovelace/config/save` risponde `unauthorized`;
- come ogni utente HA, anche non admin, può chiamare servizi. Il gateway però non lo fa mai: invia solo i comandi di lettura elencati sopra, e il codice rifiuta gli altri prima che partano.

### 2. Repo dei secret (sul PC)

Se il repo dei secret esiste già, clonalo accanto a questo e passa al punto 3. Altrimenti crealo da zero:

```sh
git clone https://github.com/<utente>/kindle-panel.git
mkdir kindle-panel-secrets && cd kindle-panel-secrets && git init
mkdir -p gateway kindle/src/local
(umask 077 && mkdir -p gateway/secrets)

# Certificati: CA privata + certificato server con SAN=DNS:<NOME_HOST> (+ IP per i test con curl)
CERTS_DIR=gateway/certs sh ../kindle-panel/gateway/scripts/gen-certs.sh <NOME_HOST> <IP_SERVER>

# Token: quello di HA (incollalo su una riga) e quello del Kindle (casuale)
$EDITOR gateway/secrets/ha_token
openssl rand -hex 32 > gateway/secrets/kindle_token
chmod 644 gateway/secrets/ha_token gateway/secrets/kindle_token

# Configurazione del gateway
cp ../kindle-panel/gateway/config.example.yaml gateway/config.yaml
cp ../kindle-panel/gateway/compose.example.yaml gateway/compose.yaml
$EDITOR gateway/config.yaml gateway/compose.yaml   # vedi sotto

# File del Kindle: copie di CA e token + IP e URL del gateway
cp gateway/certs/ca.pem kindle/src/local/ca.pem
cp gateway/secrets/kindle_token kindle/src/local/token
cp ../kindle-panel/kindle/src/local/device.example.sh kindle/src/local/device.sh
$EDITOR kindle/src/local/device.sh   # WIFI_TEST_IP="<IP_SERVER>"  GATEWAY_URL="https://<NOME_HOST>:8443"

git add -A && git commit -m "Secrets kindle-panel"
```

**`gateway/config.yaml`:** va usata una sola tra `dashboard` e `rows`.
- `dashboard`: l'URL path della plancia, cioè quello che compare nell'indirizzo del browser dopo l'host (`http://<ha>:8123/dashboard-kindle` → `dashboard-kindle`). Lettere, cifre, `-` e `_`, come nella finestra di creazione delle plance di HA;
- `language`: `it` (default) o `en`. Vale per i testi della card Home Tasks;
- `rows` (alternativa a `dashboard`): le entità da mostrare, nell'ordine in cui appaiono sullo schermo. Per la prima prova `sun.sun` va bene perché esiste in ogni installazione. `title` è il titolo in cima;
- `ha_url`:
  - HA con `network_mode: host`: `http://<IP_SERVER>:8123`;
  - HA su una rete Docker condivisa con il gateway: `http://<nome container HA>:8123`.

**`gateway/compose.yaml`:**
- HA con `network_mode: host`: togli il blocco `networks` sia dal servizio sia in fondo al file. Il gateway raggiunge HA tramite `<IP_SERVER>`;
- HA su una rete Docker: in `networks.homeassistant.name` metti il nome della rete di HA (`docker network ls`);
- porta: `"8443:8443"` ascolta su tutte le interfacce; `"<IP_SERVER>:8443:8443"` ascolta solo sulla LAN.

**`gen-certs.sh`** genera `ca.key`/`ca.pem` e `server.key`/`server.pem`, validi 10 anni. Se `ca.key`/`ca.pem` esistono già li riusa e rigenera solo il certificato server, così il Kindle continua a funzionare senza ricopiare `ca.pem`.

### 3. Copiare i secret nel repo

I secret si copiano nel repo principale **mantenendo i percorsi**; git li ignora:

```sh
cd kindle-panel
rsync -a --exclude=.git --exclude=README.md --exclude=.gitignore ../kindle-panel-secrets/ ./
git status --ignored   # i file copiati devono comparire solo sotto "Ignored files"
```

### 4. Avviare il gateway (sul server)

```sh
# Sul server: codice + secret della sola parte gateway
git clone https://github.com/<utente>/kindle-panel.git ~/kindle-panel
# Dal PC:
rsync -a ../kindle-panel-secrets/gateway/ <SERVER>:~/kindle-panel/gateway/
# Sul server:
cd ~/kindle-panel/gateway
docker compose up -d --build
docker compose logs -f   # deve comparire "Uvicorn running on https://0.0.0.0:8443"
```

Note:
- se il gateway si ferma subito, il log riporta la causa: un secret mancante o vuoto, un errore in `config.yaml` o i font mancanti;
- le cartelle `certs/` e `secrets/` sono private (700). I file montati sono 644 perché il container gira con un utente non root (UID 10001). `ca.key` resta 600 e il compose non la monta;
- i secret si possono passare anche come variabili d'ambiente (`HA_TOKEN`, `KINDLE_TOKEN`) invece che come file (`HA_TOKEN_FILE`, `KINDLE_TOKEN_FILE`), ma non entrambi.

### 5. Provare il gateway (dal PC)

```sh
cd kindle-panel-secrets
T=$(cat gateway/secrets/kindle_token)
R="--resolve <NOME_HOST>:8443:<IP_SERVER>"   # serve solo se il PC non risolve <NOME_HOST>

# 200 e un PNG 600x800 in scala di grigi: aprilo e controllalo
curl $R --cacert gateway/certs/ca.pem -H "Authorization: Bearer $T" https://<NOME_HOST>:8443/kindle.png -o out.png
# Senza token: 401
curl $R --cacert gateway/certs/ca.pem -o /dev/null -w '%{http_code}\n' https://<NOME_HOST>:8443/kindle.png
```

Una risposta **503** significa che il gateway non ha potuto disegnare l'immagine. Il Kindle tiene quella precedente. Le cause possibili:
- non raggiunge HA, oppure HA rifiuta il token;
- in modalità `dashboard`: la plancia non esiste o non è mai stata modificata, oppure una lista Home Tasks della plancia non esiste più.

Il motivo esatto è in `docker compose logs` (vedi [Log del gateway](#log-del-gateway)).

### 6. Preparare i file del Kindle (sul PC)

Con i secret già copiati al punto 3:

```sh
cd kindle-panel/kindle
make dist
```

`make dist` crea `kindle/dist/`, con questi contenuti:
- gli script;
- i file del dispositivo: `local/ca.pem`, `local/token`, `local/device.sh`;
- `xh` e `next-wakeup`, già compilati per ARM ed estratti dal tarball della release upstream `v1.0.0-beta.4` con verifica degli sha256.

Controlla che in `dist/local/` ci siano `ca.pem`, `token` e `device.sh`: se ne manca uno, il dashboard non parte.

Default in `local/env.sh`, sovrascrivibili in `device.sh`:
- `TIMEZONE="Europe/Rome"`;
- `REFRESH_SCHEDULE="*/15 7-23 * * *"`, cioè ogni 15 minuti dalle 7 alle 23. Fuori orario appare la schermata "sleeping";
- `FULL_DISPLAY_REFRESH_RATE=4`: un refresh completo ogni 4 parziali, contro il ghosting.

### 7. Installare sul Kindle

1. Collega il Kindle via USB, in modalità archivio di massa. La sua memoria è `/mnt/us` sul dispositivo.
2. Copia il **contenuto** di `kindle/dist/` in `dashboard/`:
   ```sh
   rsync -a kindle/dist/ /media/$USER/Kindle/dashboard/
   ```
   Il punto di mount può essere anche `/run/media/$USER/Kindle`.
3. Copia l'estensione KUAL:
   ```sh
   rsync -a kindle/KUAL/kindle-dash/ /media/$USER/Kindle/extensions/kindle-dash/
   ```
4. Smonta in modo sicuro (`udisksctl unmount -b /dev/sdX1` o dal file manager) e scollega.

### 8. Primo avvio

1. Sul Kindle attiva il Wi-Fi e verifica che sia connesso.
2. Apri **KUAL → Kindle dashboard → Avvia dashboard**. KUAL si chiude: è normale.
3. Entro circa 30 secondi:
   - l'interfaccia Amazon si spegne;
   - `setup-hosts.sh` scrive la voce in `/etc/hosts`, solo la prima volta;
   - compare il pannello.
4. Dopo circa 10 secondi il Kindle va in sospensione e si risveglia secondo `REFRESH_SCHEDULE`.

Se dopo il punto 2 non succede nulla e il Kindle resta usabile, il dashboard si è fermato prima di spegnere l'interfaccia Amazon. Collega il Kindle e leggi `dashboard/logs/dash.log` (vedi [Log](#log)).

---

## Uso e manutenzione

### Uscire dal dashboard

Il dashboard ferma il framework Amazon. Finché è attivo, quindi, **non funzionano né la modalità USB né KOReader**.

- **Hard reboot:** tieni premuto il tasto di accensione per circa 20 secondi. Al riavvio il Kindle torna normale.
- **Via SSH:** `/mnt/us/dashboard/stop.sh` seguito da `reboot`.
- **Voce KUAL "Ferma dashboard e riavvia":** funziona solo mentre il framework è attivo. Dopo un avvio normale il framework è fermo e KUAL non è raggiungibile.

### Cambiare plancia o entità

- **Contenuto della plancia** (card, liste, task): basta modificarla in HA. Il gateway la rilegge a ogni richiesta, quindi al ciclo successivo il Kindle mostra la versione nuova, senza riavvii.
- **Quale plancia, oppure le entità di `rows`:**
  1. modifica `gateway/config.yaml` nel repo dei secret e fai il commit;
  2. copialo sul server, poi `docker compose restart`.

Il Kindle non va toccato: al ciclo successivo scarica la nuova immagine.

### Aggiornare il codice

- **Gateway:** sul server `git pull`, poi `docker compose up -d --build`.
- **Kindle:** sul PC `git pull` e `make dist`, poi ricopia `kindle/dist/` sul Kindle (punto 7). Per collegarlo via USB devi prima uscire dal dashboard.

### Cambiare IP del server o nome host

1. Aggiorna `kindle/src/local/device.sh` nel repo dei secret.
2. Se cambia il nome host, rigenera anche il certificato server:
   ```sh
   CERTS_DIR=gateway/certs sh ../kindle-panel/gateway/scripts/gen-certs.sh <NUOVO_NOME> <IP_SERVER>
   ```
   La CA resta la stessa, quindi `ca.pem` sul Kindle non cambia.
3. Copia il nuovo certificato sul server e riavvia il gateway.
4. Ricostruisci e ricopia `dist/` sul Kindle. Al prossimo avvio `setup-hosts.sh` sostituisce la vecchia voce in `/etc/hosts`.

### Ruotare i token

- **Token del Kindle:**
  1. `openssl rand -hex 32 > gateway/secrets/kindle_token`, poi copialo anche in `kindle/src/local/token`;
  2. commit;
  3. aggiorna il server e riavvia il gateway;
  4. ricostruisci e ricopia `dist/` sul Kindle.
- **Token di HA:**
  1. creane uno nuovo dall'utente dedicato e sostituisci `gateway/secrets/ha_token`;
  2. commit, aggiorna il server e riavvia il gateway;
  3. revoca il vecchio token in HA.

---

## Repo dei secret

Il repo dei secret (per esempio `kindle-panel-secrets`) contiene **solo** i file ignorati da questo repo, con **gli stessi percorsi relativi**:

```
gateway/config.yaml
gateway/compose.yaml
gateway/certs/{ca.key,ca.pem,server.key,server.pem}
gateway/secrets/{ha_token,kindle_token}
kindle/src/local/{ca.pem,token,device.sh}
```

- Va tenuto **privato**: contiene la chiave della CA e i token, compreso quello di HA.
- **Dai secret al repo:** `rsync -a --exclude=.git --exclude=README.md --exclude=.gitignore ../kindle-panel-secrets/ ./`.
- **Se modifichi un secret nel repo principale o sul server** (per esempio `config.yaml`), ricopialo nel repo dei secret allo stesso percorso e fai il commit.
- `kindle/dist/` non va nel repo dei secret: contiene binari e si rigenera con `make dist`.

---

## Log

`/mnt/us/dashboard/logs/dash.log` riporta a ogni ciclo data e livello batteria: serve a stimare l'autonomia.

| Messaggio | Significato |
|---|---|
| `setup-hosts: added ...` / `already maps ...` | Voce in `/etc/hosts` aggiunta oppure già presente |
| `setup-hosts: ...` (errore), seguito dalla versione di BusyBox | Il dashboard non parte e il Kindle resta utilizzabile. `/etc/hosts` non è stato modificato: mancano `GATEWAY_URL`/`WIFI_TEST_IP` (`local/device.sh`) oppure il remount di `/` è fallito |
| `Partial screen refresh` / `Full screen refresh` | Nuova immagine disegnata |
| `Dashboard image unchanged` + `Not updating screen, fetch-dashboard returned 2` | Dati invariati, schermo non ridisegnato |
| `Fetch failed, xh returned N` + `... returned 1` | Download fallito, resta l'immagine precedente. `N`: 1 = connessione/TLS/DNS, 2 = timeout, 4 = HTTP 4xx (401: token errato), 5 = HTTP 5xx (503: il gateway non raggiunge HA) |
| `Missing configuration: ...` | Mancano `GATEWAY_URL`, `local/token` o `local/ca.pem` |
| `Couldn't connect to Wi-Fi` / `No test ip specified` | Il ping verso `WIFI_TEST_IP` fallisce, oppure `WIFI_TEST_IP` è vuoto |

Errori di `xh` da riconoscere:

| Errore | Causa |
|---|---|
| `invalid dnsname` | In `GATEWAY_URL` c'è un IP: va usato il nome host |
| `failed to lookup address information` | Il nome host non si risolve: controlla le righe `setup-hosts:` nel log e i valori in `device.sh` |
| `UnknownIssuer` | `local/ca.pem` non è la CA che ha firmato il certificato del gateway |
| `CertNotValidForName` | Il nome in `GATEWAY_URL` non è nel SAN del certificato |
| `CertNotValidYet` / `CertExpired` | Probabilmente l'orologio del Kindle è sbagliato (vedi sotto) |

### Log del gateway

`docker compose logs` sul server. In modalità `dashboard`:

| Messaggio | Significato |
|---|---|
| `Dashboard '...' not found, or never edited (auto-generated)` | L'URL path in `config.yaml` è sbagliato, oppure la plancia è generata automaticamente da HA e non ha una configurazione salvata |
| `Dashboard '...' cannot be drawn: ... strategy ...` | La plancia o la sua prima vista è generata da una *strategy*: esiste solo nel browser |
| `Dashboard '...' cannot be drawn: Home Tasks has no list ...` | La plancia usa un `list_id` che Home Tasks non ha (lista cancellata?) |
| `Home Assistant refused home_tasks/...: unknown_command` | Home Tasks non è installato o non è caricato |
| `Home Assistant WebSocket unavailable: HA rejected the token` | Token di HA errato o revocato |
| `Home Assistant WebSocket unavailable: ...` (altro) | HA non raggiungibile da `ha_url` |
| `Skipping unsupported cards: ...` | Card presenti nella plancia ma non disegnate (informativo) |
| `Unsupported upgrade request` / `No supported WebSocket library detected` | Qualcuno ha provato ad aprire un WebSocket sul gateway: viene rifiutato apposta (`--ws none`). Il secondo messaggio di uvicorn è fuorviante: la libreria c'è, ma serve solo verso HA |

### Orologio

Dopo la fine del supporto Amazon l'ora del Kindle potrebbe non sincronizzarsi più. Verificala con le date nel log. L'ora conta per due motivi:
- la pianificazione `REFRESH_SCHEDULE` dipende dall'ora;
- la validazione TLS fallisce se l'orologio è fuori dal periodo di validità del certificato.

Se l'ora deriva, il passo previsto per la v1.1 è impostarla dall'header `Date` del gateway; per ora la cosa è solo documentata.

### Debug

Via SSH: `DEBUG=true /mnt/us/dashboard/start.sh`. Gira in primo piano con `set -x` e usa `sleep` al posto della sospensione.

---

## Verifica sul dispositivo

- [ ] Avvio da KUAL: nel log compare `setup-hosts: added ...`.
- [ ] Il primo disegno avviene.
- [ ] Un ciclo successivo con dati invariati non ridisegna (`Not updating screen` nel log).
- [ ] Cambiando un task (o un'entità in modalità `rows`) in HA, lo schermo si aggiorna al ciclo successivo.
- [ ] Sospensione e risveglio RTC funzionano.
- [ ] Livello batteria registrato per 24 ore.
- [ ] L'ora del Kindle è corretta (`date` nel log).

---

## Sviluppo

```sh
# Test del gateway (HA simulato: respx per REST, server WebSocket locale per la WebSocket API)
cd gateway
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Script del Kindle: shellcheck -s ash + shfmt -i 2, come nella CI upstream
cd kindle && make lint
```

## Modalità dashboard

Il gateway ricostruisce la plancia come la mostrerebbe il browser su uno schermo largo 600 px, senza parti interattive:
- **solo la prima vista** della plancia;
- **vista sections:** le sezioni una sotto l'altra, nell'ordine della configurazione. Sotto i 2 × 320 px HA stesso usa una colonna sola e ignora `column_span` (`hui-sections-view.ts`). Le viste a schede (masonry, ecc.) mostrano le card in colonna;
- **card supportate:** `heading` e `custom:home-tasks-card`. Le altre vengono saltate e annotate nel log (`Skipping unsupported cards`);
- **non disegnabili:** plance auto-generate o con *strategy*. In entrambi i casi HA non ha una configurazione da leggere: la genera il browser (`ha-panel-lovelace.ts`).

### Card Home Tasks

Il comportamento della card [Home Tasks](https://github.com/L3t4l3s/home-tasks) v2.4.0 (MIT) è portato in Python in `gateway/app/home_tasks.py`. Sono replicati filtri e ordinamento di default della colonna, sezioni, gruppo "Fatto", intestazione con avanzamento e badge: priorità, sotto-attività, scadenza, ricorrenza, persona, tag e promemoria.

Il port è stato confrontato con la card vera, eseguita in jsdom con data congelata: 2000 casi casuali con tutte le combinazioni di opzioni e 0 differenze. I valori attesi in `tests/test_home_tasks.py` sono quelli prodotti dalla card.

Differenze volute:
- **scadenza oggi con orario:** la card fa il conto alla rovescia ("Tra 2 h 15 min") e il testo cambierebbe a ogni risveglio, ridisegnando lo schermo ogni volta. Il gateway scrive l'ora ("Oggi 18:00");
- **parti interattive omesse:** campo "aggiungi", microfono, filtri, ordinamento, chip di tag e persone;
- **immagini mai scaricate:** foto dei task e delle persone. Al posto della foto della persona ci sono le iniziali, come fa la card quando la foto manca;
- **icone:** le icone `mdi:` di sezioni e titoli non vengono disegnate. Persona e promemoria (👤 e ⏰ della card) sono disegnati a mano, perché DejaVu Sans non ha quei caratteri;
- **sezioni sempre aperte:** lo stato "chiusa" di una sezione la card lo salva nel `localStorage` del browser, dove il gateway non arriva;
- **liste esterne** (colonne con `entity_id`, es. Todoist): non supportate, la colonna viene saltata;
- **font:** circa il doppio di quelli del browser, per leggere il pannello a distanza. Se lo spazio finisce, il resto non viene disegnato e in fondo compare `+N`, il numero di task esclusi;
- **emoji nei titoli:** DejaVu Sans non le ha, quindi appaiono come un rettangolino.

### Security e consumi

- **Comandi verso HA:** sul WebSocket partono solo `auth` e i comandi di `ALLOWED_COMMANDS` in `app/ha_ws.py`, tutti di lettura. Ogni altro comando viene rifiutato dal codice prima di essere inviato.
- **Token di HA:**
  - non passa mai da un proxy preso dall'ambiente;
  - non segue redirect. La libreria `websockets` li seguirebbe anche verso altri host, e il token viaggia nel primo messaggio dopo l'handshake.
- **Limiti:**
  - messaggi da HA fino a 8 MiB;
  - al massimo 50 card, 10 colonne per card, 500 task per lista, 300 caratteri per testo;
  - 10 s per la conversazione WebSocket.
- **Gateway:** non accetta WebSocket in ingresso (`--ws none`).
- **Determinismo:** l'immagine dipende solo da ciò che si vede. Note, cronologia e altri campi non disegnati non la cambiano, quindi il Kindle non ridisegna lo schermo. Cambia anche a mezzanotte, perché "Oggi"/"Domani" si spostano.
- **Tempi:** su HA 2026.6.0 una richiesta completa (TLS, WebSocket verso HA, rendering) ha richiesto circa 0,1 s sul server.

## Note sul rendering (modalità rows)

- **Immagine:** 600×800, modalità `L` (8 bit, scala di grigi, senza alpha), font DejaVu Sans, nero su bianco. Il testo è antialiasato, quindi ci sono grigi solo sui bordi dei caratteri.
- **Determinismo:** l'immagine dipende solo dai dati, così il Kindle può saltare il refresh:
  - non riporta l'ora di render: "dati del HH:MM" è il `last_changed` più recente tra le entità, nel `timezone` configurato;
  - la batteria è arrotondata a passi del 5%.
- **Valori:** formato grezzo di HA:
  - numeri sempre a 1 decimale con il punto (`45` diventa `45.0`), con unità `unit_of_measurement`. `display_precision` non è disponibile da `GET /api/states/<id>`: sta nel registro entità, non negli attributi;
  - `weather.*`: mostra lo stato come arriva da HA (es. `cloudy`) più l'attributo `temperature`;
  - entità mancanti, in errore, `unavailable` o `unknown` appaiono come `—`.
- **`last_changed` e meteo:** `last_changed` cambia solo quando cambia lo stato. Per un'entità `weather` che aggiorna solo la temperatura (un attributo), l'ora "dati del" non si sposta.
