"""Weather (PLAN §49): Open-Meteo, chosen by the owner — free, no account, no key. Only coordinates (or a place name
to look up) leave the PC; never voice, text or memory. "Current location" comes from Windows' own location service.
card() is what the panel draws (icon + temperature); summary() is what the model reads."""
import json, re, time, urllib.parse, urllib.request

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_cache = {}  # key -> (time, value)

# WMO weather code -> (icon, Thai, English)
CODES = [((0,), "clear", "ท้องฟ้าแจ่มใส", "clear sky"), ((1,), "clear", "แดดเป็นส่วนใหญ่", "mainly clear"),
         ((2,), "partly", "มีเมฆบางส่วน", "partly cloudy"), ((3,), "cloud", "เมฆมาก", "overcast"),
         ((45, 48), "fog", "มีหมอก", "fog"), ((51, 53, 55, 56, 57), "rain", "ฝนปรอย", "drizzle"),
         ((61, 63, 65, 66, 67), "rain", "ฝนตก", "rain"), ((80, 81, 82), "rain", "ฝนตกเป็นช่วงๆ", "rain showers"),
         ((71, 73, 75, 77, 85, 86), "snow", "หิมะ", "snow"), ((95, 96, 99), "storm", "พายุฝนฟ้าคะนอง", "thunderstorm")]


def describe(code, is_day=1):
    """(icon, thai, english) for a WMO code; clear/partly at night become their night icons."""
    for codes, icon, th, en in CODES:
        if int(code) in codes:
            if not is_day and icon in ("clear", "partly"):
                icon = "night" if icon == "clear" else "night-partly"
            return icon, th, en
    return "cloud", "ไม่ทราบ", "unknown"


def _get(url, params, ttl=600):
    key = url + "?" + urllib.parse.urlencode(params)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with urllib.request.urlopen(key, timeout=10) as r:
        val = json.load(r)
    _cache[key] = (time.time(), val)
    return val


def here():
    """(lat, lon) from Windows location (IP / Wi-Fi / GPS, Windows decides), or None if location is off."""
    hit = _cache.get("here")
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    import asyncio
    from winrt.windows.devices.geolocation import Geolocator, GeolocationAccessStatus

    async def go():
        if await Geolocator.request_access_async() != GeolocationAccessStatus.ALLOWED:
            return None
        g = Geolocator()
        g.desired_accuracy_in_meters = 3000
        p = await asyncio.wait_for(g.get_geoposition_async(), 15)
        c = p.coordinate.point.position
        return round(c.latitude, 3), round(c.longitude, 3)
    try:
        pos = asyncio.run(go())
    except Exception:
        pos = None
    if pos:
        _cache["here"] = (time.time(), pos)
    return pos


def clean_place(place):
    """A place name only: letters (Thai/English), spaces, '-' ',' — max 40 chars. Anything else is not a place, and
    nothing else may leave the PC through this tool (a document can't smuggle notes out as a 'place')."""
    p = re.sub(r"[^\w\s,\-฀-๿]", " ", str(place or ""), flags=re.U)  # Thai tone marks are not \w
    p = re.sub(r"\d+", " ", p)
    return " ".join(p.split())[:40]


def locate(place=""):
    """(lat, lon, name). Empty / "here" -> current location."""
    p = clean_place(place)
    if not p or p.lower() in ("here", "current", "ที่นี่", "ตรงนี้", "ปัจจุบัน", "ตำแหน่งปัจจุบัน"):
        pos = here()
        if not pos:
            raise LookupError("Windows location is off — turn it on in Settings › Privacy › Location, or name a city")
        return pos[0], pos[1], "ตำแหน่งปัจจุบัน"
    r = (_get(GEOCODE, {"name": p, "count": 1, "language": "th", "format": "json"}, ttl=86400).get("results") or [None])[0]
    if not r:
        raise LookupError(f"no place called '{p}'")
    return r["latitude"], r["longitude"], r.get("name", p)


def forecast(lat, lon):
    return _get(FORECAST, {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 4,
                           "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,wind_speed_10m",
                           "hourly": "precipitation_probability",
                           "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})


THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def card(data, name):
    """What the panel draws: now (icon, temp, feels, humidity, wind, rain chance today) + the next 3 days."""
    import datetime
    cur, daily = data["current"], data["daily"]
    icon, th, en = describe(cur["weather_code"], cur.get("is_day", 1))
    now_hour = cur["time"][:13]
    hourly = data.get("hourly", {})
    rest = [p for t, p in zip(hourly.get("time", []), hourly.get("precipitation_probability", [])) if t[:10] == cur["time"][:10] and t[:13] >= now_hour]
    days = []
    for d, code, hi, lo, rain in list(zip(daily["time"], daily["weather_code"], daily["temperature_2m_max"],
                                          daily["temperature_2m_min"], daily["precipitation_probability_max"]))[1:4]:
        days.append({"day": THAI_DAYS[datetime.date.fromisoformat(d).weekday()], "icon": describe(code)[0], "text": describe(code)[1],
                     "hi": round(hi), "lo": round(lo), "rain": rain})
    return {"place": name, "icon": icon, "text": th, "text_en": en, "temp": round(cur["temperature_2m"]),
            "feels": round(cur["apparent_temperature"]), "humidity": cur["relative_humidity_2m"], "wind": round(cur["wind_speed_10m"]),
            "rain_today": max(rest) if rest else daily["precipitation_probability_max"][0],
            "hi": round(daily["temperature_2m_max"][0]), "lo": round(daily["temperature_2m_min"][0]), "days": days}


def summary(c):
    """For the model: plain facts to say in one or two sentences."""
    days = "; ".join(f"{d['day']} {d['text']} {d['lo']}-{d['hi']}°C rain {d['rain']}%" for d in c["days"])
    return (f"Weather at {c['place']} now: {c['text_en']} ({c['text']}), {c['temp']}°C, feels like {c['feels']}°C, humidity "
            f"{c['humidity']}%, wind {c['wind']} km/h. Today {c['lo']}-{c['hi']}°C, chance of rain for the rest of today "
            f"{c['rain_today']}%. Next days: {days}. (A weather card with icons is already shown on screen.)")


if __name__ == "__main__":
    assert describe(0) == ("clear", "ท้องฟ้าแจ่มใส", "clear sky") and describe(0, 0)[0] == "night" and describe(2, 0)[0] == "night-partly"
    assert describe(63)[0] == "rain" and describe(95)[0] == "storm" and describe(45)[0] == "fog" and describe(1234)[0] == "cloud"
    assert clean_place("เชียงใหม่") == "เชียงใหม่" and clean_place("Chiang Mai, TH") == "Chiang Mai, TH"
    assert not re.search(r"[/:.?=]", clean_place("https://evil.example/?d=notes"))
    assert len(clean_place("x" * 200)) == 40 and clean_place("ผู้ใช้แพ้ถั่ว 555; รหัส 1234") == "ผู้ใช้แพ้ถั่ว รหัส"  # digits never leave
    fake = {"current": {"time": "2026-10-23T07:15", "temperature_2m": 25.9, "apparent_temperature": 32.4, "relative_humidity_2m": 95,
                        "weather_code": 2, "is_day": 1, "wind_speed_10m": 2.3},
            "hourly": {"time": ["2026-10-23T06:00", "2026-10-23T07:00", "2026-10-23T15:00", "2026-10-24T01:00"],
                       "precipitation_probability": [90, 20, 60, 99]},
            "daily": {"time": ["2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26"], "weather_code": [51, 3, 51, 80],
                      "temperature_2m_max": [31.2, 32, 30.6, 29.4], "temperature_2m_min": [24.1, 24.6, 24, 23.8],
                      "precipitation_probability_max": [80, 10, 55, 70]}}
    c = card(fake, "ทดสอบ")
    assert c["icon"] == "partly" and c["temp"] == 26 and c["feels"] == 32 and c["rain_today"] == 60, c  # 06:00 already past
    assert [d["day"] for d in c["days"]] == ["ส.", "อา.", "จ."] and c["days"][2]["icon"] == "rain"
    assert "26°C" in summary(c) and "ส. " in summary(c)
    # real call, once (owner allowed Open-Meteo): current location + one named city
    try:
        lat, lon, name = locate("")
        live = card(forecast(lat, lon), name)
        print("here:", name, live["temp"], "°C", live["text"], "| days:", [(d["day"], d["hi"]) for d in live["days"]])
        print("Chiang Mai:", locate("เชียงใหม่")[2])
    except Exception as e:
        print("live call skipped:", type(e).__name__, e)
    print("WEATHER SELFTEST OK")
