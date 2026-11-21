# Time & Focus Announcer

An all-in-one accessible audio timepiece and productivity suite for [NVDA](https://www.nvaccess.org/).

- **Author:** Kailas Eknath Bhoye
- **Version:** 1.1
- **License:** MIT
- **Requires:** NVDA 2026.1 or later (last tested with NVDA 2026.3.1)

## Overview

Time & Focus Announcer brings together an accessible spoken clock, a precision countdown timer, a full Pomodoro focus engine, and a library of premium audio earcons, all designed from the ground up for NVDA users. Every setting is reachable with a clear, direct accessible label, and every feature works the same way whether you are checking the time, running a focus session, or staying on top of your posture and hydration through the day.

## Features

- **Spoken Clock:** Announces the time on demand, with seconds-level precision and the full date on repeated presses.
- **Precision Countdown Timer:** Set a timer in hours, minutes, and seconds. Supports durations of up to 24 hours (23:59:59).
- **Pomodoro Focus Engine:** A complete focus and break session cycle with configurable durations in hours, minutes and seconds (up to 999 hours each for focus and break) and spoken transitions.
- **Ambient Clock Pulse:** An optional, unobtrusive tick for a steady sense of time passing. Choose how often it ticks: every 1 second (continuous), every 3 seconds, every 5 seconds, every 10 seconds, or every 60 seconds (a minute pulse). Two tick sounds are available, a standard tick and a louder tick, and a shortcut switches between them.
- **Scheduled Announcements:** Automatic periodic time announcements, limited to the hours you actually want them.
- **12 Premium Audio Earcons:** A curated set of chime soundpacks, cycled with a single shortcut.
- **Session & Uptime Tracking:** Reports both the current NVDA session runtime and overall Windows uptime.
- **Health Reminders:** Gentle, optional hourly nudges to stay hydrated and mind your posture.

## Installation

1. Download the add-on file from the Blind Help Project download page: https://blindhelp.net/software/Time-Focus-Announcer
2. Open the downloaded file. NVDA will ask if you want to install it. Choose **Yes**.
3. Restart NVDA when it asks you to.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `NVDA+Shift+T` | Announce the current time. Press twice quickly for exact seconds, three times for the full date. |
| `NVDA+Control+Shift+T` | Set up a precision countdown timer, or check the time remaining on an active one. |
| `NVDA+Control+Shift+P` | Start or stop a Pomodoro focus session. |
| `NVDA+Control+Shift+U` | Report the current NVDA session runtime and Windows uptime. |
| `NVDA+Control+Shift+M` | Mute or unmute automated periodic announcements. |
| `NVDA+Control+Shift+K` | Turn the ambient mechanical clock pulse on or off. |
| `NVDA+Control+Shift+J` | Switch between the standard tick and the loud tick. |
| `NVDA+Control+Shift+B` | Quick-cycle through the available audio earcon soundpacks. |
| `NVDA+Control+Shift+H` | Turn hourly health companion reminders on or off. |
| `NVDA+Control+Shift+A` | Open the Time & Focus Announcer settings dialog. |

## Settings

The settings dialog (`NVDA+Control+Shift+A`) is organised into three tabs: **General**, **Schedule**, and **Advanced**. Each tab is preceded by a clear description of what that section controls, so every option is easy to find and understand with a screen reader.

## What's New in Version 1.1

- **Quiet bell during ambient clock or timer:** when the ambient clock pulse or a continuously ticking countdown timer is running, periodic announcements no longer play the bell chime. The time is still spoken. This now matches how the manual time shortcut already behaved.
- **Quiet Pomodoro alerts with the ambient clock:** while the ambient clock is on, Pomodoro focus and break alerts are spoken only, without the bell.
- **Seconds for Pomodoro focus and break:** the focus and break durations now have a seconds box next to hours and minutes. The minutes boxes can also be set to 0, so a duration such as 30 seconds is possible. If a focus or break duration is left at zero, the default of 25 minutes for focus and 5 minutes for break is used.
- **Silent on the Windows lock screen:** by default the add-on does not play sounds or announcements while Windows is locked. It checks Windows' own lock state, the lock screen picture and the sign-in screen in several ways, so it stays quiet on all of them, on laptops with the lid open and on desktop PCs, including PCs without a password. If you want them on the lock screen, tick the Announce and play sounds while Windows is locked checkbox in the Advanced tab.
- **Battery warnings only when it matters:** with the battery option ticked, periodic announcements now mention the battery only when it is critical (20 percent or lower and not charging). A normal battery state is no longer spoken during periodic announcements. A separate checkbox, Also announce the battery status when the time shortcut is pressed manually, adds the current battery status when you press the time shortcut yourself. It is off by default. In settings, the Test button speaks the battery state straight away, and says so on a computer without a battery.
- **New ambient clock frequency:** the ambient clock can now tick every 3 seconds, in addition to every 1, 5, 10 and 60 seconds.
- **Loud tick sound:** a new, louder tick sound is available for the ambient clock and the countdown timer. Choose it with the Tick Sound list in the Advanced tab, or switch between the standard tick and the loud tick at any time with a new shortcut.
- **Number box arrow keys:** number boxes use the standard arrow keys by default (Up increases, Down decreases). In the Advanced tab, the Reverse arrow keys in all number boxes checkbox switches this around, so Down increases and Up decreases. It applies to every number box in the add-on.
- **Documentation fix:** the countdown timer supports up to 24 hours (23:59:59). Pomodoro focus and break durations support up to 999 hours each.

## License

Released under the MIT License. See [LICENSE.txt](LICENSE.txt) for the full text.
