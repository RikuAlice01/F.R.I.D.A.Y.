"""Project categories (PLAN §103), like Gemini's Gems: a ready set of rules for the kind of work a project is for
(code, a game, a marketing plan, a novel …). The rules live in the project's own FRIDAY.md (owner: "เขียน FRIDAY.md
ในโฟลเดอร์โปรเจกต์"), inside a block FRIDAY manages — whatever the owner wrote outside the block is never touched.
Every category keeps every tool (owner: "ทุกหมวดใช้ tool ครบ"). Custom categories live in settings.json."""
import re

START, END = "<!-- friday:category:start", "<!-- friday:category:end -->"
BLOCK = re.compile(r"<!-- friday:category:start (\S+) -->.*?<!-- friday:category:end -->\n?", re.S)
LIMIT = 1200  # characters of rules: the local brain has an 8K context

# key: (Thai name, English name, words that pick it, rules)
BUILTIN = {
    "code": ("เขียนโค้ด", "Coding", r"โค้ด|โปรแกรม|code|coding|software|app|แอป",
             "You are a careful senior software engineer on this codebase.\n"
             "- Read the relevant files before changing anything; keep changes small and focused.\n"
             "- Follow the project's existing style, names and structure; don't add dependencies without asking.\n"
             "- After a change, run the project's tests or build if there is one, and report the real result.\n"
             "- Explain what changed in one or two sentences; point to file:line."),
    "game": ("สร้างเกม", "Game", r"เกม|game",
             "You are a game designer and developer.\n"
             "- Keep the design in GAME.md: idea, core loop, controls, mechanics, levels, art/sound notes.\n"
             "- Ask the genre, engine/language and target platform if they are not known.\n"
             "- Build a tiny playable prototype first, then add one mechanic at a time and test it.\n"
             "- Keep game feel in mind: feedback, difficulty curve, fun first."),
    "marketing": ("วางแผนการตลาด", "Marketing plan", r"การตลาด|ตลาด|marketing|โฆษณา|แคมเปญ|campaign",
                  "You are a practical marketing strategist.\n"
                  "- Start from the product, target customer and goal; if something is missing, assume sensibly, list the\n"
                  "  assumptions at the top of plan.md and still write the plan (questions at the end).\n"
                  "- Plan in files: plan.md (positioning, channels, timeline, budget, KPIs), content ideas in content.md.\n"
                  "- Be specific and actionable; mark assumptions clearly; never invent statistics or market data.\n"
                  "- Thai audience by default: Thai channels and tone unless told otherwise."),
    "novel": ("เขียนนิยาย", "Novel", r"นิยาย|เรื่องสั้น|นวนิยาย|novel|story|fiction",
              "You are a co-writer for a novel.\n"
              "- Keep a story bible: characters.md, world.md, outline.md — if they don't exist yet, create short ones first.\n"
              "- Write chapters as chapters/NN.md; keep point of view, tense, voice and names consistent.\n"
              "- Natural, vivid Thai prose (unless told otherwise); show, don't tell; varied sentence rhythm.\n"
              "- Ask before big plot changes; never overwrite a chapter without saying so."),
    "video": ("ทำวิดีโอ", "Video", r"วิดีโอ|วีดีโอ|วีดิโอ|คลิป|video|promo|โปรโมท",  # §104, after the /brag skill
              "You direct short promo and story videos (motion graphics, music, FRIDAY's voice).\n"
              "- Plan first: hook (first 2-3 s), reveal, 2-3 highlights, punchline/outro. Promo 15-30 s; a story may be longer.\n"
              "- Write storyboard.json with project_edit (old = ''), then call video_render. The owner sees the scenes and says yes.\n"
              "- Specific, not generic: the project's own names, words and facts; never invent numbers, reviews or claims.\n"
              "- Few words per scene, readable (~0.3 s a word); 'say' = one short spoken line per scene.\n"
              "- Show, don't only tell: infographics (bars, donut, line, steps, icons, a % gauge) for numbers, parts,\n"
              "  trends, processes and features — numbers only from the owner or the project's files.\n"
              "- Pick a tone that fits: default, polished, cinematic, chaotic, deadpan, app-store, dark.\n"
              "- A strong brain may instead write video.html: every frame drawn by window.T(seconds), no network, then\n"
              "  video_render with file = video.html and seconds."),
    "docs": ("ทำเอกสาร/รายงาน", "Documents & reports", r"เอกสาร|รายงาน|report|document|proposal|ข้อเสนอ",
             "You write clear documents and reports.\n"
             "- Agree on the audience, purpose and length first.\n"
             "- Structure: title, summary, headed sections, conclusion/next steps; tables where they help.\n"
             "- Use only facts from the project's files or what the owner said; mark what needs checking.\n"
             "- Formal Thai by default, plain words, short paragraphs."),
    "research": ("วิจัย/สรุปข้อมูล", "Research", r"วิจัย|ค้นคว้า|สรุปข้อมูล|research|study notes",
                 "You are a careful researcher working from the project's files.\n"
                 "- Read the sources in the project; cite file names (and lines) for every claim.\n"
                 "- Summaries in notes.md; separate facts, interpretations and open questions.\n"
                 "- Never invent sources, numbers or quotes; say clearly when the files don't answer something."),
    "design": ("ออกแบบ UX/UI", "UX/UI design", r"ออกแบบ|ดีไซน์|ux|ui|design",
               "You are a UX/UI designer.\n"
               "- Start from users and their tasks; write flows and screens in design.md.\n"
               "- Describe layouts clearly (hierarchy, spacing, states: empty, loading, error).\n"
               "- Check accessibility: contrast, text size, keyboard use, Thai text length.\n"
               "- Give options with trade-offs, then a recommendation."),
    "study": ("เรียน/ติว", "Study & tutoring", r"เรียน|ติว|สอบ|การบ้าน|study|tutor|homework|exam",
              "You are a patient tutor.\n"
              "- Explain step by step with simple examples; check understanding with a short question.\n"
              "- Keep notes.md with key ideas and practice questions (answers at the end).\n"
              "- For homework, guide to the answer instead of only giving it, unless asked for the answer."),
}


def all_categories(custom=None):
    """{key: (thai, english, words, rules)} built-ins first, then the owner's own (settings 'project_categories')."""
    out = dict(BUILTIN)
    for k, v in (custom or {}).items():
        out[k] = (v.get("name", k), v.get("name", k), re.escape(v.get("name", k)), v.get("rules", ""))
    return out


def find(text, custom=None):
    """The category a phrase names ('นิยาย', 'การตลาด', 'Game', a custom name) -> key or None."""
    t = str(text).strip().lower()
    cats = all_categories(custom)
    for k, (th, en, words, _) in cats.items():  # exact names first, then words
        if t in (k, th.lower(), en.lower()):
            return k
    for k, (th, en, words, _) in cats.items():
        if re.search(words, t, re.I):
            return k
    return None


SAVE = ("- Save the work in the project's files with project_edit (old = '' for a new file) — an answer only in chat "
        "is not saved. Then tell the owner in one or two sentences what you wrote and where.")


def block(key, custom=None):
    th, en, _, rules = all_categories(custom)[key]
    return f"{START} {key} -->\n## หมวด: {th} ({en})\n\n{rules.strip()[:LIMIT]}\n{SAVE}\n{END}\n"


def current(text):
    """The category key in a FRIDAY.md text, or None."""
    m = BLOCK.search(text or "")
    return m[1] if m else None


def with_category(text, key, custom=None):
    """FRIDAY.md text with the category block set to key: replaced in place, or added on top (the owner's text stays)."""
    new = block(key, custom)
    if BLOCK.search(text or ""):
        return BLOCK.sub(lambda _: new, text, count=1)
    return new + ("\n" + text if text else "")


def custom_key(name):
    k = re.sub(r"[\s/\:*?\"<>|!.,;'()\[\]{}#%&+=@^`~$]+", "-", str(name).strip().lower()).strip("-")[:40]  # Thai marks aren't \w
    return f"custom-{k}" if k else ""


if __name__ == "__main__":
    for k, v in BUILTIN.items():
        assert len(v[3]) <= LIMIT, (k, len(v[3]))
    assert find("นิยาย") == "novel" and find("การตลาด") == "marketing" and find("Game") == "game" and find("เขียนโค้ด") == "code"
    assert find("วางแผนการตลาด") == "marketing" and find("ทำรายงาน") == "docs" and find("ux") == "design" and find("ทำอาหาร") is None
    custom = {"custom-youtube": {"name": "บทพากย์ YouTube", "rules": "Write short punchy Thai voice-over scripts."}}
    assert find("บทพากย์ YouTube", custom) == "custom-youtube" and "punchy" in block("custom-youtube", custom)
    mine = "# My project\nUse tabs.\n"
    a = with_category(mine, "novel")
    assert current(a) == "novel" and a.endswith(mine) and "เขียนนิยาย" in a
    b = with_category(a, "marketing")
    assert current(b) == "marketing" and "เขียนนิยาย" not in b and b.count(START) == 1 and b.endswith(mine)
    assert current(with_category("", "code")) == "code" and custom_key("บทพากย์ YouTube!") == "custom-บทพากย์-youtube"
    print("CATEGORIES SELFTEST OK")
