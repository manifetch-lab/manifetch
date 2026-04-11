import enum


class SignalType(str, enum.Enum):
    HEART_RATE = "HEART_RATE"
    SPO2       = "SPO2"
    RESP_RATE  = "RESP_RATE"
    ECG        = "ECG"


class AlertStatus(str, enum.Enum):
    ACTIVE       = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED     = "RESOLVED"


class Severity(str, enum.Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class Role(str, enum.Enum):
    DOCTOR        = "DOCTOR"
    NURSE         = "NURSE"
    ADMINISTRATOR = "ADMINISTRATOR"


class ModelType(str, enum.Enum):
    RANDOM_FOREST = "RANDOM_FOREST"
    XGBOOST       = "XGBOOST"
    LIGHTGBM      = "LIGHTGBM"   # train_model.py kazanan model olarak seçebilir