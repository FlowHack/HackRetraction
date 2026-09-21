"""Константы плагина HackRetraction: дефолты параметров, ключи профиля, лимиты."""

# Дефолтные параметры генератора (единый источник для UI и генерации).
# Значения — из оригинального генератора (fork/), адаптированы под OrcaSlicer.
DEFAULT_PARAMS: dict[str, float | int | str] = {
    # Ретракция
    "startRetractiondistance": 0.5,  # стартовое втягивание, мм
    "incrementRetractiondistance": 0.5,  # шаг втягивания, мм
    "startRetractionspeed": 10.0,  # стартовая скорость втягивания, мм/с
    "incrementRetractionspeed": 10.0,  # шаг скорости втягивания, мм/с
    # Температура
    "tempStarthotend": 210,  # стартовая температура хотэнда, °C
    "tempIncrementhotend": 0,  # шаг температуры хотэнда, °C
    "tempBed": 50,  # температура стола, °C
    # Обдув
    "speedFan": 40,  # скорость вентилятора, %
    "speedFanIncrement": 0,  # шаг обдува, %
    # Печать
    "layerHeight": 0.2,  # высота слоя, мм
    "printSpeed": 40.0,  # скорость печати, мм/с
    "speedTravel": 100.0,  # скорость перемещения, мм/с
    "nozzleDiameter": 0.4,  # диаметр сопла, мм
    "filamentDiameter": 1.75,  # диаметр филамента, мм
    "extrusionMultiplier": 1.0,  # коэффициент потока
    # Стол и тест
    "dimensionX": 220,  # ширина стола, мм
    "dimensionY": 220,  # глубина стола, мм
    "layersTest": 25,  # слоёв на тест
    "NumTests": 15,  # количество тестов
    # Стартовый/конечный gcode принтера (редактируемые поля UI).
    # Пустая строка — использовать подтянутый из профиля или дефолт.
    "startGcode": "",
    "endGcode": "",
}

# Параметры, подтягиваемые из профиля принтера: ключ UI -> кортеж ключей
# пресета Orca (fallback-цепочка: первый найденный ключ побеждает).
PRESET_KEYS: dict[str, tuple[str, ...]] = {
    "nozzleDiameter": ("nozzle_diameter",),
    "dimensionX": ("printable_width",),
    "dimensionY": ("printable_depth",),
    "layerHeight": ("layer_height",),
    "extrusionMultiplier": ("filament_flow_ratio",),
    "speedTravel": ("travel_speed",),
    "printSpeed": ("outer_wall_speed", "default_print_speed"),
    "tempStarthotend": ("nozzle_temperature",),
    "tempBed": ("hot_plate_temp", "bed_temperature"),
}

# Секция пресета для каждого ключа профиля (резервный проход по цепочке
# наследования в pull_from_profile).
KEY_SECTIONS: dict[str, str] = {
    "nozzle_diameter": "printers",
    "printable_width": "printers",
    "printable_depth": "printers",
    "printable_area": "printers",
    "machine_start_gcode": "printers",
    "machine_end_gcode": "printers",
    "printer_extruder_id": "printers",
    "printer_extruder_variant": "printers",
    "filament_flow_ratio": "filaments",
    "nozzle_temperature": "filaments",
    "hot_plate_temp": "filaments",
    "bed_temperature": "filaments",
    "fan_min_speed": "filaments",
    "fan_max_speed": "filaments",
    "layer_height": "prints",
    "outer_wall_speed": "prints",
    "default_print_speed": "prints",
    "travel_speed": "prints",
}

# Ключи обдува: speedFan вычисляется как полусумма min/max (см. pull_from_profile).
FAN_SPEED_KEYS: tuple[str, str] = ("fan_min_speed", "fan_max_speed")

# Ключи стартового/конечного gcode принтера (секция printer).
START_GCODE_KEY = "machine_start_gcode"
END_GCODE_KEY = "machine_end_gcode"

# Ключи определения типа экструдера (bowden/direct drive).
# printer_extruder_variant — «Direct Drive Standard»; extruder_type — «Direct Drive».
EXTRUDER_ID_KEYS: tuple[str, str, str] = (
    "printer_extruder_id",
    "printer_extruder_variant",
    "extruder_type",
)

# Стартовые значения для типа экструдера: bowden требует большего втягивания
# и более высокой скорости, чем direct drive. Значения — старт и шаг для
# расстояния втягивания и скорости втягивания.
EXTRUDER_PRESETS: dict[str, dict[str, float]] = {
    "bowden": {
        "startRetractiondistance": 0.5,
        "incrementRetractiondistance": 0.5,
        "startRetractionspeed": 10.0,
        "incrementRetractionspeed": 10.0,
    },
    "direct": {
        "startRetractiondistance": 1.0,
        "incrementRetractiondistance": 0.1,
        "startRetractionspeed": 5.0,
        "incrementRetractionspeed": 2.0,
    },
}

# Дефолтный стартовый gcode (если machine_start_gcode не подтянулся).
# Плейсхолдеры OrcaSlicer ([...] и {...}) подставляются генератором из параметров.
DEFAULT_START_GCODE = (
    "M400 ; Очистка буфера\n"
    "M220 S100 ; Скорость печати 100%\n"
    "M221 S100 ; Поток 100%\n"
    "\n"
    "; Умный нагрев\n"
    "M104 S140 ; Преднагрев сопла до 140C\n"
    "M190 S[bed_temperature_initial_layer_single] ; Нагрев стола и ожидание\n"
    "\n"
    "G90 ; Абсолютное позиционирование\n"
    "G28 ; Парковка всех осей\n"
    "M420 S1 Z10 ; Загрузка карты стола и установка затухания компенсации на 10 мм\n"
    "\n"
    "G1 Z10 F300 ; Подъем сопла\n"
    "\n"
    "; Перемещение в начальную точку стартовой линии спереди\n"
    "G1 X{print_bed_max[0]*0.5-50} Y1.0 F6000 \n"
    "M109 S[nozzle_temperature_initial_layer] ; Финальный нагрев сопла и ожидание\n"
    "\n"
    "; Отрисовка стартовой линии спереди\n"
    "G92 E0 ; Сброс экструдера\n"
    "G1 Z0.4 F300 ; Опускание сопла\n"
    "G1 X{print_bed_max[0]*0.5+50} E30 F400 ; Первая линия (слева направо)\n"
    "G1 Z0.6 F120.0 ; Небольшой подъем сопла\n"
    "G1 X{print_bed_max[0]*0.5+47} F3000 ; Быстрое смахивание капли\n"
    "G92 E0 ; Сброс экструдера\n"
)

# Дефолтный конечный gcode (если machine_end_gcode не подтянулся).
DEFAULT_END_GCODE = (
    "G91 ; Относительное позиционирование\n"
    "G1 E-2 F2700 ; Небольшой откат\n"
    "G1 E-8 X5 Y5 Z3 F3000 ; Откат, подъем и смещение сопла\n"
    "G90 ; Абсолютное позиционирование\n"
    "G1 X0 Y{print_bed_max[1]} F3000 ; Выдвинуть стол с деталью вперед\n"
    "M106 S0 ; Выключить вентилятор\n"
    "M104 S0 ; Выключить сопло\n"
    "M140 S0 ; Выключить стол\n"
    "M84 X Y E ; Отключить моторы кроме оси Z\n"
)

# Плейсхолдеры OrcaSlicer, подставляемые генератором из параметров.
# Ключ — плейсхолдер, значение — callable(params) -> строка.
PLACEHOLDERS: dict[str, str] = {
    "[bed_temperature_initial_layer_single]": "tempBed",
    "[nozzle_temperature_initial_layer]": "tempStarthotend",
    "{print_bed_max[0]*0.5-50}": "dimensionX*0.5-50",
    "{print_bed_max[0]*0.5+50}": "dimensionX*0.5+50",
    "{print_bed_max[0]*0.5+47}": "dimensionX*0.5+47",
    "{print_bed_max[1]}": "dimensionY",
}

# Имя файла по умолчанию для экспорта.
DEFAULT_GCODE_FILENAME = "retraction_calibration.gcode"

# Шаг стрелочек числовых полей (атрибут step). Остальные поля — "any".
PARAM_STEPS: dict[str, float] = {
    "startRetractiondistance": 0.1,
    "incrementRetractiondistance": 0.1,
    "layerHeight": 0.1,
    "nozzleDiameter": 0.1,
    "filamentDiameter": 0.1,
    "extrusionMultiplier": 0.01,
}

# Реквизиты для поддержки проекта. Единый источник данных для UI: при смене
# адреса достаточно обновить эту константу. url пустой, если ссылки нет.
DONATION_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "yoomoney",
        "title": "YoMoney",
        "value": "4100119569298015",
        "url": "https://yoomoney.ru/to/4100119569298015",
    },
    {
        "id": "usdt",
        "title": "USDT (TRC-20)",
        "value": "TJRUKLwmYk8DpjFCyakQxWzXeJL6hrFTxZ",
        "url": "",
    },
    {
        "id": "btc",
        "title": "BTC",
        "value": "15f1swAtj7T1yVaXGEGWyLrfxSmDn1NKiY",
        "url": "",
    },
)
