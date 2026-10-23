package local.friday.remote

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import org.junit.Rule
import org.junit.Test

/** Screenshots of the two screens (§71), rendered on the JVM — `gradle recordPaparazziRelease`. */
class ScreensTest {
    @get:Rule
    val paparazzi = Paparazzi(deviceConfig = DeviceConfig.PIXEL_6, theme = "android:Theme.Material.NoActionBar")

    @Test
    fun pairing() = paparazzi.snapshot {
        FridayTheme { Column(Modifier.fillMaxSize().background(Ink)) { Title(); PairScreen("", {}, Modifier.fillMaxSize()) } }
    }

    @Test
    fun chat() = paparazzi.snapshot {
        FridayTheme {
            Column(Modifier.fillMaxSize().background(Ink)) {
                Title()
                Column(Modifier.weight(1f).padding(16.dp, 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp), contentAlignment = Alignment.Center) { Orb(Mood.Speaking, 96) }
                    Bubble(Msg("you", "วันนี้อากาศเป็นยังไงบ้าง"))
                    Bubble(Msg("friday", "วันนี้ฟ้าใส อุณหภูมิ 29 องศา รู้สึกเหมือน 37 องศา มีโอกาสฝนตกอีกประมาณ 35% ค่ะ"))
                    Bubble(Msg("note", "✓ อนุญาต: ล้างบทสนทนาใน session นี้?"))
                    Bubble(Msg("you", "🎙 เปิดเพลงต่อ"))
                }
                Composer("", {}, false, {}, {}, Modifier.padding(12.dp))
            }
        }
    }

    @androidx.compose.runtime.Composable
    private fun Title() = Box(Modifier.fillMaxWidth().padding(top = 36.dp, bottom = 8.dp), contentAlignment = Alignment.Center) {
        Text("F.R.I.D.A.Y.", color = Cyan, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 3.sp)
    }
}
