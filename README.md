# Time & Focus Announcer

An all-in-one accessible audio timepiece and productivity suite for [NVDA](https://www.nvaccess.org/).

- **Author:** Kailas Eknath Bhoye
- **Version:** 1.0
- **License:** MIT
- **Requires:** NVDA 2026.1 or later (last tested with NVDA 2026.2)

## Overview

Time & Focus Announcer brings together an accessible spoken clock, a precision countdown timer, a full Pomodoro focus engine, and a library of premium audio earcons, all designed from the ground up for NVDA users. Every setting is reachable with a clear, direct accessible label, and every feature works the same way whether you are checking the time, running a focus session, or staying on top of your posture and hydration through the day.

## Features

- **Spoken Clock:** Announces the time on demand, with seconds-level precision and the full date on repeated presses.
- **Precision Countdown Timer:** Set a timer in hours, minutes, and seconds. Supports durations of up to 24 hours (23:59:59).
- **Pomodoro Focus Engine:** A complete focus and break session cycle with configurable durations (up to 999 hours each for focus and break) and spoken transitions.
- **Ambient Clock Pulse:** An optional, unobtrusive tick, either continuous or at a 3-second interval, for a steady sense of time passing.
- **Scheduled Announcements:** Automatic periodic time announcements, limited to the hours you actually want them.
- **12 Premium Audio Earcons:** A curated set of chime soundpacks, cycled with a single shortcut.
- **Session & Uptime Tracking:** Reports both the current NVDA session runtime and overall Windows uptime.
- **Health Reminders:** Gentle, optional hourly nudges to stay hydrated and mind your posture.

## Installation

1. Go to the [Releases page](https://github.com/kailas2103/-time-and-focus-announcer/releases/latest) and download the file ending in `.nvda-addon`.
2. Open the downloaded file. NVDA will ask if you want to install it. Choose **Yes**.
3. Restart NVDA when it asks you to.

Alternatively, install it from inside NVDA:

1. Press `NVDA+N` to open the NVDA menu, then go to **Tools**, then **Add-on Store**.
2. Choose **Install from external source**.
3. Browse to the downloaded `.nvda-addon` file and open it.
4. Restart NVDA when it asks you to.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `NVDA+Shift+T` | Announce the current time. Press twice quickly for exact seconds, three times for the full date. |
| `NVDA+Control+Shift+T` | Set up a precision countdown timer, or check the time remaining on an active one. |
| `NVDA+Control+Shift+P` | Start or stop a Pomodoro focus session. |
| `NVDA+Control+Shift+U` | Report the current NVDA session runtime and Windows uptime. |
| `NVDA+Control+Shift+M` | Mute or unmute automated periodic announcements. |
| `NVDA+Control+Shift+K` | Turn the ambient mechanical clock pulse on or off. |
| `NVDA+Control+Shift+B` | Quick-cycle through the available audio earcon soundpacks. |
| `NVDA+Control+Shift+H` | Turn hourly health companion reminders on or off. |
| `NVDA+Control+Shift+A` | Open the Time & Focus Announcer settings dialog. |

## Settings

The settings dialog (`NVDA+Control+Shift+A`) is organised into three tabs: **General**, **Schedule**, and **Advanced**. Each tab is preceded by a clear description of what that section controls, so every option is easy to find and understand with a screen reader.

## Feedback and Issues

Found a bug or have an idea? Please open an [issue](https://github.com/kailas2103/-time-and-focus-announcer/issues) on this repository.

## License

Released under the MIT License. See [LICENSE.txt](LICENSE.txt) for the full text.
