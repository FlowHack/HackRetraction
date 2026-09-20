"""Английские комментарии gcode по умолчанию (единый источник).

Используются генератором как fallback и i18n.py как база для en.
Локализованные словари (ru/sr) — в i18n.py (I18N_COMMENTS).
"""

from __future__ import annotations

from typing import Dict

EN_DEFAULT_COMMENTS: Dict[str, str] = {
    "header_retraction": "Retraction Distance from the top looking down",
    "front": "FRONT",
    "variables_by_height": "Variables by Height",
    "table_height": "Height",
    "table_retr_speed": "Retraction Speed",
    "table_nozzle_temp": "Nozzle Temp",
    "table_fan_speed": "Fan Speed",
    "all_inputs": "All inputs",
    "dim_x": "Dimension X",
    "dim_y": "Dimension Y",
    "start_retr_dist": "Starting Retraction Distance",
    "inc_retr": "Increment Retraction",
    "start_retr_speed": "Start Retraction Speed",
    "retr_speed_inc": "Retraction Speed Increment",
    "print_speed": "Print Speed",
    "start_temp": "Starting Temp",
    "inc_temp": "Increment Temp",
    "bed_temp": "Bed Temp",
    "fan_speed": "Fan Speed",
    "fan_speed_inc": "Fan Speed Increment",
    "nozzle_diameter": "Nozzle Diameter",
    "layer_height": "Layer Height",
    "filament_diameter": "Filament Diameter",
    "extrusion_mult": "Extrusion Multiplier",
    "layers_per_test": "Layers Per Test",
    "num_tests": "Number of Tests",
    "start_gcode": "Start Gcode",
    "start_movement": "Start Movement",
    "end_gcode": "End Gcode",
    "layer": "Layer",
}