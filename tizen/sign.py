#!/usr/bin/env python3
"""Signs Pokedex-tizen.wgt with the Tizen SDK's public test certificates, no Tizen Studio needed.

    python3 tizen/sign.py            # Pokedex-tizen.wgt -> signed in place (author-signature.xml + signature1.xml)

TVs up to 2022 (Tizen 6.5) accept packages signed this way; 2023+ TVs (Tizen 7) need a Samsung certificate
made with your Samsung account (Tizen Studio's Certificate Manager, or TizenBrew Installer), then
`python3 tizen/build.py --sign <profile>`.

The first run downloads the SDK's certificate-generator package from download.tizen.org (checked against its
published SHA-256) into tizen/certs/ and makes an author certificate for you, issued by the SDK's "Tizen
Developers CA". The author key stays in tizen/certs/author.key: a TV only updates an app signed by the same
author, so keep it. Format after tizen.js (the W3C widget signature profile, RSA-SHA512, exclusive C14N).
Needs Python 3 with the `cryptography` and `lxml` packages.
"""
import base64
import datetime
import hashlib
import io
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WGT = os.path.join(ROOT, 'Pokedex-tizen.wgt')
CERTS = os.path.join(ROOT, 'tizen', 'certs')
SDK = 'https://download.tizen.org/sdk/tizenstudio/official/binary/certificate-generator_0.1.4_ubuntu-64.zip'
SDK_SHA256 = '446aa52f249205f4ad573173b02c9c38aa5de0316028b77dd189e44fd5f75964'
SDK_DIR = 'data/tools/certificate-generator/certificates/'
DISTRIBUTOR_PASS = b'tizenpkcs12passfordsigner'
DS = 'http://www.w3.org/2000/09/xmldsig#'
# The digest of the fixed <Object Id="prop"> under C14N 1.1, per role (tizen.js's constants).
PROP_DIGEST = {
    'AuthorSignature': 'aXbSAVgmAz0GsBUeZ1UmNDRrxkWhDUVGb45dZcNRq429wX3X+x6kaXT3NdNDTSNVTU+ypkysPMGvQY10fG1EWQ==',
    'DistributorSignature': '/r5npk2VVA46QFJnejgONBEh4BWtjrtu9x/IFeLksjWyGmB/cMWKSJWQl7aU3YRQRZ3AesG8gF7qGyvKX9Snig==',
}
ROLE = {'AuthorSignature': 'author', 'DistributorSignature': 'distributor'}
SIGNATURE_FILE = re.compile(r'^(author-signature|signature\d+)\.xml$')


def wrap(b64):
    return '\n'.join(b64[i:i + 76] for i in range(0, len(b64), 76))


def sdk_certificates():
    """The SDK's developer CA (cert + key + its password) and the public distributor signer, downloaded once."""
    os.makedirs(CERTS, exist_ok=True)
    path = os.path.join(CERTS, 'certificate-generator.zip')
    if not os.path.exists(path):
        print('Downloading the Tizen SDK certificate package ...')
        data = urllib.request.urlopen(SDK, timeout=120).read()
        if hashlib.sha256(data).hexdigest() != SDK_SHA256:
            sys.exit('The download does not match its published checksum; not using it.')
        with open(path, 'wb') as f:
            f.write(data)
    with zipfile.ZipFile(path) as z:
        ca_cert = x509.load_pem_x509_certificate(z.read(SDK_DIR + 'developer/tizen-developer-ca.cer'))
        conf = z.read(SDK_DIR + 'developer/conf.ini').decode()
        ca_pass = re.search(r'PASSWD_OF_ISSUER_FOR_DEV=(\S+)', conf).group(1).encode()
        ca_key = serialization.load_pem_private_key(z.read(SDK_DIR + 'developer/tizen-developer-ca-privatekey.pem'), ca_pass)
        dist_key, dist_cert, dist_chain = pkcs12.load_key_and_certificates(
            z.read(SDK_DIR + 'distributor/tizen-distributor-signer.p12'), DISTRIBUTOR_PASS)
    return ca_cert, ca_key, (dist_key, [dist_cert] + list(dist_chain))


def author_certificate(ca_cert, ca_key):
    """This project's author key and certificate, issued by the SDK's developer CA; made once, then reused."""
    key_path, cert_path = os.path.join(CERTS, 'author.key'), os.path.join(CERTS, 'author.crt')
    if os.path.exists(key_path) and os.path.exists(cert_path):
        key = serialization.load_pem_private_key(open(key_path, 'rb').read(), None)
        cert = x509.load_pem_x509_certificate(open(cert_path, 'rb').read())
        if cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc):
            return key, [cert, ca_cert]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Hush'), x509.NameAttribute(NameOID.COMMON_NAME, 'Hush')])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(ca_cert.not_valid_after_utc).sign(ca_key, hashes.SHA256()))
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(key_path, 0o600)
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print('Made a new author certificate (tizen/certs/author.key): keep it, updates must use the same one.')
    return key, [cert, ca_cert]


def signature_xml(sig_id, files, key, chain):
    """One signature file over files ({name: bytes}), in tizen.js's exact layout."""
    refs = ''
    for name in sorted(files):
        digest = base64.b64encode(hashlib.sha512(files[name]).digest()).decode()
        refs += ('<Reference URI="%s">\n<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha512"></DigestMethod>\n'
                 '<DigestValue>%s</DigestValue>\n</Reference>\n' % (urllib.parse.quote(name, safe='~!*()\''), wrap(digest)))
    refs += ('<Reference URI="#prop">\n<Transforms>\n<Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></Transform>\n'
             '</Transforms>\n<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha512"></DigestMethod>\n'
             '<DigestValue>%s</DigestValue>\n</Reference>\n' % wrap(PROP_DIGEST[sig_id]))
    certs = ''.join('<X509Certificate>\n%s\n</X509Certificate>\n' % wrap(base64.b64encode(
        c.public_bytes(serialization.Encoding.DER)).decode()) for c in chain)
    prop = ('<Object Id="prop"><SignatureProperties xmlns:dsp="http://www.w3.org/2009/xmldsig-properties">'
            '<SignatureProperty Id="profile" Target="#%(id)s"><dsp:Profile URI="http://www.w3.org/ns/widgets-digsig#profile"></dsp:Profile></SignatureProperty>'
            '<SignatureProperty Id="role" Target="#%(id)s"><dsp:Role URI="http://www.w3.org/ns/widgets-digsig#role-%(role)s"></dsp:Role></SignatureProperty>'
            '<SignatureProperty Id="identifier" Target="#%(id)s"><dsp:Identifier></dsp:Identifier></SignatureProperty>'
            '</SignatureProperties></Object>' % {'id': sig_id, 'role': ROLE[sig_id]})
    body = ('<Signature xmlns="%s" Id="%s">\n<SignedInfo>\n'
            '<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"></CanonicalizationMethod>\n'
            '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha512"></SignatureMethod>\n'
            '%s</SignedInfo>\n<SignatureValue>\n%%s\n</SignatureValue>\n<KeyInfo>\n<X509Data>\n%s</X509Data>\n</KeyInfo>\n%s\n</Signature>'
            % (DS, sig_id, refs, certs, prop))
    # Sign exactly what a verifier will canonicalise: SignedInfo under exclusive C14N, from the finished document.
    doc = etree.fromstring(body % 'x')
    canon = etree.tostring(doc.find('{%s}SignedInfo' % DS), method='c14n', exclusive=True)
    value = base64.b64encode(key.sign(canon, padding.PKCS1v15(), hashes.SHA512())).decode()
    return (body % wrap(value)).encode('utf-8')


def verify(files, name, xml):
    """Re-checks a signature file the way the TV will: canonical SignedInfo, the leaf's key, every digest."""
    root = etree.fromstring(xml)
    canon = etree.tostring(root.find('{%s}SignedInfo' % DS), method='c14n', exclusive=True)
    sig = base64.b64decode(root.findtext('{%s}SignatureValue' % DS))
    leaf = x509.load_der_x509_certificate(base64.b64decode(root.find('.//{%s}X509Certificate' % DS).text))
    leaf.public_key().verify(sig, canon, padding.PKCS1v15(), hashes.SHA512())
    for ref in root.iter('{%s}Reference' % DS):
        uri = ref.get('URI')
        if uri == '#prop':
            continue
        want = ref.findtext('{%s}DigestValue' % DS).replace('\n', '')
        if base64.b64encode(hashlib.sha512(files[urllib.parse.unquote(uri)]).digest()).decode() != want:
            sys.exit('%s: digest mismatch for %s' % (name, uri))


def sign(path):
    ca_cert, ca_key, (dist_key, dist_chain) = sdk_certificates()
    author_key, author_chain = author_certificate(ca_cert, ca_key)
    with zipfile.ZipFile(path) as z:
        files = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir() and not SIGNATURE_FILE.match(i.filename)}
    author = signature_xml('AuthorSignature', files, author_key, author_chain)
    verify(files, 'author-signature.xml', author)
    with_author = dict(files, **{'author-signature.xml': author})
    distributor = signature_xml('DistributorSignature', with_author, dist_key, dist_chain)
    verify(with_author, 'signature1.xml', distributor)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('signature1.xml', distributor)
        z.writestr('author-signature.xml', author)
        for name in sorted(files):
            z.writestr(name, files[name])
    with open(path, 'wb') as f:
        f.write(out.getvalue())
    print('Signed %s: author %s, distributor %s (%d files).' % (
        os.path.basename(path), author_chain[0].subject.rfc4514_string(), dist_chain[0].subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, len(files)))


if __name__ == '__main__':
    sign(sys.argv[1] if len(sys.argv) > 1 else WGT)
