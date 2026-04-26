from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from database import get_db
from models import Device, Loan
from schemas import DeviceCreate, DeviceOut, DeviceStatusUpdate, LoanOut

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(
    available_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Device).options(selectinload(Device.loans)).filter(Device.is_active == True)
    devices = query.all()
    if available_only:
        devices = [d for d in devices if not d.is_lending]
    return devices


@router.post("", response_model=DeviceOut, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    no = (payload.no or "").strip()
    device_id_code = (payload.device_id_code or "").strip() or None
    memo = (payload.memo or "").strip() or None

    if not no:
        raise HTTPException(status_code=400, detail="no is required")
    
    exists_no = db.query(Device).filter(Device.no == no).first()
    if exists_no:
        raise HTTPException(status_code=409, detail="no already exists")
    
    if device_id_code is not None:
        exists_code = db.query(Device).filter(Device.device_id_code == device_id_code).first()
        if exists_code:
            raise HTTPException(status_code=409, detail="device_id_code already exists")
        
    device = Device(no=no, device_id_code=device_id_code, memo=memo)
    db.add(device)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Device unique constraint violation")
    device = db.query(Device).options(selectinload(Device.loans)).filter(Device.id == device.id).first()
    return device


@router.get("/{device_id}/history", response_model=list[LoanOut])
def device_history(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    loans = (
        db.query(Loan)
        .options(selectinload(Loan.device).selectinload(Device.loans))
        .filter(Loan.device_id == device_id)
        .order_by(Loan.lent_at.desc())
        .all()
    )
    return loans


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).options(selectinload(Device.loans)).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.is_lending:
        raise HTTPException(status_code=409, detail="Cannot delete a device currently on loan")
    if not device.is_active:
        raise HTTPException(status_code=409, detail="Device is already deleted")
    device.is_active = False
    device.deleted_at = datetime.now()
    db.commit()


@router.patch("/{device_id}/status", response_model=DeviceOut)
def update_device_status(device_id: int, payload: DeviceStatusUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).options(selectinload(Device.loans)).filter(Device.id == device_id, Device.is_active == True).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if payload.status in ("broken", "retired") and device.is_lending:
        raise HTTPException(status_code=409, detail="貸出中の端末はステータス変更できません")
    prev_status = device.status
    device.status = payload.status
    if payload.status == "broken":
        device.recovered_at = None
    elif payload.status == "retired" and prev_status != "retired":
        device.retired_at = datetime.now()
    elif payload.status == "active" and prev_status in ("broken", "retired"):
        device.recovered_at = datetime.now()
    db.commit()
    device = db.query(Device).options(selectinload(Device.loans)).filter(Device.id == device_id).first()
    return device
