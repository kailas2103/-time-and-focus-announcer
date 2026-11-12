# Time & Focus Announcer for NVDA (v1.0 Clean Open Source)
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

PULSE_INTERVALS = [1, 5, 10, 60]
PULSE_LABELS = ["Every 1 second (Continuous clock)", "Every 5 seconds", "Every 10 seconds", "Every 60 seconds (Minute pulse)"]

CONFIG_SECTION = "timeAndFocusAnnouncer"
config.conf.spec[CONFIG_SECTION] = {
    "intervalMinutes": "integer(default=0)",
    "format24Hour": "boolean(default=false)",
    "enableGreetings": "boolean(default=true)",
    "includeDateInPeriodic": "boolean(default=false)",
    "includeBatteryStatus": "boolean(default=false)",
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
    "focusMinutes": "integer(default=25,min=1,max=59)",
    "breakHours": "integer(default=0,min=0,max=999)",
    "breakMinutes": "integer(default=5,min=1,max=59)",
    "muteAnnouncements": "boolean(default=false)",
    "healthReminders": "boolean(default=true)",
    "healthReminderType": "integer(default=0)",
    "clockPulseEnabled": "boolean(default=false)",
    "clockPulseIntervalSecs": "integer(default=1)",
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

def playActiveBell(override_path=None):
    path = override_path or getResolvedBellPath()
    try:
        if os.path.exists(path):
            nvwave.playWaveFile(path, asynchronous=True)
    except Exception:
        pass

def playTick():
    try:
        if os.path.exists(TICK_PATH):
            nvwave.playWaveFile(TICK_PATH, asynchronous=True)
    except Exception:
        pass

def syncClockPulse():
    global _clockPulseTimerObj
    if not _clockPulseTimerObj:
        _clockPulseTimerObj = wx.Timer()
        _clockPulseTimerObj.Bind(wx.EVT_TIMER, _onClockPulseTick)

    if _cfg()["clockPulseEnabled"]:
        ms = max(1000, _cfg().get("clockPulseIntervalSecs", 1) * 1000)
        _clockPulseTimerObj.Start(ms)
    else:
        _clockPulseTimerObj.Stop()

def _onClockPulseTick(event):
    if not _cfg()["clockPulseEnabled"]:
        return
    if _cfg()["suppressOnFullscreen"] and isForegroundFullscreen():
        return
    playTick()

def getBatterySummary():
    try:
        sps = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
            percent = int(sps.BatteryLifePercent)
            if percent <= 100:
                is_plugged = (sps.ACLineStatus == 1)
                state = "plugged in" if is_plugged else "on battery"
                warning = ", battery critical warning" if (percent <= 20 and not is_plugged) else ""
                return f", Battery at {percent}% {state}{warning}"
    except Exception:
        pass
    return ""

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

def buildTimeSentence(now=None, override_24=None, override_greetings=None, override_inc_date=None, override_battery=None):
    now = now or datetime.datetime.now()
    cfg = _cfg()
    is24 = override_24 if override_24 is not None else cfg["format24Hour"]
    use_greetings = override_greetings if override_greetings is not None else cfg["enableGreetings"]
    inc_date = override_inc_date if override_inc_date is not None else cfg["includeDateInPeriodic"]
    inc_battery = override_battery if override_battery is not None else cfg["includeBatteryStatus"]

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
    if inc_battery:
        out += getBatterySummary()
    return out

def isWithinSchedule(now=None):
    if not _cfg()["scheduleEnabled"]:
        return True
    now = now or datetime.datetime.now()
    start = _cfg()["startHour"] * 60 + _cfg()["startMinute"]
    end = _cfg()["endHour"] * 60 + _cfg()["endMinute"]
    cur = now.hour * 60 + now.minute
    return (start <= cur <= end) if (start <= end) else (cur >= start or cur <= end)

def announceTime(override_bell=None, override_24=None, override_greetings=None, override_inc_date=None, override_battery=None, override_chime_only=None, is_periodic=False):
    if is_periodic and _cfg()["muteAnnouncements"]:
        return

    is_chime_only = override_chime_only if override_chime_only is not None else _cfg().get("chimeOnlyMode", False)

    if is_periodic and is_chime_only:
        playActiveBell(override_bell)
        return

    is_clock_pulse_on = _cfg().get("clockPulseEnabled", False)
    is_timer_running = _countdownActive and _cfg().get("timerContinuousTick", True)

    should_play_bell = not is_periodic and not (is_clock_pulse_on or is_timer_running)
    if should_play_bell or is_periodic:
        playActiveBell(override_bell)
    else:
        playTick()

    delay = BELL_DELAY_MS if (should_play_bell or is_periodic) else 0

    def doSpeech():
        text = buildTimeSentence(
            override_24=override_24,
            override_greetings=override_greetings,
            override_inc_date=override_inc_date,
            override_battery=override_battery
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
        _countdownTimerObj.Stop()
        playActiveBell(DEFAULT_BELL)
        wx.CallLater(600, lambda: ui.message("Time is up! Your countdown timer has finished."))

def stopCountdown():
    global _countdownActive, _countdownTimerObj, _timerRemainingSecs
    if _countdownActive:
        _countdownActive = False
        if _countdownTimerObj:
            _countdownTimerObj.Stop()
        _timerRemainingSecs = 0
        ui.message("Countdown timer cancelled.")
    else:
        ui.message("No active timer running.")

def startPomodoroWithCustom(f_h, f_m, b_h, b_m):
    global _pomodoroActive, _pomodoroIsBreak, _pomodoroRemainingSecs, _pomodoroTimerObj, _countdownActive
    if _countdownActive:
        ui.message("Countdown timer is currently active. Please stop the timer before starting focus.")
        return
    cfg = _cfg()
    cfg["focusHours"] = f_h
    cfg["focusMinutes"] = f_m
    cfg["breakHours"] = b_h
    cfg["breakMinutes"] = b_m

    tot_focus_sec = (f_h * 3600) + (f_m * 60)
    if tot_focus_sec <= 0:
        tot_focus_sec = 25 * 60

    _pomodoroActive = True
    _pomodoroIsBreak = False
    _pomodoroRemainingSecs = tot_focus_sec

    if not _pomodoroTimerObj:
        _pomodoroTimerObj = wx.Timer()
        _pomodoroTimerObj.Bind(wx.EVT_TIMER, _onPomodoroTick)
    _pomodoroTimerObj.Start(1000)
    playActiveBell()

    f_parts = []
    if f_h: f_parts.append(f"{f_h} hours")
    if f_m: f_parts.append(f"{f_m} minutes")
    f_text = " ".join(f_parts) if f_parts else "25 minutes"
    wx.CallLater(350, lambda: ui.message(f"Pomodoro focus session started for {f_text}."))

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
            cfg.get("breakHours", 0),
            cfg.get("breakMinutes", 5)
        )

def _onPomodoroTick(event):
    global _pomodoroActive, _pomodoroIsBreak, _pomodoroRemainingSecs
    if not _pomodoroActive:
        return
    _pomodoroRemainingSecs -= 1
    if _pomodoroRemainingSecs <= 0:
        playActiveBell()
        cfg = _cfg()
        if not _pomodoroIsBreak:
            _pomodoroIsBreak = True
            tot_break_sec = (cfg.get("breakHours", 0) * 3600) + (cfg.get("breakMinutes", 5) * 60)
            _pomodoroRemainingSecs = tot_break_sec if tot_break_sec > 0 else 300
            b_parts = []
            if cfg.get("breakHours", 0): b_parts.append(f"{cfg['breakHours']} hours")
            if cfg.get("breakMinutes", 5): b_parts.append(f"{cfg['breakMinutes']} minutes")
            b_text = " ".join(b_parts) if b_parts else "5 minutes"
            wx.CallLater(600, lambda: ui.message(f"Focus complete! Take a {b_text} break."))
        else:
            _pomodoroIsBreak = False
            tot_focus_sec = (cfg.get("focusHours", 0) * 3600) + (cfg.get("focusMinutes", 25) * 60)
            _pomodoroRemainingSecs = tot_focus_sec if tot_focus_sec > 0 else 1500
            wx.CallLater(600, lambda: ui.message("Break finished! Ready for next focus session."))

def setupInvertedSpinCtrl(spin_ctrl, label_name):
    spin_ctrl.SetName(label_name)
    def onSpinKey(event):
        key = event.GetKeyCode()
        val = spin_ctrl.GetValue()
        s_min = spin_ctrl.GetMin()
        s_max = spin_ctrl.GetMax()

        if key == wx.WXK_DOWN:
            if val < s_max:
                spin_ctrl.SetValue(val + 1)
            ui.message(str(spin_ctrl.GetValue()))
            return
        elif key == wx.WXK_UP:
            if val > s_min:
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
        setupInvertedSpinCtrl(self.hSpin, "Timer Hours")
        grid.Add(self.hSpin, 0)

        lblM = wx.StaticText(self, label="Timer Minutes:")
        grid.Add(lblM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.mSpin = wx.SpinCtrl(self, min=0, max=59, initial=5)
        setupInvertedSpinCtrl(self.mSpin, "Timer Minutes")
        grid.Add(self.mSpin, 0)

        lblS = wx.StaticText(self, label="Timer Seconds:")
        grid.Add(lblS, flag=wx.ALIGN_CENTER_VERTICAL)
        self.sSpin = wx.SpinCtrl(self, min=0, max=59, initial=0)
        setupInvertedSpinCtrl(self.sSpin, "Timer Seconds")
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

        self.includeBatteryCheck = wx.CheckBox(panel, label="&Append laptop battery status and critical warning")
        self.includeBatteryCheck.SetValue(cfg["includeBatteryStatus"])
        sizer.Add(self.includeBatteryCheck, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

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
                override_chime_only=False,
                is_periodic=False
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
        setupInvertedSpinCtrl(self.tabHSpin, "Timer Hours")
        tRow.Add(self.tabHSpin, 0, wx.RIGHT, 10)

        lblTM = wx.StaticText(panel, label="Timer Minutes:")
        tRow.Add(lblTM, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.tabMSpin = wx.SpinCtrl(panel, min=0, max=59, initial=5, size=(55, -1))
        setupInvertedSpinCtrl(self.tabMSpin, "Timer Minutes")
        tRow.Add(self.tabMSpin, 0, wx.RIGHT, 10)

        lblTS = wx.StaticText(panel, label="Timer Seconds:")
        tRow.Add(lblTS, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        self.tabSSpin = wx.SpinCtrl(panel, min=0, max=59, initial=0, size=(55, -1))
        setupInvertedSpinCtrl(self.tabSSpin, "Timer Seconds")
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

        pGrid = wx.FlexGridSizer(2, 4, 8, 8)
        lblFH = wx.StaticText(panel, label="Focus Duration Hours:")
        pGrid.Add(lblFH, flag=wx.ALIGN_CENTER_VERTICAL)
        self.focusHSpin = wx.SpinCtrl(panel, min=0, max=999, initial=cfg.get("focusHours", 0), size=(65, -1))
        setupInvertedSpinCtrl(self.focusHSpin, "Focus Duration Hours")
        pGrid.Add(self.focusHSpin, 0)

        lblFM = wx.StaticText(panel, label="Focus Duration Minutes:")
        pGrid.Add(lblFM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.focusMSpin = wx.SpinCtrl(panel, min=1, max=59, initial=cfg.get("focusMinutes", 25), size=(55, -1))
        setupInvertedSpinCtrl(self.focusMSpin, "Focus Duration Minutes")
        pGrid.Add(self.focusMSpin, 0)

        lblBH = wx.StaticText(panel, label="Break Duration Hours:")
        pGrid.Add(lblBH, flag=wx.ALIGN_CENTER_VERTICAL)
        self.breakHSpin = wx.SpinCtrl(panel, min=0, max=999, initial=cfg.get("breakHours", 0), size=(65, -1))
        setupInvertedSpinCtrl(self.breakHSpin, "Break Duration Hours")
        pGrid.Add(self.breakHSpin, 0)

        lblBM = wx.StaticText(panel, label="Break Duration Minutes:")
        pGrid.Add(lblBM, flag=wx.ALIGN_CENTER_VERTICAL)
        self.breakMSpin = wx.SpinCtrl(panel, min=1, max=59, initial=cfg.get("breakMinutes", 5), size=(55, -1))
        setupInvertedSpinCtrl(self.breakMSpin, "Break Duration Minutes")
        pGrid.Add(self.breakMSpin, 0)
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
        b_h = self.breakHSpin.GetValue()
        b_m = self.breakMSpin.GetValue()
        startPomodoroWithCustom(f_h, f_m, b_h, b_m)

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

    def onOK(self, event):
        cfg = _cfg()
        cfg["intervalMinutes"] = INTERVAL_CHOICES[self.intervalChoice.GetSelection()]
        cfg["format24Hour"] = (self.formatChoice.GetSelection() == 1)
        cfg["enableGreetings"] = self.greetingsCheck.GetValue()
        cfg["includeDateInPeriodic"] = self.includeDateCheck.GetValue()
        cfg["includeBatteryStatus"] = self.includeBatteryCheck.GetValue()
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
        cfg["breakHours"] = self.breakHSpin.GetValue()
        cfg["breakMinutes"] = self.breakMSpin.GetValue()
        cfg["timerContinuousTick"] = self.timerTickCheck.GetValue()
        cfg["soundPack"] = SOUNDPACKS[self.packChoice.GetSelection()][0]
        cfg["customBellPath"] = self.customPath.GetValue().strip()
        cfg["healthReminders"] = self.healthCheck.GetValue()
        cfg["clockPulseEnabled"] = self.pulseCheck.GetValue()
        cfg["clockPulseIntervalSecs"] = PULSE_INTERVALS[self.pulseChoice.GetSelection()]
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
            interval = _cfg()["intervalMinutes"]
            if interval <= 0: return
            now = datetime.datetime.now()
            if now.minute % interval != 0 or now.second >= 20: return
            if not isWithinSchedule(now): return
            if _cfg()["suppressOnFullscreen"] and isForegroundFullscreen(): return
            key = now.strftime("%Y%m%d%H%M")
            if key == self._lastAnnouncedKey: return
            self._lastAnnouncedKey = key
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
        cfg["clockPulseEnabled"] = not cfg["clockPulseEnabled"]
        syncClockPulse()
        st = "enabled" if cfg["clockPulseEnabled"] else "disabled"
        ui.message(f"Ambient clock pulse {st}")

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
