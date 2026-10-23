package local.friday.remote

import android.content.SharedPreferences
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * The app's real network code against the live FRIDAY on this PC (§70: app 2.0 set headers after connect() and every
 * request died with "Already connected"). Skipped unless FRIDAY_TEST_HOST / FRIDAY_TEST_FP are set.
 */
class RemoteCallTest {
    private class Prefs : SharedPreferences {
        val m = HashMap<String, Any?>()
        override fun getAll() = m
        override fun getString(k: String, d: String?) = m[k] as String? ?: d
        override fun getStringSet(k: String, d: MutableSet<String>?) = d
        override fun getInt(k: String, d: Int) = m[k] as Int? ?: d
        override fun getLong(k: String, d: Long) = d
        override fun getFloat(k: String, d: Float) = d
        override fun getBoolean(k: String, d: Boolean) = m[k] as Boolean? ?: d
        override fun contains(k: String) = m.containsKey(k)
        override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
            override fun putString(k: String, v: String?) = apply { m[k] = v }
            override fun putStringSet(k: String, v: MutableSet<String>?) = this
            override fun putInt(k: String, v: Int) = apply { m[k] = v }
            override fun putLong(k: String, v: Long) = this
            override fun putFloat(k: String, v: Float) = this
            override fun putBoolean(k: String, v: Boolean) = apply { m[k] = v }
            override fun remove(k: String) = apply { m.remove(k) }
            override fun clear() = apply { m.clear() }
            override fun commit() = true
            override fun apply() {}
        }
        override fun registerOnSharedPreferenceChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener?) {}
        override fun unregisterOnSharedPreferenceChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    }

    @Test
    fun postReachesFriday() {
        val host = System.getenv("FRIDAY_TEST_HOST")
        val fp = System.getenv("FRIDAY_TEST_FP")
        assumeTrue(host != null && fp != null)
        val r = Remote(Prefs())
        // a wrong pairing code: FRIDAY must answer 403 with its own message — proof the POST body arrived
        val res = r.call("POST", "/pair", """{"t":"wrong","name":"test","d":"x","a":"x"}""".toByteArray(), sign = false,
            hosts = listOf("fd00::dead", host!!), port = 47321, fp = fp) // first address unreachable: must move on
        assertEquals(403, res.getInt("_code"))
        assertTrue(res.getString("error"), res.getString("error").contains("pairing code"))
    }

    @Test(expected = SecurityException::class)
    fun wrongCertificateIsRefused() {
        val host = System.getenv("FRIDAY_TEST_HOST")
        assumeTrue(host != null)
        try {
            Remote(Prefs()).call("GET", "/hello", sign = false, hosts = listOf(host!!), port = 47321, fp = "0".repeat(64))
        } catch (e: Exception) {
            var c: Throwable? = e
            while (c != null && c !is SecurityException) c = c.cause
            throw c ?: e
        }
    }
}
