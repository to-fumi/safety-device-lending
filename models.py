from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    device_id_code: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True, index=True)
    memo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    broken_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    broken_reported_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    broken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    loans: Mapped[list["Loan"]] = relationship("Loan", back_populates="device")

    @property
    def is_lending(self) -> bool:
        return any(l.is_active_loan for l in self.loans)
    

class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), index=True)
    user_employee_id: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=False)
    lend_type: Mapped[str] = mapped_column(String(30), default="full_set")
    is_smartphone_out: Mapped[bool] = mapped_column(Boolean, default=True)
    is_dock_out: Mapped[bool] = mapped_column(Boolean, default=True)
    is_cable_out: Mapped[bool] = mapped_column(Boolean, default=True)
    lent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    smartphone_returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dock_returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cable_returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cable_weight_g: Mapped[datetime | None] = mapped_column(Float, nullable=True)
    cable_weight_ok: Mapped[datetime | None] = mapped_column(Boolean, nullable=True)
    broken_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    broken_reported_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    broken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device: Mapped["Device"] = relationship("Device", back_populates="loans")
    smartphone_loans: Mapped[list["SmartphoneLoan"]] = relationship(
        "SmartphoneLoan", back_populates="loan", order_by="SmartphoneLoan.lent_at"
    )

    @property
    def is_active_loan(self) -> bool:
        return self.is_smartphone_out or self.is_dock_out or self.is_cable_out
    
    @property
    def active_smartphone_loan(self) -> "SmartphoneLoan | None":
        return next((sl for sl in self.smartphone_loans if sl.returned_at is None), None)

    @property
    def borrower_employee_ids(self) -> list[str]:
        ids: list[str] = []
        primary = (self.user_employee_id or "").upper()
        if primary:
            ids.append(primary)

        for sp in self.smartphone_loans:
            code = (sp.user_employee_id or "").upper()
            if code and code not in ids:
                ids.append(code)
            ret_code = (sp.returned_by_employee_id or "").upper()
            if ret_code and ret_code not in ids:
                ids.append(ret_code)
        return ids
    

class SmartphoneLoan(Base):
    __tablename__ = "smartphone_loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    loan_id: Mapped[int] = mapped_column(Integer, ForeignKey("loans.id"), index=True)
    user_employee_id: Mapped[str] = mapped_column(String(50), nullable=False)
    lent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_by_employee_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dock_no_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    test_course_rule_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    loan: Mapped["Loan"] = relationship("Loan", back_populates="smartphone_loans")
