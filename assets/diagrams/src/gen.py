"""FRIDAY README diagrams (PLAN §112) with the stack-diagram skill (github.com/caru-ini/stack-diagram, MIT):
template.html + this spec -> build.py (inline fonts/icons) -> PNG light + dark (Edge headless, .canvas at 2x).
python gen.py <skill-dir> <icons-dir> <out-dir>"""
import base64, json, os, re, subprocess, sys, time

SKILL, ICONS, OUT = sys.argv[1:4]
sys.path.insert(0, r"E:\friday\app")
import video  # Edge headless over DevTools (FRIDAY's own renderer)

DARK = {"ollama", "anthropic", "openai", "nvidia", "github", "qwen"}  # have <name>_dark for group labels


def node(cx, top, icon, name, role, tile=""):
    return f'''<div class="node" style="left:{cx - 66}px;top:{top}px"><div class="tile {tile}"><img src="%%ICON_{icon}%%" alt=""></div>
<div class="name"><span>{name}</span></div><div class="role"><span>{role}</span></div></div>'''


def group(cls, left, top, w, h, label, icon=None):
    img = ""
    if icon:
        img = (f'<img class="lt" src="%%ICON_{icon}%%" alt=""><img class="dk" src="%%ICON_{icon}_dark%%" alt="">' if icon in DARK
               else f'<img src="%%ICON_{icon}%%" alt="">')
    return f'<div class="group {cls}" style="left:{left}px; top:{top}px; width:{w}px; height:{h}px;"><div class="g-label">{img}{label}</div></div>'


def edge(cls, d, label=None, at=None, start=False):
    s = f'<path class="{cls}" d="{d}" marker-end="url(#ar)"' + (' marker-start="url(#ar)"' if start else "") + "/>"
    if label:
        x, y, *anchor = at
        lc = "el a" if cls.startswith("e") else "el"
        s += f'<text class="{lc}" x="{x}" y="{y}" text-anchor="{anchor[0] if anchor else "middle"}">{label}</text>'
    return s


D = {}

# 1 · overview -----------------------------------------------------------------------------------------------------
D["overview"] = dict(w=1000, h=620, kicker="FRIDAY · ภาพรวม", title="FRIDAY ทำงานอย่างไร",
    lede="คุณสั่งได้ 3 ทาง · FRIDAY คิดด้วยสมองที่คุณเลือก · ทุกการกระทำผ่านด่านในโค้ดก่อนถึงเครื่อง",
    groups=[group("gb", 10, 40, 180, 530, "คุณ", "user"), group("ga", 250, 40, 180, 530, "FRIDAY · ในเครื่อง", "python"),
            group("gb", 510, 40, 180, 530, "สมอง (เลือกได้)", "brain"), group("gb", 790, 40, 180, 530, "ผลลัพธ์", "sparkles")],
    nodes=[node(100, 100, "mic", "ไมค์", "Hey Friday"), node(100, 260, "panel", "แผงแชต", "พิมพ์ · คลิก"),
           node(100, 420, "phone", "มือถือ", "แอป F.R.I.D.A.Y."),
           node(340, 100, "shield", "ด่านความปลอดภัย", "กฎ · Windows Hello"), node(340, 260, "python", "FRIDAY", "แอป tray · Python"),
           node(340, 420, "obsidian", "Obsidian vault", "ความจำ · Markdown"),
           node(600, 100, "ollama", "Ollama", "qwen3.5:4b · ค่าเริ่มต้น"), node(600, 260, "claude", "Claude", "API key ของคุณ"),
           node(600, 420, "openai", "OpenAI", "API key ของคุณ"),
           node(880, 100, "speaker", "ลำโพง", "เสียง FRIDAY"), node(880, 260, "windows", "Windows · แอป", "เปิด · สั่ง · ใช้แอปแทน"),
           node(880, 420, "panel", "แผง + มือถือ", "ข้อความ · การ์ด")],
    edges=[edge("e", "M136 130 H220 V290 H304"), edge("e", "M136 290 H304"), edge("e", "M136 450 H220 V290 H304"),
           edge("e", "M376 290 H470 V130 H564", "ในเครื่อง", (517, 122)), edge("n dash", "M376 290 H564", "คลาวด์", (517, 282)),
           edge("n dash", "M470 290 V450 H564"),
           edge("n", "M340 254 V206", "เรียก tool", (350, 234, "start")), edge("n", "M340 366 V414", "จำ · ค้น", (350, 394, "start"), start=True),
           edge("e", "M376 130 H450 V230 H740 V290 H844", "ผ่านด่านแล้ว", (595, 222)), edge("e", "M740 230 V130 H844"),
           edge("e", "M740 290 V450 H844")])

# 2 · voice ---------------------------------------------------------------------------------------------------------
D["voice"] = dict(w=1000, h=470, kicker="FRIDAY · เสียง", title="จากเสียงคุณ ถึงเสียง FRIDAY",
    lede="ฟังคำปลุกบน CPU · ถอดเสียงและคิดบนการ์ดจอ · พูดบน CPU — ไม่มีเสียงออกนอกเครื่อง",
    groups=[group("gb", 140, 60, 180, 370, "CPU", "cpu"), group("ga", 330, 60, 330, 370, "NVIDIA RTX 3060", "nvidia"),
            group("gb", 670, 60, 180, 370, "CPU", "cpu")],
    nodes=[node(70, 120, "mic", "ไมค์", "16 kHz"), node(230, 120, "waves", "Silero VAD", "คำปลุก · tiny.en"),
           node(230, 280, "fingerprint", "WeSpeaker", "จำเสียงเจ้าของ"),
           node(420, 120, "openai", "Whisper turbo", "ถอดเสียง"),
           node(420, 280, "huggingface", "Thonburian", "Whisper · ภาษาไทย"),
           node(570, 120, "qwen", "Qwen 3.5 4B", "Ollama · สมอง"),
           node(760, 120, "huggingface", "VaniraTTS", "เสียงไทย"), node(760, 280, "waves", "Piper", "เสียงอังกฤษ"),
           node(920, 120, "speaker", "ลำโพง", "หรือมือถือ")],
    edges=[edge("e", "M106 150 H194"), edge("e", "M266 150 H384", "Hey Friday", (325, 142)), edge("e", "M456 150 H534"),
           edge("e", "M606 150 H724", "คำตอบ", (665, 142)), edge("e", "M796 150 H884"),
           edge("n", "M230 226 V274", "ใครพูด", (240, 252, "start")), edge("n", "M420 226 V274", "ภาษาไทย", (430, 252, "start")),
           edge("n", "M456 310 H540 V226"), edge("n", "M760 226 V274", "อังกฤษ", (770, 252, "start")),
           edge("n", "M796 310 H880 V226")])

# 3 · brain + memory -------------------------------------------------------------------------------------------------
D["brain"] = dict(w=1000, h=470, kicker="FRIDAY · สมองและความจำ", title="สมองเปลี่ยนได้ ความจำอยู่ที่เดิม",
    lede="ทุกจุดที่ใช้ AI ผ่าน brain.chat() ที่เดียว · ความจำ กฎ และด่านอยู่ในเครื่องเสมอ",
    groups=[group("ga", 380, 50, 180, 210, "ในเครื่อง · 127.0.0.1", "ollama"),
            group("gb", 620, 50, 340, 210, "คลาวด์", "cloud")],
    nodes=[node(90, 110, "python", "FRIDAY", "คำสั่งของคุณ"), node(280, 110, "brain", "brain.chat()", "จุดเดียวที่เรียก AI"),
           node(470, 110, "qwen", "Ollama", "qwen3.5:4b · GPU"), node(710, 110, "claude", "Claude", "Anthropic API"),
           node(870, 110, "openai", "OpenAI", "OpenAI API"),
           node(90, 290, "obsidian", "Obsidian vault", "ความจำ · Markdown"), node(280, 290, "search", "fastembed", "ค้นตามความหมาย"),
           node(790, 300, "lock", "Windows DPAPI", "เก็บ API key")],
    edges=[edge("e", "M126 140 H244"), edge("e", "M316 140 H434", "ค่าเริ่มต้น", (375, 132)),
           edge("n dash", "M280 104 V30 H710 V104", "HTTPS · ถามก่อนส่งเอกสาร/ภาพจอ", (495, 22)), edge("n dash", "M710 30 H870 V104"),
           edge("n", "M90 216 V284", "อ่าน · เขียน", (100, 252, "start"), start=True), edge("n", "M126 320 H244"),
           edge("n", "M280 284 V216", "โน้ตที่เกี่ยว", (290, 252, "start")), edge("n dash", "M790 294 V266", "key", (800, 284, "start"))])

# 4 · safety ---------------------------------------------------------------------------------------------------------
D["safety"] = dict(w=1000, h=450, kicker="FRIDAY · ด่านความปลอดภัย", title="ทุกครั้งที่ AI จะทำอะไรกับเครื่อง",
    lede="ด่านอยู่ในโค้ด ไม่ได้อยู่ในคำสั่งที่ส่งให้ AI — AI ข้ามไม่ได้",
    groups=[group("gb", 130, 60, 600, 210, "ด่านในโค้ด", "gate")],
    nodes=[node(70, 120, "brain", "AI ขอใช้ tool", "รันคำสั่ง · เขียนไฟล์ …"), node(220, 120, "ban", "โหมดปลอดภัย", "เปิด = ไม่ทำ"),
           node(360, 120, "shield", "ไฟล์ FRIDAY", "SHA-256 · ถูกแก้ = พัก"), node(500, 120, "eye", "เพิ่งอ่านเอกสาร?", "ถามก่อน"),
           node(640, 120, "list", "rules.check", "deny › allow › ถาม"), node(780, 120, "hello", "Windows Hello", "คำสั่งอันตราย"),
           node(920, 120, "terminal", "ทำงาน", "บนเครื่องคุณ"), node(780, 300, "fingerprint", "นิ้ว/PIN มือถือ", "ตอนสั่งจากมือถือ"),
           node(920, 300, "audit", "audit log", "บันทึกทุกครั้ง")],
    edges=[edge("e", "M106 150 H184"), edge("e", "M256 150 H324", "ปิด", (290, 142)), edge("e", "M396 150 H464"),
           edge("e", "M536 150 H604"), edge("e", "M676 150 H744", "อันตราย", (710, 142)), edge("e", "M816 150 H884", "ยืนยัน", (850, 142)),
           edge("n dash", "M640 226 V330 H744", "จากมือถือ", (650, 280, "start")), edge("n dash", "M816 330 H880 V226"),
           edge("n", "M920 226 V294")])

# 5 · phone ----------------------------------------------------------------------------------------------------------
D["phone"] = dict(w=1000, h=470, kicker="FRIDAY · มือถือ", title="สั่งจากมือถือ ต่อตรงถึงคอมคุณ",
    lede="ไม่มีเซิร์ฟเวอร์กลาง · ทุกคำขอเข้ารหัสและมีลายเซ็นจากชิปในมือถือ · คำถามยืนยันใช้นิ้ว/PIN",
    groups=[group("ga", 20, 60, 340, 370, "Android", "android"), group("gb", 620, 60, 340, 370, "คอมของคุณ", "windows")],
    nodes=[node(110, 120, "mic", "พิมพ์ด้วยเสียง", "ตัวรู้จำเสียงในมือถือ"), node(270, 120, "compose", "F.R.I.D.A.Y.", "Kotlin · Compose"),
           node(110, 280, "huggingface", "VaniraTTS", "เสียง FRIDAY ในมือถือ"), node(270, 280, "key", "Android Keystore", "กุญแจ 2 ดอก · นิ้ว/PIN"),
           node(490, 120, "tailscale", "Tailscale", "เครือข่ายส่วนตัว"),
           node(710, 120, "lock", "remote.py", "TLS pin + ลายเซ็น"), node(870, 120, "python", "FRIDAY", "คิด · ทำ · ตอบ"),
           node(710, 280, "hello", "จับคู่", "QR + Windows Hello")],
    edges=[edge("e", "M146 140 H234"), edge("n", "M234 166 H190 V310 H146", "รหัสเสียง", (186, 238, "end")),
           edge("n", "M270 274 V226", "ลายเซ็น", (280, 252, "start")),
           edge("e", "M306 150 H454", "HTTPS", (380, 142), start=True), edge("e", "M526 150 H674", start=True),
           edge("e", "M746 150 H834", start=True), edge("n dash", "M710 274 V226", "ครั้งเดียว", (720, 252, "start"))])

# 6 · PC control -----------------------------------------------------------------------------------------------------
D["control"] = dict(w=1000, h=600, kicker="FRIDAY · สั่งเครื่องและแอป", title="FRIDAY ทำอะไรกับเครื่องได้บ้าง",
    lede="ทุกเส้นผ่านด่านความปลอดภัยก่อน · ออกเน็ตเฉพาะข้อยกเว้นที่คุณเคาะไว้",
    groups=[group("ga", 350, 60, 180, 510, "Windows", "windows"), group("gb", 570, 60, 180, 510, "แอปที่คุม", "window"),
            group("gb", 790, 60, 180, 360, "ออกเน็ต (ข้อยกเว้น)", "web")],
    nodes=[node(80, 270, "python", "FRIDAY", "tool ที่ AI เรียก"), node(230, 270, "shield", "ด่าน", "กฎ · Hello"),
           node(440, 120, "monitor", "Win32", "หน้าต่าง · เสียง · จอ"), node(440, 270, "powershell", "PowerShell", "allowlist"),
           node(440, 420, "mouse", "cua-driver", "MCP · ใช้แอปแทนคุณ"),
           node(660, 120, "spotify", "Spotify", "SMTC · คุมเพลง"), node(660, 270, "youtube", "YouTube", "ในเบราว์เซอร์"),
           node(660, 420, "file", "แอปไหนก็ได้", "Notepad · …"),
           node(880, 120, "cloud", "Open-Meteo", "อากาศ"), node(880, 270, "brave", "เบราว์เซอร์", "ค้นเว็บที่คุณขอ")],
    edges=[edge("e", "M116 300 H194"), edge("e", "M266 300 H404"), edge("e", "M310 300 V150 H404"), edge("e", "M310 300 V450 H404"),
           edge("n", "M476 150 H624", "SMTC", (550, 142)), edge("n", "M550 150 V300 H624"),
           edge("n", "M476 450 H624", "UI Automation", (550, 442)),
           edge("n dash", "M230 264 V30 H780 V150 H844", "HTTPS", (505, 22)), edge("n dash", "M780 150 V300 H844")])

# 7 · projects + video -----------------------------------------------------------------------------------------------
D["projects"] = dict(w=1000, h=680, kicker="FRIDAY · โปรเจกต์และวิดีโอ", title="ทำงานในโฟลเดอร์ของคุณ และทำวิดีโอในเครื่อง",
    lede="โปรเจกต์: อ่าน แก้ รันได้เฉพาะในโฟลเดอร์ · วิดีโอ: บทถูกตรวจก่อน แล้ววาดด้วย CSS + JS ใน Edge แบบไม่มีเน็ต",
    groups=[group("ga", 140, 60, 830, 210, "โฟลเดอร์โปรเจกต์", "folder"),
            group("gb", 140, 280, 630, 360, "วิดีโอ · ในเครื่อง", "film")],
    nodes=[node(70, 120, "qwen", "สมอง", "เขียน · แก้ · สั่ง"), node(230, 120, "shield", "project.inside()", "ออกนอกโฟลเดอร์ไม่ได้"),
           node(380, 120, "search", "อ่าน · ค้นหา", "ไม่อ่านไฟล์ลับ"), node(530, 120, "file", "แก้ไฟล์", "diff → Hello"),
           node(680, 120, "powershell", "รันคำสั่ง", "ในโฟลเดอร์ · 2 นาที"), node(880, 120, "scroll", "FRIDAY.md", "กฎของหมวด"),
           node(70, 340, "scroll", "script.md", "บท / storyboard"), node(230, 340, "eye", "ตรวจเนื้อเรื่อง", "ซ้ำ · วน · ตอนจบ"),
           node(380, 340, "film", "video_player", "CSS + JS · T(t)"), node(530, 340, "edge", "Edge headless", "ไม่มีเน็ต"),
           node(680, 340, "ffmpeg", "ffmpeg", "ภาพ + เสียง → mp4"), node(880, 340, "film", "video-….mp4", "ในโฟลเดอร์โปรเจกต์"),
           node(530, 490, "music", "VaniraTTS + เพลง", "พากย์ · numpy")],
    edges=[edge("e", "M106 150 H194"), edge("e", "M266 150 H344"), edge("e", "M416 150 H494"), edge("e", "M566 150 H644"),
           edge("n dash", "M880 114 V30 H70 V114", "กฎหมวด → สมอง", (475, 22)),
           edge("e", "M70 226 V334", "เขียนบท", (80, 280, "start")), edge("e", "M106 370 H194"), edge("e", "M266 370 H344"),
           edge("e", "M416 370 H494", "เฟรม", (455, 362)), edge("e", "M566 370 H644"), edge("e", "M716 370 H844"),
           edge("n", "M566 520 H680 V446", "เสียง", (624, 512))])

# 8 · build + release ------------------------------------------------------------------------------------------------
D["build"] = dict(w=1000, h=430, kicker="FRIDAY · build และติดตั้ง", title="จากโค้ด ถึงเครื่องของคุณ",
    lede="แก้โค้ดแล้ว self-test ทุกตัวต้องผ่าน · build exe ใหม่ทุกครั้ง · ตัวติดตั้งแจกผ่าน GitHub Releases",
    groups=[group("gb", 20, 60, 630, 330, "เครื่องนักพัฒนา", "terminal")],
    nodes=[node(110, 120, "uv", "Python + uv", "venv · .venv-tts"), node(260, 120, "pyinst", "PyInstaller", "friday.spec"),
           node(410, 120, "windows", "FRIDAY.exe", "เปิดตอน login"), node(560, 120, "inno", "Inno Setup", "ตัวติดตั้ง"),
           node(740, 120, "github", "GitHub Releases", "ดาวน์โหลด"), node(900, 120, "monitor", "เครื่องคุณ", "Windows 10/11"),
           node(410, 260, "list", "self-test", "ทุกโมดูลต้องผ่าน"), node(740, 260, "git", "GitHub repo", "โค้ด · README")],
    edges=[edge("e", "M146 150 H224"), edge("e", "M296 150 H374"), edge("e", "M446 150 H524"), edge("e", "M596 150 H704", "upload", (650, 142)),
           edge("e", "M776 150 H864"), edge("n", "M410 226 V254", None), edge("n dash", "M446 290 H704", "git push", (575, 282))])

TEMPLATE = open(os.path.join(SKILL, "assets", "template.html"), encoding="utf-8").read()
CREDIT = "icons: svgl / devicon / gilbarbara/logos / Lucide"


def page(name, d):
    w, h = d["w"], d["h"]
    html = TEMPLATE.replace('<html lang="en">', '<html lang="th">', 1)
    html = html.replace("<title><!-- TITLE --></title>", f"<title>{d['title']}</title>")
    html = html.replace("<!-- KICKER: e.g. stack-diagram / author / 2026-08 -->", d["kicker"])
    html = html.replace("<h1><!-- TITLE --></h1>", f"<h1>{d['title']}</h1>")
    html = html.replace("<!-- LEDE: 1-2 short sentences, or delete this <p> -->", d["lede"])
    html = html.replace(".canvas { position: relative; width: 1000px; height: 540px;", f".canvas {{ position: relative; width: {w}px; height: {h}px;")
    html = html.replace("svg.edges { position:absolute; inset:0; width:1000px; height:540px;", f"svg.edges {{ position:absolute; inset:0; width:{w}px; height:{h}px;")
    a = html.index("<!-- GROUPS")
    b = html.index('<path class="e" d="M148 150 H306"')
    c = html.index("</svg>", b)
    e_ = html.index("<!-- NODES")
    f = html.index("</div>\n  </div>\n\n  <div class=\"legend\">")
    defs_start = html.index('<svg class="edges"', a)
    svg_head = html[defs_start:b].replace('viewBox="0 0 1000 540"', f'viewBox="0 0 {w} {h}"')
    html = html[:a] + "\n".join(d["groups"]) + "\n" + svg_head + "\n".join(d["edges"]) + "\n" + html[c:e_] + "\n".join(d["nodes"]) + "\n" + html[f:]
    html = html.replace("<!-- FOOT-LEFT: author / one-liner -->", "F.R.I.D.A.Y. — ผู้ช่วย AI ในเครื่องคุณ")
    html = html.replace('<!-- FOOT-RIGHT: icon sources actually used, from manifest.json, e.g. "icons: svgl / devicon / Lucide" -->', CREDIT)
    draft = os.path.join(OUT, "src", f"{name}.draft.html")
    built = os.path.join(OUT, "src", f"{name}.html")
    os.makedirs(os.path.dirname(draft), exist_ok=True)
    open(draft, "w", encoding="utf-8").write(html)
    subprocess.run([sys.executable, "-I", os.path.join(SKILL, "scripts", "build.py"), draft, ICONS, built, "--fonts",
                    os.path.join(SKILL, "assets", "fonts")], check=True)
    os.remove(draft)
    return built


def render(built, name):
    prof = os.path.abspath(os.path.join(OUT, "src", "edge-prof"))
    os.makedirs(prof, exist_ok=True)
    p, cdp = video._start_edge(1200, 900, prof, 1)
    try:
        cdp.call("Emulation.setDeviceMetricsOverride", width=1200, height=900, deviceScaleFactor=2, mobile=False)
        cdp.call("Page.navigate", url="file:///" + os.path.abspath(built).replace("\\", "/"))
        time.sleep(1.5)
        cdp.js("document.fonts.ready.then(() => 1)")
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            cdp.js(f"document.documentElement.setAttribute('data-theme', '{theme}'); "
                   "document.querySelector('.scroller').style.borderRadius = '0'; document.querySelector('.scroller').style.border = '0'; 1")
            time.sleep(0.3)
            r = cdp.js("JSON.stringify(document.querySelector('.canvas').getBoundingClientRect())")
            r = json.loads(r)
            shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                            clip={"x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"], "scale": 1})
            open(os.path.join(OUT, f"{name}{suffix}.png"), "wb").write(base64.b64decode(shot["data"]))
    finally:
        cdp.close()
        video._kill(p)


only = sys.argv[4:] or list(D)
for n in only:
    render(page(n, D[n]), n)
    print("rendered", n)
