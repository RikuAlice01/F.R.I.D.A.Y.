"""Whatever is playing (YouTube / YouTube Music in a browser or as an app, Spotify, Apple Music, Media Player, VLC…)
through Windows' own media controls — the same ones as the keyboard's media keys, without pressing anything (PLAN §51).
§91: every app that plays, not only Windows' "current" one — "pause Spotify" while YouTube plays; more actions
(stop, shuffle, repeat, seek); search a song in the service the user names."""
import asyncio, re, urllib.parse

STATUS = {4: "playing", 5: "paused", 3: "stopped", 2: "starting", 1: "opened", 0: "closed"}
BROWSERS = {"brave": "Brave", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "opera": "Opera", "vivaldi": "Vivaldi", "arc": "Arc"}
# app id (AUMID / exe) words -> service name; YouTube Music installed as an app from Chrome/Edge has this extension id
APPS = [("cinhimbnkkaeohfgghhklpknlkffjgod", "YouTube Music"), ("youtube music", "YouTube Music"), ("youtubemusic", "YouTube Music"),
        ("spotify", "Spotify"), ("applemusic", "Apple Music"), ("itunes", "iTunes"), ("zunemusic", "Media Player"),
        ("zunevideo", "Movies & TV"), ("vlc", "VLC"), ("foobar", "foobar2000"), ("aimp", "AIMP"), ("musicbee", "MusicBee"),
        ("tidal", "TIDAL"), ("deezer", "Deezer"), ("amazonmusic", "Amazon Music"), ("joox", "JOOX"), ("soundcloud", "SoundCloud")]
# what the user may call a service -> service name (Thai and English)
SERVICES = [(r"youtube\s*music|yt\s*music|ยูทูบ\s*มิวสิ[กค]|ยูทูป\s*มิวสิ[กค]", "YouTube Music"), (r"youtube|ยูทูบ|ยูทูป", "YouTube"),
            (r"spotify|สปอติฟาย|สป็อติฟาย", "Spotify"), (r"apple\s*music", "Apple Music"), (r"media\s*player|มีเดียเพลเยอร์", "Media Player"),
            (r"vlc", "VLC"), (r"soundcloud", "SoundCloud"), (r"joox|จู๊กซ์", "JOOX"), (r"tidal", "TIDAL"), (r"deezer", "Deezer")]
SEARCH = {"YouTube": "https://www.youtube.com/results?search_query={q}", "YouTube Music": "https://music.youtube.com/search?q={q}",
          "Spotify": "https://open.spotify.com/search/{q}", "SoundCloud": "https://soundcloud.com/search?q={q}",
          "Apple Music": "https://music.apple.com/search?term={q}", "JOOX": "https://www.joox.com/th/search?keyword={q}"}
SEEK_S = 10


def service(name):
    """'ยูทูบมิวสิก' -> 'YouTube Music'; None if it names no music service."""
    for rx, s in SERVICES:
        if re.search(rx, str(name or ""), re.I):
            return s
    return None


def app_name(aumid, titles=()):
    """Friendly name of a media session. A browser playing is YouTube / YouTube Music when one of its window titles says so."""
    a = str(aumid).lower()
    for key, name in APPS:
        if key in a:
            return name
    for key, name in BROWSERS.items():
        if key in a:
            t = " ".join(titles).lower()
            return f"YouTube Music ({name})" if "youtube music" in t else f"YouTube ({name})" if "youtube" in t else name
    return re.sub(r"\.exe$|_[a-z0-9]{13}!.*$", "", str(aumid), flags=re.I) or "app"


def _titles():
    try:
        import windows
        out = {}
        for _, title, exe in windows.windows():
            out.setdefault(exe.removesuffix(".exe"), []).append(title)
        return out
    except Exception:
        return {}


async def _all():
    """[(session, info)] of every app that reports media, playing ones first."""
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
    m = await M.request_async()
    cur = m.get_current_session()
    cur_id = cur.source_app_user_model_id if cur else None
    titles, out = _titles(), []
    for s in m.get_sessions():
        p = await s.try_get_media_properties_async()
        aumid = s.source_app_user_model_id
        exe = next((k for k in BROWSERS if k in aumid.lower()), "")
        out.append((s, {"app": app_name(aumid, titles.get(exe, [])), "id": aumid, "title": p.title, "artist": p.artist,
                        "status": STATUS.get(int(s.get_playback_info().playback_status), "unknown"), "current": aumid == cur_id}))
    out.sort(key=lambda x: (x[1]["status"] != "playing", not x[1]["current"]))
    return out


def pick(infos, app=None):
    """Index of the session to act on: the app the user named (YouTube also matches a browser that plays), else the one
    playing (Windows' current first), else Windows' current one. None when nothing matches."""
    if not infos:
        return None
    if app:
        want = service(app) or str(app)
        exact = [i for i, x in enumerate(infos) if want.lower() in x["app"].lower() or want.lower() in x["id"].lower()]
        if exact:
            return exact[0]
        if want in ("YouTube", "YouTube Music"):  # a background tab: the window title shows another page
            web = [i for i, x in enumerate(infos) if any(b in x["id"].lower() for b in BROWSERS)]
            return web[0] if web else None
        return None
    return 0


def now_playing(app=None):
    """{"app", "title", "artist", "status", "others": [...]} or None when nothing is playing."""
    async def go():
        sessions = await _all()
        infos = [i for _, i in sessions]
        k = pick(infos, app)
        if k is None:
            return None
        return {**infos[k], "others": [i for j, i in enumerate(infos) if j != k]}
    return asyncio.run(go())


def control(action, app=None):
    """play | pause | toggle | stop | next | previous | shuffle | repeat | forward | back | restart
    -> (True/False the app accepted it, the app's name), or (None, None) if no app plays / matches."""
    async def go():
        sessions = await _all()
        k = pick([i for _, i in sessions], app)
        if k is None:
            return None, None
        s, info = sessions[k]
        if action in ("forward", "back", "restart"):
            tl = s.get_timeline_properties()
            pos = tl.position.duration / 1e7  # TimeSpan in 100 ns ticks
            to = 0 if action == "restart" else max(0, pos + (SEEK_S if action == "forward" else -SEEK_S))
            return bool(await s.try_change_playback_position_async(int(to * 1e7))), info["app"]
        if action == "shuffle":
            on = s.get_playback_info().is_shuffle_active
            return bool(await s.try_change_shuffle_active_async(not on)), info["app"]
        if action == "repeat":
            from winrt.windows.media import MediaPlaybackAutoRepeatMode as R
            mode = s.get_playback_info().auto_repeat_mode
            return bool(await s.try_change_auto_repeat_mode_async(R.LIST if mode == R.NONE else R.NONE)), info["app"]
        call = {"play": s.try_play_async, "pause": s.try_pause_async, "toggle": s.try_toggle_play_pause_async,
                "stop": s.try_stop_async, "next": s.try_skip_next_async, "previous": s.try_skip_previous_async}[action]
        return bool(await call()), info["app"]
    return asyncio.run(go())


def search_url(query, app=None):
    """Where to look for a song: the service the user named (YouTube when none), as a web page (opened in the browser)."""
    svc = service(app) or "YouTube"
    return svc, SEARCH.get(svc, SEARCH["YouTube"]).format(q=urllib.parse.quote(str(query).strip()))


def describe(info):
    """Thai sentence about what is playing (and what else is open)."""
    if not info:
        return "ตอนนี้ไม่มีเพลงหรือวิดีโอที่เล่นอยู่ค่ะ"
    who = f" ของ {info['artist']}" if info.get("artist") else ""
    state = {"playing": "กำลังเล่น", "paused": "หยุดไว้"}.get(info["status"], info["status"])
    more = info.get("others") or []
    rest = (" · มีอีก: " + ", ".join(f"{o['app']} ({'เล่น' if o['status'] == 'playing' else 'หยุด'})" for o in more[:3])) if more else ""
    return f"{state}: {info['title']}{who} ({info['app']}){rest}"


if __name__ == "__main__":
    assert describe(None).startswith("ตอนนี้ไม่มี")
    assert describe({"app": "Brave", "title": "Better", "artist": "Khalid", "status": "playing"}) == "กำลังเล่น: Better ของ Khalid (Brave)"
    # §91 which app: names, services, picking the one the user means
    assert app_name("Spotify.exe") == "Spotify" and app_name("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic") == "Media Player"
    assert app_name("Brave", ["Lo-fi beats - YouTube - Brave"]) == "YouTube (Brave)" and app_name("Chrome", ["Home - YouTube Music"]) == "YouTube Music (Chrome)"
    assert app_name("Chrome._crx_cinhimbnkkaeohfgghhklpknlkffjgod") == "YouTube Music" and app_name("msedge", ["Docs"]) == "Edge"
    assert service("ยูทูบมิวสิก") == "YouTube Music" and service("youtube") == "YouTube" and service("สปอติฟาย") == "Spotify" and service("ข่าว") is None
    infos = [{"app": "YouTube (Brave)", "id": "Brave", "status": "playing"}, {"app": "Spotify", "id": "Spotify.exe", "status": "paused"},
             {"app": "Edge", "id": "MSEdge", "status": "paused"}]
    assert pick(infos) == 0 and pick(infos, "spotify") == 1 and pick(infos, "ยูทูบ") == 0 and pick(infos, "vlc") is None and pick([], None) is None
    assert pick([infos[2]], "youtube music") == 0  # YouTube Music in a background tab: the browser is the best guess
    assert search_url("ลาลาลอย", "spotify") == ("Spotify", "https://open.spotify.com/search/%E0%B8%A5%E0%B8%B2%E0%B8%A5%E0%B8%B2%E0%B8%A5%E0%B8%AD%E0%B8%A2")
    assert search_url("lofi")[0] == "YouTube" and search_url("lofi", "yt music")[1].startswith("https://music.youtube.com/search?q=lofi")
    info = now_playing()  # read-only on the real PC: nothing is paused or skipped here
    print("now playing:", describe(info))
    print("MEDIA SELFTEST OK")
