"""Phone remote (PLAN §70): the FRIDAY phone app talks straight to this PC over IPv6 — no server in between.

Trust, in order:
  1. TLS 1.3 with this PC's own certificate; the phone pins its SHA-256 (from the pairing QR), so nobody in the
     middle can pose as the PC.
  2. Pairing: the QR (shown on the PC screen only) carries a one-time code valid 5 minutes; the owner confirms the new
     phone with Windows Hello on the PC. The phone makes two keys in its Android Keystore and sends only the public
     halves: D signs every request, A signs approvals and works only after the phone's fingerprint/face/PIN.
  3. Every request: signed by D over method, path, time, nonce and body hash — 60 s window, each nonce once.
  4. What Windows Hello guards on the PC (PowerShell, shutdown, writing files, ...) the phone approves with A:
     a fresh challenge signed after the phone's own fingerprint/PIN — so "no clicking yes on the PC" but not
     "anyone with the phone".
  5. Bad requests: 5 from one address in 10 min = that address is refused for an hour; 50 in an hour = the server
     shuts itself and the tray says so.
Keys, devices and the TLS key's password live in the DPAPI secrets (security.set_secret); nothing in settings.json.
"""
import base64, datetime, hashlib, hmac, http.server, ipaddress, json, os, secrets, socket, ssl, subprocess, threading, time

import security

ROOT = os.environ.get("FRIDAY_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "remote")  # not in git
PORT = int(os.environ.get("FRIDAY_REMOTE_PORT", "47321"))
BODY_MAX = 8 * 2**20  # 60 s of 16 kHz PCM is ~1.9 MB
SKEW_S, PAIR_S, APPROVE_S = 60, 300, 120


# ---------- certificate ----------
def _paths():
    return os.path.join(DIR, "cert.pem"), os.path.join(DIR, "key.pem")


def ensure_cert():
    """Self-signed P-256 certificate (10 years). The private key file is encrypted; its password is a DPAPI secret.
    Returns the certificate's SHA-256 (hex) — what the phone pins."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    cert_p, key_p = _paths()
    if not (os.path.isfile(cert_p) and os.path.isfile(key_p) and security.secret("remote_key_pw")):
        os.makedirs(DIR, exist_ok=True)
        pw = secrets.token_urlsafe(32)
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FRIDAY")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650)).sign(key, hashes.SHA256()))
        with open(key_p, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.BestAvailableEncryption(pw.encode())))
        with open(cert_p, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        security.set_secret("remote_key_pw", pw)
    return fingerprint()


def fingerprint():
    with open(_paths()[0], "rb") as f:
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(f.read().decode())).hexdigest()


# ---------- addresses ----------
# Tailscale's own IPv6 range: the owner's devices reach each other through it (WireGuard, direct when possible) even
# where the home router drops inbound IPv6 — the ZTE F6107A here does (§70, "จับคู่ไม่สำเร็จ" on mobile data)
TAILSCALE = ipaddress.IPv6Network("fd7a:115c:a1e0::/48")


def pick(addrs):
    """Addresses worth putting in the QR: Tailscale first (works from anywhere), then public IPv6."""
    ips = []
    for a in addrs:
        try:
            ips.append(ipaddress.IPv6Address(a.split("%")[0]))
        except ValueError:
            continue
    return [str(i) for i in ips if i in TAILSCALE] + [str(i) for i in ips if i.is_global and i not in TAILSCALE]


_addr_cache = [0.0, []]


_addr_refresh = threading.Lock()


def addresses(cached=False):
    """This PC's Tailscale + public IPv6 addresses that last (not the daily-rotating "temporary" ones), best first.
    cached=True never waits (review §73: PowerShell on the request thread slowed every poll): returns what is known
    and refreshes in the background when older than 10 minutes."""
    if cached:
        if time.time() - _addr_cache[0] > 600 and _addr_refresh.acquire(blocking=False):
            def refresh():
                try:
                    addresses()
                finally:
                    _addr_refresh.release()
            threading.Thread(target=refresh, daemon=True).start()
        return _addr_cache[1]
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-NetIPAddress -AddressFamily IPv6 | Where-Object { $_.SuffixOrigin -ne 'Random' -and "
                              "$_.AddressState -eq 'Preferred' } | ForEach-Object { $_.IPAddress }"],
                             capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        _addr_cache[0] = time.time()  # a failure is remembered too: no retry storm
        return _addr_cache[1]
    _addr_cache[:] = [time.time(), pick(out.split())]
    return _addr_cache[1]


# ---------- devices (DPAPI secrets) ----------
_dev_cache = [None, {}]


def devices():
    try:
        mt = os.path.getmtime(security.SECRETS)
    except OSError:
        mt = None
    if _dev_cache[0] != mt or mt is None:
        _dev_cache[:] = [mt, security.secret("remote_devices") or {}]
    return dict(_dev_cache[1])


def _save_devices(d):
    security.set_secret("remote_devices", d)
    _dev_cache[0] = None


def forget(dev_id):
    d = devices()
    gone = d.pop(dev_id, None)
    _save_devices(d)
    return gone


def _pub(pem):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)


def _verify(pub_pem, sig_b64, data):
    """ECDSA P-256 / SHA-256 (DER signature, base64) — what Android's SHA256withECDSA makes."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        _pub(pub_pem).verify(base64.b64decode(sig_b64), data, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def signed_text(method, path, ts, nonce, body):
    return f"{method}\n{path}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()


# ---------- pairing ----------
_pairing = {}  # one-time code -> expiry


def pair_payload():
    """What the QR holds (JSON). The code works once, for PAIR_S seconds."""
    fp = ensure_cert()
    code = secrets.token_urlsafe(24)
    _pairing.clear()  # only the newest QR is valid
    _pairing[code] = time.time() + PAIR_S
    return json.dumps({"v": 1, "app": "friday", "h": addresses(), "p": PORT, "f": fp, "t": code}, separators=(",", ":"))


def _take_code(code):
    for c, exp in list(_pairing.items()):
        if hmac.compare_digest(c.encode(), str(code).encode()):
            del _pairing[c]
            return exp > time.time()
    return False


# ---------- jobs (one phone request = one job, polled) ----------
_local = threading.local()


class Job:
    def __init__(self, dev_id, dev_name):
        self.id, self.dev, self.dev_name = secrets.token_hex(8), dev_id, dev_name
        self.status, self.replies, self.audio, self.heard = "running", [], [], ""
        self.speech, self.speak = [], True  # §72 texts to voice after the reply is shown; phone may not want audio
        self.ids_ok = False  # §73 the phone app says it has the voice model (X-Friday-Voice: ids)
        self.voice = None  # §73 {"speaker", "ids": [[...] per piece]}: the phone speaks with its own copy of the model
        self.question, self.challenge, self._answer, self._ok = "", "", threading.Event(), False
        self.created = time.time()

    def approve(self, question):
        """Called on the job's own thread when the PC would ask for Windows Hello: wait for the phone's signed yes."""
        self.question, self.challenge = question[:300], base64.b64encode(secrets.token_bytes(32)).decode()
        self._answer.clear()
        self.status = "confirm"
        got = self._answer.wait(APPROVE_S)
        self.status, self.question = "running", ""
        ok, self._ok, self.challenge = got and self._ok, False, ""
        return ok

    def answer(self, sig_b64, pub_a):
        if self.status != "confirm" or not self.challenge:
            return False
        self._ok = bool(sig_b64) and _verify(pub_a, sig_b64, f"{self.id}\n{self.challenge}".encode())
        self._answer.set()
        return self._ok

    def view(self):
        """running -> (confirm) -> replied (text ready, voice being made) -> done (with voice). §72: the phone shows
        the text at "replied" instead of waiting for ~1 MB of audio."""
        out = {"id": self.id, "status": self.status, "reply": "\n\n".join(self.replies), "heard": self.heard}
        if self.status == "confirm":
            out.update(question=self.question, challenge=self.challenge)
        if self.status in ("replied", "done"):
            out["h"] = addresses(cached=True)  # §72 the phone keeps the PC's current addresses: no re-pair on a new prefix
        if self.status == "done":
            out["audio"] = [base64.b64encode(a).decode() for a in self.audio]
            if self.voice:
                out["voice"] = self.voice
        return out


def current():
    """The phone job this thread is running, or None (friday.py: no PC speaker, no Hello box, no panel)."""
    return getattr(_local, "job", None)


# ---------- server ----------
class Server:
    """on_turn(job, text, pcm16k_bytes) runs FRIDAY on the job's thread; on_pair(name) -> bool asks Windows Hello;
    on_alert(text) tells the owner on the PC (tray balloon)."""

    def __init__(self, on_turn, on_pair, on_alert, port=PORT, host="::", on_history=None):
        self.on_turn, self.on_pair, self.on_alert, self.on_history = on_turn, on_pair, on_alert, on_history
        self.jobs, self.nonces, self.fails, self.banned, self.lock = {}, {}, {}, {}, threading.Lock()
        self.total_fails = []
        ensure_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(*_paths(), password=security.secret("remote_key_pw"))
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            server_version, sys_version, timeout = "FRIDAY", "", 30

            def log_message(self, *a):
                pass

            def setup(self):
                self.request.do_handshake()  # here, on this request's thread (review §70: not on the accept loop)
                super().setup()

            def do_GET(self):
                outer._handle(self, "GET")

            def do_POST(self):
                outer._handle(self, "POST")

        class S(http.server.ThreadingHTTPServer):
            address_family, daemon_threads = socket.AF_INET6, True

            def server_bind(self):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)  # IPv6 only, as asked
                super().server_bind()

            def get_request(self):
                sock, addr = self.socket.accept()
                sock.settimeout(30)
                return ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

            def handle_error(self, request, client_address):
                pass  # TLS handshakes from scanners etc.: not worth a traceback in the log

        self.httpd = S((host, port), H)
        self.port = self.httpd.server_address[1]

    def start(self):
        addresses(cached=True)  # warm the address cache off the request path
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    stopped = False

    def stop(self):
        self.stopped = True
        self.httpd.shutdown()
        self.httpd.server_close()

    # --- abuse limits ---
    @staticmethod
    def _who(ip):
        """Abuse is counted per /64 (one home or phone line) — per /128 a single attacker has endless addresses."""
        try:
            return str(ipaddress.IPv6Network(ip.split("%")[0] + "/64", strict=False))
        except ValueError:
            return ip

    def _bad(self, ip, why):
        ip = self._who(ip)
        now = time.time()
        with self.lock:
            f = self.fails.setdefault(ip, [])
            f[:] = [t for t in f if now - t < 600] + [now]
            if len(f) >= 5:
                self.banned[ip] = now + 3600
            self.total_fails[:] = [t for t in self.total_fails if now - t < 3600] + [now]
            many = len(self.total_fails) >= 50
        security.audit("phone", "remote_refused", ip, "denied", why)
        if many:
            self.on_alert("มีคนพยายามเข้า FRIDAY จากเน็ตผิดๆ หลายครั้ง — ปิดรับคำสั่งจากมือถือแล้ว (เปิดใหม่ได้ที่เมนู tray)")
            threading.Thread(target=self.stop, daemon=True).start()

    def _reply(self, h, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        h.send_response(code)
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(body)

    def _handle(self, h, method):
        ip = h.client_address[0]
        try:
            if self.banned.get(self._who(ip), 0) > time.time() and h.path != "/pair":  # re-pairing stays possible (review §73)
                return self._reply(h, 403, {"error": "blocked"})
            n = int(h.headers.get("Content-Length") or 0)
            if n < 0 or n > BODY_MAX:
                self._bad(ip, "body size")
                return self._reply(h, 413, {"error": "too large"})
            body = h.rfile.read(n) if n else b""
            path = h.path.split("?")[0]
            if method == "POST" and path == "/pair":
                return self._pair(h, ip, body)
            dev = self._auth(h, ip, method, path, body)
            if dev is None:
                return self._reply(h, 401, {"error": "unauthorized"})
            dev_id, info = dev
            if method == "POST" and path in ("/ask", "/voice"):
                return self._start(h, dev_id, info, body, path == "/voice")
            if method == "GET" and path.startswith("/job/"):
                job = self.jobs.get(path[5:])
                if not job or job.dev != dev_id:
                    return self._reply(h, 404, {"error": "no such job"})
                return self._reply(h, 200, job.view())
            if method == "POST" and path.startswith("/approve/"):
                job = self.jobs.get(path[9:])
                if not job or job.dev != dev_id:
                    return self._reply(h, 404, {"error": "no such job"})
                sig = (json.loads(body or b"{}") or {}).get("sig", "")
                question = job.question  # answer() wakes the job thread, which clears it
                ok = job.answer(sig, info["a"])
                security.audit("phone", "remote_approve", f"{info['name']}: {question[:80]}", "done" if ok else "declined")
                return self._reply(h, 200, {"ok": ok})
            if method == "GET" and path.startswith("/history/") and self.on_history:  # §73 chats typed on the PC
                return self._reply(h, 200, self.on_history(int(path[9:])))
            if method == "GET" and path == "/hello":
                return self._reply(h, 200, {"ok": True, "name": "FRIDAY"})
            return self._reply(h, 404, {"error": "not found"})
        except (ValueError, KeyError, json.JSONDecodeError):
            self._bad(ip, "bad request")
            return self._reply(h, 400, {"error": "bad request"})

    def _pair(self, h, ip, body):
        req = json.loads(body)
        if not _take_code(req.get("t", "")):
            self._bad(ip, "pair code")
            return self._reply(h, 403, {"error": "pairing code wrong or expired — make a new QR"})
        name = "".join(ch for ch in str(req.get("name", "phone")) if ch.isprintable())[:40] or "phone"
        _pub(req["d"]), _pub(req["a"])  # both must be real public keys
        if not self.on_pair(name):
            security.audit("phone", "remote_pair", name, "declined")
            return self._reply(h, 403, {"error": "not approved on the PC"})
        dev_id = secrets.token_hex(8)
        d = devices()
        d[dev_id] = {"name": name, "d": req["d"], "a": req["a"], "created": time.strftime("%Y-%m-%d %H:%M")}
        _save_devices(d)
        security.audit("phone", "remote_pair", name, "done", dev_id)
        return self._reply(h, 200, {"id": dev_id})

    def _auth(self, h, ip, method, path, body):
        dev_id, ts, nonce, sig = (h.headers.get(k, "") for k in ("X-Friday-Device", "X-Friday-Time", "X-Friday-Nonce", "X-Friday-Sig"))
        info = devices().get(dev_id)
        now = time.time()
        if not info or not nonce or len(nonce) > 64 or abs(now - int(ts or 0) / 1000) > SKEW_S:
            self._bad(ip, "unknown device / clock")
            return None
        with self.lock:
            self.nonces = {k: t for k, t in self.nonces.items() if now - t < 2 * SKEW_S}
            if nonce in self.nonces:
                replay = True
            else:
                replay = False
                self.nonces[nonce] = now
        if replay or not _verify(info["d"], sig, signed_text(method, path, ts, nonce, body)):
            self._bad(ip, "replay" if replay else "signature")
            return None
        return dev_id, info

    def _start(self, h, dev_id, info, body, voice):
        if voice:
            text, pcm = None, body
        else:
            text, pcm = str(json.loads(body).get("text", "")).strip()[:4000], None
            if not text:
                return self._reply(h, 400, {"error": "empty"})
        job = Job(dev_id, info["name"])
        job.speak = h.headers.get("X-Friday-Speak", "1") != "0"  # not signed: it only decides whether audio comes back
        job.ids_ok = h.headers.get("X-Friday-Voice") == "ids"  # review §73: an older app gets a WAV
        with self.lock:
            self.jobs = {k: j for k, j in self.jobs.items() if time.time() - j.created < 900}
            self.jobs[job.id] = job

        def run():
            _local.job = job
            try:
                self.on_turn(job, text, pcm)
            except Exception as e:
                job.replies.append(f"เกิดข้อผิดพลาดค่ะ ({type(e).__name__})")
            finally:
                _local.job = None
                job.status = "done"
        threading.Thread(target=run, daemon=True).start()
        return self._reply(h, 202, {"id": job.id})


if __name__ == "__main__":  # selftest: real TLS on ::1, a fake phone with its own keys
    import http.client, tempfile, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    tmp = tempfile.mkdtemp()
    security.SECRETS, security.AUDIT, DIR = os.path.join(tmp, "s.dat"), os.path.join(tmp, "audit.log"), os.path.join(tmp, "remote")
    pair_ok = [True]
    alerts = []

    def on_turn(job, text, pcm):
        if text == "ช้า":  # §72: the text is visible ("replied") while the voice is still being made
            job.replies.append("ตอบแล้ว")
            job.status = "replied"
            time.sleep(0.5)
            job.audio.append(b"RIFF")
            return
        if text == "ปิดเครื่อง":
            job.replies.append("ปิดแล้ว" if current().approve("ปิดเครื่อง?") else "ไม่ได้ปิด")
        else:
            job.replies.append(f"echo {text}" if text else f"pcm {len(pcm)}")
        job.audio.append(b"RIFF")

    srv = Server(on_turn, lambda name: pair_ok[0], alerts.append, port=0, host="::1").start()
    fp = fingerprint()

    def conn():
        c = http.client.HTTPSConnection("::1", srv.port, context=ssl._create_unverified_context(), timeout=10)
        c.connect()
        assert hashlib.sha256(c.sock.getpeercert(binary_form=True)).hexdigest() == fp  # what the phone pins
        assert c.sock.version() == "TLSv1.3"
        return c

    def call(method, path, obj=None, raw=None, dev=None, key=None, ts=None, nonce=None, sig=None):
        body = raw if raw is not None else (json.dumps(obj).encode() if obj is not None else b"")
        hdr = {"Content-Length": str(len(body))}
        if dev:
            ts = str(ts or int(time.time() * 1000))
            nonce = nonce or secrets.token_hex(12)
            sig = sig or base64.b64encode(key.sign(signed_text(method, path, ts, nonce, body), ec.ECDSA(hashes.SHA256()))).decode()
            hdr.update({"X-Friday-Device": dev, "X-Friday-Time": ts, "X-Friday-Nonce": nonce, "X-Friday-Sig": sig})
        c = conn()
        c.request(method, path, body=body, headers=hdr)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    pem = lambda k: k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    kd, ka, evil = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    assert pick(["fe80::1%4", "2606:4700:4700::1111", "fd7a:115c:a1e0::12", "fd00::1", "::1", "junk"]) == \
        ["fd7a:115c:a1e0::12", "2606:4700:4700::1111"]  # Tailscale first; link-local / other ULA / loopback never
    qr = json.loads(pair_payload())
    assert qr["f"] == fp and qr["t"] and qr["p"] == PORT
    assert call("POST", "/pair", {"t": "wrong", "name": "x", "d": pem(kd), "a": pem(ka)})[0] == 403
    st, r = call("POST", "/pair", {"t": qr["t"], "name": "Pixel", "d": pem(kd), "a": pem(ka)})
    assert st == 200 and r["id"] in devices(), (st, r)
    dev = r["id"]
    assert call("POST", "/pair", {"t": qr["t"], "name": "again", "d": pem(evil), "a": pem(evil)})[0] == 403  # code is single-use
    pair_ok[0] = False
    assert call("POST", "/pair", {"t": json.loads(pair_payload())["t"], "name": "x", "d": pem(evil), "a": pem(evil)})[0] == 403  # PC said no
    srv.fails.clear(), srv.banned.clear()

    def run_job(text):
        st, r = call("POST", "/ask", {"text": text}, dev=dev, key=kd)
        assert st == 202, (st, r)
        for _ in range(100):
            st, v = call("GET", f"/job/{r['id']}", dev=dev, key=kd)
            if v["status"] != "running":
                return r["id"], v
            time.sleep(0.05)
        raise AssertionError("job stuck")

    st, r = call("POST", "/ask", {"text": "ช้า"}, dev=dev, key=kd)
    time.sleep(0.2)
    v = call("GET", f"/job/{r['id']}", dev=dev, key=kd)[1]
    assert v["status"] == "replied" and v["reply"] == "ตอบแล้ว" and "audio" not in v and "h" in v, v
    time.sleep(0.5)
    assert call("GET", f"/job/{r['id']}", dev=dev, key=kd)[1]["audio"] == [base64.b64encode(b"RIFF").decode()]
    _, v = run_job("สวัสดี")
    assert v["status"] == "done" and v["reply"] == "echo สวัสดี" and v["audio"] == [base64.b64encode(b"RIFF").decode()], v
    # a dangerous command waits for a signature by key A over (job, challenge)
    jid, v = run_job("ปิดเครื่อง")
    assert v["status"] == "confirm" and v["question"] == "ปิดเครื่อง?", v
    bad = base64.b64encode(evil.sign(f"{jid}\n{v['challenge']}".encode(), ec.ECDSA(hashes.SHA256()))).decode()
    assert call("POST", f"/approve/{jid}", {"sig": bad}, dev=dev, key=kd)[1] == {"ok": False}
    time.sleep(0.2)
    assert call("GET", f"/job/{jid}", dev=dev, key=kd)[1]["reply"] == "ไม่ได้ปิด"
    jid, v = run_job("ปิดเครื่อง")
    good = base64.b64encode(ka.sign(f"{jid}\n{v['challenge']}".encode(), ec.ECDSA(hashes.SHA256()))).decode()
    assert call("POST", f"/approve/{jid}", {"sig": good}, dev=dev, key=kd)[1] == {"ok": True}
    time.sleep(0.2)
    assert call("GET", f"/job/{jid}", dev=dev, key=kd)[1]["reply"] == "ปิดแล้ว"
    # voice: raw PCM body
    st, r = call("POST", "/voice", raw=b"\0\0" * 1600, dev=dev, key=kd)
    time.sleep(0.2)
    assert call("GET", f"/job/{r['id']}", dev=dev, key=kd)[1]["reply"] == "pcm 3200"
    # forged / replayed / stale / wrong key are refused; 5 failures ban the address
    n = secrets.token_hex(8)
    assert call("GET", "/hello", dev=dev, key=kd, nonce=n)[0] == 200
    assert call("GET", "/hello", dev=dev, key=kd, nonce=n)[0] == 401  # replay
    assert call("GET", "/hello", dev=dev, key=evil)[0] == 401  # someone else's key
    assert call("GET", "/hello", dev=dev, key=kd, ts=int(time.time() * 1000) - 120000)[0] == 401  # old
    assert call("GET", "/hello")[0] == 401  # no signature
    assert call("GET", "/hello", dev="nope", key=kd)[0] == 401
    assert call("GET", "/hello", dev=dev, key=kd)[0] == 403  # banned now, even when signed right
    assert Server._who("2001:db8:85b8:1::1") == Server._who("2001:db8:85b8:1:ffff::2") == "2001:db8:85b8:1::/64"
    srv.banned.clear()
    assert call("GET", "/hello", dev=dev, key=kd)[0] == 200
    import socket as _s  # a silent TCP connection must not block the next client (handshake off the accept loop)
    idle = _s.create_connection(("::1", srv.port))
    assert call("GET", "/hello", dev=dev, key=kd)[0] == 200
    idle.close()
    assert forget(dev) and call("GET", "/hello", dev=dev, key=kd)[0] == 401  # forgotten phone is out at once
    srv.stop()
    assert srv.stopped
    print("REMOTE SELFTEST OK")
