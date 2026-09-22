Features of HackRetraction 0.1.0:

- 🧪 Retraction calibration tower: distance grows around the cube perimeter, speed / temperature / fan change block by block in height.
- 👁️ Live HTML preview: top view (retraction values around the square) and side view (tower blocks with parameters), updates instantly.
- ⚙️ Pull parameters from the active profile: nozzle, bed size, layer height, flow ratio, speeds, temperatures, start/end G-code; extruder type detection (bowden/direct).
- 🔒 Step locking: only one incremental parameter at a time (speed / temperature / fan), other fields are locked with a tooltip explanation; validation before generation.
- 💾 Export menu after "Generate GCODE": copy to clipboard or save to file; load previously generated G-code with parameter restore.
- ❓ Built-in help: red "?" button with a step-by-step calibration guide.
- 🔔 Toast notifications instead of the status bar.
- 🎨 Settings: theme (auto/dark/light), font size and family, interface language (EN/RU/SR), G-code comment language.
- 🛡️ Negative incremental steps are rejected.
- 📊 Parameter table in G-code is written top-down (top tower block first).