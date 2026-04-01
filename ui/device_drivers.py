class BaseDriver:
    @staticmethod
    def scale_value(raw, ch_config):
        scale = ch_config.get('scale', 1.0)
        offset = ch_config.get('offset', 0.0)
        return (raw * scale) + offset

class CWT_BSR_Driver(BaseDriver):
    @staticmethod
    def scale_value(raw, ch_config):
        sensor_min = ch_config.get('min', 0)
        sensor_max = ch_config.get('max', 100)
        scale = ch_config.get('scale', 1.0)
        offset = ch_config.get('offset', 0.0)
        # คำนวณตามช่วงแรงดัน/กระแส (0-4000)
        base_val = (raw * (sensor_max - sensor_min) / 4000.0) + sensor_min
        return (base_val * scale) + offset

class Waveshare_8CH_Driver(BaseDriver):
    @staticmethod
    def scale_value(raw, ch_config):
        sensor_min = ch_config.get('min', 0)
        sensor_max = ch_config.get('max', 100)
        scale = ch_config.get('scale', 1.0)
        offset = ch_config.get('offset', 0.0)
        # คำนวณตามความละเอียด 12-bit (0-4095)
        base_val = (raw * (sensor_max - sensor_min) / 4095.0) + sensor_min
        return (base_val * scale) + offset

DRIVERS = {
    "CWT_BSR": CWT_BSR_Driver,
    "WAVESHARE_8CH": Waveshare_8CH_Driver,
    "DEFAULT": BaseDriver
}