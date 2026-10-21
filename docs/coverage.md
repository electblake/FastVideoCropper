# Specification coverage

Target: Windows desktop, Python 3.12+, system Qt Widgets style, mouse and
keyboard. No custom fonts, themes, or widget painting.

## Implemented

- Multiple-file picker and drag/drop, queue position, previous/next, done state.
- Mixed file/folder input through the existing picker, Files panel drops, and
  launch arguments; immediate folder videos append without duplicate paths.
- Explicit Select none and Clear files controls; unloading preserves the list and
  cached segments, while clearing removes them. Switching releases the old source.
- Qt Multimedia source playback, pause, mute, millisecond position display,
  native scrubber with 250 ms keyboard increments.
- Scene detection with live scan progress, cancellation, a selectable segment
  list, independent segment crops, and separate numbered exports.
- Bounded third-party crop dragging and eight resize handles, outside mask,
  percentage position and pixel size controls.
- All twelve specified ratios as direct native buttons, independent aspect locking, center, full-frame reset,
  clockwise/counterclockwise rotation preserving geometry, selection zoom and
  optional pointer-centered wheel zoom.
- Retained crop geometry, ratio, rotation, and aspect lock per video segment during the session.
- Saved application and detection preferences through QSettings in the platformdirs user config directory.
- HEVC export, copied audio, segment time intervals, numbered segment output alongside
  the source, overwrite, optional square-pixel normalization.
- Explicit CPU, NVIDIA, Intel and AMD encoder selection when compiled into
  FFmpeg. NVIDIA device index is exposed. Auto GPU uses Windows device discovery
  and encoder availability, preferring NVIDIA, Intel, then AMD without retries.
- Asynchronous progress, FPS, speed, ETA and source-processing preview at 500 ms
  intervals without waiting for frame callbacks between seeks.
- Pause/resume, stop with FFmpeg finalization, cancel and delete, locate output.
- Optional completion beep/taskbar attention, next-file advance, auto-run and
  quit countdowns with cancellation.
- Native saved-settings viewer, process log and diagnostic-report export.

## Deliberate Qt translation choices

- Geometry uses rotated source pixels rather than rounded preview-canvas text.
- Crop controls and file opening are disabled throughout export.
- Qt owns playback decoder selection. FFmpeg uses software decoding and filtering,
  then the selected encoder. There is no hardware-decoding pipeline or retry on
  another device.
- PyQtGraph supplies its native gesture behavior. Its Ctrl snapping and Alt
  aspect behavior replace the old custom Shift gesture semantics.
- Layout and view changes are immediate, except for a 500 ms resize debounce.
- Errors from dependencies are not caught, wrapped or retried. Qt/FFmpeg
  diagnostics are shown directly; unsupported exports fail in FFmpeg.
- FFmpeg's `N/A` startup progress records are not elapsed-time samples; only
  timestamp-bearing records update progress.

## Release channel

Help → Check for Updates queries the latest release of
`electblake/fastvideocropper`. Downloads use the installer asset matching the
application version and Windows architecture. Installation starts after the
application exits. The original application's releases remain a separate
reference link.

## Verification limits

Automated tests use real FFmpeg CPU encoding and Qt Multimedia playback.
They cover crop dimensions, all quarter-turn filters, decoded first-frame
content, selected frame counts, copied-audio duration, same-size navigation,
geometry persistence, numeric locking, eight library handles, process suspension,
stop/finalization and cancellation/deletion.
Preset checks cover every button while locked and unlocked, keyboard selection,
reciprocal selection after rotation, restoration on load, and clearing to Custom.
Position edits preserve unedited fractional dimensions instead of rounding them.
Segment tests cover real scene boundaries, partial log records, retained trim
precision, independent crops, numbered exports, progress without scene changes,
and cancellation without deleting prior exports. Detection restores a default
segment when enabled and the timeline is empty after cancellation or failure.
File-lifecycle checks cover repeated exports followed by list selection, opening,
and dropping new files; they inspect decoded frames and rendered preview pixels.
They also verify file-handle release, deselection, clearing, saved crops, playback,
and repeated switching between different video dimensions and rotations.
Metadata and GPU discovery tests verify that the Qt event loop stays responsive.
Square-pixel export and anamorphic preview-to-source coordinate mapping are
also exercised with real media, both before and after rotation. Embedded display
rotation is checked against the video item's actual bounds and a real export.

Hardware encoders require the corresponding installed device and driver and
have not been verified across vendors. HDR,
long-duration media, screen readers and RTL translations require
additional platform-specific verification. UI rendering was inspected at the
machine's system DPI and font settings.
