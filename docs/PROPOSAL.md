# Scanner portal

A proposal for a scanner portal in xdg-desktop-portal, so that sandboxed applications can
scan without bundling drivers or holding `--device=all`.

Status: draft for review. The interfaces below are implemented in C for xdg-desktop-portal (as
patches for 1.22.1 and for main, with a helper process that holds libsane, and dialogs for
xdg-desktop-portal-gnome and -gtk), and by a prototype service in Rust. Two applications, Simple
Scan and Negative Vibes, use them on real hardware and from inside a Flatpak sandbox. Nothing is
final; the open questions in the last section are the parts that most need a decision from
upstream.

Scope of v1: scanners driven by SANE. eSCL and IPP-Scan providers are not part of v1, but
the option model is deliberately abstract enough to be fed by one later.

Interface definitions in this directory:

- `org.freedesktop.portal.Scanner.xml` — frontend interface, what applications call
- `org.freedesktop.impl.portal.Scanner.xml` — backend interface, UI only

## Problem

There is no portal for scanners. A Flatpak application that wants to scan has to bundle
sane-backends and hold `--device=all` for USB scanners and `--share=network` for network
ones. That has a cost on every side:

- **Security.** `--device=all` is access to all of `/dev`, and `--share=network` is the whole
  network, both granted permanently at install time for a device the user may use twice a year.
- **Drivers.** The bundled backends are the only ones the application can use. Host-installed
  drivers, out-of-tree drivers and proprietary vendor drivers are all invisible to it, even
  when the same scanner works fine outside the sandbox.
- **Configuration.** The host's SANE configuration — `dll.conf`, per-backend configuration,
  network scanner definitions — does not reach the sandbox, so a scanner the user already
  set up has to be set up again, if it can be at all.
- **Control.** The user cannot see which applications may scan and cannot revoke it. There is
  no prompt, no list, no entry in the permission store.
- **Duplication.** Every application ships and updates its own copy of sane-backends.

Printing has had a portal for years. Scanning, which is the same kind of device access with
the same kind of consent question, has none.

## Goals

- A sandboxed application can scan with no device, network or filesystem access.
- The user chooses which scanners an application may use, in a dialog. The choice lasts while
  the application runs. An application that keeps a scanner of its own, such as a profile, may ask
  for the choice to be remembered, and the user is asked in the dialog: it is then kept in the
  permission store for the scanners whose id stays the same, and revoked there (see the decisions
  table).
- libsane and its backends run on the host, so host and proprietary drivers work and the
  host's SANE configuration applies.
- The API is rich enough for demanding applications: multi-bit-depth, infrared, multi-pass,
  and backend-specific options all survive it.
- Simple applications stay simple: well-known option names mean a "resolution and mode" UI
  needs no special cases.
- One entry per physical scanner, with capabilities the portal sets. SANE reports a network
  printer once for each driver that finds it, and its device type differs between drivers, so
  the portal merges the duplicates, tries the drivers in order and says which scanners are for
  film, so that a film application and a document application are each offered theirs.

## Non-goals

- Scanner **discovery** by sandboxed applications. The portal searches and the dialog shows the
  user what it found, but the application is handed only the scanners the user chose, never a
  list of what is on the network.
- A **per-scan prompt**. The grant is the consent, and the dialog names the scanner. What an
  application can do with a grant is limited to what is on the glass or in the feeder, which is
  why one choice is proportionate; see the decisions table.
- **Scanner setup**: adding a network scanner, installing a driver or editing SANE's
  configuration. The portal uses what the host has already set up.
- **Sharing one scanner between applications at the same time.** The lock is exclusive; see
  the decisions table.
- **Image processing**: OCR, file formats, colour management, cropping. The portal returns
  frames as the scanner produced them and applications do the rest.
- **Scanners that SANE does not drive**, such as WIA. Provided by another provider later, if at
  all; the option model is abstract enough for one.
- **Fixing SANE's device metadata upstream.** The portal corrects what it needs in its own
  table instead, since a change to SANE's API would have to keep every existing application
  working.

## Hardware buttons

Some scanners have buttons, and an application can want to react to them: Negative Vibes scans
when the user presses QuickScan on the 8200i and previews on IntelliScan. SANE has no event for
them. A backend that has buttons exposes them as sensor options (the Plustek 8200i has
`intelliscan` and `scan`), which an application polls with `GetOptionValues` on an open
session. That works in v1, and is the fallback for a backend the portal does not know, but it
makes every application hold the scanner and the exclusive lock, poll over D-Bus several times a
second, and know each backend's quirks. The portal does the polling instead.

Network scanners are out of scope. eSCL has no push-scan event, `sane-airscan` exposes no buttons,
and HP's scan-to-computer uses vendor mechanisms that SANE does not see. This is for USB scanners
whose backend exposes sensors.

**The signal.** One signal carries a press, however the application receives it:

```
ButtonEvent(session_handle, scanner_id, button, details)
```

`button` is a name from a small vocabulary: `scan`, `copy`, `email`, `pdf`, `file`, `extra`.
`details` carries `option`, the backend's own option name (`intelliscan`), so that an
application can tell the two buttons of the 8200i apart. The scanner's info gains `buttons`, the
names it can report, so that an application shows "press Scan on the scanner" only when that
works.

**Detecting a press.** The helper polls the button options about four times a second while a
session is open and no frame is running, since many backends cannot read a sensor in the middle of
a scan: a press during a scan is lost. A press is a read of true after a read of false. That
handles backends that latch (reading clears the value) and backends that report a held button.
What the scanner had queued when the session opened is discarded, since a press from before is
not one the application is waiting for. Some backends need a nudge first: the Pixma backend wants
its `button-update` action pressed before `button-1` is valid, which the table can express and
which has not been tried on a Pixma. What is a button, what it is called in the vocabulary, the
option to press first and the interval are per backend, in `scanner-devices.json`, in a `buttons`
section. A backend that is not named there gets no `ButtonEvent`, and `buttons` is empty. Only the
`plustek8200i` entry has been checked on hardware; the `genesys` entry is taken from that
backend's documentation.

**An application that gets `ButtonEvent` must not read the sensor options too.** A reading clears
a latched press, the helper reads the same options for its events, and whoever reads second sees
nothing. Negative Vibes had both until it was changed to take presses from the events when the
portal reports them.

**Events in a scan session.** The helper polls between frames and the frontend emits
`ButtonEvent` on the session that has the scanner open. Nothing new for an application to call.
There is no way to watch the buttons without holding the scanner, and no launch of an
application on a press: both would need the portal to know an application across launches, which
it does not, unless the user let it remember the grant, which is not an application that is
running or one that has been told of a press.

**Who gets a press.** The session that has the scanner open, which is one at a time because the
lock is exclusive. A press goes only to an application that was granted the scanner; it tells it
nothing a scan would not.

**Rejected.** Leaving it to applications is the fallback above, not the design. Depending on
`scanbd` is not an option for a portal: it is not installed by default, it has its own
configuration, and it fights the portal over who opens the device.

**Open.** Whether the vocabulary is enough; `extra` and the raw option name cover the odd cases. Who keeps the per-backend table: it
is in the same file as the film scanners. A host tool that holds the device, such as `scanbd`,
will conflict with the portal, which the documentation should say.

## Architecture

The split follows the USB portal: the backend draws the dialog and nothing else, and the
frontend does the work.

```
  sandbox                     |  host
                              |
  application                 |  xdg-desktop-portal
    |                         |    org.freedesktop.portal.Scanner  (frontend)
    |  D-Bus calls -----------+---->  |
    |                         |       |-- grants, in memory, per application connection
    |  pixel data <-----------+-------|-- helper process per session -- libsane -- scanner
    |      (pipe fd)          |       |
                              |       '-- org.freedesktop.impl.portal.Scanner  (dialog)
                              |             in xdg-desktop-portal-gnome / -kde
```

Two properties of this layout matter:

**The frontend must not link libsane.** libsane is not thread-safe, it loads backend code
into the process, and that code can be proprietary and of unknown quality. Running it in
xdg-desktop-portal itself would put it in a long-lived process that every portal shares. It
therefore belongs in a helper, one per open scanner, which also means a wedged backend
cannot take down other applications' scans. The frontend starts it for each session and
it ends with the session; see the decisions table.

**Pixel data does not travel over D-Bus.** A single 7200 dpi frame is hundreds of megabytes.
`StartFrame` returns the read end of a pipe, so the data path is a plain fd with kernel
backpressure, no temporary files and no message size limits — the same handover the USB
portal uses.

## The interface

Consent and enumeration:

| Member | Purpose |
|---|---|
| `SelectScanners(parent_window, options) → Request` | Shows the dialog and records the grant for the application's connection. Called on a user action, or when `ListScanners` comes back empty, which is the case on every start for a choice that was not remembered. `options` can ask for `multiple`, for `persist` (the user is asked to let the portal remember the choice, for the scanners whose `persistent` is true) and filter on `required_capabilities` (all of them) or `any_capabilities` (at least one of them), from `film`, `feeder`, `infrared`, `flatbed`, `color`. |
| `ListScanners(options) → a(sa{sv})` | The granted, currently available scanners. Each is an opaque id plus `name`, `vendor`, `model`, `backend`, `kind`, `type` (`scanner`, `film` or `other`), `capabilities`, `buttons`, `available`. |

Scanning, on a `Session` from `OpenScanner`:

| Member | Purpose |
|---|---|
| `OpenScanner(scanner_id, options) → Request` | Opens a granted scanner and takes the host's exclusive lock. It is a request, answered at once: opening can take tens of seconds, lamp warm-up and calibration, and on a network scanner 16 to 25 s in testing, at D-Bus's default 25 s call timeout. The `Response` carries `session_handle`, or, with response code 2, `error` (`busy` or `failed`) and `message`. Closing the request gives up, and no `Response` follows. Closing the session, or leaving the bus, cancels any scan and releases the scanner. An application that leaves the bus while the scanner is still opening does not keep it locked: the portal checks that the caller is still there once the helper is up, and if not closes the session and gives up. |
| `GetOptions(session, options) → aa{sv}` | SANE-shaped option descriptors in backend order: `name`, `title`, `description`, `type`, `unit`, `size`, `constraint`, `capabilities`. |
| `GetOptionValues(session, options) → a{sv}` | The current value of every readable, active option. |
| `SetOptions(session, a(sv), options) → applied, flags` | Sets options **in array order**. Returns what each option ended up with, and flags `inexact`, `reload-options`, `reload-params`. |
| `GetFrameParameters(session, options) → a{sv}` | The layout the next frame would have, as an estimate, for sizing buffers and previews. |
| `StartFrame(session, options) → (fd, frame)` | Starts one frame and returns at once with the read end of a pipe and the number of the frame. |
| `Cancel(session, frame)` | Cancels the frame with that number, which `StartFrame` returned. A frame that is over is not cancelled again, and a number never returned is an error. |
| `FrameEvent(session, state, details)` | `started`, `finished`, `cancelled`, `no-documents` or `error`. `started` carries `format`, `depth`, `pixels_per_line`, `bytes_per_line`, `lines` and `last_in_image`. Every event carries its frame number. |
| `ButtonEvent(session, scanner_id, button, details)` | A press of a button on the scanner, while no frame is running: `button` is `scan`, `copy`, `email`, `pdf`, `file` or `extra`, and `details` has the backend's option name. Only for a scanner whose info lists `buttons`. See Hardware buttons. |

A typical exchange:

```
SelectScanners()                     once, on a user action
ListScanners()                       → [(id, {name: "Plustek OpticFilm 8200i", …})]
OpenScanner(id)                      → request; Response gives the session
GetOptions(session)                  → descriptors
SetOptions(session, [("mode","Color"), ("resolution",3600)])
loop:
    StartFrame(session)              → fd
    FrameEvent started               → format, depth, bytes_per_line, lines, last_in_image
    read(fd) until EOF
    FrameEvent finished
    until last_in_image
Session.Close(session)
```

An application detects the portal by checking for the `version` property of
`org.freedesktop.portal.Scanner` on `org.freedesktop.portal.Desktop`, and falls back to
libsane when it is absent.

The backend interface has two methods. `SelectScanners` receives the scanner list the frontend
assembled and returns the ids the user picked. Searching can take seconds, since a network driver
waits on the network, so the frontend shows the dialog after at most 300 ms with what has been
found, sets `searching` in the options, and sends the rest with `UpdateScanners` as the drivers
answer; the last call says the search is over. Only scanners that were offered to the dialog can be
granted. The frontend keeps the grant in memory for as long as the application stays on the bus.
Only if the application asked with `persist` and the dialog says that the user agreed is a grant
for a scanner whose `persistent` is true also written to the permission store, which is what
`ListScanners` and `OpenScanner` look in on the next run.

## Decisions and why

| Decision | Reason |
|---|---|
| A SANE-shaped typed option model, not a reduced `resolution`/`mode`/`source` API | Film scanning needs infrared channels, 16-bit depth, multi-pass and backend-specific options; a reduced API loses them and the application has to go around the portal. Well-known option names keep the simple cases simple. |
| Typed D-Bus values, with constraints and units; names as strings | The print portal's all-string settings dictionary is the mistake not to repeat: it moves validation into every application. That is about values. The names of a frame's state, a capability, a button or a device type are strings, since they are read by people, are logged as they are, and can be added to without changing a signature. A client that gets one it does not know ignores it. |
| A pipe fd per frame, not a file or D-Bus bytes | Frames reach hundreds of megabytes. A pipe gives backpressure for free, needs no temporary file and no disk access in the sandbox. One frame per call mirrors `sane_start` and covers RGB plus infrared. |
| `StartFrame` returns immediately; state arrives in `FrameEvent` | `sane_start` can block for many seconds on warm-up or carriage movement, which no application should hold a D-Bus call open for. End of data on a pipe also cannot distinguish success from failure, so `finished` has to be explicit. |
| Ordered `a(sv)` for `SetOptions`, not `a{sv}` | D-Bus dictionaries do not preserve order and SANE option setting is order-dependent: `mode` must be set before options that are inactive in the wrong mode, such as `three-pass` in grayscale. A dictionary cannot express that at all. |
| A frame number on every `FrameEvent`, returned by `StartFrame` and named by `Cancel` | A client that cancels a frame and immediately starts another must be able to tell the old frame's trailing events from the new frame's. A per-session counter, and the rule that a frame ends with exactly one non-`started` event, let it discard anything not newer than the last frame it saw end. Without it every client reimplements a drain-and-wait by hand. `Cancel` names the frame for the same reason: one that arrives late would otherwise stop the frame started after the one it was meant for. Only the last frame started can be cancelled, an older one is over and is left alone, and a number never returned is an invalid argument. |
| Automatic values as the vardict `{'auto': <true>}` | SANE has `SANE_ACTION_SET_AUTO` and real applications use it, for example to let the scanner pick the source. D-Bus has no empty structure, so a vardict stands in for the "no value" marker, and leaves room for further per-option modifiers. |
| `backend` in the scanner info | The scanner id is opaque, so applications cannot match device quirks on it — and device quirks are unavoidable in practice. The driver name has to be exposed on purpose. |
| `type` in the scanner info, alongside `kind`, in the portal's own words | Applications hide devices that are not scanners (webcams through `v4l`, SANE's `test` backend). `kind`, the connection, cannot express that. SANE's own type string can, but it differs between drivers, is free text and can hold an address (`ip=192.0.2.10` for `airscan`), so the portal says `scanner`, `film` (a scanner only for film) or `other` (not a scanner: a camera, SANE's `test` device), worked out from the driver's string and the capabilities, and keeps the raw string out. An application only needs to hide `other`, which Simple Scan and Negative Vibes do, so there is one word for it. New values may be added. |
| `GetFrameParameters` as an estimate | SANE allows `sane_get_parameters` before `sane_start` and applications use it to size buffers and previews. Without it a client cannot know the frame size until data is already flowing. |
| `org.freedesktop.DBus.Error.AccessDenied` for a session that is not the caller's, closed or unknown | The other portals that have sessions answer this way, and it does not tell an application whether the session exists for someone else. `NotAllowed` stays for a scanner that was not granted, which is a decision of the user's. |
| One helper process per open scanner, started by the frontend | libsane keeps global state, some backends leak or install signal handlers, and `sane_exit` plus `sane_init` is the only reliable reset, so a process that ends with the session is the reset. A crash costs one session. A systemd user service that owns libsane would keep that state for as long as it runs; it could come with a provider other than SANE, and nothing here needs one. |
| `ListScanners` is a snapshot, and v1 has no event for a scanner that comes or goes | Polling the drivers is not the way: `sane_get_devices` on a network takes seconds and stalls the other backends. The sources that know are udev for USB and Avahi for network scanners. An earlier draft had `CreateSession` and `ScannerEvents` for it. Nothing emitted the event, and a scanner has to be there to be granted, so it could only report a granted scanner that came back, which `ListScanners` answers. If events are added, it is one event per signal. |
| Options are scalar in v1; array-valued ones are hidden | Gamma tables and calibration data are arrays. The descriptor has `size` for them, and an array form of the value could be added without changing what exists. |
| An exclusive lock on the scanner | SANE backends are single-open and most scanners do one scan at a time, so `Busy` is the honest answer. Sharing would mean queueing, which has no good default. |
| Applications need no permission beyond `--talk-name=org.freedesktop.portal.Desktop` | They already have it. Both Simple Scan and Negative Vibes run from Flatpaks without `--device=all` or `--share=network`, against the frontend in C, and scan on the 8200i. |
| The dialog only chooses devices, with no scan settings | Print's dialog also collects settings, but print settings are uniform and scanner settings are not: resolution, mode, source and bit depth differ between backends, and film has none of the document ones. Settings in the dialog would be a second option model. |
| Capabilities come from a table in the portal, not from SANE | SANE's device type says little and differs between drivers: one calls a Plustek OpticFilm a film scanner and another a flatbed, and `airscan` gives its address. The portal keeps a list of the scanners that are for film, by USB id or product line, in `scanner-devices.json`, read at run time so that a distribution or an administrator can ship a newer one, and it assumes that a scanner not known to be only for film is for documents, so it has `flatbed` unless its driver says it is a sheet feeder. Film scanners are few and a film application is the one that needs them found, so a list is feasible where a list of document scanners would not be. A flatbed with a transparency unit has both. If the SANE project takes a capability field in its description files, the table can move there. |
| One entry per physical scanner, and the drivers in a fixed order | A network printer is found by an eSCL driver and by the vendor's, and a USB scanner by more than one backend. The helper reports which physical scanner a device is (the USB bus address, or the host of a network scanner), and the frontend gives those one id, offers the dialog one entry and keeps the drivers in order: `airscan` and `escl` before the others, HPLIP's `hpaio` after them and SANE's `net` driver last. Scanners found only through `net` are not merged, since the host may serve several. |
| Ties between drivers go by the driver's name | The 8200i SE is found by both `genesys` and `plustek8200i`. They ranked the same, the order of the search decided, and `genesys` won. It does not report the scanner's buttons, and opening the scanner through it is the likely reason the buttons went silent until a power cycle (see `docs/HARDWARE-TEST.md`). |
| A table entry can name the driver that opens the scanner first | `"driver": "plustek8200i"` puts that driver ahead of every other that found the scanner, whatever the ranks, so a known problem scanner is fixed at its description and not in the global ranks. The scanner info's `backend` is that of the driver that will open it, also in the answer to `SelectScanners`. |
| A second driver is tried only when the first says it does not drive the scanner | That is SANE's `INVAL` or `UNSUPPORTED`, the way HPLIP answers for a printer that only speaks eSCL. Not after a busy scanner, which another driver would only meet too, and not after an I/O error: the driver may have talked to the device, and a second one on a device in an unknown state is how a scanner gets reset. |
| No `excluded_capabilities` option | A scanner not known to be for film is given `flatbed`, so a document application that asks for `any_capabilities` of `flatbed` and `adf` is already offered no film-only scanner, and still gets a flatbed with a transparency unit, which it should. An exclusion would only matter for an application that wants everything but one kind, and there is none yet. |
| `handheld` is a capability, not only a frame with `lines` = -1 | A handheld scanner differs from the others before it is opened: its height is unknown and a person moves it, so a document application would not want it in the dialog. The portal takes it from SANE's device type "handheld scanner" and does not give it `flatbed`, so `any_capabilities` of `flatbed` and `feeder` already leaves it out and an application written for one asks for `handheld`. |
| `last_in_image`, not `last_frame` | The flag is true on the last frame of the image the application combines (the blue pass of an RGB scan), not on the last frame of the scan: a feeder has more pages after it. The name says which. The end of the scan is a `no-documents` event, as before. |
| `OpenScanner` is a request, not a call that returns the session | Opening takes seconds on USB and on a network scanner through `airscan` took 16 and 25 s, at D-Bus's default call timeout of 25 s, so a client that kept the default could fail on a scanner that would have opened. ScreenCast and GlobalShortcuts create their sessions the same way, and an application can show progress while it waits. The portal, Simple Scan, Negative Vibes and the test double all use it, and the scenarios check that the call returns before the scanner is open and that closing the request gives no `Response` and lets the scanner go. |
| A dedicated `Busy` error | A locked scanner, a frame in progress and an option set during a frame are ordinary, expected conditions that an application must handle differently from a real failure. Folding them into `Failed` forces clients to guess from the message. |
| Opaque scanner ids, never raw SANE device names | Some backends interpret device names as file paths or network addresses. Handing an application control of that string lets it steer the host at arbitrary files and hosts. |
| The application sees only granted scanners | Enumerating the LAN's scanners is a fingerprinting and privacy problem, and not something an application needs before the user has chosen anything. |
| A `Session` for an open scanner | Lifecycle comes for free: the application exiting releases the hardware lock, and the portal can revoke access with `Session.Closed`. |
| No per-scan prompt once granted | An application with a grant can scan only what is on the glass or in the feeder, and the dialog names the scanner, so one choice per run of the application is proportionate. It is not true that a scan cannot happen unnoticed: a page left in the scanner can be read. The exposure is small, and a prompt for every scan would make the scanning applications unusable. Open to argument if reviewers disagree. |
| Grants last for the application's run, unless the application asks and the user agrees to have them remembered | The print portal asks every time and keeps nothing, and scanning is an occasional, deliberate act like printing, so a dialog at the start of a scanning session is the expected cost for most applications. An application with profiles tied to one scanner, as NAPS2 has, would ask at every launch, and cannot be built on that. So the application may pass `persist`, and the dialog, which is where the user is told, answers with `persist` if the user agreed, as a switch that is off to start with. The frontend keeps the choice only on that answer, so a dialog that knows nothing of it keeps nothing. What is kept is one entry of the permission store for each scanner, in the table `scanner`, under its id, and a "yes" for the application, as the USB portal does for devices; it is taken back with `flatpak permission-remove scanner ID APP` and by anything else that edits the store. Only a scanner whose `persistent` is true can be kept, since another has a new id the next time. A host application with no id gets nothing kept, and the dialog is not told it may be. `ListScanners` and `OpenScanner` read the table, `ListScanners` without a look at the hardware for an application that has nothing in it. The portal says nothing of an entry for a scanner that is not there: it is not listed, as the call has always said. |
| The backend does UI only | Same split as `org.freedesktop.impl.portal.Usb`, and it keeps libsane out of the desktop shell's process as well as out of the frontend's. |

## Scanner identity

Today an id is the first 16 hex characters of the SHA-256 of a string the helper calls
`physical`: `usb:<bus>:<devnum>` for USB, the host for a network scanner. That is stable for as
long as the helper runs and no longer. The bus and device number are assigned by the kernel when
the scanner is enumerated, so they change when it is replugged, moved to another port or the
machine restarts, and the host of a network scanner changes with DHCP. That is why v1 keeps ids
per run, and why a grant that outlives the run needs a different id. This section is the rules
for one. The USB rules are implemented in the patch series and tested with a stand-in helper; the
only real scanner they have been looked at on is the 8200i.

**What SANE offers.** Nothing that is stable across runs and drivers. The device name is a string
private to the driver:

| Bus | Example name | Stable? |
|---|---|---|
| USB | `plustek8200i:libusb:003:014` | No: bus and device number |
| eSCL | `airscan:e0:HP Color LaserJet MFP M283cdw (61F0E7)` | The `e0` is a discovery index and changes; the model with its suffix is steadier |
| HPLIP | `hpaio:/net/colorlaserjet_mfp_m282-m285?ip=192.168.68.91` | No: the address is in the name |
| SANE `net` | `net:<host>:<backend>:<device>` | As stable as the host name or address |
| Video | `v4l:/dev/video2` | No, and `type` is `other`, so it is not offered |

A USB serial number is not enough either. The 8200i reports `serial=1` in sysfs, and many scanners
report none or a placeholder.

**The rules.** Implemented for USB; the network rule is design only (see below).

1. **An id outlives the run only if the portal can name the device.** A scanner is `persistent`
   when it can, and `persistent` is in its info. Otherwise it is granted for the run only, as in
   v1, with an id made as before.
2. **USB.** The id comes from the USB id and the serial number when the scanner has one that tells
   it from every other USB device of that USB id on the machine, so that it survives a move to
   another port. A serial number that is empty, short (under four characters), one character
   repeated, a known placeholder ("0123456789", "none", …) or shared with another device of the
   kind is not used; the 8200i reports `serial=1`. Then the id comes from the USB id and the port
   path in sysfs (`3-4`, the hubs and ports from the root), which survives a replug into the same
   port and a restart but not a move to another port. Never from the bus and device number.
3. **Every driver gives the same id.** The helper reads sysfs for what the scanner is, not what
   its driver is, so the id is the same whichever driver finds it. This is a requirement and not
   a nicety: `SelectScanners` offers the dialog a scanner as soon as one driver finds it, and the
   id the user is granted has to be the one `ListScanners` gives afterwards, when the drivers have
   been merged. For the same reason the id is made for each scanner alone and not in a pass over
   the whole list.
4. **A wrong match is worse than a lost grant.** The USB id and model alone never make an id, so
   a grant for one scanner cannot apply to a second of the same model. Two identical scanners are
   told apart by their serial numbers, or by their ports, which sysfs gives one device each.
5. **The id stays opaque.** It is a hash of the pieces above with a version, so that the rules
   can change without the application seeing it, and it does not say which rule made it. The
   application learns only `persistent`.
6. **A network scanner is not persistent.** Only one driver, `airscan`, finds a name that stays
   the same (the service name without the discovery index); the others have an address, which
   does not. By rule 3 the id must be the same from each, so a network scanner cannot have one
   until the host can give every driver the same name, from mDNS: Avahi, which the helper does
   not use today. This is the open part.
7. **A grant that is kept names a scanner that may be missing.** It is not listed: `ListScanners`
   is the scanners that are granted and there, as it was, and the entry waits in the store for
   the scanner to come back. It is never matched to another scanner.
8. **Losing a grant is never an error.** If a port changes, the application gets an empty
   `ListScanners` and calls `SelectScanners` again.

**What was found by building it.**

- The helper does the checking, since it can see sysfs: whether a serial number is shared is
  asked of the whole machine and not of the scanners one driver found, so that every driver
  agrees. The frontend only turns what the helper says into an id.
- On the 8200i the serial number is rejected and the id comes from the port, `3-4`. The
  network printer on the same machine gets no stable id.
- It is tested with a stand-in helper (`tests/stable-ids.py`): an id with a serial number and
  with a port is the same after a replug (a new bus address), the id of a scanner found by two
  drivers is the same from both, two scanners of a kind get different ids, and one found by an
  address or without a port is not persistent. **Not tested:** a real replug of a scanner, a
  scanner with a real serial number, two real scanners of a kind, and a scanner behind a hub.

**What it costs.** Reading sysfs in the helper, which `usb_id_for_address` already does. A
network scanner needs a lookup of the mDNS name for each driver.

**What it does not do.** It does not make every scanner persistent: one without a serial number
loses its id when the cable moves, and a network scanner has none yet, and the application should
say so and not treat that as a fault. And an application that wants to know that the scanner it
saved is gone, and not only that it is not listed, has no call for it; it keeps its own name for
the scanner and compares.

## Security and privacy

- No `/dev`, no network and no filesystem access is needed by the application; the data path
  is a pipe the portal creates.
- Device ids are opaque and not constructible, so an application cannot name a device that was
  not granted, and cannot smuggle a path or host into a backend's device string.
- Option types that would make the host open a file or socket of the application's choosing —
  file name options above all — are not listed by `GetOptions` and cannot be set.
- Grants are kept in memory by the frontend, per application connection, and end when the
  application leaves the bus, which also closes its sessions. A restart of the frontend forgets
  them, and applications ask again, except for the ones the user let the portal remember, which are
  in the permission store, the same place and the same revocation as the USB portal's. They are
  asked for by the application and agreed to by the user in the dialog, and only for scanners whose
  id stays the same, and only for an application with an id. The portal can still end a session at any time with
  `Session.Closed`.
- The host's exclusive lock means one application at a time has the scanner, so one sandbox
  cannot read another's scan in progress.
- Backend code runs in a helper process, not in xdg-desktop-portal, so a backend that crashes
  or hangs affects one session.

## Notes for implementers

Two things are easy to get wrong and are worth stating in the interface documentation rather
than leaving to each implementation:

1. **Cancellation must not depend on the application reading.** If the application stops
   reading, the pipe fills at 64 KB and the writer blocks. An implementation that cancels
   from the same thread will then never see `Cancel()`, and the scan hangs until the
   application reads or exits. The writer has to be non-blocking and poll for cancellation.
   The rule for the API is: *a frame is cancelled by `Cancel()` or by the application closing
   the pipe, and neither may depend on the application reading the data.*
2. **Whether a new session inherits the last one's options depends on the implementation.**
   Some SANE backends keep option values on the device, so with libsane in one process a new
   session can inherit the previous one's settings, as the prototype's does. The frontend in C
   starts a helper per session, so every session starts from the backend's own defaults, and a
   backend's defaults can be poor: the test backend's default resolution reads back as
   0.00076 dpi, which gives a frame one pixel wide. Applications must set every option they
   depend on, and the interface should say so; one of the scenario checks relied on the
   inheritance and had to be changed.

## Validation

A prototype service implements the frontend interface over libsane, with the dialog stubbed
(auto-grant) in the service and a real dialog tested separately against the backend
interface. Two applications have been ported to it, and both ran
against it from inside a Flatpak with neither `--device=all` nor `--share=network`.

| Checked | How | Result |
|---|---|---|
| Interface behaviour | 65 scenario checks on a private bus, against SANE's `test` backend, with the frontend in C | Pass: the shape of the interface as introspected (`StartFrame` returns the frame, `Cancel` takes it, no `ScannerEvents`), grants, opaque ids, the exclusive lock, an application that leaves during `OpenScanner` not leaving the scanner locked, other applications refused on someone else's session, option errors, option order, automatic values, frame numbers, `Cancel()` by frame number (a frame that is over is left alone, a number never returned is refused), the rows of a frame, closing the pipe early, release when the application leaves the bus, hand scanner (`lines` = -1), `no-documents` from an empty feeder, the `type` vocabulary, `OpenScanner` answering at once and giving no `Response` when its request is closed. The Rust prototype passes all but one, which is a limit of its test double (it keeps grants for all applications, not each) |
| Drivers and curation | `tests/duplicates.py` with fake drivers, with the frontend in C | Pass: one scanner found by two drivers is one entry, a handheld scanner is not taken for a flatbed and is found by its own capability, the table names capabilities and an unusable entry applies to nothing, ties between drivers go by name, the driver a table entry names comes first and describes the scanner, a driver that does not drive the scanner is followed by the next, an I/O error is not |
| Hardware buttons | `tests/buttons.py` with a fake backend, and the 8200i | Pass: a press is one event, a held button is one press, two buttons are told apart, a latch is read once, a button down when the session opened is not a press. On the 8200i 23 and 24 presses in 40 s of QuickScan and IntelliScan were reported through the portal, each under the right name, and Negative Vibes scanned and previewed from the buttons. The scanner went silent twice after it had been opened through `genesys`, which a power cycle cured; see `docs/HARDWARE-TEST.md` |
| Pixel data correctness | Prototype client output compared with `scanimage` | Byte for byte identical for grayscale, 8-bit RGB, 16-bit RGB and three-pass red/green/blue |
| Portal path versus libsane | Parity test scanning the same options through both, via one trait | Frame parameters, pixel data, option descriptors and constraints identical; busy scanner, empty feeder, rejected value and cancel-with-unread-pipe all surface as the same conditions |
| Real hardware | Plustek OpticFilm 8200i film scanner, 23 checks | Pass, including colour plus infrared, two numbered frames in one session, and cancel then rescan; colour, infrared, repeat and cancel match libsane within sensor noise |
| Flatpak sandbox | Scenarios and a GTK application, no `--device=all`, no network | Pass: preview and raw scan on the 8200i, so fd passing and signals work through the Flatpak D-Bus proxy |
| Remembered grants | `tests/persist.py` with the stand-in helper and dialog and a real permission store, with the frontend in C; and the 8200i | Pass: a choice nobody asked to remember, or the user declined, is not there in the next run; one the user agreed to is, for the scanners whose id stays the same and without a dialog, and the others are refused; the store has a "yes" for the application under each id; taking one permission back, or all, takes the scanner away and `OpenScanner` is refused; another application's entry is not this one's; a host application with no id is kept nothing. On the 8200i with the real helper only it was remembered, not the network printer, with the id it had before the replug. The dialogs of GNOME (a switch, Remember My Choice) and GTK (a check button) have the control, and answer `persist` only when it is on and a chosen scanner is `persistent`; the GNOME dialog is built and shows it, the GTK one only compiles as far as its dialog file, and the dialog buttons were not clicked through in a test yet |
| A second, independent application | GNOME Simple Scan ported to the draft | Scanned from the sandbox on the 8200i, was cancelled mid-frame and scanned again in the same session; the device arrived as a film scanner, and the application hid it itself |
| The dialog | A libadwaita implementation of `org.freedesktop.impl.portal.Scanner` for xdg-desktop-portal-gnome, called directly with made-up scanners on a private bus on a Wayland session | Pass: select returns the chosen id, Escape and Cancel answer "cancelled" with no results, `Request.Close` destroys the window without an answer; unavailable scanners are shown and cannot be chosen; the application's title shows as secondary text under the heading the portal writes. Shown before the search is over: with the system's SANE configuration the dialog is up after 0.30 s where a full listing took about 6 s, scanners found later are added to it, and it says "Searching for Scanners…" until the search ends, not "No Scanners Found" |
| The frontend in C, in xdg-desktop-portal | The frontend, a helper process that holds libsane, and the dialog above, on a private bus: both applications, the SANE `test` backend, the 8200i and a network scanner | Pass for the grant and the dialog, `OpenScanner` with the exclusive lock and `Busy`, options, `auto`, `StartFrame` with the pipe, frame events and numbers, `Cancel`, closing the pipe early, the helper killed in the middle of a frame (the pipe ends and the application gets `Session.Closed`) and the application leaving in the middle of a frame, checked with scripted clients against the `test` backend. Negative Vibes scanned and rescanned after a stop on the 8200i; Simple Scan, from its Flatpak sandbox, scanned on the 8200i and on an HP Color LaserJet MFP M283cdw through the `airscan` backend. The stop on the 8200i was confirmed by hand, and Simple Scan has no cancel button. The 23 hardware checks (`tools/portal-hw-check.sh --frontend c`) also passed on the 8200i with the frontend in C: colour and infrared scans against `scanimage`, a repeat scan, progress, and a cancel at 30% followed by a rescan |

The second application is what produced the frame numbers, the automatic values, the `type`
field and a good deal of the interface documentation: the first application's needs alone
were not enough to settle them.

Not yet verified: the patches for main since the frame number, the `feeder` and `type` words, the removal of `ScannerEvents`, `handheld` and `last_in_image` (they apply, and were tested on 1.22.1), Simple Scan since the same changes, window-handle attachment for the dialog, the dialog in portal-gtk and in
KDE, more than one network scanner or backend (one eSCL scanner has been tried), a helper
that stops answering without dying, two applications opening the same scanner at the same
instant, buttons on any scanner but the 8200i (the `genesys` and Pixma entries of the table in
particular), and any provider other than SANE.

## Open questions

1. **Is `Busy` an acceptable error name?** `org.freedesktop.portal.Error.Busy` is not in
   xdg-desktop-portal's existing error set, and the condition is real and common. Add it, or
   use another name?
2. **The option filter list.** Hiding file name and button options needs a pass over the
   actual SANE backends to be sure the list is right.
3. **A scanner that is replugged.** A USB scanner is matched by its bus address while the helper
   is listing it, so after it is replugged or power cycled it has a new address and a name from
   before is stale. An id outlives the run, by the rules in Scanner
   identity (serial number, else port path, else not at all), and a grant may be kept for it with
   `persist`. Is that the right amount? Feedback on sane-devel from an application with per-scanner
   profiles (NAPS2) asked for it, and for an "all scanners" grant, which this does not add: the
   application still cannot list a scanner the user has not chosen.

## Upstreaming plan

1. Open an issue on xdg-desktop-portal with this proposal and the measured results, and
   settle the open questions.
2. Implement the frontend in C: `src/scanner.c` (`desktop-portal/scanner.c` on main), the
   helper, the in-memory grants, `data/org.freedesktop.portal.Scanner.xml`,
   `data/org.freedesktop.impl.portal.Scanner.xml`, `data/scanner-devices.json`, documentation and
   tests in `tests/`. Written, as 21 patches for 1.22.1 and for main.
3. Implement the dialog in `xdg-desktop-portal-gtk`, as a plain GTK 4 window, which is where the
   print dialog lives and which serves GTK desktops other than GNOME (a sandboxed application
   there has no other way to scan), and in `xdg-desktop-portal-gnome` with libadwaita, where the
   USB dialog lives. A KDE counterpart follows. The libadwaita version is written and tested; the
   GTK one is written (three patches) and not yet tested.
4. Land the Simple Scan port once the interface is accepted, as a non-prototype consumer.

## Prior art

- sane-devel, September 2020, "Sandboxing scanner applications" (Bastien Nocera): concluded
  that a host-side service is preferable to bundled drivers. This proposal is that service,
  with a consent dialog.
- The print portal (`org.freedesktop.portal.Print`): the closest precedent for the dialog, for
  the options of the call (`modal`, `accept_label`, `parent_window`, the response codes 0
  success, 1 cancelled, 2 other, and `Request.Close` destroying the dialog) and for the consent
  model: it stores nothing and asks when the application needs the device, as this proposal
  does for v1. It differs in three ways. Its dialog is `GtkPrintUnixDialog`, which lists the
  printers itself and also collects print settings, whereas there is no scan dialog in GTK, so
  the backend draws the list the frontend gives it, as the USB backend does. Its backend also
  does the printing, handing the document to CUPS, whereas here the frontend and a helper do
  the scanning and the backend is only a dialog, so that GNOME and KDE do not each carry a
  scanning stack. And it keeps the all-string settings dictionary that this proposal does not.
- The USB portal (`org.freedesktop.portal.Usb`): the fd handover and the frontend/backend
  split this follows.
- PWG IPP-Scan and WS-Scan: close to each other and to this option model in spirit.
  Reviewers of earlier attempts asked that the API not be locked to SANE; the v1 option
  vocabulary is typed, constrained and carries units, which an eSCL provider can fill in
  without changing the wire format.
