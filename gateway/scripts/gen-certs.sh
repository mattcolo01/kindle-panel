#!/bin/sh
# Generate a private CA and a server certificate for kindle-gateway.
#
#   scripts/gen-certs.sh <NOME_HOST> [IP_LAN]
#
# Writes into ./certs (or $CERTS_DIR):
#   ca.key, ca.pem          CA (10 years). ca.pem goes on the Kindle.
#   server.key, server.pem  server certificate (10 years), SAN=DNS:<NOME_HOST>
#                           (+ IP:<IP_LAN> if given, for tests with curl).
#
# The xh binary on the Kindle (0.16.1, rustls) cannot connect to https://<IP>,
# so the Kindle must use NOME_HOST. If ca.key/ca.pem already exist they are
# reused: only the server certificate is regenerated and the Kindle keeps
# working without copying a new ca.pem.
set -eu

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "Uso: $0 <NOME_HOST> [IP_LAN]" >&2
  exit 1
fi
HOST=$1
IP=${2:-}
DIR=${CERTS_DIR:-certs}
DAYS=3650

SAN="DNS:$HOST"
[ -n "$IP" ] && SAN="$SAN,IP:$IP"

umask 077
mkdir -p "$DIR"
chmod 700 "$DIR"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ -f "$DIR/ca.key" ] && [ -f "$DIR/ca.pem" ]; then
  echo "CA esistente riutilizzata: $DIR/ca.pem"
else
  cat >"$tmp/ca.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = kindle-panel CA
[v3_ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EOF
  openssl genrsa -out "$DIR/ca.key" 3072
  openssl req -x509 -new -sha256 -days "$DAYS" -key "$DIR/ca.key" \
    -config "$tmp/ca.cnf" -extensions v3_ca -out "$DIR/ca.pem"
  echo "Nuova CA: $DIR/ca.pem"
fi

cat >"$tmp/server.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = $HOST
[v3_server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = $SAN
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF
openssl genrsa -out "$DIR/server.key" 2048
openssl req -new -sha256 -key "$DIR/server.key" -config "$tmp/server.cnf" -out "$tmp/server.csr"
openssl x509 -req -sha256 -days "$DAYS" -in "$tmp/server.csr" \
  -CA "$DIR/ca.pem" -CAkey "$DIR/ca.key" -set_serial "0x$(openssl rand -hex 16)" \
  -extfile "$tmp/server.cnf" -extensions v3_server -out "$DIR/server.pem"

# The directory is private (700); the files mounted one by one into the
# container must be readable by its unprivileged user. ca.key is never mounted.
chmod 644 "$DIR/ca.pem" "$DIR/server.pem" "$DIR/server.key"
chmod 600 "$DIR/ca.key"

openssl verify -CAfile "$DIR/ca.pem" "$DIR/server.pem"
echo "Certificato server: $DIR/server.pem (SAN=$SAN)"
