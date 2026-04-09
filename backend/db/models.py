import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Index, SmallInteger
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.db.base import Base
from backend.db.enums import SignalType, AlertStatus, Severity, Role, ModelType
from backend.db.encryption import encrypt, decrypt


def new_uuid() -> str:
    return str(uuid.uuid4())


SIGNAL_UNITS = {
    SignalType.HEART_RATE.value: "BPM",
    SignalType.SPO2.value:       "%",
    SignalType.RESP_RATE.value:  "breaths/min",
    SignalType.ECG.value:        "mV",
}


class Patient(Base):
    __tablename__ = "patients"

    patient_id            = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    _full_name            = Column("full_name", String, nullable=False)
    gestational_age_weeks = Column(SmallInteger, nullable=False)
    postnatal_age_days    = Column(SmallInteger, nullable=False)
    admission_date        = Column(DateTime(timezone=True), default=datetime.utcnow)
    is_active             = Column(Boolean, default=True, nullable=False)

    @property
    def full_name(self) -> str:
        return decrypt(self._full_name)

    @full_name.setter
    def full_name(self, value: str):
        self._full_name = encrypt(value)

    signal_streams     = relationship("SignalStream",     back_populates="patient", cascade="all, delete-orphan")
    vital_measurements = relationship("VitalMeasurement", back_populates="patient", cascade="all, delete-orphan")
    threshold_rules    = relationship("ThresholdRule",    back_populates="patient", cascade="all, delete-orphan")
    alerts             = relationship("Alert",            back_populates="patient", cascade="all, delete-orphan")
    ai_results         = relationship("AIResult",         back_populates="patient", cascade="all, delete-orphan")


class SignalStream(Base):
    __tablename__ = "signal_streams"

    stream_id  = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    patient_id = Column(UUID(as_uuid=False), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    stopped_at = Column(DateTime(timezone=True), nullable=True)

    patient      = relationship("Patient",          back_populates="signal_streams")
    measurements = relationship("VitalMeasurement", back_populates="stream", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_signal_streams_patient_id", "patient_id"),
    )


class VitalMeasurement(Base):
    __tablename__ = "vital_measurements"

    measurement_id        = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    patient_id            = Column(UUID(as_uuid=False), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False)
    stream_id             = Column(UUID(as_uuid=False), ForeignKey("signal_streams.stream_id", ondelete="SET NULL"), nullable=True)
    signal_type           = Column(String(16), nullable=False)
    value                 = Column(Float, nullable=False)
    timestamp             = Column(DateTime(timezone=True), nullable=False)
    timestamp_sec         = Column(Float, nullable=False)
    is_valid              = Column(Boolean, default=True)
    gestational_age_weeks = Column(SmallInteger, nullable=True)
    postnatal_age_days    = Column(SmallInteger, nullable=True)
    pma_weeks             = Column(Float, nullable=True)
    label_sepsis          = Column(SmallInteger, default=0)
    label_apnea           = Column(SmallInteger, default=0)
    label_cardiac         = Column(SmallInteger, default=0)
    label_healthy         = Column(SmallInteger, default=0)

    @property
    def unit(self) -> str:
        return SIGNAL_UNITS.get(self.signal_type, "")

    patient = relationship("Patient",     back_populates="vital_measurements")
    stream  = relationship("SignalStream", back_populates="measurements")
    alerts  = relationship("Alert",        back_populates="measurement")

    __table_args__ = (
        Index("ix_vital_patient_timestamp", "patient_id", "timestamp"),
        Index("ix_vital_signal_type",       "signal_type"),
        Index("ix_vital_timestamp",         "timestamp"),
    )


class ThresholdRule(Base):
    __tablename__ = "threshold_rules"

    rule_id     = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    patient_id  = Column(UUID(as_uuid=False), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False)
    signal_type = Column(String(16), nullable=False)
    min_value   = Column(Float, nullable=False)
    max_value   = Column(Float, nullable=False)
    enabled     = Column(Boolean, default=True, nullable=False)
    severity    = Column(String(16), default=Severity.MEDIUM.value, nullable=False)

    patient = relationship("Patient", back_populates="threshold_rules")
    alerts  = relationship("Alert",   back_populates="rule")

    __table_args__ = (
        Index("ix_threshold_patient_signal", "patient_id", "signal_type"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    alert_id        = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    patient_id      = Column(UUID(as_uuid=False), ForeignKey("patients.patient_id",          ondelete="CASCADE"),  nullable=False)
    rule_id         = Column(UUID(as_uuid=False), ForeignKey("threshold_rules.rule_id",      ondelete="SET NULL"), nullable=True)
    measurement_id  = Column(UUID(as_uuid=False), ForeignKey("vital_measurements.measurement_id", ondelete="SET NULL"), nullable=True)
    acknowledged_by = Column(UUID(as_uuid=False), ForeignKey("users.user_id",                ondelete="SET NULL"), nullable=True)
    status          = Column(String(16), default=AlertStatus.ACTIVE.value, nullable=False)
    severity        = Column(String(16), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at     = Column(DateTime(timezone=True), nullable=True)

    patient      = relationship("Patient",          back_populates="alerts")
    rule         = relationship("ThresholdRule",    back_populates="alerts")
    measurement  = relationship("VitalMeasurement", back_populates="alerts")
    acknowledger = relationship("User",             back_populates="acknowledged_alerts")

    __table_args__ = (
        Index("ix_alerts_patient_status", "patient_id", "status"),
        Index("ix_alerts_created_at",     "created_at"),
    )


class AIResult(Base):
    __tablename__ = "ai_results"

    result_id        = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    patient_id       = Column(UUID(as_uuid=False), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False)
    timestamp        = Column(DateTime(timezone=True), nullable=False)
    risk_score       = Column(Float, nullable=False)
    risk_level       = Column(String(16), nullable=False)
    sepsis_score     = Column(Float, nullable=True)
    apnea_score      = Column(Float, nullable=True)
    cardiac_score    = Column(Float, nullable=True)
    sepsis_label     = Column(SmallInteger, nullable=True)
    apnea_label      = Column(SmallInteger, nullable=True)
    cardiac_label    = Column(SmallInteger, nullable=True)
    model_used       = Column(String(128), default=ModelType.RANDOM_FOREST.value, nullable=False)
    shap_values_json = Column(String, nullable=True)

    patient = relationship("Patient", back_populates="ai_results")

    __table_args__ = (
        Index("ix_ai_results_patient_timestamp", "patient_id", "timestamp"),
    )


class User(Base):
    __tablename__ = "users"

    user_id       = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    username      = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role          = Column(String(16), default=Role.NURSE.value, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    _display_name = Column("display_name", String, nullable=False)

    @property
    def display_name(self) -> str:
        return decrypt(self._display_name)

    @display_name.setter
    def display_name(self, value: str):
        self._display_name = encrypt(value)

    acknowledged_alerts = relationship("Alert", back_populates="acknowledger")

    __table_args__ = (
        Index("ix_users_username", "username"),
    )