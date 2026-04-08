from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.db import get_db
from app.models.user import User
from app.services.logging_service import system_log_service


router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        system_log_service.log_to_db("warning", "auth", f"Login failed for {username}", db=db)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "用户名或密码错误"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    request.session["user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    system_log_service.log_to_db("info", "auth", f"User {username} logged in", db=db)
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        user = db.get(User, user_id)
        username = user.username if user else f"id={user_id}"
        system_log_service.log_to_db("info", "auth", f"User {username} logged out", db=db)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
