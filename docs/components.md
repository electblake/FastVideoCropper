# Component decisions

Research and implementation: 2026-10-20. The five supplied specifications describe
the previous program; their implementation notes are evidence, not instructions
to copy its custom controls or recovery logic.

| Need | Selected existing component | Reason |
| --- | --- | --- |
| Desktop shell | QMainWindow, QSplitter, QTabWidget, QScrollArea | Native resizing, navigation, and overflow |
| Playback and audio | QMediaPlayer, QAudioOutput | Qt owns decoding, seeking and playback |
| Video in a crop scene | QGraphicsVideoItem | Native video item supports scene transforms and overlays without Python frame copies |
| Crop interaction | PyQtGraph RectROI and addScaleHandle | Existing drag, resize, bounds and aspect constraints; eight handles |
| Outside shading | Four QGraphicsRectItem instances | Stock scene items; no painter or input implementation |
| View fitting and zoom | PyQtGraph ViewBox | Existing coordinate mapping, aspect-preserving scaling and range management |
| Timeline | QSlider; PyQtGraph LinearRegionItem and InfLineLabel | Native scrubbing and existing labeled range indicators |
| Segment selection | QListWidget and numbered LinearRegionItems | Native keyboard selection and clickable timeline regions |
| Scene detection | QDialog, QDoubleSpinBox, QProcess; FFmpeg select/showinfo | Streaming progress and diagnostics, with cancellation through the existing process lifecycle |
| Source and GPU discovery | QProcess | Asynchronous metadata and GPU queries keep the event loop responsive |
| Geometry and detection settings | QDoubleSpinBox | Native keyboard editing, locale, focus and accessibility |
| Aspect presets | Checkable QPushButtons, QButtonGroup, QGridLayout | Twelve directly accessible presets with native selected/focus states |
| Aspect locking | QCheckBox | Independent, keyboard-accessible lock/unlock toggle |
| Process lifecycle | QProcess; psutil suspend/resume | Asynchronous pipes plus existing process control |
| Preferences | QSettings + platformdirs | INI storage in the user config directory; segment crops remain video-specific |
| Progress and diagnostics | QProgressBar, QLabel, QPlainTextEdit, QFileDialog | Standard controls |

Qt's QRubberBand draws a selection outline but does not provide a complete
bounded, eight-handle crop editor. QGraphicsRectItem does not provide resize
handles either. PyQtGraph already implements this interaction, supports PySide6,
and has a public GitHub repository. It was selected before any crop interaction
implementation. There are no custom QWidget/QGraphicsItem subclasses,
paintEvent implementations, stylesheets, or replacement pointer-gesture engines.

The application controller composes these components and translates their
state into FFmpeg commands. Export coordinates are explicit rotated source pixel
coordinates. FFprobe supplies encoded dimensions and display rotation; QGraphicsVideoItem supplies
display dimensions including pixel aspect ratio. Their ratios map the visible
selection to FFmpeg's crop coordinates. View zoom never enters export arithmetic.
The controller accounts for metadata rotation when sizing the video item and
lets the scene own aspect preservation, avoiding the item's internal
letterboxing against its unrotated native size.

## Sources

- [LosslessCut segment workflow reference](https://github.com/mifi/lossless-cut)
- [FFmpeg scene selection](https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect)
- [Original application](https://github.com/electblake/VideoCropper)
- [Qt QRubberBand](https://doc.qt.io/qt-6/qrubberband.html)
- [Qt QGraphicsVideoItem](https://doc.qt.io/qtforpython-6/PySide6/QtMultimediaWidgets/QGraphicsVideoItem.html)
- [Qt QVideoSink](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QVideoSink.html)
- [PyQtGraph repository and supported bindings](https://github.com/pyqtgraph/pyqtgraph)
- [PyQtGraph ROI reference](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/roi.html)
- [PyQtGraph ROI source](https://github.com/pyqtgraph/pyqtgraph/blob/master/pyqtgraph/graphicsItems/ROI.py)

The ROI's `aspectLocked` constructor argument forces a square in its scale
implementation. This application uses `addScaleHandle(lockAspect=True)` to
preserve arbitrary crop ratios instead. Edge handles use an off-axis anchor
while locked so the library scales both dimensions. Regression tests exercise
all eight handles.
