HackRetraction is an OrcaSlicer plugin that generates a retraction calibration test: a G-code pattern with increasing retraction distance around the cube, speed, cooling and temperature steps by height.

It pulls base parameters and the printer's start/end G-code from your active profile, so the test matches your machine out of the box.

## Features

### Retraction calibration test

Builds a full calibration cube: 15 tests per side with increasing retraction distance, speed steps per layer, optional fan and temperature steps. The generated G-code is compatible with the classic retraction calibration workflow.

### Profile integration

One click pulls nozzle diameter, bed size, layer height, flow ratio, print and travel speeds, temperatures and the printer's start/end G-code from the active preset. Extruder type (bowden/direct) is detected to suggest starting speeds.

### Visual preview

Top view shows retraction values around the cube; side view shows speed, cooling and temperature steps by height. The front label is printed on the first layer.

### Export

Save the G-code to any location you choose, or copy it to the clipboard. Previously generated files can be loaded back — all parameters are restored automatically.

### Settings

Theme (auto/dark/light), font size and family, interface language (English, Russian, Serbian) and the language of G-code comments.

## Installation

Install from the OrcaCloud subscription page:
[https://cloud.orcaslicer.com/p/XXXXXXXX](https://cloud.orcaslicer.com/p/XXXXXXXX)

## Usage

1. Open the Plugins dialog: **File → Plugins**.
2. Tick the checkbox to the left of **HackRetraction** to activate it.
3. Expand the plugin by clicking the arrow in its row.
4. Click the launch button on the right — the generator window opens.

Set the parameters (or click "Pull from profile"), press **Generate**, then **Copy** or enter a path and press **Save**.