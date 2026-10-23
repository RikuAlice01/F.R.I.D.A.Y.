package local.friday.remote

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import org.json.JSONObject
import java.io.File
import java.nio.LongBuffer

/**
 * FRIDAY's own voice on the phone (§73): the same Vanira model the PC uses (packed in the APK). The PC sends the
 * phoneme ids (its Thai G2P is Python); this runs the model and plays it — same samples as the PC's voice.
 */
class PhoneVoice(private val ctx: Context) {
    private var session: OrtSession? = null
    private val env by lazy { OrtEnvironment.getEnvironment() }

    private fun session(): OrtSession {
        session?.let { return it }
        val f = File(ctx.filesDir, "tts.onnx")
        val size = ctx.assets.openFd("tts.onnx").use { it.length } // stored uncompressed (noCompress) -> real size
        if (f.length() != size) ctx.assets.open("tts.onnx").use { i -> f.outputStream().use { i.copyTo(it) } } // once per app version
        val opts = OrtSession.SessionOptions().apply { setIntraOpNumThreads(4) }
        return env.createSession(f.path, opts).also { session = it }
    }

    /** voice = {"speaker": n, "ids": [[...], ...]} — one piece after another, blocking. Synchronized with release():
     *  the model is never closed while it speaks (review §73). */
    @Synchronized
    fun speak(voice: JSONObject, stop: () -> Boolean = { false }) {
        val pieces = voice.getJSONArray("ids")
        val speaker = voice.optInt("speaker", 0)
        for (p in 0 until pieces.length()) {
            if (stop()) return
            val a = pieces.getJSONArray(p)
            val ids = LongArray(a.length()) { a.getLong(it) }
            if (ids.isEmpty()) continue
            play(synth(ids, speaker))
        }
    }

    private fun synth(ids: LongArray, speaker: Int): FloatArray {
        val s = session()
        val inputs = mapOf(
            "token_ids" to OnnxTensor.createTensor(env, LongBuffer.wrap(ids), longArrayOf(1, ids.size.toLong())),
            "pace" to OnnxTensor.createTensor(env, floatArrayOf(1f)),
            "speaker" to OnnxTensor.createTensor(env, intArrayOf(speaker)),
            "emotion" to OnnxTensor.createTensor(env, intArrayOf(0)),
            "pitch_mul" to OnnxTensor.createTensor(env, floatArrayOf(1f)),
            "pitch_add" to OnnxTensor.createTensor(env, floatArrayOf(0f)),
        )
        try {
            s.run(inputs).use { r ->
                val v = r[0].value
                val audio = when (v) {
                    is FloatArray -> v
                    is Array<*> -> (v.firstOrNull() as? FloatArray) ?: (v.firstOrNull() as? Array<*>)?.firstOrNull() as FloatArray
                    else -> FloatArray(0)
                }
                val peak = audio.maxOfOrNull { kotlin.math.abs(it) }?.coerceAtLeast(1e-6f) ?: 1f
                return FloatArray(audio.size) { audio[it] / peak * 0.9f } // same normalising as the PC
            }
        } finally {
            inputs.values.forEach { it.close() }
        }
    }

    private fun play(samples: FloatArray) {
        if (samples.isEmpty()) return
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_FLOAT).setSampleRate(RATE)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC).setBufferSizeInBytes(samples.size * 4).build()
        try {
            t.write(samples, 0, samples.size, AudioTrack.WRITE_BLOCKING)
            t.play()
            Thread.sleep(samples.size * 1000L / RATE + 120)
        } finally {
            t.release()
        }
    }

    /** Frees the model (~0.4 GB RAM) when the app goes to the background. */
    @Synchronized
    fun release() {
        session?.close()
        session = null
    }

    companion object { const val RATE = 44100 }
}
