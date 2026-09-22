HackRetraction is an OrcaSlicer plugin that generates a smart retraction calibration tower: retraction distance grows around the cube perimeter, while speed, temperature or fan settings change block by block in height.

The test is built from blocks: each new block or perimeter dot uses slightly different values, so you can find the perfect balance between stringing and underextrusion.

## ✨ Features

### 🧪 Retraction calibration test

Builds a full calibration cube: 15 tests per side with increasing retraction distance, speed steps per layer, optional fan and temperature steps by height. The generated G-code is compatible with the classic retraction calibration workflow.

### ⚙️ Profile integration

One click pulls nozzle diameter, bed size, layer height, flow ratio, print and travel speeds, temperatures and the printer's start/end G-code from the active preset. Extruder type (bowden/direct) is detected to suggest starting values.

### 👁️ Live visual preview

Top view shows retraction values around the cube perimeter; side view shows the tower blocks with speed, cooling and temperature per height. The preview updates instantly as you type. The front label "HACKRETRACTION" is printed on the first layer as a compass.

### 🔒 Step locking

Only one incremental parameter can be non-zero at a time (retraction speed, temperature or fan). The other two step fields are locked with an explanation in the tooltip, and generation is validated before running.

### 💾 Export

After "Generate GCODE" choose between copying to the clipboard or saving to a file. Previously generated files can be loaded back — all parameters are restored automatically.

### ❓ Built-in help

A red "?" button opens a step-by-step calibration guide right in the plugin: how to run the test, how to read the tower and how to pick the ideal settings. No external instructions needed.

### 🎨 Settings

Theme (auto/dark/light), font size and family, interface language (English, Russian, Serbian) and the language of G-code comments.

## 📸 Screenshots

![Main screen](https://raw.githubusercontent.com/FlowHack/HackRetraction/master/assets/screenshot_main.png)

![Settings](https://raw.githubusercontent.com/FlowHack/HackRetraction/master/assets/screenshot_settings.png)

![Help](https://raw.githubusercontent.com/FlowHack/HackRetraction/master/assets/screenshot_help.png)

## 📦 Installation

Subscribe to the plugin on its OrcaCloud page:
[https://cloud.orcaslicer.com/p/XXXXXXXX](https://cloud.orcaslicer.com/p/XXXXXXXX)

After subscribing, the plugin appears in the plugin list in OrcaSlicer (Plugins dialog) and is ready to use.

## 🚀 Usage

1. Open the Plugins dialog: **File → Plugins**.
2. Tick the checkbox to the left of **HackRetraction** — the plugin tab appears on the main screen of OrcaSlicer.
3. Once the printer is calibrated, you can hide the plugin: open **File → Plugins** again and untick the checkbox.

### 🛠️ How to run the calibration

1. Click **"Pull parameters"** to load your printer's base settings (the plugin also pulls them on startup; if that did not happen — click the button).
2. Test only **ONE** incremental parameter at a time. Leave the step (increment) non-zero only for retraction speed, temperature **or** fan. Set the other steps to 0.
3. Click **"Generate GCODE"** and choose **"Copy to clipboard"** or **"Save to file"**.
4. Send the file to print. If anything is unclear — press the red **"?"** button: the built-in help explains the whole workflow.

### 🔍 How to read the tower

- **Top view (distance):** dots on the outer walls of the square. Each dot is a new retraction distance; values increase around the perimeter.
- **Side view (parameters by height):** each vertical segment of the tower is printed with its own unique settings (speed, temperature or fan), changing block by block.

Your goal is to find the wall segment that looks the most solid: no "spider webs" (excess plastic) and no gaps (underextrusion from too much retraction). The ideal distance is the value at the dot on that segment; the ideal speed/temperature/fan is the parameter of the height block where that dot sits.

### 💡 Pro tips

- **Direct Drive extruders:** short retraction. Set the retraction step to 0.1–0.25 mm.
- **Bowden extruders:** keep the starting retraction at 0.5 mm and the step at 0.5 mm.
- **Fan:** less cooling usually gives better results on this test.