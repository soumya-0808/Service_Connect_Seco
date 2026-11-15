"""ServiceConnect API. Run with: uvicorn app.main:app --reload"""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
import secrets

import bcrypt
import jwt
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Boolean, Date, DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, Numeric, String, Text, Time, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./serviceconnect.db"
    jwt_secret: str = "development-only-change-this-secret-please"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5500,http://127.0.0.1:5500"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    admin_email: str = "admin@serviceconnect.local"
    admin_password: str = "change-this-before-deploying"

settings = Settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, poolclass=StaticPool if settings.database_url.endswith(":memory:") else None)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Role(str, Enum): customer="customer"; provider="provider"; admin="admin"
class BookingStatus(str, Enum): pending="Pending"; accepted="Accepted"; rejected="Rejected"; in_progress="In Progress"; completed="Completed"; cancelled="Cancelled"

class User(Base):
    __tablename__="users"
    user_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    full_name: Mapped[str]=mapped_column(String(120), nullable=False)
    email: Mapped[str]=mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str]=mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]]=mapped_column(String(30))
    role: Mapped[Role]=mapped_column(SqlEnum(Role), default=Role.customer, nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
    profile: Mapped[Optional["ProviderProfile"]]=relationship(back_populates="user", cascade="all, delete-orphan")

class ProviderProfile(Base):
    __tablename__="provider_profiles"
    provider_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)
    business_name: Mapped[str]=mapped_column(String(160), nullable=False)
    description: Mapped[str]=mapped_column(Text, default="")
    city: Mapped[str]=mapped_column(String(100), default="")
    experience_years: Mapped[int]=mapped_column(Integer, default=0)
    is_approved: Mapped[bool]=mapped_column(Boolean, default=False)
    user: Mapped[User]=relationship(back_populates="profile")
    services: Mapped[list["Service"]]=relationship(back_populates="provider")

class Category(Base):
    __tablename__="categories"
    category_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    category_name: Mapped[str]=mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str]=mapped_column(Text, default="")
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)

class Service(Base):
    __tablename__="services"
    service_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int]=mapped_column(ForeignKey("provider_profiles.provider_id", ondelete="RESTRICT"), index=True)
    category_id: Mapped[int]=mapped_column(ForeignKey("categories.category_id", ondelete="RESTRICT"), index=True)
    service_name: Mapped[str]=mapped_column(String(140), nullable=False)
    description: Mapped[str]=mapped_column(Text, default="")
    price: Mapped[Decimal]=mapped_column(Numeric(10,2), nullable=False)
    estimated_duration: Mapped[int]=mapped_column(Integer, default=60)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)
    provider: Mapped[ProviderProfile]=relationship(back_populates="services")
    category: Mapped[Category]=relationship()

class Booking(Base):
    __tablename__="bookings"
    __table_args__=(Index("ix_booking_provider_slot", "provider_id", "booking_date", "start_time", "end_time"),)
    booking_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), index=True)
    provider_id: Mapped[int]=mapped_column(ForeignKey("provider_profiles.provider_id", ondelete="RESTRICT"), index=True)
    service_id: Mapped[int]=mapped_column(ForeignKey("services.service_id", ondelete="RESTRICT"), index=True)
    service_name: Mapped[str]=mapped_column(String(140), default="")
    booking_date: Mapped[date]=mapped_column(Date, nullable=False)
    start_time: Mapped[time]=mapped_column(Time, nullable=False)
    end_time: Mapped[time]=mapped_column(Time, nullable=False)
    address: Mapped[str]=mapped_column(Text, nullable=False)
    problem_description: Mapped[str]=mapped_column(Text, default="")
    total_amount: Mapped[Decimal]=mapped_column(Numeric(10,2), nullable=False)
    status: Mapped[BookingStatus]=mapped_column(SqlEnum(BookingStatus), default=BookingStatus.pending, index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class Availability(Base):
    __tablename__="provider_availability"
    availability_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int]=mapped_column(ForeignKey("provider_profiles.provider_id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int]=mapped_column(Integer, nullable=False)
    start_time: Mapped[time]=mapped_column(Time, nullable=False)
    end_time: Mapped[time]=mapped_column(Time, nullable=False)
    is_available: Mapped[bool]=mapped_column(Boolean, default=True)

class Review(Base):
    __tablename__="reviews"
    __table_args__=(UniqueConstraint("booking_id", name="uq_review_booking"),)
    review_id: Mapped[int]=mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int]=mapped_column(ForeignKey("bookings.booking_id", ondelete="RESTRICT"), unique=True)
    customer_id: Mapped[int]=mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), index=True)
    provider_id: Mapped[int]=mapped_column(ForeignKey("provider_profiles.provider_id", ondelete="RESTRICT"), index=True)
    rating: Mapped[int]=mapped_column(Integer, nullable=False)
    comment: Mapped[str]=mapped_column(Text, default="")
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class RegisterIn(BaseModel):
    full_name: str=Field(min_length=2,max_length=120); email: EmailStr; password: str=Field(min_length=8,max_length=128); phone: Optional[str]=None
    role: Role=Role.customer; business_name: Optional[str]=None; city: Optional[str]=None; description: Optional[str]=None
class LoginIn(BaseModel): email: EmailStr; password: str
class UserUpdate(BaseModel): full_name: Optional[str]=Field(default=None,min_length=2,max_length=120); phone: Optional[str]=None
class ProviderUpdate(BaseModel): business_name: str=Field(min_length=2,max_length=160); description: str=""; city: str=""; experience_years: int=Field(default=0,ge=0,le=80)
class CategoryIn(BaseModel): category_name: str=Field(min_length=2,max_length=100); description: str=""; is_active: bool=True
class ServiceIn(BaseModel): category_id: int; service_name: str=Field(min_length=2,max_length=140); description: str=""; price: Decimal=Field(gt=0); estimated_duration: int=Field(default=60,ge=15,le=720); is_active: bool=True
class BookingIn(BaseModel): service_id: int; booking_date: date; start_time: time; address: str=Field(min_length=5,max_length=1000); problem_description: str=""
class StatusIn(BaseModel): status: BookingStatus
class AvailabilityIn(BaseModel): day_of_week: int=Field(ge=0,le=6); start_time: time; end_time: time; is_available: bool=True
class ReviewIn(BaseModel): booking_id: int; rating: int=Field(ge=1,le=5); comment: str=Field(default="",max_length=2000)

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
bearer=HTTPBearer(auto_error=False)
def user_view(u: User): return {"user_id":u.user_id,"full_name":u.full_name,"email":u.email,"phone":u.phone,"role":u.role.value,"is_active":u.is_active}
def current_user(response: Response, cred=Depends(bearer), db: Session=Depends(get_db), cookie: Optional[str]=Cookie(None, alias="sc_session")):
    token=cred.credentials if cred else cookie
    if not token: raise HTTPException(401,"Authentication required")
    try: uid=int(jwt.decode(token,settings.jwt_secret,algorithms=["HS256"]).get("sub"))
    except Exception: raise HTTPException(401,"Invalid or expired session")
    u=db.get(User,uid)
    if not u or not u.is_active: raise HTTPException(401,"Account is inactive")
    return u
def role_required(*roles):
    def dep(u: User=Depends(current_user)):
        if u.role not in roles: raise HTTPException(403,"You do not have permission for this action")
        return u
    return dep
def provider_for(db,u):
    p=db.scalar(select(ProviderProfile).where(ProviderProfile.user_id==u.user_id))
    if not p: raise HTTPException(404,"Provider profile not found")
    return p
def provider_view(p,db):
    u=db.get(User,p.user_id)
    avg=db.scalar(select(func.avg(Review.rating)).where(Review.provider_id==p.provider_id))
    return {"provider_id":p.provider_id,"user_id":p.user_id,"business_name":p.business_name,"description":p.description,"city":p.city,"experience_years":p.experience_years,"is_approved":p.is_approved,"is_active":u.is_active,"full_name":u.full_name,"rating":round(float(avg or 0),1)}
def service_view(s,db):
    p=db.get(ProviderProfile,s.provider_id); c=db.get(Category,s.category_id)
    return {"service_id":s.service_id,"provider_id":s.provider_id,"category_id":s.category_id,"category_name":c.category_name,"service_name":s.service_name,"description":s.description,"price":float(s.price),"estimated_duration":s.estimated_duration,"is_active":s.is_active,"provider":provider_view(p,db)}
def booking_view(b,db):
    customer=db.get(User,b.customer_id); p=db.get(ProviderProfile,b.provider_id)
    return {"booking_id":b.booking_id,"customer_id":b.customer_id,"customer_name":customer.full_name,"provider_id":b.provider_id,"provider_name":p.business_name,"service_id":b.service_id,"service_name":b.service_name,"booking_date":b.booking_date.isoformat(),"start_time":b.start_time.strftime("%H:%M"),"end_time":b.end_time.strftime("%H:%M"),"address":b.address,"problem_description":b.problem_description,"total_amount":float(b.total_amount),"status":b.status.value,"created_at":b.created_at.isoformat()}

app=FastAPI(title="ServiceConnect API",version="1.0.0",description="Local service booking platform API")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name,desc in [("Electrical","Repairs and installations"),("Plumbing","Pipes, leaks and fixtures"),("Air Conditioning","AC service and repairs"),("Home Cleaning","Home and deep cleaning"),("Appliance Repair","Home appliance repairs"),("Painting","Interior and exterior painting")]:
            if not db.scalar(select(Category).where(Category.category_name==name)): db.add(Category(category_name=name,description=desc))
        if not db.scalar(select(User).where(User.email==settings.admin_email.lower())):
            db.add(User(full_name="ServiceConnect Admin",email=settings.admin_email.lower(),password_hash=bcrypt.hashpw(settings.admin_password.encode(),bcrypt.gensalt()).decode(),role=Role.admin))
        db.commit()

@app.get("/api/health")
def health(): return {"status":"ok","service":"ServiceConnect"}
@app.post("/api/auth/register",status_code=201)
def register(data:RegisterIn,db:Session=Depends(get_db)):
    if data.role==Role.admin: raise HTTPException(403,"Admin accounts cannot be self-registered")
    if db.scalar(select(User).where(User.email==data.email.lower())): raise HTTPException(409,"Email already registered")
    u=User(full_name=data.full_name.strip(),email=data.email.lower(),password_hash=bcrypt.hashpw(data.password.encode(),bcrypt.gensalt()).decode(),phone=data.phone,role=data.role)
    db.add(u); db.flush()
    if data.role==Role.provider:
        db.add(ProviderProfile(user_id=u.user_id,business_name=(data.business_name or data.full_name).strip(),city=data.city or "",description=data.description or ""))
    db.commit(); return {"user":user_view(u),"message":"Registration successful"}
@app.post("/api/auth/login")
def login(data:LoginIn,response:Response,db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==data.email.lower()))
    if not u or not bcrypt.checkpw(data.password.encode(),u.password_hash.encode()) or not u.is_active: raise HTTPException(401,"Invalid email or password")
    token=jwt.encode({"sub":str(u.user_id),"exp":datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes)},settings.jwt_secret,algorithm="HS256")
    response.set_cookie("sc_session",token,httponly=True,secure=settings.cookie_secure,samesite=settings.cookie_samesite.lower(),max_age=settings.jwt_expire_minutes*60,path="/")
    return {"user":user_view(u),"access_token":token,"token_type":"bearer"}
@app.post("/api/auth/logout")
def logout(response:Response): response.delete_cookie("sc_session",path="/"); return {"message":"Signed out"}
@app.get("/api/auth/me")
def me(u:User=Depends(current_user),db:Session=Depends(get_db)):
    result=user_view(u)
    if u.role==Role.provider:
        p=provider_for(db,u); result["provider"]=provider_view(p,db)
    return result
@app.get("/api/users/me")
def get_me(u:User=Depends(current_user)): return user_view(u)
@app.put("/api/users/me")
def update_me(data:UserUpdate,u:User=Depends(current_user),db:Session=Depends(get_db)):
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(u,k,v)
    db.commit(); return user_view(u)

@app.get("/api/categories/")
def categories(db:Session=Depends(get_db),admin:bool=False): return [{"category_id":c.category_id,"category_name":c.category_name,"description":c.description,"is_active":c.is_active} for c in db.scalars(select(Category).where(Category.is_active==True).order_by(Category.category_name))]
@app.post("/api/categories/",status_code=201)
def create_category(data:CategoryIn,db:Session=Depends(get_db),u:User=Depends(role_required(Role.admin))):
    c=Category(**data.model_dump()); db.add(c)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Category already exists")
    return {"category_id":c.category_id,"category_name":c.category_name,"description":c.description,"is_active":c.is_active}
@app.put("/api/categories/{id}")
def update_category(id:int,data:CategoryIn,db:Session=Depends(get_db),u:User=Depends(role_required(Role.admin))):
    c=db.get(Category,id)
    if not c: raise HTTPException(404,"Category not found")
    for k,v in data.model_dump().items(): setattr(c,k,v)
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Category already exists")
    return {"category_id":c.category_id,"category_name":c.category_name,"description":c.description,"is_active":c.is_active}
@app.delete("/api/categories/{id}",status_code=204)
def delete_category(id:int,db:Session=Depends(get_db),u:User=Depends(role_required(Role.admin))):
    c=db.get(Category,id)
    if not c: raise HTTPException(404,"Category not found")
    c.is_active=False; db.commit()

@app.get("/api/services/")
def list_services(search:Optional[str]=None,category_id:Optional[int]=None,city:Optional[str]=None,skip:int=Query(0,ge=0),limit:int=Query(24,ge=1,le=100),db:Session=Depends(get_db)):
    q=select(Service).join(ProviderProfile).join(User).where(Service.is_active==True,ProviderProfile.is_approved==True,User.is_active==True,Category.is_active==True).join(Category)
    if search: q=q.where(Service.service_name.ilike(f"%{search}%")|Service.description.ilike(f"%{search}%")|ProviderProfile.business_name.ilike(f"%{search}%"))
    if category_id: q=q.where(Service.category_id==category_id)
    if city: q=q.where(ProviderProfile.city.ilike(f"%{city}%"))
    rows=db.scalars(q.order_by(Service.service_id.desc()).offset(skip).limit(limit)).all()
    return {"items":[service_view(s,db) for s in rows],"skip":skip,"limit":limit}
@app.get("/api/services/{id}")
def get_service(id:int,db:Session=Depends(get_db)):
    s=db.get(Service,id)
    if not s or not s.is_active: raise HTTPException(404,"Service not found")
    p=db.get(ProviderProfile,s.provider_id); u=db.get(User,p.user_id)
    if not p.is_approved or not u.is_active: raise HTTPException(404,"Service not found")
    return service_view(s,db)
@app.post("/api/services/",status_code=201)
def create_service(data:ServiceIn,db:Session=Depends(get_db),u:User=Depends(role_required(Role.provider))):
    p=provider_for(db,u)
    if not p.is_approved: raise HTTPException(403,"Provider approval is required before adding services")
    if not db.get(Category,data.category_id): raise HTTPException(404,"Category not found")
    s=Service(provider_id=p.provider_id,**data.model_dump()); db.add(s); db.commit(); return service_view(s,db)
@app.put("/api/services/{id}")
def update_service(id:int,data:ServiceIn,db:Session=Depends(get_db),u:User=Depends(role_required(Role.provider))):
    s=db.get(Service,id); p=provider_for(db,u)
    if not s or s.provider_id!=p.provider_id: raise HTTPException(404,"Service not found")
    for k,v in data.model_dump().items(): setattr(s,k,v)
    db.commit(); return service_view(s,db)
@app.delete("/api/services/{id}",status_code=204)
def deactivate_service(id:int,db:Session=Depends(get_db),u:User=Depends(role_required(Role.provider))):
    s=db.get(Service,id); p=provider_for(db,u)
    if not s or s.provider_id!=p.provider_id: raise HTTPException(404,"Service not found")
    s.is_active=False; db.commit()

@app.get("/api/providers/")
def providers(city:Optional[str]=None,db:Session=Depends(get_db)):
    q=select(ProviderProfile).join(User).where(ProviderProfile.is_approved==True,User.is_active==True)
    if city:q=q.where(ProviderProfile.city.ilike(f"%{city}%"))
    return [provider_view(p,db) for p in db.scalars(q).all()]
@app.get("/api/providers/availability")
def get_availability(u:User=Depends(role_required(Role.provider)),db:Session=Depends(get_db)):
    p=provider_for(db,u)
    return [{"availability_id":a.availability_id,"day_of_week":a.day_of_week,"start_time":a.start_time.strftime("%H:%M"),"end_time":a.end_time.strftime("%H:%M"),"is_available":a.is_available} for a in db.scalars(select(Availability).where(Availability.provider_id==p.provider_id).order_by(Availability.day_of_week))]
@app.get("/api/providers/{id}")
def get_provider(id:int,db:Session=Depends(get_db)):
    p=db.get(ProviderProfile,id)
    if not p: raise HTTPException(404,"Provider not found")
    return provider_view(p,db)
@app.put("/api/providers/profile")
def update_provider(data:ProviderUpdate,u:User=Depends(role_required(Role.provider)),db:Session=Depends(get_db)):
    p=provider_for(db,u)
    for k,v in data.model_dump().items(): setattr(p,k,v)
    db.commit(); return provider_view(p,db)
@app.put("/api/providers/availability")
def set_availability(items:list[AvailabilityIn],u:User=Depends(role_required(Role.provider)),db:Session=Depends(get_db)):
    p=provider_for(db,u)
    for i in items:
        if i.end_time<=i.start_time: raise HTTPException(422,"Availability end must follow start")
    db.query(Availability).filter(Availability.provider_id==p.provider_id).delete()
    db.add_all([Availability(provider_id=p.provider_id,**i.model_dump()) for i in items]); db.commit(); return {"message":"Availability saved","count":len(items)}

@app.post("/api/bookings/",status_code=201)
def create_booking(data:BookingIn,u:User=Depends(role_required(Role.customer)),db:Session=Depends(get_db)):
    today=date.today()
    if data.booking_date<today or (data.booking_date==today and data.start_time<=datetime.now().time()): raise HTTPException(422,"Booking must be in the future")
    s=db.get(Service,data.service_id)
    if not s or not s.is_active: raise HTTPException(404,"Service is unavailable")
    p=db.get(ProviderProfile,s.provider_id); provider_user=db.get(User,p.user_id)
    if not p.is_approved or not provider_user.is_active: raise HTTPException(422,"Provider is not available")
    duration=s.estimated_duration; start=data.start_time
    start_dt=datetime.combine(data.booking_date,start); end_dt=start_dt+timedelta(minutes=duration)
    if end_dt.date()!=data.booking_date: raise HTTPException(422,"Booking must fit within the selected day")
    end=end_dt.time()
    avail=db.scalars(select(Availability).where(Availability.provider_id==p.provider_id,Availability.day_of_week==data.booking_date.weekday(),Availability.is_available==True)).all()
    if avail and not any(a.start_time<=start and a.end_time>=end for a in avail): raise HTTPException(422,"Selected time is outside provider availability")
    # Transactional overlap check; row lock serializes writes per provider on MySQL.
    db.execute(select(ProviderProfile).where(ProviderProfile.provider_id==p.provider_id).with_for_update()).first()
    collision=db.scalar(select(Booking).where(Booking.provider_id==p.provider_id,Booking.booking_date==data.booking_date,Booking.status.in_([BookingStatus.pending,BookingStatus.accepted,BookingStatus.in_progress]),Booking.start_time<end,Booking.end_time>start))
    if collision: raise HTTPException(409,"That time overlaps an existing booking")
    b=Booking(customer_id=u.user_id,provider_id=p.provider_id,service_id=s.service_id,service_name=s.service_name,booking_date=data.booking_date,start_time=start,end_time=end,address=data.address,problem_description=data.problem_description,total_amount=s.price,status=BookingStatus.pending)
    db.add(b); db.commit(); db.refresh(b); return booking_view(b,db)
@app.get("/api/bookings/my")
def my_bookings(status_filter:Optional[BookingStatus]=Query(None,alias="status"),skip:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),u:User=Depends(role_required(Role.customer)),db:Session=Depends(get_db)):
    q=select(Booking).where(Booking.customer_id==u.user_id)
    if status_filter:q=q.where(Booking.status==status_filter)
    return [booking_view(b,db) for b in db.scalars(q.order_by(Booking.created_at.desc()).offset(skip).limit(limit))]
@app.get("/api/provider/bookings")
def provider_bookings(status_filter:Optional[BookingStatus]=Query(None,alias="status"),u:User=Depends(role_required(Role.provider)),db:Session=Depends(get_db)):
    p=provider_for(db,u); q=select(Booking).where(Booking.provider_id==p.provider_id)
    if status_filter:q=q.where(Booking.status==status_filter)
    return [booking_view(b,db) for b in db.scalars(q.order_by(Booking.booking_date.desc(),Booking.start_time))]
@app.get("/api/bookings/{id}")
def get_booking(id:int,u:User=Depends(current_user),db:Session=Depends(get_db)):
    b=db.get(Booking,id)
    if not b: raise HTTPException(404,"Booking not found")
    if u.role==Role.customer and b.customer_id!=u.user_id: raise HTTPException(403,"Booking belongs to another customer")
    if u.role==Role.provider and provider_for(db,u).provider_id!=b.provider_id: raise HTTPException(403,"Booking belongs to another provider")
    return booking_view(b,db)
@app.patch("/api/bookings/{id}/status")
def update_booking_status(id:int,data:StatusIn,u:User=Depends(role_required(Role.provider)),db:Session=Depends(get_db)):
    b=db.get(Booking,id); p=provider_for(db,u)
    if not b or b.provider_id!=p.provider_id: raise HTTPException(404,"Booking not found")
    allowed={BookingStatus.pending:{BookingStatus.accepted,BookingStatus.rejected},BookingStatus.accepted:{BookingStatus.in_progress},BookingStatus.in_progress:{BookingStatus.completed}}
    if data.status not in allowed.get(b.status,set()): raise HTTPException(409,f"Cannot change {b.status.value} to {data.status.value}")
    if data.status==BookingStatus.accepted:
        conflict=db.scalar(select(Booking).where(Booking.provider_id==p.provider_id,Booking.booking_date==b.booking_date,Booking.booking_id!=b.booking_id,Booking.status.in_([BookingStatus.accepted,BookingStatus.in_progress]),Booking.start_time<b.end_time,Booking.end_time>b.start_time))
        if conflict: raise HTTPException(409,"Cannot accept overlapping booking")
    b.status=data.status; db.commit(); return booking_view(b,db)
@app.patch("/api/bookings/{id}/cancel")
def cancel_booking(id:int,u:User=Depends(role_required(Role.customer)),db:Session=Depends(get_db)):
    b=db.get(Booking,id)
    if not b or b.customer_id!=u.user_id: raise HTTPException(404,"Booking not found")
    if b.status not in {BookingStatus.pending,BookingStatus.accepted}: raise HTTPException(409,"This booking can no longer be cancelled")
    b.status=BookingStatus.cancelled; db.commit(); return booking_view(b,db)

@app.post("/api/reviews/",status_code=201)
def add_review(data:ReviewIn,u:User=Depends(role_required(Role.customer)),db:Session=Depends(get_db)):
    b=db.get(Booking,data.booking_id)
    if not b or b.customer_id!=u.user_id: raise HTTPException(404,"Booking not found")
    if b.status!=BookingStatus.completed: raise HTTPException(409,"Only completed bookings can be reviewed")
    if db.scalar(select(Review).where(Review.booking_id==b.booking_id)): raise HTTPException(409,"This booking already has a review")
    r=Review(booking_id=b.booking_id,customer_id=u.user_id,provider_id=b.provider_id,rating=data.rating,comment=data.comment); db.add(r); db.commit()
    return {"review_id":r.review_id,"booking_id":r.booking_id,"rating":r.rating,"comment":r.comment}
@app.get("/api/providers/{id}/reviews")
def provider_reviews(id:int,db:Session=Depends(get_db)):
    return [{"review_id":r.review_id,"booking_id":r.booking_id,"customer_name":db.get(User,r.customer_id).full_name,"rating":r.rating,"comment":r.comment,"created_at":r.created_at.isoformat()} for r in db.scalars(select(Review).where(Review.provider_id==id).order_by(Review.created_at.desc()))]

@app.get("/api/admin/dashboard")
def admin_dashboard(u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    count=lambda stmt: db.scalar(stmt) or 0
    by_status={s.value:count(select(func.count()).select_from(Booking).where(Booking.status==s)) for s in BookingStatus}
    return {"customers":count(select(func.count()).select_from(User).where(User.role==Role.customer)),"providers":count(select(func.count()).select_from(ProviderProfile)),"pending_providers":count(select(func.count()).select_from(ProviderProfile).where(ProviderProfile.is_approved==False)),"bookings":count(select(func.count()).select_from(Booking)),"booking_status":by_status,"categories":count(select(func.count()).select_from(Category))}
@app.get("/api/admin/users")
def admin_users(skip:int=0,limit:int=Query(100,ge=1,le=500),u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    return [user_view(x) for x in db.scalars(select(User).order_by(User.created_at.desc()).offset(skip).limit(limit))]
@app.patch("/api/admin/users/{id}/active")
def admin_user_active(id:int,active:bool,db:Session=Depends(get_db),u:User=Depends(role_required(Role.admin))):
    target=db.get(User,id)
    if not target: raise HTTPException(404,"User not found")
    if target.user_id==u.user_id and not active: raise HTTPException(422,"You cannot deactivate your own account")
    target.is_active=active; db.commit(); return user_view(target)
@app.get("/api/admin/providers")
def admin_providers(skip:int=0,limit:int=Query(100,ge=1,le=500),u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    return [provider_view(p,db) for p in db.scalars(select(ProviderProfile).order_by(ProviderProfile.provider_id.desc()).offset(skip).limit(limit))]
@app.patch("/api/admin/providers/{id}/approve")
def approve_provider(id:int,approved:bool=True,u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    p=db.get(ProviderProfile,id)
    if not p: raise HTTPException(404,"Provider not found")
    p.is_approved=approved; db.commit(); return provider_view(p,db)
@app.patch("/api/admin/providers/{id}/active")
def active_provider(id:int,active:bool,u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    p=db.get(ProviderProfile,id)
    if not p: raise HTTPException(404,"Provider not found")
    db.get(User,p.user_id).is_active=active; db.commit(); return provider_view(p,db)
@app.get("/api/admin/bookings")
def admin_bookings(status_filter:Optional[BookingStatus]=Query(None,alias="status"),skip:int=0,limit:int=Query(200,ge=1,le=500),u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    q=select(Booking)
    if status_filter:q=q.where(Booking.status==status_filter)
    return [booking_view(b,db) for b in db.scalars(q.order_by(Booking.created_at.desc()).offset(skip).limit(limit))]
@app.get("/api/admin/reviews")
def admin_reviews(u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    return [{"review_id":r.review_id,"booking_id":r.booking_id,"customer_name":db.get(User,r.customer_id).full_name,"provider_name":db.get(ProviderProfile,r.provider_id).business_name,"rating":r.rating,"comment":r.comment,"created_at":r.created_at.isoformat()} for r in db.scalars(select(Review).order_by(Review.created_at.desc()))]
@app.delete("/api/admin/reviews/{id}",status_code=204)
def delete_review(id:int,u:User=Depends(role_required(Role.admin)),db:Session=Depends(get_db)):
    r=db.get(Review,id)
    if not r: raise HTTPException(404,"Review not found")
    db.delete(r); db.commit()
