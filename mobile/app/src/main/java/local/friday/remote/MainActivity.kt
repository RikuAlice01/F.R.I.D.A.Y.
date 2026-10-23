package local.friday.remote

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Base64
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.concurrent.thread

/**
 * FRIDAY remote (PLAN §70–§72). Opens behind the phone's fingerprint/face/PIN; chat with the PC's FRIDAY by text or
 * voice; what the PC would guard with Windows Hello asks for the fingerprint/PIN here (key A signs the challenge).
 * UI: Jetpack Compose + Material 3, edge-to-edge (android/skills: migrate-xml-views-to-jetpack-compose, edge-to-edge).
 */
class MainActivity : FragmentActivity() {
    private val remote by lazy { Remote(getSharedPreferences("friday", MODE_PRIVATE)) }
    private val store by lazy { ChatStore(File(filesDir, "chat.bin")) }
    private val voice by lazy { PhoneVoice(this) }
    private val prefs by lazy { getSharedPreferences("friday", MODE_PRIVATE) }
    @Volatile private var syncing = false
    private val saver = java.util.concurrent.Executors.newSingleThreadExecutor() // history saves in order, one at a time
    private val messages = mutableStateListOf<Msg>()
    private var mood by mutableStateOf(Mood.Idle)
    private var paired by mutableStateOf(false)
    private var speak by mutableStateOf(true)
    private var recording by mutableStateOf(false)
    private var draft by mutableStateOf("")
    private var pairStatus by mutableStateOf("")
    private var askUnpair by mutableStateOf(false)
    private var askClear by mutableStateOf(false)
    private var unlocked = false
    private var prompting = false // the PIN screen is its own activity: our onStop/onResume run meanwhile
    private var recognizer: SpeechRecognizer? = null
    private var sttPc = false // this session: the phone has no on-device Thai, use the PC

    private val scan = registerForActivityResult(ScanContract()) { r -> r.contents?.let { pair(it) } }

    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE) // no screenshots / recents preview
        paired = remote.paired
        speak = remote.speak
        messages.addAll(store.load()) // §72 encrypted history
        setContent {
            FridayTheme {
                Scaffold(
                    containerColor = Ink,
                    contentWindowInsets = WindowInsets.safeDrawing,
                    topBar = {
                        CenterAlignedTopAppBar(
                            title = { Text("F.R.I.D.A.Y.", color = Cyan, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 3.sp) },
                            navigationIcon = {
                                if (paired) IconButton({ askUnpair = true }) { Icon(painterResource(R.drawable.ic_unlink), "ลบการจับคู่", tint = Dim) }
                            },
                            actions = {
                                if (paired) {
                                    IconButton({ askClear = true }) { Icon(painterResource(R.drawable.ic_delete), "ล้างแชต", tint = Soft) }
                                    IconButton({ speak = !speak; remote.speak = speak }) {
                                        Icon(painterResource(if (speak) R.drawable.ic_volume else R.drawable.ic_volume_off),
                                            if (speak) "ปิดเสียงตอบ" else "เปิดเสียงตอบ", tint = Soft)
                                    }
                                    IconButton({ startScan() }) { Icon(painterResource(R.drawable.ic_qr), "จับคู่ใหม่", tint = Soft) }
                                }
                            },
                            colors = TopAppBarDefaults.centerAlignedTopAppBarColors(containerColor = Ink),
                        )
                    },
                ) { inner ->
                    if (!paired) PairScreen(pairStatus, ::startScan, Modifier.fillMaxSize().padding(inner)) else Chat(inner)
                    if (askClear) AlertDialog( // §74 clears the PC session too (fingerprint/PIN like Windows Hello)
                        onDismissRequest = { askClear = false },
                        title = { Text("ล้างแชต?") },
                        text = { Text("ลบบทสนทนาทั้งบนมือถือและบน PC (session ปัจจุบัน) — ยืนยันด้วยนิ้ว/PIN") },
                        confirmButton = { TextButton({ askClear = false; send("ล้างแชท") }) { Text("ล้าง") } },
                        dismissButton = { TextButton({ askClear = false }) { Text("ยกเลิก") } },
                        containerColor = Glass,
                    )
                    if (askUnpair) AlertDialog(
                        onDismissRequest = { askUnpair = false },
                        title = { Text("ลบการจับคู่?") },
                        text = { Text("มือถือนี้จะสั่ง FRIDAY ไม่ได้จนกว่าจะสแกน QR ใหม่ · ที่ PC ลบได้ที่ tray › มือถือ") },
                        confirmButton = { TextButton({ askUnpair = false; remote.unpair(); paired = false; pairStatus = "" }) { Text("ลบ") } },
                        dismissButton = { TextButton({ askUnpair = false }) { Text("ยกเลิก") } },
                        containerColor = Glass,
                    )
                }
            }
        }
    }

    @Composable
    private fun Chat(inner: PaddingValues) {
        val list = rememberLazyListState()
        LaunchedEffect(messages.size) { if (messages.isNotEmpty()) list.animateScrollToItem(messages.size) }
        // Scaffold's contentWindowInsets = safeDrawing includes the keyboard: no extra imePadding (avoids double padding)
        Column(Modifier.fillMaxSize().padding(inner).consumeWindowInsets(inner)) {
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, contentPadding = PaddingValues(16.dp, 8.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp)) {
                item {
                    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) {
                        Orb(mood, if (messages.isEmpty()) 180 else 96)
                    }
                }
                items(messages) { Bubble(it) }
            }
            Composer(draft, { draft = it }, recording, ::toggleMic, { send(draft) }, Modifier.padding(12.dp))
        }
    }

    override fun onResume() {
        super.onResume()
        if (!unlocked && !prompting) unlock()
        if (!syncing) { syncing = true; thread { while (syncing) { if (paired && unlocked) syncPcChat(); Thread.sleep(3000) } } }
    }

    override fun onStop() {
        super.onStop()
        if (!prompting) unlocked = false // leaving the app locks it again
        if (recording) toggleMic()
        syncing = false
        thread { voice.release() } // the voice model (~0.4 GB) only while the app is open (waits for speech to end)
    }

    /** §73 chat typed on the PC shows here as text (its voice stays on the PC). First look = start from now. */
    private fun syncPcChat() {
        try {
            val last = prefs.getInt("hist_last", -1)
            val r = remote.call("GET", "/history/${maxOf(last, 0)}")
            if (r.getInt("_code") == 401) return forgotten() // review §73: polling on would get this phone banned
            if (r.getInt("_code") != 200) return
            val total = r.getInt("total")
            val session = r.optString("session")
            val cleared = r.optString("cleared")
            if (last >= 0 && session == prefs.getString("hist_session", "") && cleared.isNotEmpty() && cleared != prefs.getString("hist_cleared", "")) {
                runOnUiThread { // §74 the session was cleared (on the PC, or from here): this copy goes too
                    messages.clear()
                    saver.execute { store.clear() }
                    note("ล้างบทสนทนาแล้ว — ทั้ง PC และมือถือ")
                }
            } else if (last >= 0 && session == prefs.getString("hist_session", "")) {
                val items = r.getJSONArray("items")
                for (i in 0 until items.length()) items.getJSONObject(i).let {
                    add(Msg(it.getString("role"), (if (it.getString("role") == "you") "💻 " else "") + it.getString("text")))
                }
            }
            prefs.edit().putInt("hist_last", total).putString("hist_session", session).putString("hist_cleared", cleared).apply()
        } catch (e: Exception) { /* offline: try again in 3 s */ }
    }

    /** One message on screen + into the encrypted history. */
    private fun add(m: Msg) = runOnUiThread {
        messages.add(m)
        val snapshot = messages.toList()
        saver.execute { store.save(snapshot) } // review §73: parallel saves to one file lost/corrupted history
    }

    /** The PC removed this phone: stop asking (each refused request counts toward a ban) and show the pair screen. */
    private fun forgotten() = runOnUiThread {
        syncing = false
        remote.unpair()
        paired = false
        pairStatus = "PC ลบมือถือนี้แล้ว — สแกน QR ใหม่เพื่อจับคู่"
    }

    private fun note(text: String) = add(Msg("note", text))

    // ---------- unlock: the phone's own fingerprint / face / PIN ----------
    private fun unlock() {
        val info = BiometricPrompt.PromptInfo.Builder().setTitle("F.R.I.D.A.Y.").setSubtitle("ปลดล็อกเพื่อสั่งงาน")
            .setAllowedAuthenticators(BIOMETRIC_STRONG or DEVICE_CREDENTIAL).build()
        BiometricPrompt(this, ContextCompat.getMainExecutor(this), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) { prompting = false; unlocked = true }
            override fun onAuthenticationError(code: Int, msg: CharSequence) { prompting = false; finish() }
        }).authenticate(info)
        prompting = true
    }

    // ---------- pairing ----------
    private fun startScan() {
        scan.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("สแกน QR บนจอ PC").setBeepEnabled(false).setOrientationLocked(false))
    }

    private fun pair(qr: String) {
        pairStatus = "กำลังจับคู่… ยืนยันด้วย Windows Hello ที่ PC"
        mood = Mood.Thinking
        thread {
            val err = try { remote.pair(qr, Build.MODEL) } catch (e: Exception) { e.message ?: "ผิดพลาด" }
            runOnUiThread {
                mood = Mood.Idle
                if (err == null) { paired = true; pairStatus = ""; note("จับคู่แล้ว ✓ สั่งงาน FRIDAY ได้เลย") }
                else { pairStatus = "จับคู่ไม่สำเร็จ: $err"; if (paired) note(pairStatus) }
            }
        }
    }

    // ---------- asking ----------
    private fun ready(): Boolean {
        if (!unlocked) { unlock(); return false }
        return true
    }

    private fun send(raw: String) {
        val text = raw.trim()
        if (text.isEmpty() || !ready()) return
        draft = ""
        add(Msg("you", text))
        mood = Mood.Thinking
        thread { run("/ask", JSONObject().put("text", text).toString().toByteArray()) }
    }

    private fun run(path: String, body: ByteArray) {
        try {
            val start = remote.call("POST", path, body, speak = speak)
            if (start.getInt("_code") == 401) return forgotten()
            if (start.getInt("_code") != 202) return note("ส่งไม่ได้ (${start.optString("error")})")
            val id = start.getString("id")
            var asked = ""
            var heard = false
            var shown = false
            while (true) {
                Thread.sleep(300) // §72 was 700 ms
                val v = remote.call("GET", "/job/$id")
                if (v.getInt("_code") >= 400) return note("งานนี้หายไปแล้ว (${v.optString("error")}) — PC รีสตาร์ท หรือมือถือถูกลบจาก PC")
                if (!heard && v.optString("heard").isNotEmpty()) { heard = true; add(Msg("you", "🎙 " + v.getString("heard"))) }
                val status = v.optString("status")
                if (status == "confirm" && v.getString("challenge") != asked) { asked = v.getString("challenge"); approve(id, v.getString("question"), asked) }
                if ((status == "replied" || status == "done") && !shown) { // §72 text first, voice after
                    shown = true
                    remote.rememberHosts(v.optJSONArray("h"))
                    add(Msg("friday", v.optString("reply")))
                    runOnUiThread { mood = if (speak) Mood.Speaking else Mood.Idle }
                    if (!speak) return
                }
                if (status == "done") {
                    if (speak) {
                        val vo = v.optJSONObject("voice") // §73 FRIDAY's voice made on this phone
                        try { if (vo != null) voice.speak(vo) { !speak } else play(v.optJSONArray("audio")) }
                        catch (e: Exception) { note("เล่นเสียงไม่ได้: ${e.message}") }
                    }
                    return
                }
            }
        } catch (e: Exception) {
            note("ต่อ PC ไม่ได้: ${e.message} — Tailscale บนมือถือเปิดอยู่ไหม / PC เปิดอยู่ไหม")
        } finally {
            runOnUiThread { mood = Mood.Idle }
        }
    }

    /** What would need Windows Hello on the PC: the phone's fingerprint/PIN unlocks key A, which signs the challenge. */
    private fun approve(id: String, question: String, challenge: String) = runOnUiThread {
        val info = BiometricPrompt.PromptInfo.Builder().setTitle("FRIDAY ขออนุญาต").setDescription(question)
            .setAllowedAuthenticators(BIOMETRIC_STRONG or DEVICE_CREDENTIAL).build()
        fun answer(sig: ByteArray?) = thread { // a network error here must not crash the app (review §70)
            try { remote.approve(id, sig) } catch (e: Exception) { note("ส่งคำตอบไม่ได้: ${e.message}") }
        }
        BiometricPrompt(this, ContextCompat.getMainExecutor(this), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                prompting = false
                answer(result.cryptoObject!!.signature!!.apply { update("$id\n$challenge".toByteArray()) }.sign())
                note("✓ อนุญาต: $question")
            }
            override fun onAuthenticationError(code: Int, msg: CharSequence) {
                prompting = false
                answer(null)
                note("✗ ไม่อนุญาต: $question")
            }
        }).authenticate(info, BiometricPrompt.CryptoObject(remote.approvalSignature()))
        prompting = true
    }

    private fun play(audio: JSONArray?) {
        if (audio == null) return
        for (i in 0 until audio.length()) {
            val f = File(cacheDir, "reply$i.wav").apply { writeBytes(Base64.decode(audio.getString(i), Base64.DEFAULT)) }
            val done = Object()
            val mp = MediaPlayer().apply { setDataSource(f.path); prepare() }
            mp.setOnCompletionListener { synchronized(done) { done.notifyAll() } }
            synchronized(done) { mp.start(); done.wait(120000) }
            mp.release()
            f.delete()
        }
    }

    // ---------- voice ----------
    // §72 owner: "บนมือถือมีฟังก์ชันการพิมพ์ด้วยเสียงอยู่ลองใช้จากมือถือเลย" — the phone's ON-DEVICE recogniser (Android 12+):
    // the voice stays on the phone (the cloud recogniser is never used — FRIDAY's rule: no audio leaves the owner's
    // devices). No on-device Thai on this phone = record and let the PC's Whisper transcribe, as before.
    private fun toggleMic() {
        if (recording) { recognizer?.stopListening(); recording = false; return }
        if (!ready()) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1); return
        }
        recording = true
        mood = Mood.Listening
        // on-device recognition exists from Android 12 (API 31); minSdk is 30 (review §73)
        if (Build.VERSION.SDK_INT >= 31 && SpeechRecognizer.isOnDeviceRecognitionAvailable(this) && !sttPc) listenOnPhone()
        else recordForPc()
    }

    private fun sttIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "th-TH")
        .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)

    @androidx.annotation.RequiresApi(31)
    private fun listenOnPhone() {
        val r = SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
        recognizer = r
        r.setRecognitionListener(object : RecognitionListener {
            override fun onPartialResults(b: Bundle) { b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { draft = it } }
            override fun onResults(b: Bundle) {
                recording = false; r.destroy(); recognizer = null
                val text = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                if (text.isBlank()) { mood = Mood.Idle; note("ไม่ได้ยิน — กด 🎙 แล้วพูดอีกครั้ง") } else send(text)
            }
            override fun onError(code: Int) {
                r.destroy(); recognizer = null
                if (code == SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED || code == SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE) {
                    if (Build.VERSION.SDK_INT >= 33) SpeechRecognizer.createOnDeviceSpeechRecognizer(this@MainActivity).triggerModelDownload(sttIntent())
                    sttPc = true
                    note("มือถือยังไม่มีภาษาไทยแบบในเครื่อง (ขอดาวน์โหลดให้แล้ว) — ระหว่างนี้ส่งเสียงไปถอดที่ PC")
                    recordForPc()
                } else {
                    recording = false; mood = Mood.Idle
                    if (code != SpeechRecognizer.ERROR_NO_MATCH && code != SpeechRecognizer.ERROR_SPEECH_TIMEOUT) note("ฟังไม่ได้ (รหัส $code)")
                    else note("ไม่ได้ยิน — กด 🎙 แล้วพูดอีกครั้ง")
                }
            }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        r.startListening(sttIntent())
    }

    /** Fallback: 16 kHz PCM to the PC's Whisper (on the owner's own PC, never a cloud service). */
    private fun recordForPc() {
        recording = true
        mood = Mood.Listening
        thread {
            val rate = 16000
            val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min * 4)
            val out = ByteArrayOutputStream()
            val buf = ByteArray(min)
            rec.startRecording()
            val t0 = System.currentTimeMillis()
            while (recording && System.currentTimeMillis() - t0 < 60000) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) out.write(buf, 0, n)
            }
            rec.stop(); rec.release()
            runOnUiThread { recording = false; mood = Mood.Thinking }
            if (out.size() > rate) run("/voice", out.toByteArray()) else { note("สั้นเกินไป — กด 🎙 พูด แล้วกด ⏹"); runOnUiThread { mood = Mood.Idle } }
        }
    }
}
