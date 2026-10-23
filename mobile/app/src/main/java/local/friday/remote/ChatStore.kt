package local.friday.remote

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Chat history on the phone (§72): AES-256-GCM, the key lives in the Android Keystore and can't be exported — the
 * file (app-private) is unreadable outside this app, and tampering fails the GCM check (then history starts empty).
 */
class ChatStore(private val file: File, private val max: Int = 500) {
    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as SecretKey?)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return g.generateKey()
    }

    fun load(): List<Msg> = try {
        val b = file.readBytes()
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, b, 0, 12)) }
        val a = JSONArray(String(c.doFinal(b, 12, b.size - 12), Charsets.UTF_8))
        (0 until a.length()).map { a.getJSONObject(it).let { o -> Msg(o.getString("r"), o.getString("t")) } }
    } catch (e: Exception) { emptyList() } // no file yet, or not ours

    fun save(msgs: List<Msg>) {
        val a = JSONArray()
        msgs.takeLast(max).forEach { a.put(JSONObject().put("r", it.role).put("t", it.text)) }
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) } // Keystore picks the IV
        val tmp = File(file.path + ".tmp")
        tmp.writeBytes(c.iv + c.doFinal(a.toString().toByteArray(Charsets.UTF_8)))
        tmp.renameTo(file)
    }

    fun clear() {
        file.delete()
    }

    companion object { const val ALIAS = "friday_chat" }
}
