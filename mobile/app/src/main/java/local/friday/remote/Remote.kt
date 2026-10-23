package local.friday.remote

import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.net.URL
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Signature
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * Talks straight to the owner's PC (PLAN §70) — over Tailscale's or the public IPv6 address, HTTPS pinned to the PC
 * certificate's SHA-256 from the pairing QR. Two Android Keystore keys: D signs every request (no prompt), A signs
 * approvals and opens only after this phone's fingerprint/face/PIN. No UI here.
 */
class Remote(private val prefs: SharedPreferences) {
    val paired get() = prefs.getString("dev", null) != null
    var speak: Boolean
        get() = prefs.getBoolean("speak", true)
        set(v) = prefs.edit().putBoolean("speak", v).apply()

    /** The pairing stays until the owner removes it (here, or on the PC). §72 */
    fun unpair() {
        val ks = keyStore()
        listOf(prefs.getString("key_d", null), prefs.getString("key_a", null)).filterNotNull().forEach { ks.deleteEntry(it) }
        prefs.edit().remove("dev").remove("hosts").remove("fp").remove("port").remove("last").remove("key_d").remove("key_a").apply()
    }

    /** §72 the PC sends its current addresses with each answer: a new IPv6 prefix doesn't need a new pairing. */
    fun rememberHosts(h: JSONArray?) {
        if (h != null && h.length() > 0) prefs.edit().putString("hosts", h.toString()).apply()
    }

    // ---------- keys (private halves never leave the phone's secure hardware) ----------
    private fun keyStore() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private fun makeKey(alias: String, needsUser: Boolean): String {
        val spec = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1")).setDigests(KeyProperties.DIGEST_SHA256)
        if (needsUser) spec.setUserAuthenticationRequired(true)
            .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL)
            .setInvalidatedByBiometricEnrollment(false)
        val g = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        g.initialize(spec.build())
        val pub = g.generateKeyPair().public.encoded
        return "-----BEGIN PUBLIC KEY-----\n" + Base64.encodeToString(pub, Base64.NO_WRAP).chunked(64).joinToString("\n") + "\n-----END PUBLIC KEY-----\n"
    }

    /** "d" or "a": the key of the pairing in use (a re-pair makes new aliases and swaps only when the PC said yes). */
    private fun privateKey(which: String) = keyStore().getKey(prefs.getString("key_$which", "friday_$which"), null) as PrivateKey

    /** Key A, ready to sign once the phone's fingerprint/PIN prompt succeeds (BiometricPrompt.CryptoObject). */
    fun approvalSignature(): Signature = Signature.getInstance("SHA256withECDSA").apply { initSign(privateKey("a")) }

    // ---------- HTTPS pinned to the PC's certificate ----------
    private fun pinnedContext(fp: String): SSLContext {
        val tm = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = throw SecurityException()
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                val got = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded).joinToString("") { "%02x".format(it) }
                if (got != fp) throw SecurityException("certificate is not this FRIDAY's") // someone in the middle
            }
            override fun getAcceptedIssuers() = arrayOf<X509Certificate>()
        }
        return SSLContext.getInstance("TLSv1.3").apply { init(null, arrayOf(tm), SecureRandom()) }
    }

    /** One request. Signed with key D unless pairing. Tries the PC's addresses, the one that worked last first. */
    fun call(method: String, path: String, body: ByteArray = ByteArray(0), sign: Boolean = true,
             hosts: List<String>? = null, port: Int? = null, fp: String? = null, speak: Boolean = true): JSONObject {
        val hs = hosts ?: JSONArray(prefs.getString("hosts", "[]")).let { a -> (0 until a.length()).map { a.getString(it) } }
            .sortedBy { if (it == prefs.getString("last", "")) 0 else 1 }
        val ctx = pinnedContext(fp ?: prefs.getString("fp", "")!!)
        var err: Exception? = null
        for (h in hs) {
            val c = URL("https://[$h]:${port ?: prefs.getInt("port", 47321)}$path").openConnection() as HttpsURLConnection
            c.sslSocketFactory = ctx.socketFactory
            c.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true } // the pinned certificate is the check
            c.connectTimeout = 6000; c.readTimeout = 60000; c.requestMethod = method
            if (!speak) c.setRequestProperty("X-Friday-Speak", "0") // §72 no voice wanted: the PC skips making it
            c.setRequestProperty("X-Friday-Voice", "ids") // §73 this app speaks phoneme ids with its own model
            if (sign) {
                val ts = System.currentTimeMillis().toString()
                val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
                val bodyHash = MessageDigest.getInstance("SHA-256").digest(body).joinToString("") { "%02x".format(it) }
                val s = Signature.getInstance("SHA256withECDSA").apply {
                    initSign(privateKey("d")); update("$method\n$path\n$ts\n$nonce\n$bodyHash".toByteArray())
                }
                c.setRequestProperty("X-Friday-Device", prefs.getString("dev", ""))
                c.setRequestProperty("X-Friday-Time", ts)
                c.setRequestProperty("X-Friday-Nonce", nonce)
                c.setRequestProperty("X-Friday-Sig", Base64.encodeToString(s.sign(), Base64.NO_WRAP))
            }
            if (method == "POST") { c.doOutput = true; c.setFixedLengthStreamingMode(body.size) }
            // everything above must be set BEFORE connect(): after it HttpURLConnection throws "Already connected"
            // (§70 "จับคู่ไม่สำเร็จ" on Tailscale — app 2.0.1). Only a failed CONNECT moves on to the next address: once
            // the request is out, a lost answer must not send the command a second time (review §70)
            try { c.connect() } catch (e: Exception) { err = e; continue }
            if (method == "POST") c.outputStream.use { it.write(body) }
            val code = c.responseCode
            val text = (if (code < 400) c.inputStream else c.errorStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: "{}"
            prefs.edit().putString("last", h).apply()
            return JSONObject(text).put("_code", code)
        }
        throw err ?: IllegalStateException("no address")
    }

    /** Pairing from the QR's JSON. Returns null when paired, else what went wrong (Thai, for the screen). */
    fun pair(qr: String, deviceName: String): String? {
        val q = try { JSONObject(qr) } catch (e: Exception) { return "QR นี้ไม่ใช่ของ FRIDAY" }
        if (q.optString("app") != "friday") return "QR นี้ไม่ใช่ของ FRIDAY"
        val hosts = q.getJSONArray("h").let { a -> (0 until a.length()).map { a.getString(it) } }
        if (hosts.isEmpty()) return "QR ไม่มีที่อยู่ให้ต่อ — เปิด Tailscale ที่ PC แล้วเปิด QR ใหม่"
        // new keys under new names: a failed re-pair (old QR, "no" at the PC, no network) leaves the working pairing alone
        val tag = System.currentTimeMillis().toString()
        val body = JSONObject().put("t", q.getString("t")).put("name", deviceName)
            .put("d", makeKey("friday_d_$tag", false)).put("a", makeKey("friday_a_$tag", true)).toString().toByteArray()
        val r = try { call("POST", "/pair", body, sign = false, hosts = hosts, port = q.getInt("p"), fp = q.getString("f")) }
                catch (e: Exception) { JSONObject().put("_code", 0).put("error", "${e.message} — เปิดแอป Tailscale บนมือถือ (บัญชีเดียวกับ PC) แล้วลองใหม่") }
        if (r.getInt("_code") != 200) {
            keyStore().apply { deleteEntry("friday_d_$tag"); deleteEntry("friday_a_$tag") }
            return r.optString("error", "PC ไม่ยอมรับ")
        }
        val old = listOf(prefs.getString("key_d", null), prefs.getString("key_a", null))
        prefs.edit().putString("dev", r.getString("id")).putString("hosts", JSONArray(hosts).toString())
            .putInt("port", q.getInt("p")).putString("fp", q.getString("f"))
            .putString("key_d", "friday_d_$tag").putString("key_a", "friday_a_$tag").apply()
        keyStore().apply { old.filterNotNull().forEach { deleteEntry(it) } }
        return null
    }

    fun approve(id: String, sig: ByteArray?) {
        call("POST", "/approve/$id", JSONObject().put("sig", sig?.let { Base64.encodeToString(it, Base64.NO_WRAP) } ?: "").toString().toByteArray())
    }
}
