"""README promo image (PLAN §79):  .venv\\Scripts\\python.exe assets\\promo\\make.py  ->  assets\\promo\\friday-promo.png

Real UI only: the PC panel is app/ui.html itself (rendered by Edge headless, transparent, with a DEMO conversation —
never the owner's chats), the phone is the app's own Compose screen (Paparazzi snapshot, mobile/). Then promo.html
lays them out Apple-style on white and Edge renders that to PNG.
"""
import json, os, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PHONE = os.path.join(ROOT, "mobile", "app", "src", "test", "snapshots", "images", "local.friday.remote_ScreensTest_chat.png")

DEMO = [  # what the panel shows: a made-up morning, Thai first like FRIDAY
    {"msg": {"role": "user", "text": "วันนี้มีอะไรบ้าง"}},
    {"msg": {"role": "assistant", "text": "อรุณสวัสดิ์ค่ะ วันนี้มี 3 อย่าง\n- ประชุมทีม 10 โมงเช้า\n- ส่งรายงานก่อนบ่ายสาม\n- เตือนรับของ 5 โมงเย็น"}},
    {"msg": {"role": "user", "text": "อากาศเป็นยังไง"}},
    {"weather": {"place": "กรุงเทพฯ", "icon": "partly", "text": "มีเมฆบางส่วน", "text_en": "partly cloudy", "temp": 31,
                 "feels": 35, "humidity": 68, "wind": 9, "rain_today": 20, "hi": 33, "lo": 26,
                 "days": [{"day": "ส.", "icon": "rain", "text": "ฝนตก", "hi": 32, "lo": 25, "rain": 60},
                          {"day": "อา.", "icon": "partly", "text": "มีเมฆบางส่วน", "hi": 33, "lo": 26, "rain": 20},
                          {"day": "จ.", "icon": "clear", "text": "แจ่มใส", "hi": 34, "lo": 26, "rain": 5}]}},
    {"msg": {"role": "assistant", "text": "ฟ้าเปิดบางส่วน 31 องศาค่ะ บ่ายนี้โอกาสฝนน้อย"}},
    {"interactive": True}, {"visible": True}, {"state": "speaking"}, {"level": 0.45},
]


def edge(url, out, w, h, scale=2, transparent=False):
    args = [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", f"--window-size={w},{h}",
            f"--force-device-scale-factor={scale}", "--virtual-time-budget=4000", f"--screenshot={out}", url]
    if transparent:
        args.insert(2, "--default-background-color=00000000")
    subprocess.run(args, check=True, capture_output=True, timeout=120)


tmp = tempfile.mkdtemp()
# 1. the panel, transparent, with the demo conversation
ui = open(os.path.join(ROOT, "app", "ui.html"), encoding="utf-8").read()
# headless Edge lays out wider than it shoots: pin the panel to 430 px and crop to that
inject = ("<style>html,body{width:430px!important;height:860px!important}</style>"
          "<script>addEventListener('load',()=>{for(const e of %s) friday.event(e);});</script></body>" % json.dumps(DEMO, ensure_ascii=False))
open(os.path.join(tmp, "panel.html"), "w", encoding="utf-8").write(ui.replace("</body>", inject))
edge("file:///" + os.path.join(tmp, "panel.html").replace("\\", "/"), os.path.join(HERE, "panel.png"), 640, 860, transparent=True)
from PIL import Image
Image.open(os.path.join(HERE, "panel.png")).crop((0, 0, 860, 1720)).save(os.path.join(HERE, "panel.png"))
# 2. the layout
shutil.copy(PHONE, os.path.join(HERE, "phone.png"))
edge("file:///" + os.path.join(HERE, "promo.html").replace("\\", "/"), os.path.join(HERE, "friday-promo.png"), 1600, 2140)
for f in ("panel.png", "phone.png"):
    os.remove(os.path.join(HERE, f))
shutil.rmtree(tmp, ignore_errors=True)
print("ok", os.path.join(HERE, "friday-promo.png"))
