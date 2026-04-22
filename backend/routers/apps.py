from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import App, Ticket
from ..schemas import AppOut, AppCreate, AppUpdate
from .admin import require_auth

public_router = APIRouter(prefix="/api/apps", tags=["apps"])
admin_router = APIRouter(prefix="/api/admin/apps", tags=["apps-admin"])


@public_router.get("", response_model=list[AppOut])
def list_apps(db: Session = Depends(get_db)):
    return db.query(App).order_by(App.display_order, App.label).all()


@admin_router.post("", response_model=AppOut)
def create_app(
    app_in: AppCreate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    if db.query(App).filter(App.slug == app_in.slug).first():
        raise HTTPException(status_code=409, detail="Slug already exists")
    if db.query(App).filter(App.prefix == app_in.prefix).first():
        raise HTTPException(status_code=409, detail="Prefix already exists")
    app_row = App(**app_in.model_dump())
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    return app_row


@admin_router.patch("/{slug}", response_model=AppOut)
def update_app(
    slug: str,
    update: AppUpdate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    app_row = db.query(App).filter(App.slug == slug).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="App not found")
    data = update.model_dump(exclude_none=True)
    if "prefix" in data and data["prefix"] != app_row.prefix:
        clash = db.query(App).filter(App.prefix == data["prefix"], App.slug != slug).first()
        if clash:
            raise HTTPException(status_code=409, detail="Prefix already in use")
    for field, value in data.items():
        setattr(app_row, field, value)
    db.commit()
    db.refresh(app_row)
    return app_row


@admin_router.delete("/{slug}")
def delete_app(
    slug: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_auth),
):
    app_row = db.query(App).filter(App.slug == slug).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="App not found")
    ticket_count = db.query(Ticket).filter(Ticket.app == slug).count()
    if ticket_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {ticket_count} ticket(s) reference this app. Reassign or delete them first.",
        )
    db.delete(app_row)
    db.commit()
    return {"message": "App deleted"}
