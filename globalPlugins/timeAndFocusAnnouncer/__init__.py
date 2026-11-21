# Time & Focus Announcer for NVDA (v1.1 Clean Open Source)
# Author: Kailas Eknath Bhoye
# Copyright (c) 2026 Kailas Eknath Bhoye
# Licensed under MIT License

import os
import time
import datetime
import ctypes
from ctypes import wintypes
import wx
import gui
import config
import ui
import scriptHandler
import globalPluginHandler
import nvwave
import winUser
from scriptHandler import script
from logHandler import log

SOUND_DIR = os.path.join(os.path.dirname(__file__), "sounds")
TICK_PATH = os.path.join(SOUND_DIR, "tick.wav")
# Tick sounds the user can switch between: (settings key, spoken name, file name)
TICK_SOUNDS = [
    ("standard", "Standard tick", "tick.wav"),
    ("loud", "Loud tick", "tick_loud.wav"),
]
DEFAULT_BELL = os.path.join(SOUND_DIR, "crystal.wav")
BELL_DELAY_MS = 600

HOURS_12 = ["12", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
HOURS_24 = [f"{i:02d}" for i in range(24)]
MINUTES_LIST = [str(i) for i in range(60)]

SOUNDPACKS = [
    ("crystal", "1. Crystal Glass Bell (Default)", "crystal.wav"),
    ("westminster", "2. Westminster Palace Gong", "westminster.wav"),
    ("tibetan", "3. Tibetan Singing Bowl", "tibetan.wav"),
    ("digital", "4. Modern Smartwatch Alert", "digital.wav"),
    ("woodblock", "5. Organic Woodblock Tap", "woodblock.wav"),
    ("tubular", "6. Acoustic Tubular Chime", "tubular.wav"),
    ("windchime", "7. Deep Wind Chimes", "windchime.wav"),
    ("cosmic", "8. Cosmic Starlight Ping", "cosmic.wav"),
    ("deskbell", "9. Vintage Desk Bell", "deskbell.wav"),
    ("cathedral", "10. Grand Cathedral Bronze", "cathedral.wav"),
    ("zen", "11. Zen Harmony Bell", "zen.wav"),
    ("marimba", "12. Soft Acoustic Marimba", "marimba.wav"),
]

PULSE_INTERVALS = [1, 3, 5, 10, 60]
PULSE_LABELS = ["Every 1 second (Continuous clock)", "Every 3 seconds", "Every 5 seconds", "Every 10 seconds", "Every 60 seconds (Minute pulse)"]

CONFIG_SECTION = "timeAndFocusAnnouncer"
config.conf.spec[CONFIG_SECTION] = {
    "intervalMinutes": "integer(default=0)",
    "invertSpinKeys": "boolean(default=false)",
    "announceWhenLocked": "boolean(default=false)",
    "format24Hour": "boolean(default=false)",
    "enableGreetings": "boolean(default=true)",
    "includeDateInPeriodic": "boolean(default=false)",
    "includeBatteryStatus": "boolean(default=false)",
    "batteryOnManualPress": "boolean(default=false)",
    "chimeOnlyMode": "boolean(default=false)",
    "suppressOnFullscreen": "boolean(default=true)",
    "soundPack": "string(default='crystal')",
    "customBellPath": "string(default='')",
    "scheduleEnabled": "boolean(default=false)",
    "scheduleFormat24Hour": "boolean(default=false)",
    "startHour": "integer(default=8,min=0,max=23)",
    "startMinute": "integer(default=0,min=0,max=59)",
    "endHour": "integer(default=22,min=0,max=23)",
    "endMinute": "integer(default=0,min=0,max=59)",
    "focusHours": "integer(default=0,min=0,max=999)",
    "focusMinutes": "integer(default=25,min=0,max=59)",
    "focusSeconds": "integer(default=0,min=0,max=59)",
    "breakHours": "integer(default=0,min=0,max=999)",
    "breakMinutes": "integer(default=5,min=0,max=59)",
    "breakSeconds": "integer(default=0,min=0,max=59)",
    "muteAnnouncements": "boolean(default=false)",
    "healthReminders": "boolean(default=true)",
    "healthReminderType": "integer(default=0)",
    "clockPulseEnabled": "boolean(default=false)",
    "clockPulseIntervalSecs": "integer(default=1)",
    "tickSound": "string(default=standard)",
    "timerContinuousTick": "boolean(default=true)",
}

INTERVAL_CHOICES = [0, 15, 30, 45, 60]
INTERVAL_LABELS = ["Off", "Every 15 minutes", "Every 30 minutes", "Every 45 minutes", "Every 1 hour"]
_timerRemainingSecs = 0
_countdownActive = False
_countdownTimerObj = None

_pomodoroActive = False
_pomodoroIsBreak = False
_pomodoroRemainingSecs = 0
_pomodoroTimerObj = None

_clockPulseTimerObj = None
_nvdaSessionStartTime = time.time()

class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]

def _cfg():
    return config.conf[CONFIG_SECTION]

def getResolvedBellPath(override_custom=None):
    if override_custom and os.path.exists(override_custom):
        return override_custom
    custom = _cfg().get("customBellPath", "").strip()
    if custom and os.path.exists(custom):
        return custom
    sp = _cfg().get("soundPack", "crystal")
    for key, _, fname in SOUNDPACKS:
        if key == sp:
            p = os.path.join(SOUND_DIR, fname)
            if os.path.exists(p):
                return p
    return DEFAULT_BELL

def _lockedByWtsSession():
    """Windows' own record of this session: is it locked?

    This also covers the lock screen picture (the screen with the clock that shows
    before the sign-in box), which runs on the normal desktop.
    """
    try:
        import os
        wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wts.WTSQuerySessionInformationW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)
        ]
        wts.WTSQuerySessionInformationW.restype = ctypes.c_int
        wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        kernel32.ProcessIdToSessionId.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        mySession = ctypes.c_uint32(0)
        if not kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(mySession)):
            return False
        buf = ctypes.c_void_p()
        size = ctypes.c_uint32(0)
        # WTS_CURRENT_SERVER_HANDLE = NULL, WTS_CURRENT_SESSION = 0xFFFFFFFF, WTSSessionInfoEx = 25
        if not wts.WTSQuerySessionInformationW(None, 0xFFFFFFFF, 25, ctypes.byref(buf), ctypes.byref(size)):
            return False
        try:
            if not buf.value or size.value < 20:
                return False
            # WTSINFOEX: Level (4 bytes) and 4 bytes of padding, because the data that follows is
            # 8-byte aligned. Then SessionId (offset 8), SessionState (offset 12), SessionFlags (offset 16).
            sessionId = ctypes.c_uint32.from_address(buf.value + 8).value
            if sessionId != mySession.value:
                return False  # the layout is not what we expect, so do not trust it
            flags = ctypes.c_uint32.from_address(buf.value + 16).value
            return flags == 0  # WTS_SESSIONSTATE_LOCK
        finally:
            wts.WTSFreeMemory(buf)
    except Exception:
        return False

def _lockedByNvda():
    """NVDA's own lock tracking."""
    try:
        from winAPI.sessionTracking import isWindowsLocked as _nvdaIsWindowsLocked
        return bool(_nvdaIsWindowsLocked())
    except Exception:
        return False

def _lockedBySecureDesktop():
    """The sign-in screen runs on a secure desktop that a normal program cannot open."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenInputDesktop.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        user32.CloseDesktop.argtypes = [ctypes.c_void_p]
        user32.GetUserObjectInformationW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)
        ]
        hDesk = user32.OpenInputDesktop(0, 0, 0x0001)  # DESKTOP_READOBJECTS
        if not hDesk:
            # Access denied means the secure desktop (sign-in screen) is active.
            return ctypes.get_last_error() == 5
        try:
            buf = ctypes.create_unicode_buffer(256)
            needed = ctypes.c_uint32(0)
            ok = user32.GetUserObjectInformationW(hDesk, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed))  # 2 = UOI_NAME
        finally:
            user32.CloseDesktop(hDesk)
        return bool(ok) and buf.value.lower() != "default"
    except Exception:
        return False

def _lockedByForegroundWindow():
    """The lock screen is a full-screen window of LockApp.exe (or LogonUI.exe)."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)
        ]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = ctypes.c_uint32(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hProc = kernel32.OpenProcess(0x1000, 0, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not hProc:
            return False
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = ctypes.c_uint32(520)
            if not kernel32.QueryFullProcessImageNameW(hProc, 0, buf, ctypes.byref(size)):
                return False
            exeName = buf.value.replace("/", "\\").split("\\")[-1].lower()
        finally:
            kernel32.CloseHandle(hProc)
        return exeName in ("lockapp.exe", "logonui.exe")
    except Exception:
        return False

_lockCache = {"time": 0.0, "value": False}

def isWindowsLocked():
    """True while Windows is locked: the lock screen picture or the sign-in screen.

    Several independent checks are used, and any one of them is enough, so this works
    on laptops with the lid open and on desktop PCs, including PCs without a password.
    The answer is remembered for half a second because it is asked often.
    """
    import time
    now = time.monotonic()
    if now - _lockCache["time"] < 0.5:
        return _lockCache["value"]
    reasons = [
        name for name, check in (
            ("session", _lockedByWtsSession),
            ("nvda", _lockedByNvda),
            ("secureDesktop", _lockedBySecureDesktop),
            ("foreground", _lockedByForegroundWindow),
        ) if check()
    ]
    locked = bool(reasons)
    _lockCache["time"] = now
    _lockCache["value"] = locked
    if locked:
        try:
            from logHandler import log
            log.debug("Time and Focus Announcer: Windows is locked (" + ", ".join(reasons) + ")")
        except Exception:
            pass
    return locked

def isSilentForLock():
    """True when automatic sounds and speech should stay quiet because Windows is locked."""
    try:
        if _cfg()["announceWhenLocked"]:
            return False
    except Exception:
        pass
    return isWindowsLocked()

def playActiveBell(override_path=None):
    if isSilentForLock():
        return
    path = override_path or getResolvedBellPath()
    try:
        if os.path.exists(path):
            nvwave.playWaveFile(path, asynchronous=True)
    except Exception:
        pass

def getTickPath():
    try:
        chosen = _cfg().get("tickSound", "standard")
    except Exception:
        chosen = "standard"
    for key, _name, fileName in TICK_SOUNDS:
        if key == chosen:
            path = os.path.join(SOUND_DIR, fileName)
            if os.path.exists(path):
                return path
    return TICK_PATH

def playTick():
    if isSilentForLock():
        return
    try:
        path = getTickPath()
        if os.path.exists(path):
            nvwave.playWaveFile(path, asynchronous=True)
    except Exception:
        pass

def _timerBlocksClockPulse():
    """True while a countdown timer with continuous ticking is running."""
    return bool(_countdownActive and _cfg().get("timerContinuousTick", True))

def _timerFinalCountdownActive():
    """True during the last 3 seconds of a countdown timer, when the timer plays its own ticks."""
    return bool(_countdownActive and 1 <= _timerRemainingSecs <= 3)

CLOCK_BLOCKED_MESSAGE = (
    "Sorry, the ambient clock cannot be turned on while a countdown timer with continuous ticking is running. "
    "Please let the timer finish or stop it first, and then turn the ambient clock on. Thank you."
)

def syncClockPulse():
    global _clockPulseTimerObj
    if not _clockPulseTimerObj:
        _clockPulseTimerObj = wx.Timer()
        _clockPulseTimerObj.Bind(wx.EVT_TIMER, _onClockPulseTick)

    if _cfg()["clockPulseEnabled"] and not _timerBlocksClockPulse():
        ms = max(1000, _cfg().get("clockPulseIntervalSecs", 1) * 1000)
        _clockPulseTimerObj.Start(ms)
    else:
        _clockPulseTimerObj.Stop()

def _onClockPulseTick(event):
    if not _cfg()["clockPulseEnabled"] or _timerBlocksClockPulse() or _timerFinalCountdownActive():
        return
    if _cfg()["suppressOnFullscreen"] and isForegroundFullscreen():
        return
    playTick()

def getBatterySummary(mode="critical", explain_critical=False):
    """Return the battery sentence fragment.

    mode "critical": only when the battery is critical (20% or lower and not
        charging). A normal battery state returns nothing. Used for automatic
        (periodic) announcements.
    mode "full": the current battery state, or the critical warning when critical.
        Used when the user presses the time shortcut and has asked for it.
    mode "test": always says something, for the Test button in settings.
    """
    try:
        sps = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
            percent = int(sps.BatteryLifePercent)
            no_battery = (percent > 100) or bool(sps.BatteryFlag & 128)
            if no_battery:
                return ", No battery detected on this computer" if mode == "test" else ""
            is_plugged = (sps.ACLineStatus == 1)
            is_critical = (percent <= 20 and not is_plugged)
            if is_critical:
                return f", Warning: battery is critical at {percent}% and not charging"
            if mode == "critical":
                return ""
            state = "plugged in" if is_plugged else "on battery"
            out = f", Battery at {percent}% {state}"
            if mode == "test" and explain_critical:
                out += ". The battery warning is on, and it will be announced when the battery is at 20 percent or lower and not charging"
            return out
    except Exception:
        pass
    return ", Battery status is not available" if mode == "test" else ""

def isForegroundFullscreen():
    try:
        hwnd = winUser.getForegroundWindow()
        if not hwnd or hwnd == winUser.getDesktopWindow() or hwnd == winUser.getShellWindow():
            return False
        rect = winUser.getWindowRect(hwnd)
        screen_w = winUser.user32.GetSystemMetrics(0)
        screen_h = winUser.user32.GetSystemMetrics(1)
        return ((rect[2] - rect[0]) >= screen_w and (rect[3] - rect[1]) >= screen_h)
    except Exception:
        return False

def getUptimeReport():
    now_sec = time.time()
    nvda_duration = int(max(0, now_sec - _nvdaSessionStartTime))
    nvda_hours = nvda_duration // 3600
    nvda_mins = (nvda_duration % 3600) // 60

    if nvda_hours > 0:
        session_str = f"NVDA session runtime is {nvda_hours} hours and {nvda_mins} minutes"
    else:
        session_str = f"NVDA session runtime is {nvda_mins} minutes"

    try:
        uptime_ms = ctypes.windll.kernel32.GetTickCount64()
        sys_sec = int(uptime_ms // 1000)
        sys_hours = sys_sec // 3600
        sys_mins = (sys_sec % 3600) // 60
        return f"{session_str}. Windows uptime is {sys_hours} hours and {sys_mins} minutes."
    except Exception:
        return session_str

def buildTimeSentence(now=None, override_24=None, override_greetings=None, override_inc_date=None, override_battery=None, override_battery_manual=None, battery_test=False, is_periodic=False):
    now = now or datetime.datetime.now()
    cfg = _cfg()
    is24 = override_24 if override_24 is not None else cfg["format24Hour"]
    use_greetings = override_greetings if override_greetings is not None else cfg["enableGreetings"]
    inc_date = override_inc_date if override_inc_date is not None else cfg["includeDateInPeriodic"]
    inc_battery = override_battery if override_battery is not None else cfg["includeBatteryStatus"]
    inc_battery_manual = override_battery_manual if override_battery_manual is not None else cfg["batteryOnManualPress"]

    h24 = now.hour
    m = now.minute

    greeting = ""
    if use_greetings:
        if 0 <= h24 < 12:
            greeting = "Good morning! "
        elif 12 <= h24 < 16:
            greeting = "Good afternoon! "
        else:
            greeting = "Good evening! "

    if is24:
        if m == 0:
            time_str = f"The time is {h24} 0 0"
        else:
            time_str = f"The time is {h24}:{m:02d}"
    else:
        h12 = h24 % 12 or 12
        ampm = "AM" if h24 < 12 else "PM"
        time_str = f"It is {h12} o'clock {ampm}" if m == 0 else f"It is {h12}:{m:02d} {ampm}"

    out = f"{greeting}{time_str}".strip()
    if inc_date:
        out += f", {now.strftime('%A, %B %d')}"
    if battery_test:
        if inc_battery or inc_battery_manual:
            out += getBatterySummary("test", explain_critical=inc_battery)
    elif is_periodic:
        if inc_battery:
            out += getBatterySummary("critical")
    elif inc_battery_manual:
        out += getBatterySummary("full")
    return out

def isWithinSchedule(now=None):
    if not _cfg()["scheduleEnabled"]:
        return True
    now = now or datetime.datetime.now()
    start = _cfg()["startHour"] * 60 + _cfg()["startMinute"]
    end = _cfg()["endHour"] * 60 + _cfg()["endMinute"]
    cur = now.hour * 60 + now.minute
    return (start <= cur <= end) if (start <= end) else (cur >= start or cur <= end)

def announceTime(override_bell=None, override_24=None, override_greetings=None, override_inc_date=None, override_battery=None, override_chime_only=None, is_periodic=False, is_test=False, override_battery_manual=None):
    if is_periodic and _cfg()["muteAnnouncements"]:
        return
    if is_periodic and isSilentForLock():
        return

    is_chime_only = override_chime_only if override_chime_only is not None else _cfg().get("chimeOnlyMode", False)

    if is_periodic and is_chime_only:
        playActiveBell(override_bell)
        return

    is_clock_pulse_on = _cfg().get("clockPulseEnabled", False)
    is_timer_running = _countdownActive and _cfg().get("timerContinuousTick", True)

    # The bell is muted whenever the ambient clock or a ticking countdown timer
    # is running. This now applies to periodic announcements as well as manual ones.
    is_ambient_active = is_clock_pulse_on or is_timer_running
    should_play_bell = not is_ambient_active
    if should_play_bell:
        playActiveBell(override_bell)
    elif not is_periodic:
        playTick()

    delay = BELL_DELAY_MS if should_play_bell else 0

    def doSpeech():
        text = buildTimeSentence(
            override_24=override_24,
            override_greetings=override_greetings,
            override_inc_date=override_inc_date,
            override_battery=override_battery,
            override_battery_manual=override_battery_manual,
            battery_test=is_test,
            is_periodic=is_periodic
        )
        if is_periodic and _cfg()["healthReminders"]:
            hType = _cfg()["healthReminderType"]
            if hType == 0:
                text += ". Remember to drink some water and stretch your posture."
            elif hType == 1:
                text += ". Time to drink a glass of water."
            else:
                text += ". Check your back posture and relax your shoulders."
        ui.message(text.rstrip(" .,!?:;"))

    if delay > 0:
        wx.CallLater(delay, doSpeech)
    else:
        doSpeech()

def announceDate():
    is_timer_running = (_countdownActive and _cfg().get("timerContinuousTick", True)) or _cfg().get("clockPulseEnabled", False)
    if not is_timer_running:
        playActiveBell()
    else:
        playTick()

    delay = BELL_DELAY_MS if not is_timer_running else 0

    def doSpeech():
        now = datetime.datetime.now()
        ui.message(now.strftime("Today is %A, %B %d, %Y"))

    if delay > 0:
        wx.CallLater(delay, doSpeech)
    else:
        doSpeech()

def announcePrecisionSeconds():
    is_timer_running = (_countdownActive and _cfg().get("timerContinuousTick", True)) or _cfg().get("clockPulseEnabled", False)
    if not is_timer_running:
        playActiveBell()
    else:
        playTick()

    delay = BELL_DELAY_MS if not is_timer_running else 0

    def doSpeech():
        now = datetime.datetime.now()
        cfg = _cfg()
        is24 = cfg["format24Hour"]
        h24 = now.hour
        m = now.minute
        s = now.second

        m_unit = "minute" if m == 1 else "minutes"
        s_unit = "second" if s == 1 else "seconds"

        if is24:
            h_unit = "hour" if h24 == 1 else "hours"
            ui.message(f"Exact time is {h24} {h_unit}, {m} {m_unit}, and {s} {s_unit}")
        else:
            h12 = h24 % 12 or 12
            ampm = "AM" if h24 < 12 else "PM"
            h_unit = "hour" if h12 == 1 else "hours"
            ui.message(f"Exact time is {h12} {h_unit}, {m} {m_unit}, and {s} {s_unit} {ampm}")

    if delay > 0:
        wx.CallLater(delay, doSpeech)
    else:
        doSpeech()

def startCountdown(seconds):
    global _timerRemainingSecs, _countdownActive, _countdownTimerObj, _pomodoroActive
    if _pomodoroActive:
        ui.message("Pomodoro focus session is currently active. Please stop focus before starting a timer.")
        return
    _timerRemainingSecs = seconds
    _countdownActive = True
    syncClockPulse()
    if not _countdownTimerObj:
        _countdownTimerObj = wx.Timer()
        _countdownTimerObj.Bind(wx.EVT_TIMER, _onCountdownTick)
    _countdownTimerObj.Start(1000)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    parts = []
    if h: parts.append(f"{h} hours")
    if m: parts.append(f"{m} minutes")
    if s: parts.append(f"{s} seconds")
    msg = f"Countdown timer started for {' '.join(parts)}"
    wx.CallLater(350, lambda: ui.message(msg))

def _onCountdownTick(event):
    global _timerRemainingSecs, _countdownActive, _countdownTimerObj
    if not _countdownActive:
        return
    _timerRemainingSecs -= 1

    continuous = _cfg().get("timerContinuousTick", True)
    if _timerRemainingSecs > 0:
        if continuous or (1 <= _timerRemainingSecs <= 3):
            playTick()
    elif _timerRemainingSecs <= 0:
        _countdownActive = False
        syncClockPulse()
        _countdownTimerObj.Stop()
        playActiveBell(DEFAULT_BELL)
        if not isSilentForLock():
            wx.CallLater(600, lambda: ui.message("Time is up! Your countdown timer has finished."))

def stopCountdown():
    global _countdownActive, _countdownTimerObj, _timerRemainingSecs
    if _countdownActive:
        _countdownActive = False
        syncClockPulse()
        if _countdownTimerObj:
            _countdownTimerObj.Stop()
        _timerRemainingSecs = 0
        ui.message("Countdown timer cancelled.")
    else:
        ui.message("No active timer running.")

def _pomodoroBellAllowed():
    # While the ambient clock is on, focus session alerts are speech only (no bell).
    return not _cfg().get("clockPulseEnabled", False)

def _speakAfterBell(bell_played, delay_ms, text):
    if isSilentForLock():
        return
    if bell_played:
        wx.CallLater(delay_ms, lambda: ui.message(text))
    else:
        ui.message(text)

def _durationText(h, m, sec, default_text):
    parts = []
    if h: parts.append(f"{h} {'hour' if h == 1 else 'hours'}")
    if m: parts.append(f"{m} {'minute' if m == 1 else 'minutes'}")
    if sec: parts.append(f"{sec} {'second' if sec == 1 else 'seconds'}")
    return " ".join(parts) if parts else default_text

def _focusTotalSecs(cfg):
    total = cfg.get("focusHours", 0) * 3600 + cfg.get("focusMinutes", 25) * 60 + cfg.get("focusSeconds", 0)
    return total if total > 0 else 25 * 60

def _breakTotalSecs(cfg):
    total = cfg.get("breakHours", 0) * 3600 + cfg.get("breakMinutes", 5) * 60 + cfg.get("breakSeconds", 0)
    return total if total > 0 else 5 * 60

def startPomodoroWithCustom(f_h, f_m, f_s, b_h, b_m, b_s):
    global _pomodoroActive, _pomodoroIsBreak, _pomodoroRemainingSecs, _pomodoroTimerObj, _countdownActive
    if _countdownActive:
        ui.message("Countdown timer is currently active. Please stop the timer before starting focus.")
        return
    cfg = _cfg()
    cfg["focusHours"] = f_h
    cfg["focusMinutes"] = f_m
    cfg["focusSeconds"] = f_s
    cfg["breakHours"] = b_h
    cfg["breakMinutes"] = b_m
    cfg["breakSeconds"] = b_s

    _pomodoroActive = True
    _pomodoroIsBreak = False
    _pomodoroRemainingSecs = _focusTotalSecs(cfg)

    if not _pomodoroTimerObj:
        _pomodoroTimerObj = wx.Timer()
        _pomodoroTimerObj.Bind(wx.EVT_TIMER, _onPomodoroTick)
    _pomodoroTimerObj.Start(1000)
    bell_on = _pomodoroBellAllowed()
    if bell_on:
        playActiveBell()

    f_text = _durationText(f_h, f_m, f_s, "25 minutes")
    _speakAfterBell(bell_on, 350, f"Pomodoro focus session started for {f_text}.")

def stopPomodoroSession():
    global _pomodoroActive, _pomodoroTimerObj
    if _pomodoroActive:
        _pomodoroActive = False
        if _pomodoroTimerObj:
            _pomodoroTimerObj.Stop()
        ui.message("Pomodoro session stopped.")
    else:
        ui.message("No active Pomodoro session running.")

def stopAllActiveSessions():
    global _countdownActive, _pomodoroActive
    stopped_any = False
    if _countdownActive:
        stopCountdown()
        stopped_any = True
    if _pomodoroActive:
        stopPomodoroSession()
        stopped_any = True
    if not stopped_any:
        ui.message("No active timer or focus session running.")

def togglePomodoro():
    global _pomodoroActive, _pomodoroIsBreak, _pomodoroRemainingSecs, _pomodoroTimerObj
    if _pomodoroActive:
        stopPomodoroSession()
    else:
        cfg = _cfg()
        startPomodoroWithCustom(
            cfg.get("focusHours", 0),
            cfg.get("focusMinutes", 25),
            cfg.get("focusSeconds", 0),
            cfg.get("breakHours", 0),
            cfg.get("breakMinutes", 5),
            cfg.get("breakSeconds", 0)
        )

def _onPomodoroTick(event):
    global _pomodoroActive, _pomodoroIsBreak, _pomodoroRemainingSecs
    if not _pomodoroActive:
        return
    _pomodoroRemainingSecs -= 1
    if _pomodoroRemainingSecs <= 0:
        bell_on = _pomodoroBellAllowed()
        if bell_on:
            playActiveBell()
        cfg = _cfg()
        if not _pomodoroIsBreak:
            _pomodoroIsBreak = True
            _pomodoroRemainingSecs = _breakTotalSecs(cfg)
            b_text = _durationText(cfg.get("breakHours", 0), cfg.get("breakMinutes", 5), cfg.get("breakSeconds", 0), "5 minutes")
            _speakAfterBell(bell_on, 600, f"Focus complete! Take a break for {b_text}.")
        else:
            _pomodoroIsBreak = False
            _pomodoroRemainingSecs = _focusTotalSecs(cfg)
            _speakAfterBell(bell_on, 600, "Break finished! Ready for next focus session.")

def setupSpinCtrl(spin_ctrl, label_name):
    """Name a number box and apply the arrow key direction chosen in Advanced settings.

    Default (standard): Up arrow increases the value, Down arrow decreases it.
    When "Reverse arrow keys in number boxes" is ticked: Down increases, Up decreases.
    """
    spin_ctrl.SetName(label_name)

    def onSpinKey(event):
        try:
            reverse = bool(_cfg()["invertSpinKeys"])
        except Exception:
            reverse = False
        if not reverse:
            event.Skip()
            return
        key = event.GetKeyCode()
        val = spin_ctrl.GetValue()
        if key == wx.WXK_DOWN:
            if val < spin_ctrl.GetMax():
                spin_ctrl.SetValue(val + 1)
            ui.message(str(spin_ctrl.GetValue()))
            return
        elif key == wx.WXK_UP:
            if val > spin_ctrl.GetMin():
                spin_ctrl.SetValue(val - 1)
            ui.message(str(spin_ctrl.GetValue()))
            return
        event.Skip()
    spin_ctrl.Bind(wx.EVT_CHAR_HOOK, onSpinKey)

class PrecisionCountdownDialog(wx.Dialog):
    _instance = None

    def __init__(self, parent):
        super().__init__(parent, title="Countdown Timer - Time & Focus Announcer", style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP)
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(1, 6, 8, 8)

        lblH = wx.StaticText(self, label="Timer Hours:")
        grid.Add(lblH, flag=wx.ALIGN_CENTER_VERTICAL)
        self.hSpin = wx.SpinCtrl(self, min=0, max=23, initial=0)
        setupSpinCtrl(self.hSpin, "Timer Hours")
        grid.Add(self.hSpin, 0)

        lblM = wx.StaticText(self, label="Timer Minutes:")
        grid.Add(lblM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.mSpin = wx.SpinCtrl(self, min=0, max=59, initial=5)
        setupSpinCtrl(self.mSpin, "Timer Minutes")
        grid.Add(self.mSpin, 0)

        lblS = wx.StaticText(self, label="Timer Seconds:")
        grid.Add(lblS, flag=wx.ALIGN_CENTER_VERTICAL)
        self.sSpin = wx.SpinCtrl(self, min=0, max=59, initial=0)
        setupSpinCtrl(self.sSpin, "Timer Seconds")
        grid.Add(self.sSpin, 0)
        sizer.Add(grid, flag=wx.ALL | wx.EXPAND, border=12)

        btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btnSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=10)
        self.Bind(wx.EVT_BUTTON, self.onStart, id=wx.ID_OK)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.SetSizerAndFit(sizer)
        self.CenterOnScreen()

    def onCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            PrecisionCountdownDialog._instance = None
            self.Destroy()
            return
        event.Skip()

    def onStart(self, event):
        tot = self.hSpin.GetValue() * 3600 + self.mSpin.GetValue() * 60 + self.sSpin.GetValue()
        if tot <= 0:
            ui.message("Please enter a valid time duration.")
            return
        PrecisionCountdownDialog._instance = None
        self.Destroy()
        startCountdown(tot)

    def onClose(self, event):
        PrecisionCountdownDialog._instance = None
        event.Skip()

def openCountdownDialog():
    if PrecisionCountdownDialog._instance is not None:
        try:
            PrecisionCountdownDialog._instance.Raise()
            PrecisionCountdownDialog._instance.SetFocus()
            return
        except Exception:
            PrecisionCountdownDialog._instance = None
    dlg = PrecisionCountdownDialog(gui.mainFrame)
    PrecisionCountdownDialog._instance = dlg
    dlg.Show()
    dlg.Raise()
    dlg.hSpin.SetFocus()

class SettingsDialog(wx.Dialog):
    _instance = None

    def __init__(self, parent):
        super().__init__(parent, title="Time & Focus Announcer Settings")
        cfg = _cfg()
        outer = wx.BoxSizer(wx.VERTICAL)

        headerPanel = wx.Panel(self)
        headerPanel.SetBackgroundColour(wx.Colour(30, 42, 56))
        headBox = wx.BoxSizer(wx.VERTICAL)
        lblTitle = wx.StaticText(headerPanel, label="Time & Focus Announcer")
        lblTitle.SetForegroundColour(wx.Colour(255, 255, 255))
        fTitle = lblTitle.GetFont()
        fTitle.SetPointSize(fTitle.GetPointSize() + 3)
        fTitle.SetWeight(wx.FONTWEIGHT_BOLD)
        lblTitle.SetFont(fTitle)

        lblSub = wx.StaticText(headerPanel, label="Accessible Audio Timepiece & Focus Suite  |  Author: Kailas Eknath Bhoye")
        lblSub.SetForegroundColour(wx.Colour(180, 205, 230))
        headBox.Add(lblTitle, flag=wx.ALL, border=8)
        headBox.Add(lblSub, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
        headerPanel.SetSizer(headBox)
        outer.Add(headerPanel, flag=wx.EXPAND)

        self.notebook = wx.Notebook(self)
        self._buildGeneralTab(cfg)
        self._buildScheduleTab(cfg)
        self._buildAdvancedTab(cfg)
        outer.Add(self.notebook, 1, flag=wx.ALL | wx.EXPAND, border=8)

        btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(btnSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=8)

        self.Bind(wx.EVT_BUTTON, self.onOK, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

        self.ID_HOTKEY_TEST_TIME = wx.NewIdRef()
        self.ID_HOTKEY_START_TIMER = wx.NewIdRef()
        self.ID_HOTKEY_STOP_COMMON = wx.NewIdRef()
        self.ID_HOTKEY_START_FOCUS = wx.NewIdRef()
        self.ID_HOTKEY_TEST_CHIME = wx.NewIdRef()
        self.ID_HOTKEY_BROWSE = wx.NewIdRef()

        self.Bind(wx.EVT_MENU, lambda e: self.onGeneralTestClick(None), id=self.ID_HOTKEY_TEST_TIME)
        self.Bind(wx.EVT_MENU, lambda e: self.onStartTabTimer(None), id=self.ID_HOTKEY_START_TIMER)
        self.Bind(wx.EVT_MENU, lambda e: stopAllActiveSessions(), id=self.ID_HOTKEY_STOP_COMMON)
        self.Bind(wx.EVT_MENU, lambda e: self.onStartTabFocus(None), id=self.ID_HOTKEY_START_FOCUS)
        self.Bind(wx.EVT_MENU, lambda e: self.onTestCurrentChime(None), id=self.ID_HOTKEY_TEST_CHIME)
        self.Bind(wx.EVT_MENU, lambda e: self.onBrowseWav(None), id=self.ID_HOTKEY_BROWSE)

        accel_entries = [
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('T'), self.ID_HOTKEY_TEST_TIME),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('S'), self.ID_HOTKEY_START_TIMER),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('X'), self.ID_HOTKEY_STOP_COMMON),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('F'), self.ID_HOTKEY_START_FOCUS),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('P'), self.ID_HOTKEY_TEST_CHIME),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord('B'), self.ID_HOTKEY_BROWSE),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))

        self.SetSizerAndFit(outer)
        self.SetMinSize((580, 750))
        wx.CallAfter(self.notebook.SetFocus)

    def onCharHook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            SettingsDialog._instance = None
            self.Destroy()
            return
        event.Skip()

    def _bindEnterKey(self, btn, action_func):
        def onKey(evt):
            if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE):
                action_func(None)
            else:
                evt.Skip()
        btn.Bind(wx.EVT_CHAR_HOOK, onKey)

    def getActiveDialogBellPath(self):
        cPath = self.customPath.GetValue().strip()
        if cPath and os.path.exists(cPath):
            return cPath
        idx = self.packChoice.GetSelection()
        if idx < 0 or idx >= len(SOUNDPACKS):
            idx = 0
        key, _, fname = SOUNDPACKS[idx]
        return os.path.join(SOUND_DIR, fname)

    def _buildGeneralTab(self, cfg):
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        lblInt = wx.StaticText(panel, label="Automatic Announcement Frequency:")
        sizer.Add(lblInt, flag=wx.LEFT | wx.TOP, border=8)
        self.intervalChoice = wx.Choice(panel, choices=INTERVAL_LABELS)
        self.intervalChoice.SetName("Automatic Announcement Frequency")
        try: idx = INTERVAL_CHOICES.index(cfg["intervalMinutes"])
        except ValueError: idx = 0
        self.intervalChoice.SetSelection(idx)
        sizer.Add(self.intervalChoice, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=8)

        lblFmt = wx.StaticText(panel, label="Spoken Time Format:")
        sizer.Add(lblFmt, flag=wx.LEFT | wx.TOP, border=8)
        self.formatChoice = wx.Choice(panel, choices=["12-hour format (e.g. It is 2:30 PM)", "24-hour format (e.g. 13:00 / 13:01)"])
        self.formatChoice.SetName("Spoken Time Format")
        self.formatChoice.SetSelection(1 if cfg["format24Hour"] else 0)
        sizer.Add(self.formatChoice, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=8)

        self.greetingsCheck = wx.CheckBox(panel, label="&Include contextual greetings (Good morning / afternoon / evening)")
        self.greetingsCheck.SetValue(cfg["enableGreetings"])
        sizer.Add(self.greetingsCheck, flag=wx.ALL, border=8)

        self.includeDateCheck = wx.CheckBox(panel, label="&Include current day and date in periodic announcements")
        self.includeDateCheck.SetValue(cfg["includeDateInPeriodic"])
        sizer.Add(self.includeDateCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.includeBatteryCheck = wx.CheckBox(panel, label="&Warn about a critical battery in periodic announcements (20 percent or lower and not charging)")
        self.includeBatteryCheck.SetValue(cfg["includeBatteryStatus"])
        sizer.Add(self.includeBatteryCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.batteryManualCheck = wx.CheckBox(panel, label="Also announce the battery status when the time &shortcut is pressed manually")
        self.batteryManualCheck.SetValue(cfg["batteryOnManualPress"])
        sizer.Add(self.batteryManualCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.chimeOnlyCheck = wx.CheckBox(
            panel,
            label="&Chime-only discrete mode (Play a single bell chime at selected interval without speech)"
        )
        self.chimeOnlyCheck.SetValue(cfg["chimeOnlyMode"])
        sizer.Add(self.chimeOnlyCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.fullscreenCheck = wx.CheckBox(panel, label="&Do not disturb when fullscreen apps or games are active")
        self.fullscreenCheck.SetValue(cfg["suppressOnFullscreen"])
        sizer.Add(self.fullscreenCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.testBtn = wx.Button(panel, label="&Test Selected Announcement Mode (Alt+T)")
        self.testBtn.Bind(wx.EVT_BUTTON, self.onGeneralTestClick)
        self._bindEnterKey(self.testBtn, self.onGeneralTestClick)
        sizer.Add(self.testBtn, flag=wx.ALL, border=8)

        panel.SetSizer(sizer)
        self.notebook.AddPage(panel, "General")

    def onGeneralTestClick(self, event):
        live_bell = self.getActiveDialogBellPath()
        is24 = (self.formatChoice.GetSelection() == 1)
        use_greetings = self.greetingsCheck.GetValue()
        inc_date = self.includeDateCheck.GetValue()
        inc_battery = self.includeBatteryCheck.GetValue()
        inc_battery_manual = self.batteryManualCheck.GetValue()
        is_chime = self.chimeOnlyCheck.GetValue()

        if is_chime:
            playActiveBell(live_bell)
            ui.message("Testing chime-only discrete mode: single bell chime played.")
        else:
            announceTime(
                override_bell=live_bell,
                override_24=is24,
                override_greetings=use_greetings,
                override_inc_date=inc_date,
                override_battery=inc_battery,
                override_battery_manual=inc_battery_manual,
                override_chime_only=False,
                is_periodic=False,
                is_test=True
            )

    def _buildScheduleTab(self, cfg):
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.scheduleCheck = wx.CheckBox(panel, label="&Only announce automatically during scheduled daytime window")
        self.scheduleCheck.SetValue(cfg["scheduleEnabled"])
        sizer.Add(self.scheduleCheck, flag=wx.ALL, border=10)

        lblFmt = wx.StaticText(panel, label="Schedule Time Input Format:")
        sizer.Add(lblFmt, flag=wx.LEFT | wx.TOP, border=8)
        self.schedFormatChoice = wx.Choice(panel, choices=["12-hour format (12, 1..11 with AM/PM)", "24-hour format (00..23)"])
        self.schedFormatChoice.SetName("Schedule Time Input Format")
        sched_is_24 = cfg.get("scheduleFormat24Hour", False)
        self.schedFormatChoice.SetSelection(1 if sched_is_24 else 0)
        self.schedFormatChoice.Bind(wx.EVT_CHOICE, self.onSchedFormatChanged)
        sizer.Add(self.schedFormatChoice, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=8)

        s_h24 = cfg["startHour"]
        e_h24 = cfg["endHour"]
        s_min = cfg["startMinute"]
        e_min = cfg["endMinute"]

        grid = wx.FlexGridSizer(2, 6, 8, 8)
        lblStart = wx.StaticText(panel, label="Scheduled Start Hour:")
        grid.Add(lblStart, flag=wx.ALIGN_CENTER_VERTICAL)
        init_choices = HOURS_24 if sched_is_24 else HOURS_12
        self.startHourChoice = wx.Choice(panel, choices=init_choices)
        self.startHourChoice.SetName("Scheduled Start Hour")
        self._setHourSelection(self.startHourChoice, s_h24, sched_is_24)
        grid.Add(self.startHourChoice, 0)

        lblStartMin = wx.StaticText(panel, label="Scheduled Start Minute:")
        grid.Add(lblStartMin, flag=wx.ALIGN_CENTER_VERTICAL)
        self.startMinuteChoice = wx.Choice(panel, choices=MINUTES_LIST)
        self.startMinuteChoice.SetName("Scheduled Start Minute")
        self.startMinuteChoice.SetSelection(max(0, min(59, s_min)))
        grid.Add(self.startMinuteChoice, 0)

        self.startAmPm = wx.Choice(panel, choices=["AM", "PM"])
        self.startAmPm.SetName("Scheduled Start AM or PM")
        self.startAmPm.SetSelection(0 if s_h24 < 12 else 1)
        grid.Add(self.startAmPm, 0)
        grid.Add(wx.StaticText(panel, label=""), 0)

        lblEnd = wx.StaticText(panel, label="Scheduled End Hour:")
        grid.Add(lblEnd, flag=wx.ALIGN_CENTER_VERTICAL)
        self.endHourChoice = wx.Choice(panel, choices=init_choices)
        self.endHourChoice.SetName("Scheduled End Hour")
        self._setHourSelection(self.endHourChoice, e_h24, sched_is_24)
        grid.Add(self.endHourChoice, 0)

        lblEndMin = wx.StaticText(panel, label="Scheduled End Minute:")
        grid.Add(lblEndMin, flag=wx.ALIGN_CENTER_VERTICAL)
        self.endMinuteChoice = wx.Choice(panel, choices=MINUTES_LIST)
        self.endMinuteChoice.SetName("Scheduled End Minute")
        self.endMinuteChoice.SetSelection(max(0, min(59, e_min)))
        grid.Add(self.endMinuteChoice, 0)

        self.endAmPm = wx.Choice(panel, choices=["AM", "PM"])
        self.endAmPm.SetName("Scheduled End AM or PM")
        self.endAmPm.SetSelection(0 if e_h24 < 12 else 1)
        grid.Add(self.endAmPm, 0)
        grid.Add(wx.StaticText(panel, label=""), 0)

        sizer.Add(grid, flag=wx.ALL | wx.EXPAND, border=10)
        panel.SetSizer(sizer)
        self.notebook.AddPage(panel, "Schedule")

        if sched_is_24:
            self.startAmPm.Hide()
            self.endAmPm.Hide()

    def _setHourSelection(self, ctrl, h24, is24):
        if is24: ctrl.SetSelection(h24 % 24)
        else: ctrl.SetSelection(h24 % 12)

    def _getHourValue24(self, ctrl, ampm_ctrl, is24):
        idx = ctrl.GetSelection()
        if idx == wx.NOT_FOUND: idx = 0
        if is24: return idx
        val = idx
        if ampm_ctrl.GetSelection() == 1: val = (val % 12) + 12
        else: val = val % 12
        return val

    def onSchedFormatChanged(self, event):
        is24 = (self.schedFormatChoice.GetSelection() == 1)
        curr_start_h24 = self._getHourValue24(self.startHourChoice, self.startAmPm, not is24)
        curr_end_h24 = self._getHourValue24(self.endHourChoice, self.endAmPm, not is24)
        new_choices = HOURS_24 if is24 else HOURS_12
        self.startHourChoice.Clear()
        self.startHourChoice.AppendItems(new_choices)
        self.endHourChoice.Clear()
        self.endHourChoice.AppendItems(new_choices)
        self._setHourSelection(self.startHourChoice, curr_start_h24, is24)
        self._setHourSelection(self.endHourChoice, curr_end_h24, is24)
        if is24:
            self.startAmPm.Hide()
            self.endAmPm.Hide()
        else:
            self.startAmPm.SetSelection(0 if curr_start_h24 < 12 else 1)
            self.endAmPm.SetSelection(0 if curr_end_h24 < 12 else 1)
            self.startAmPm.Show()
            self.endAmPm.Show()
        self.Layout()

    def _buildAdvancedTab(self, cfg):
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        tRow = wx.BoxSizer(wx.HORIZONTAL)
        lblTH = wx.StaticText(panel, label="Timer Hours:")
        tRow.Add(lblTH, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.tabHSpin = wx.SpinCtrl(panel, min=0, max=23, initial=0, size=(65, -1))
        setupSpinCtrl(self.tabHSpin, "Timer Hours")
        tRow.Add(self.tabHSpin, 0, wx.RIGHT, 10)

        lblTM = wx.StaticText(panel, label="Timer Minutes:")
        tRow.Add(lblTM, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.tabMSpin = wx.SpinCtrl(panel, min=0, max=59, initial=5, size=(55, -1))
        setupSpinCtrl(self.tabMSpin, "Timer Minutes")
        tRow.Add(self.tabMSpin, 0, wx.RIGHT, 10)

        lblTS = wx.StaticText(panel, label="Timer Seconds:")
        tRow.Add(lblTS, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.tabSSpin = wx.SpinCtrl(panel, min=0, max=59, initial=0, size=(55, -1))
        setupSpinCtrl(self.tabSSpin, "Timer Seconds")
        tRow.Add(self.tabSSpin, 0, wx.RIGHT, 12)

        self.btnStartTimer = wx.Button(panel, label="&Start Timer (Alt+S)")
        self.btnStartTimer.Bind(wx.EVT_BUTTON, self.onStartTabTimer)
        self._bindEnterKey(self.btnStartTimer, self.onStartTabTimer)
        tRow.Add(self.btnStartTimer, 0, wx.RIGHT, 6)

        self.btnStopTimer = wx.Button(panel, label="Stop Timer / Focus (Alt+X)")
        self.btnStopTimer.Bind(wx.EVT_BUTTON, lambda e: stopAllActiveSessions())
        self._bindEnterKey(self.btnStopTimer, lambda e: stopAllActiveSessions())
        tRow.Add(self.btnStopTimer, 0)
        sizer.Add(tRow, flag=wx.ALL | wx.EXPAND, border=10)

        self.timerTickCheck = wx.CheckBox(panel, label="&Continuous ticking sound while countdown timer is running (uncheck for final 3 seconds only)")
        self.timerTickCheck.SetValue(cfg.get("timerContinuousTick", True))
        sizer.Add(self.timerTickCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        pGrid = wx.FlexGridSizer(2, 6, 8, 8)
        lblFH = wx.StaticText(panel, label="Focus Duration Hours:")
        pGrid.Add(lblFH, flag=wx.ALIGN_CENTER_VERTICAL)
        self.focusHSpin = wx.SpinCtrl(panel, min=0, max=999, initial=cfg.get("focusHours", 0), size=(65, -1))
        setupSpinCtrl(self.focusHSpin, "Focus Duration Hours")
        pGrid.Add(self.focusHSpin, 0)

        lblFM = wx.StaticText(panel, label="Focus Duration Minutes:")
        pGrid.Add(lblFM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.focusMSpin = wx.SpinCtrl(panel, min=0, max=59, initial=cfg.get("focusMinutes", 25), size=(55, -1))
        setupSpinCtrl(self.focusMSpin, "Focus Duration Minutes")
        pGrid.Add(self.focusMSpin, 0)

        lblFS = wx.StaticText(panel, label="Focus Duration Seconds:")
        pGrid.Add(lblFS, flag=wx.ALIGN_CENTER_VERTICAL)
        self.focusSSpin = wx.SpinCtrl(panel, min=0, max=59, initial=cfg.get("focusSeconds", 0), size=(55, -1))
        setupSpinCtrl(self.focusSSpin, "Focus Duration Seconds")
        pGrid.Add(self.focusSSpin, 0)

        lblBH = wx.StaticText(panel, label="Break Duration Hours:")
        pGrid.Add(lblBH, flag=wx.ALIGN_CENTER_VERTICAL)
        self.breakHSpin = wx.SpinCtrl(panel, min=0, max=999, initial=cfg.get("breakHours", 0), size=(65, -1))
        setupSpinCtrl(self.breakHSpin, "Break Duration Hours")
        pGrid.Add(self.breakHSpin, 0)

        lblBM = wx.StaticText(panel, label="Break Duration Minutes:")
        pGrid.Add(lblBM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.breakMSpin = wx.SpinCtrl(panel, min=0, max=59, initial=cfg.get("breakMinutes", 5), size=(55, -1))
        setupSpinCtrl(self.breakMSpin, "Break Duration Minutes")
        pGrid.Add(self.breakMSpin, 0)

        lblBS = wx.StaticText(panel, label="Break Duration Seconds:")
        pGrid.Add(lblBS, flag=wx.ALIGN_CENTER_VERTICAL)
        self.breakSSpin = wx.SpinCtrl(panel, min=0, max=59, initial=cfg.get("breakSeconds", 0), size=(55, -1))
        setupSpinCtrl(self.breakSSpin, "Break Duration Seconds")
        pGrid.Add(self.breakSSpin, 0)
        sizer.Add(pGrid, flag=wx.ALL, border=10)

        pBtnRow = wx.BoxSizer(wx.HORIZONTAL)
        self.btnStartFocus = wx.Button(panel, label="Start &Focus Session (Alt+F)")
        self.btnStartFocus.Bind(wx.EVT_BUTTON, self.onStartTabFocus)
        self._bindEnterKey(self.btnStartFocus, self.onStartTabFocus)
        pBtnRow.Add(self.btnStartFocus, 0, wx.RIGHT, 8)

        self.btnStopFocus = wx.Button(panel, label="Stop Focus / Timer (Alt+X)")
        self.btnStopFocus.Bind(wx.EVT_BUTTON, lambda e: stopAllActiveSessions())
        self._bindEnterKey(self.btnStopFocus, lambda e: stopAllActiveSessions())
        pBtnRow.Add(self.btnStopFocus, 0)
        sizer.Add(pBtnRow, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.healthCheck = wx.CheckBox(panel, label="&Include hourly posture and hydration health reminders")
        self.healthCheck.SetValue(cfg["healthReminders"])
        sizer.Add(self.healthCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.pulseCheck = wx.CheckBox(panel, label="&Enable ambient mechanical clock seconds tick pulse")
        self.pulseCheck.SetValue(cfg["clockPulseEnabled"])
        self.pulseCheck.Bind(wx.EVT_CHECKBOX, self.onPulseCheckToggled)
        sizer.Add(self.pulseCheck, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=10)

        pulseGrid = wx.BoxSizer(wx.HORIZONTAL)
        lblTick = wx.StaticText(panel, label="Clock Pulse Frequency:")
        pulseGrid.Add(lblTick, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        self.pulseChoice = wx.Choice(panel, choices=PULSE_LABELS)
        self.pulseChoice.SetName("Clock Pulse Frequency")
        try: pIdx = PULSE_INTERVALS.index(cfg["clockPulseIntervalSecs"])
        except ValueError: pIdx = 0
        self.pulseChoice.SetSelection(pIdx)
        pulseGrid.Add(self.pulseChoice, 1, flag=wx.EXPAND)
        sizer.Add(pulseGrid, flag=wx.ALL | wx.EXPAND, border=10)

        tickRow = wx.BoxSizer(wx.HORIZONTAL)
        lblTickSound = wx.StaticText(panel, label="Tick Sound:")
        tickRow.Add(lblTickSound, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        self.tickSoundChoice = wx.Choice(panel, choices=[name for _k, name, _f in TICK_SOUNDS])
        self.tickSoundChoice.SetName("Tick Sound")
        tickKeys = [k for k, _n, _f in TICK_SOUNDS]
        try: tIdx = tickKeys.index(cfg.get("tickSound", "standard"))
        except ValueError: tIdx = 0
        self.tickSoundChoice.SetSelection(tIdx)
        tickRow.Add(self.tickSoundChoice, 1, flag=wx.EXPAND)
        sizer.Add(tickRow, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=10)

        packRow = wx.BoxSizer(wx.HORIZONTAL)
        lblChime = wx.StaticText(panel, label="Chime Sound Theme:")
        packRow.Add(lblChime, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        self.packChoice = wx.Choice(panel, choices=[lbl for _, lbl, _ in SOUNDPACKS])
        self.packChoice.SetName("Chime Sound Theme")
        selIdx = 0
        for i, (k, _, _) in enumerate(SOUNDPACKS):
            if k == cfg.get("soundPack", "crystal"):
                selIdx = i
                break
        self.packChoice.SetSelection(selIdx)
        packRow.Add(self.packChoice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.btnTestChime = wx.Button(panel, label="&Play Selected Chime (Alt+P)")
        self.btnTestChime.Bind(wx.EVT_BUTTON, self.onTestCurrentChime)
        self._bindEnterKey(self.btnTestChime, self.onTestCurrentChime)
        packRow.Add(self.btnTestChime, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(packRow, flag=wx.ALL | wx.EXPAND, border=10)

        cSizer = wx.BoxSizer(wx.HORIZONTAL)
        lblCust = wx.StaticText(panel, label="Custom .wav Audio File:")
        cSizer.Add(lblCust, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        self.customPath = wx.TextCtrl(panel, value=cfg.get("customBellPath", ""))
        self.customPath.SetName("Custom .wav Audio File Path")
        self.btnBrowse = wx.Button(panel, label="&Browse Custom File... (Alt+B)")
        self.btnBrowse.Bind(wx.EVT_BUTTON, self.onBrowseWav)
        self._bindEnterKey(self.btnBrowse, self.onBrowseWav)

        self.btnReset = wx.Button(panel, label="&Remove / Reset")
        self.btnReset.Bind(wx.EVT_BUTTON, self.onResetWav)
        self._bindEnterKey(self.btnReset, self.onResetWav)

        cSizer.Add(self.customPath, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        cSizer.Add(self.btnBrowse, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        cSizer.Add(self.btnReset, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(cSizer, flag=wx.ALL | wx.EXPAND, border=10)

        self.lockedCheck = wx.CheckBox(panel, label="Announce and play sounds while &Windows is locked (off by default, so the lock screen stays quiet)")
        self.lockedCheck.SetValue(cfg["announceWhenLocked"])
        sizer.Add(self.lockedCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.invertSpinCheck = wx.CheckBox(panel, label="Re&verse arrow keys in all number boxes (Down arrow increases, Up arrow decreases)")
        self.invertSpinCheck.SetValue(cfg["invertSpinKeys"])
        sizer.Add(self.invertSpinCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        panel.SetSizer(sizer)
        self.notebook.AddPage(panel, "Advanced")

    def onStartTabTimer(self, event):
        tot = self.tabHSpin.GetValue() * 3600 + self.tabMSpin.GetValue() * 60 + self.tabSSpin.GetValue()
        if tot <= 0:
            ui.message("Please enter a valid time duration.")
            return
        startCountdown(tot)

    def onStartTabFocus(self, event):
        f_h = self.focusHSpin.GetValue()
        f_m = self.focusMSpin.GetValue()
        f_s = self.focusSSpin.GetValue()
        b_h = self.breakHSpin.GetValue()
        b_m = self.breakMSpin.GetValue()
        b_s = self.breakSSpin.GetValue()
        if (f_h * 3600 + f_m * 60 + f_s) <= 0:
            ui.message("Please enter a focus duration greater than zero.")
            return
        if (b_h * 3600 + b_m * 60 + b_s) <= 0:
            ui.message("Please enter a break duration greater than zero.")
            return
        startPomodoroWithCustom(f_h, f_m, f_s, b_h, b_m, b_s)

    def onTestCurrentChime(self, event):
        is_pulse_on = _cfg().get("clockPulseEnabled", False)
        is_timer_ticking = _countdownActive and _cfg().get("timerContinuousTick", True)
        
        if is_timer_ticking or is_pulse_on:
            ui.message("Active ambient clock or continuous timer is currently running. Please turn off the ambient clock or continuous timer to properly test the chime audio.")
        else:
            playActiveBell(self.getActiveDialogBellPath())
            ui.message("Playing selected chime preview.")

    def onBrowseWav(self, event):
        dlg = wx.FileDialog(self, message="Select Chime File", wildcard="Wave (*.wav)|*.wav", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.customPath.SetValue(path)
            playActiveBell(path)
        dlg.Destroy()

    def onResetWav(self, event):
        self.customPath.SetValue("")
        idx = self.packChoice.GetSelection()
        key, _, fname = SOUNDPACKS[idx]
        playActiveBell(os.path.join(SOUND_DIR, fname))
        ui.message("Custom chime removed. Restored earcon pack.")

    def onPulseCheckToggled(self, event):
        if self.pulseCheck.GetValue() and not _cfg()["clockPulseEnabled"] and _timerBlocksClockPulse():
            self.pulseCheck.SetValue(False)
            gui.messageBox(CLOCK_BLOCKED_MESSAGE, "Time and Focus Announcer", wx.OK | wx.ICON_WARNING, self)
            self.pulseCheck.SetFocus()
        event.Skip()

    def onOK(self, event):
        cfg = _cfg()
        cfg["intervalMinutes"] = INTERVAL_CHOICES[self.intervalChoice.GetSelection()]
        cfg["format24Hour"] = (self.formatChoice.GetSelection() == 1)
        cfg["enableGreetings"] = self.greetingsCheck.GetValue()
        cfg["includeDateInPeriodic"] = self.includeDateCheck.GetValue()
        cfg["includeBatteryStatus"] = self.includeBatteryCheck.GetValue()
        cfg["batteryOnManualPress"] = self.batteryManualCheck.GetValue()
        cfg["chimeOnlyMode"] = self.chimeOnlyCheck.GetValue()
        cfg["suppressOnFullscreen"] = self.fullscreenCheck.GetValue()
        cfg["scheduleEnabled"] = self.scheduleCheck.GetValue()
        is_sched_24 = (self.schedFormatChoice.GetSelection() == 1)
        cfg["scheduleFormat24Hour"] = is_sched_24
        cfg["startHour"] = self._getHourValue24(self.startHourChoice, self.startAmPm, is_sched_24)
        cfg["endHour"] = self._getHourValue24(self.endHourChoice, self.endAmPm, is_sched_24)
        s_m_idx = self.startMinuteChoice.GetSelection()
        e_m_idx = self.endMinuteChoice.GetSelection()
        cfg["startMinute"] = s_m_idx if s_m_idx != wx.NOT_FOUND else 0
        cfg["endMinute"] = e_m_idx if e_m_idx != wx.NOT_FOUND else 0
        cfg["focusHours"] = self.focusHSpin.GetValue()
        cfg["focusMinutes"] = self.focusMSpin.GetValue()
        cfg["focusSeconds"] = self.focusSSpin.GetValue()
        cfg["breakHours"] = self.breakHSpin.GetValue()
        cfg["breakMinutes"] = self.breakMSpin.GetValue()
        cfg["breakSeconds"] = self.breakSSpin.GetValue()
        cfg["timerContinuousTick"] = self.timerTickCheck.GetValue()
        cfg["soundPack"] = SOUNDPACKS[self.packChoice.GetSelection()][0]
        cfg["customBellPath"] = self.customPath.GetValue().strip()
        cfg["healthReminders"] = self.healthCheck.GetValue()
        wantPulse = self.pulseCheck.GetValue()
        if wantPulse and not cfg["clockPulseEnabled"] and _timerBlocksClockPulse():
            wantPulse = False  # a timer with continuous ticking is running
        cfg["clockPulseEnabled"] = wantPulse
        cfg["clockPulseIntervalSecs"] = PULSE_INTERVALS[self.pulseChoice.GetSelection()]
        cfg["tickSound"] = TICK_SOUNDS[self.tickSoundChoice.GetSelection()][0]
        cfg["invertSpinKeys"] = self.invertSpinCheck.GetValue()
        cfg["announceWhenLocked"] = self.lockedCheck.GetValue()
        syncClockPulse()
        SettingsDialog._instance = None
        self.Destroy()

    def onCancel(self, event):
        SettingsDialog._instance = None
        self.Destroy()

    def onClose(self, event):
        SettingsDialog._instance = None
        event.Skip()

def openSettingsDialog():
    if SettingsDialog._instance is not None:
        try:
            SettingsDialog._instance.Raise()
            SettingsDialog._instance.SetFocus()
            return
        except Exception:
            SettingsDialog._instance = None
    dlg = SettingsDialog(gui.mainFrame)
    SettingsDialog._instance = dlg
    dlg.Show()
    dlg.Raise()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "Time & Focus Announcer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lastAnnouncedKey = None
        self._timer = wx.Timer()
        self._timer.Bind(wx.EVT_TIMER, self._onTimerTick)
        self._timer.Start(20000)

        syncClockPulse()

        self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
        self.subMenu = wx.Menu()
        aItem = self.subMenu.Append(wx.ID_ANY, "&Announce time now\tNVDA+Shift+T")
        gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, lambda e: announceTime(), aItem)
        sItem = self.subMenu.Append(wx.ID_ANY, "&Settings...\tNVDA+Control+Shift+A")
        gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, lambda e: wx.CallAfter(openSettingsDialog), sItem)
        self.subMenuItem = self.toolsMenu.AppendSubMenu(self.subMenu, "Time & Focus &Announcer")

    def _onTimerTick(self, event):
        try:
            cfg = _cfg()
            interval = cfg["intervalMinutes"]
            if interval <= 0: return
            now = datetime.datetime.now()
            if now.minute % interval != 0 or now.second >= 20: return
            key = now.strftime("%Y%m%d%H%M")
            if key == self._lastAnnouncedKey: return
            self._lastAnnouncedKey = key
            if not isWithinSchedule(now): return
            if cfg["suppressOnFullscreen"] and isForegroundFullscreen(): return
            announceTime(is_periodic=True)
        except Exception:
            pass

    @script(description="Announce time (1x), seconds (2x), or day & date (3x)", gesture="kb:NVDA+shift+t")
    def script_announceTime(self, gesture):
        count = scriptHandler.getLastScriptRepeatCount()
        if count == 0: announceTime()
        elif count == 1: announcePrecisionSeconds()
        else: announceDate()

    @script(description="Precision countdown timer (setup or status)", gesture="kb:NVDA+control+shift+t")
    def script_countdown(self, gesture):
        count = scriptHandler.getLastScriptRepeatCount()
        if count > 0 and _countdownActive:
            stopCountdown()
            return
        if _countdownActive:
            m, s = divmod(_timerRemainingSecs, 60)
            h, m = divmod(m, 60)
            h_str = f"{h} hours " if h > 0 else ""
            ui.message(f"Timer active: {h_str}{m} minutes and {s} seconds remaining. Press twice quickly to cancel.")
        else:
            wx.CallAfter(openCountdownDialog)

    @script(description="Toggle Pomodoro focus session", gesture="kb:NVDA+control+shift+p")
    def script_pomodoro(self, gesture):
        togglePomodoro()

    @script(description="Report NVDA session runtime and duration", gesture="kb:NVDA+control+shift+u")
    def script_uptime(self, gesture):
        ui.message(getUptimeReport())

    @script(description="Toggle all automated announcements mute", gesture="kb:NVDA+control+shift+m")
    def script_muteToggle(self, gesture):
        cfg = _cfg()
        cfg["muteAnnouncements"] = not cfg["muteAnnouncements"]
        st = "Muted" if cfg["muteAnnouncements"] else "Unmuted"
        ui.message(f"Periodic announcements {st}")

    @script(description="Toggle ambient mechanical clock pulse rhythm", gesture="kb:NVDA+control+shift+k")
    def script_clockPulseToggle(self, gesture):
        cfg = _cfg()
        if not cfg["clockPulseEnabled"] and _timerBlocksClockPulse():
            ui.message(CLOCK_BLOCKED_MESSAGE)
            return
        cfg["clockPulseEnabled"] = not cfg["clockPulseEnabled"]
        syncClockPulse()
        st = "enabled" if cfg["clockPulseEnabled"] else "disabled"
        ui.message(f"Ambient clock pulse {st}")

    @script(description="Switch between the standard tick and the loud tick", gesture="kb:NVDA+control+shift+j")
    def script_cycleTickSound(self, gesture):
        cfg = _cfg()
        keys = [k for k, _n, _f in TICK_SOUNDS]
        cur = cfg.get("tickSound", "standard")
        idx = (keys.index(cur) + 1) % len(keys) if cur in keys else 0
        cfg["tickSound"] = keys[idx]
        ui.message(f"Tick sound: {TICK_SOUNDS[idx][1]}")
        playTick()

    @script(description="Quick-cycle audio earcon soundpacks", gesture="kb:NVDA+control+shift+b")
    def script_cycleEarcons(self, gesture):
        cfg = _cfg()
        cur = cfg.get("soundPack", "crystal")
        keys = [k for k, _, _ in SOUNDPACKS]
        idx = (keys.index(cur) + 1) % len(keys) if cur in keys else 0
        cfg["soundPack"] = keys[idx]
        cfg["customBellPath"] = ""
        
        is_pulse_on = cfg.get("clockPulseEnabled", False)
        is_timer_ticking = _countdownActive and cfg.get("timerContinuousTick", True)
        
        if is_timer_ticking or is_pulse_on:
            ui.message(f"Audio earcon switched to {SOUNDPACKS[idx][1]}. (Bell preview muted due to active timer or ambient clock).")
        else:
            playActiveBell()
            ui.message(f"Audio earcon switched to {SOUNDPACKS[idx][1]}")

    @script(description="Toggle health companion reminders", gesture="kb:NVDA+control+shift+h")
    def script_healthToggle(self, gesture):
        cfg = _cfg()
        cfg["healthReminders"] = not cfg["healthReminders"]
        st = "enabled" if cfg["healthReminders"] else "disabled"
        ui.message(f"Hourly health companion reminders {st}")

    @script(description="Open Time & Focus Announcer settings", gesture="kb:NVDA+control+shift+a")
    def script_openSettings(self, gesture):
        wx.CallAfter(openSettingsDialog)

    def terminate(self):
        try: self._timer.Stop()
        except Exception: pass
        try:
            if _clockPulseTimerObj:
                _clockPulseTimerObj.Stop()
        except Exception: pass
        try: self.toolsMenu.Remove(self.subMenuItem)
        except Exception: pass
