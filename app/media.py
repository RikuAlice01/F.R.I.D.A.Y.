"""Whatever is playing (YouTube in a browser, Spotify, a music app) through Windows' own media controls — the same
ones as the keyboard's media keys, without pressing anything (PLAN §51)."""
import asyncio

STATUS = {4: "playing", 5: "paused", 3: "stopped", 2: "starting", 1: "opened", 0: "closed"}


async def _session():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
    return (await M.request_async()).get_current_session()


def now_playing():
    """{"app", "title", "artist", "status"} or None when nothing is playing."""
    async def go():
        s = await _session()
        if not s:
            return None
        p = await s.try_get_media_properties_async()
        return {"app": s.source_app_user_model_id, "title": p.title, "artist": p.artist,
                "status": STATUS.get(int(s.get_playback_info().playback_status), "unknown")}
    return asyncio.run(go())


def control(action):
    """play | pause | toggle | next | previous -> True if the app accepted it, None if nothing is playing."""
    async def go():
        s = await _session()
        if not s:
            return None
        call = {"play": s.try_play_async, "pause": s.try_pause_async, "toggle": s.try_toggle_play_pause_async,
                "next": s.try_skip_next_async, "previous": s.try_skip_previous_async}[action]
        return bool(await call())
    return asyncio.run(go())


def describe(info):
    """Thai sentence about what is playing."""
    if not info:
        return "ตอนนี้ไม่มีเพลงหรือวิดีโอที่เล่นอยู่ค่ะ"
    who = f" ของ {info['artist']}" if info.get("artist") else ""
    state = {"playing": "กำลังเล่น", "paused": "หยุดไว้"}.get(info["status"], info["status"])
    return f"{state}: {info['title']}{who} ({info['app']})"


if __name__ == "__main__":
    assert describe(None).startswith("ตอนนี้ไม่มี")
    assert describe({"app": "Brave", "title": "Better", "artist": "Khalid", "status": "playing"}) == "กำลังเล่น: Better ของ Khalid (Brave)"
    info = now_playing()  # read-only on the real PC: nothing is paused or skipped here
    print("now playing:", describe(info))
    print("MEDIA SELFTEST OK")
