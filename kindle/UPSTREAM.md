# Upstream: pascalw/kindle-dash

- **Repository:** https://github.com/pascalw/kindle-dash
- **Commit:** `c83842e7561340e902812f358481f689cdec24a4` (tag `v1.0.0-beta.4`)
- **Licenza:** MIT, Copyright (c) 2021 Pascal Widdershoven. Il testo è in [`LICENSE`](LICENSE).

## File vendorizzati

Questi file sono copiati senza modifiche dal commit indicato (commit `e76dba6` di questo repo):

```
LICENSE  Makefile  KUAL/kindle-dash/{config.xml,menu.json}
src/{dash.sh,start.sh,stop.sh,wait-for-wifi.sh,sleeping.png}
src/local/{env.sh,fetch-dashboard.sh,low-battery.sh}
```

Non sono stati inclusi `README.md`, `CHANGELOG.md`, `docs/`, `example/`, `.github/` e il sorgente di `src/next-wakeup/`, che non serve perché non si ricompila. Gli script in `src/` sono identici a quelli contenuti nel tarball della release `v1.0.0-beta.4` (verificato con `cmp`).

Per vedere tutte le modifiche locali: `git diff e76dba6 -- kindle/`.

## Binari dalla release (non ricompilati)

`make dist` scarica il tarball della release e ne estrae `xh` e `next-wakeup`, verificando gli sha256:

| File | sha256 |
|---|---|
| `kindle-dash-v1.0.0-beta.4.tgz` | `3bdf2626dd94bc9636e54ae159f193379aea257a4c39f4b3a91d5f395fa76889` |
| `xh` | `d77c9b66a5bcd2ef0375d922b7f709f8ce4697a9d57c4b2452d6cb7ce6eaef70` |
| `next-wakeup` | `fb91e220f501be4a74cd5e06c61db26656c1db3e172d177fff90ac1de1c8f8b7` |

Entrambi sono `ELF 32-bit LSB executable, ARM, EABI5, statically linked`. `xh --version`, eseguito con qemu-arm, risponde `xh 0.16.1` / `-native-tls`: è compilato con rustls 0.20.4, senza OpenSSL.

### Limite verificato: niente HTTPS verso indirizzi IP

Con rustls 0.20 `xh` 0.16.1 rifiuta gli URL `https://<IP>`. Il messaggio d'errore è `invalid dnsname` / `rustls does not support HTTPS for IP addresses`, anche con `--verify=no`. Con un nome host funziona, e il pinning della CA con `--verify=<file>` è rispettato: una CA diversa produce `UnknownIssuer`. L'ho verificato eseguendo il binario ARM della release con qemu-arm contro un server locale.

Per questo il Kindle raggiunge il gateway **per nome host** (SAN=DNS nel certificato, risolto dal DNS della LAN) e non per IP, come prevedeva invece il design iniziale.

### Flag di xh 0.16.1 usati

Li ho verificati nel sorgente `src/cli.rs` del tag `v0.16.1` e con il binario della release:
- `--verify=<file>`: usa solo quella CA e disattiva le root di sistema;
- `-A bearer -a <token>`;
- `--check-status`: 4 per HTTP 4xx, 5 per 5xx; con `-d` è comunque implicito;
- `--timeout 20`: timeout dell'intera richiesta;
- `-d -q -o <file>`: in caso di errore HTTP il file non viene scritto;
- `--ignore-stdin`.

Gli altri codici d'uscita sono 1 per errori di connessione o TLS e 2 per il timeout.

## Modifiche applicate

1. **`src/local/fetch-dashboard.sh`**, riscritto:
   - legge `GATEWAY_URL` e `KINDLE_TOKEN` dall'ambiente (`local/env.sh`); se manca, legge il token da `local/token` togliendo `\r` e `\n`;
   - scarica in `local/state/dash.png.tmp` con
     `xh --ignore-stdin --verify=local/ca.pem -A bearer -a "$KINDLE_TOKEN" --check-status --timeout 20 -d -q -o "$tmp" get "$GATEWAY_URL/kindle.png" X-Kindle-Battery:<gasgauge-info -c senza %>`;
   - se lo scaricamento fallisce: scrive nel log il codice d'uscita di `xh`, cancella il file temporaneo ed esegue `exit 1`;
   - calcola l'hash con `md5sum`, oppure `sha1sum` o `cksum` se manca. Se è uguale a `local/state/last_hash` esegue `exit 2` e lo schermo non viene ridisegnato. Altrimenti sposta il file su `$1`, salva l'hash ed esegue `exit 0`. Un hash vuoto, cioè un comando di hash fallito, non conta mai come "invariato";
   - rispetto al comando del design aggiunge `--ignore-stdin`. Senza questo flag `xh` legge lo stdin come body quando non è un terminale: avviato via SSH non interattivo resterebbe bloccato. L'ho verificato con il binario 0.16.1.
2. **`src/dash.sh`**: cancella `local/state/last_hash` in `prepare_sleep()`, così al risveglio dopo la schermata "sleeping" il dashboard viene ridisegnato. Lo cancella **anche in `init()`**: l'hash resta su `/mnt/us` tra un avvio e l'altro, e senza questa riga il primo disegno dopo un riavvio verrebbe saltato se i dati non sono cambiati.
3. **`src/local/env.sh`**: nuovi default:
   - `TIMEZONE="Europe/Rome"`;
   - `REFRESH_SCHEDULE="*/15 7-23 * * *"`;
   - `FULL_DISPLAY_REFRESH_RATE=4`.

   Contiene inoltre `WIFI_TEST_IP` e `GATEWAY_URL`, vuoti e obbligatori. I valori del dispositivo vanno in `local/device.sh`, ignorato da git (modello: `local/device.example.sh`), che `env.sh` carica per primo se esiste.
4. **`src/stop-and-reboot.sh`** (nuovo): esegue `stop.sh` e poi `reboot`, per la voce KUAL.
5. **`KUAL/kindle-dash/menu.json`**: voci "Avvia dashboard" (`start.sh`) e "Ferma dashboard e riavvia" (`stop-and-reboot.sh`). La seconda funziona solo mentre il framework Amazon è attivo.
5b. **`src/setup-hosts.sh`** (nuovo), chiamato da `init()` in `src/dash.sh` prima di `framework stop`: aggiunge `<WIFI_TEST_IP> <host di GATEWAY_URL>` in `/etc/hosts`, così non serve un record DNS. Il filesystem di sistema viene riaperto in scrittura (`mount -o rw,remount /`) solo se la voce manca o è diversa. Se fallisce, il dashboard non parte e il framework resta attivo.
6. **`Makefile`**:
   - `dist/xh` e `dist/next-wakeup` si estraggono dal tarball della release, con verifica sha256, invece di compilarli con `cross`;
   - `dist` copia anche `src/local/ca.pem`, `src/local/token` e `src/local/device.sh` se presenti, perché sono git-ignored;
   - nuovo target `lint` (`shellcheck -s ash` + `shfmt -i 2 -d`, come nella CI upstream).

   Il resto è invariato: `wait-for-wifi.sh`, `start.sh`, `stop.sh`, `low-battery.sh`, il log della batteria e `sleeping.png`.
