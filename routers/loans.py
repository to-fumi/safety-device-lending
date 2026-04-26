from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from database import get_db
from models import Device, Loan, SmartphoneLoan
from schemas import LoanCreate, LoanOut, ReturnUpdate, SmartphoneLendRequest

router = APIRouter(prefix="/loans", tags=["loans"])

_LOAN_OPTS = [
    selectinload(Loan.device).selectinload(Device.loans),
    selectinload(Loan.smartphone_loans),
]


def _append_note(base_note: str | None, msg: str | None) -> str | None:
    if not msg:
        return base_note
    return f"{base_note or ''} / {msg}".strip(" /")


def _get_loan_or_404(loan_id: int, db: Session) -> Loan:
    loan = db.query(Loan).options(*_LOAN_OPTS).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return Loan


@router.post("", response_model=LoanOut, status_code=201)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    device = (
        db.query(Device)
        .options(selectinload(Device.loans))
        .filter(Device.id == payload.device_id, Device.is_active == True)
        .first()
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.status == 'broken':
        raise HTTPException(status_code=409, detail="故障中の端末です。別の端末を読み取りください。")
    if device.status == 'retired':
        raise HTTPException(status_code=409, detail="廃却済み端末のため貸出できません。")
    if device.is_lending:
        raise HTTPException(status_code=409, detail="既に貸出中です")
    if not payload.test_course_rule_confirmed:
        raise HTTPException(status_code=400, detail="テストコースルールの遵守確認が必要です")
    
    now = datetime.now()
    employee_code = payload.user_employee_id.upper()

    loan = Loan(
        device_id=payload.device_id,
        user_employee_id=employee_code,
        lend_type="full_set",
        is_smartphone_out=True,
        is_dock_out=True,
        is_cable_out=True,
        note=None,
        lent_at=now,
    )
    db.add(loan)
    db.flush()

    sp_loan = SmartphoneLoan(
        loan_id=loan.id,
        user_employee_id=employee_code,
        lent_at=now,
        dock_no_confirmed=True,
        test_course_rule_confirmed=payload.test_course_rule_confirmed,
    )
    db.add(sp_loan)
    db.commit()
    db.refresh(loan)
    return db.query(Loan).options(*_LOAN_OPTS).filter(Loan.id == loan.id).first()


@router.post("/smartphone-lend", response_model=LoanOut, status_code=201)
def lend_smartphone(payload: SmartphoneLendRequest, db: Session = Depends(get_db)):
    loan = _get_loan_or_404(payload.loan_id, db)

    if not loan.is_active_loan:
        raise HTTPException(status_code=409, detail="この貸出は既に完了しています")
    if loan.is_smartphone_out:
        raise HTTPException(status_code=409, detail="スマホは既に貸出中です")
    if not (loan.is_dock_out or loan.is_cable_out):
        raise HTTPException(status_code=409, detail="台座/コードが全て返却済みです")
    if not payload.dock_no_confirmed:
        raise HTTPException(status_code=400, detail="台座NoとスマホのNoが一致していることを確認してください")
    if not payload.test_course_rule_confirmed:
        raise HTTPException(status_code=400, detail="テストコースルールの遵守確認が必要です")
    
    now = datetime.now()
    employee_code = payload.user_employee_id.upper()

    loan.is_smartphone_out = True
    loan.lend_type = "smartphone_only"

    sp_loan = SmartphoneLoan(
        loan_id=loan.id,
        user_employee_id=employee_code,
        lent_at=now,
        dock_no_confirmed=payload.dock_no_confirmed,
        test_course_rule_confirmed=payload.test_course_rule_confirmed,
    )
    db.add(sp_loan)
    db.commit()
    db.refresh(loan)
    return db.query(Loan).options(*_LOAN_OPTS).filter(Loan.id == loan.id).first()


@router.patch("/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: int, payload: ReturnUpdate, db: Session = Depends(get_db)):
    loan = _get_loan_or_404(loan_id, db)
    if not loan.is_active_loan:
        raise HTTPException(status_code=409, detail="Already returned")
    
    operator = payload.user_employee_id.upper()
    active_sp = loan.active_smartphone_loan

    now = datetime.now()

    if payload.return_type == "smartphone_only":
        if not loan.is_smartphone_out:
            raise HTTPException(status_code=409, detail="スマホは既に返却済みです")
        loan.is_smartphone_out = False
        loan.smartphone_returned_at = now
        if active_sp:
            active_sp.returned_at = now
            active_sp.returned_by_employee_id = operator

    elif payload.return_type == "dock_and_cable_only":
        if loan.is_smartphone_out:
            raise HTTPException(status_code=409, detail="先にスマホを返却してください")
        if not (loan.is_dock_out or loan.is_cable_out):
            raise HTTPException(status_code=409, detail="台座/コードはすでに返却済みです")
        if loan.is_cable_out and payload.cable_weight_checked is not True:
            raise HTTPException(status_code=400, detail="コード返却時は重量確認チェックをONにしてください")
        if loan.is_dock_out:
            loan.is_dock_out = False
            loan.dock_returned_at = now
        if loan.is_cable_out:
            loan.is_cable_out = False
            loan.cable_returned_at = now
            loan.cable_weight_g = None
            loan.cable_weight_ok = payload.cable_weight_checked

    else:
        if loan.is_smartphone_out:
            loan.is_smartphone_out = False
            loan.smartphone_returned_at = now
            if active_sp:
                active_sp.returned_at = now
                active_sp.returned_by_employee_id = operator
        if loan.is_dock_out:
            loan.is_dock_out = False
            loan.dock_returned_at = now
        if loan.is_cable_out:
            if payload.cable_weight_checked is not True:
                raise HTTPException(status_code=400, detail="コード返却時は重量確認チェックをONにしてください")
            loan.is_cable_out = False
            loan.cable_returned_at = now
            loan.cable_weight_g = None
            loan.cable_weight_ok = payload.cable_weight_checked

    loan.returned_at = now if not loan.is_active_loan else None
    loan.note = _append_note(loan.note, payload.note)

    if payload.note and not loan.is_active_loan:
        loan.broken_note = payload.note
        loan.broken_reported_by = operator
        loan.broken_at = now
        loan.device.status = "broken"
        loan.device.broken_note = payload.note
        loan.device.broken_reported_by = operator
        loan.device.broken_at = now

    db.commit()
    db.refresh(loan)
    return db.query(Loan).options(*_LOAN_OPTS).filter(Loan.id == loan.id).first()


@router.get("", response_model=list[LoanOut])
def list_loans(
    status: str | None = Query(None, description="lending | returned"),
    device_id: int | None = Query(None),
    q: str | None = Query(None, description="社員ID の部分一致"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_, select
    query = (
        db.query(Loan)
        .options(*_LOAN_OPTS)
        .order_by(Loan.lent_at.desc())
    )
    if status == "lending":
        query = query.filter(Loan.returned_at.is_(None))
    elif status == "returned":
        query = query.filter(Loan.returned_at.isnot(None))
    if device_id:
        query = query.filter(Loan.device_id == device_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Loan.user_employee_id.like(like),
                Loan.id.in_(
                    select(SmartphoneLoan.loan_id).where(
                        or_(
                            SmartphoneLoan.user_employee_id.like(like),
                            SmartphoneLoan.returned_by_employee_id.like(like),
                        )
                    )
                )
            )
        )
    return query.offset(offset).limit(limit).all()
