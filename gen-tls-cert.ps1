# Generate a self-signed TLS certificate for the NPU server
# Valid for 3 years, covers localhost and the WSL2 host IP

$PY = "C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Generating self-signed TLS certificate..."
& $PY -c @"
from pathlib import Path
import datetime, ipaddress

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'cryptography', '-q'])
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

import datetime, ipaddress

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, u'NemoClaw-NPU'),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, u'NemoClaw'),
])
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1095))
    .add_extension(x509.SubjectAlternativeName([
        x509.DNSName(u'localhost'),
        x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
        x509.IPAddress(ipaddress.IPv4Address('172.27.208.1')),
        x509.IPAddress(ipaddress.IPv4Address('0.0.0.0')),
    ]), critical=False)
    .sign(key, hashes.SHA256())
)

out = Path(r'$ScriptDir')
(out / 'server.key').write_bytes(key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption()
))
(out / 'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print('Generated server.crt and server.key')
print('Expires:', (datetime.datetime.utcnow() + datetime.timedelta(days=1095)).strftime('%Y-%m-%d'))
"@
