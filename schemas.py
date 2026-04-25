from datetime import datetime
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, field_validator

class DeviceBase(BaseModel):
    no: str
    device_id_code: str | None = None
    memo: str | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceStatusUpdate(BaseModel):
    status: Literal["active", "broken", "retired"]


class DeviceOut(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_lending: bool
    status: str
    broken_note: str | None = None
    broken_reported_by: str | None = None
    broken_at: datetime | None = None
    recovered_at: datetime | None = None
    retired_at: datetime | None = None
    deleted_at: datetime | None = None


def _validate_emp(v: str) -> str:
    v = v.upper()
    if not re.match(r'^(?:\d{7}|[SZ]\d{6})$', v):
        raise ValueError('invalid employee code')
    return v


class LoanCreate(BaseModel):
    device_id: int
    user_employee_id: str
    test_course_rule_confirmed: bool = False

    @field_validator('user_employee_id')
    @classmethod
    def validate_employee_code(cls, v: str):
        return _validate_emp(v)
    

class SmartphoneLendRequest(BaseModel):
    load_id: int
    user_employee_id: str
    dock_no_confirmed: bool = False
    test_course_rule_confirmed: bool = False

    @field_validator('user_employee_id')
    @classmethod
    def validate_employee_code(cls, v: str):
        return _validate_emp(v)
    

class ReturnUpdate(BaseModel):
    return_type: Literal["full_set", "smartphone_only", "dock_and_cable_only"] = "full_set"
    user_employee_id: str
    cable_weight_checked: bool | None = None
    note: str | None = None

    @field_validator("user_employee_id")
    @classmethod
    def validate_employee_code(cls, v: str):
        return _validate_emp(v)
    

class SmartphoneLoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loan_id: int
    user_employee_id: str
    lent_at: datetime
    returned_at: datetime | None
    returned_by_employee_id: str | None
    dock_no_confirmed: bool
    test_course_rule_confirmed: bool


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    device: DeviceOut
    user_employee_id: str
    lend_type: str
    is_smartphone_out: bool
    is_dock_out: bool
    is_cable_out: bool
    note: str | None
    lent_at: datetime
    smartphone_returned_at: datetime | None
    dock_returned_at: datetime | None
    cable_returned_at: datetime | None
    cable_weight_g: float | None
    cable_weight_ok: bool | None
    broken_note: str | None
    broken_reported_by: str | None
    broken_at: datetime | None
    returned_at: datetime | None
    smartphone_loans: list[SmartphoneLoanOut] = []
    borrower_employee_ids: list[str] = []

    @property
    def status(self) -> str:
        return "returned" if self.returned_at else "lending"
    