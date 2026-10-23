package local.friday.remote

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.sin

// The PC panel's palette (app/ui.html): near-black glass, cyan + violet light, soft white text
val Ink = Color(0xFF0B0C11)
val Glass = Color(0xFF16181F)
val Line = Color(0xFF2C3040)
val Cyan = Color(0xFF3EE6FF)
val Violet = Color(0xFF8B5CF6)
val Soft = Color(0xFFE8E8EE)
val Dim = Color(0xFF8A8FA3)

@Composable
fun FridayTheme(content: @Composable () -> Unit) = MaterialTheme(
    colorScheme = darkColorScheme(primary = Cyan, secondary = Violet, background = Ink, surface = Glass,
        onPrimary = Ink, onBackground = Soft, onSurface = Soft, outline = Line),
    content = content,
)

enum class Mood { Idle, Listening, Thinking, Speaking }

/** The FRIDAY orb: layered cyan/violet light that breathes; faster and brighter while listening/thinking/speaking. */
@Composable
fun Orb(mood: Mood, size: Int, modifier: Modifier = Modifier) {
    val speed = when (mood) { Mood.Idle -> 9000; Mood.Listening -> 5000; Mood.Thinking -> 3200; Mood.Speaking -> 4200 }
    val t = rememberInfiniteTransition(label = "orb")
    val turn by t.animateFloat(0f, 6.2832f, infiniteRepeatable(tween(speed, easing = LinearEasing)), label = "turn")
    val breath by t.animateFloat(0.92f, 1.04f, infiniteRepeatable(tween(speed / 3), RepeatMode.Reverse), label = "breath")
    val glow by animateFloatAsState(if (mood == Mood.Idle) 0.55f else 0.95f, tween(600), label = "glow")
    Canvas(modifier.size(size.dp).semantics { contentDescription = "FRIDAY ${mood.name}" }) {
        val r = this.size.minDimension / 2 * breath
        val c = center
        drawCircle(Brush.radialGradient(listOf(Cyan.copy(alpha = 0.22f * glow), Color.Transparent), c, r * 1.6f), r * 1.6f, c)
        for (i in 0 until 3) {
            val a = turn + i * 2.094f
            val p = Offset(c.x + cos(a) * r * 0.22f, c.y + sin(a) * r * 0.22f)
            val col = listOf(Cyan, Violet, Color(0xFF5B8CFF))[i]
            drawCircle(Brush.radialGradient(listOf(col.copy(alpha = 0.85f * glow), col.copy(alpha = 0f)), p, r * 0.9f), r * 0.9f, p)
        }
        drawCircle(Brush.radialGradient(listOf(Color.White.copy(alpha = 0.55f * glow), Color.Transparent), c, r * 0.45f), r * 0.45f, c)
    }
}

data class Msg(val role: String, val text: String) // role: you | friday | note

@Composable
fun Bubble(m: Msg) {
    val mine = m.role == "you"
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        when (m.role) {
            "note" -> Text(m.text, color = Dim, fontSize = 13.sp, modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp))
            else -> Text(
                m.text, color = if (mine) Ink else Soft, fontSize = 16.sp, lineHeight = 22.sp,
                modifier = Modifier.widthIn(max = 300.dp)
                    .clip(RoundedCornerShape(20.dp, 20.dp, if (mine) 6.dp else 20.dp, if (mine) 20.dp else 6.dp))
                    .background(if (mine) Brush.linearGradient(listOf(Cyan, Color(0xFF7FD8FF))) else Brush.linearGradient(listOf(Glass, Glass)))
                    .then(if (mine) Modifier else Modifier.border(1.dp, Line, RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }
    }
}

/** Pill composer like the PC panel: text, then mic (or stop while recording) and send. */
@Composable
fun Composer(text: String, onText: (String) -> Unit, recording: Boolean, onMic: () -> Unit, onSend: () -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Glass).border(1.dp, Line, RoundedCornerShape(28.dp))
        .padding(start = 6.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        TextField(text, onText, Modifier.weight(1f), placeholder = { Text("สั่ง FRIDAY…", color = Dim) }, maxLines = 4,
            colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
                focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent, cursorColor = Cyan,
                focusedTextColor = Soft, unfocusedTextColor = Soft))
        IconButton(onMic, colors = IconButtonDefaults.iconButtonColors(containerColor = if (recording) Color(0xFFFF4D6D) else Color.Transparent)) {
            Icon(painterResource(if (recording) R.drawable.ic_stop else R.drawable.ic_mic), if (recording) "หยุดอัด" else "พูด",
                tint = if (recording) Color.White else Cyan)
        }
        IconButton(onSend, enabled = text.isNotBlank(), colors = IconButtonDefaults.iconButtonColors(containerColor = Cyan,
            disabledContainerColor = Line)) {
            Icon(painterResource(R.drawable.ic_send), "ส่ง", tint = Ink, modifier = Modifier.size(20.dp))
        }
    }
}

/** First screen until paired: the orb, what to do on the PC, one button. */
@Composable
fun PairScreen(status: String, onScan: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Orb(Mood.Idle, 200)
        Spacer(Modifier.height(24.dp))
        Text("จับคู่กับ PC", color = Soft, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text("ที่ PC: คลิกขวาไอคอน FRIDAY › มือถือ › จับคู่มือถือ…\nแล้วสแกน QR ที่ขึ้นบนจอ", color = Dim, fontSize = 14.sp,
            lineHeight = 20.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 32.dp))
        Spacer(Modifier.height(28.dp))
        Box(Modifier.clip(CircleShape).background(Brush.linearGradient(listOf(Cyan, Violet)))) {
            IconButton(onScan, Modifier.size(width = 200.dp, height = 52.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(painterResource(R.drawable.ic_qr), null, tint = Ink)
                    Spacer(Modifier.size(8.dp))
                    Text("สแกน QR", color = Ink, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        if (status.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            Text(status, color = Dim, fontSize = 13.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 32.dp))
        }
    }
}
