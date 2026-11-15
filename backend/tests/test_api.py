from fastapi.testclient import TestClient
from app.main import app
from datetime import date, timedelta

client = TestClient(app)

def account(role="customer"):
    import uuid
    email=f"serviceconnect-{uuid.uuid4().hex}@example.com"
    res=client.post("/api/auth/register",json={"full_name":"Test Person","email":email,"password":"TestPass123!","role":role,"business_name":"Test Repairs","city":"Pune"})
    assert res.status_code==201, res.text
    login=client.post("/api/auth/login",json={"email":email,"password":"TestPass123!"})
    assert login.status_code==200
    return email,login.json()["access_token"]

def headers(token): return {"Authorization":f"Bearer {token}"}

def test_health_and_public_categories():
    assert client.get("/api/health").json()["status"]=="ok"
    assert client.get("/api/categories/").status_code==200

def test_registration_login_and_current_user():
    email,token=account()
    me=client.get("/api/auth/me",headers=headers(token))
    assert me.status_code==200 and me.json()["email"]==email and me.json()["role"]=="customer"

def test_admin_authorization_and_provider_approval():
    _,token=account("provider")
    assert client.get("/api/admin/dashboard",headers=headers(token)).status_code==403
    admin=client.post("/api/auth/login",json={"email":"admin@serviceconnect.local","password":"change-this-before-deploying"})
    # A configured deployment may replace the bootstrap credentials.
    if admin.status_code!=200: return
    providers=client.get("/api/admin/providers",headers=headers(admin.json()["access_token"]))
    assert providers.status_code==200
    assert any(not p["is_approved"] for p in providers.json())

def test_unauthorized_endpoints_are_protected():
    client.cookies.clear()
    assert client.get("/api/bookings/my").status_code==401
    assert client.post("/api/categories/",json={"category_name":"Test"}).status_code==401

def test_booking_workflow_and_validation():
    client.cookies.clear()
    admin=client.post("/api/auth/login",json={"email":"admin@serviceconnect.local","password":"change-this-before-deploying"})
    if admin.status_code!=200: return
    admin_token=admin.json()["access_token"]
    _,provider_token=account("provider")
    provider=client.get("/api/auth/me",headers=headers(provider_token)).json()["provider"]
    approved=client.patch(f"/api/admin/providers/{provider['provider_id']}/approve",headers=headers(admin_token))
    assert approved.status_code==200 and approved.json()["is_approved"]

    category=client.get("/api/categories/").json()[0]["category_id"]
    service=client.post("/api/services/",headers=headers(provider_token),json={"category_id":category,"service_name":"Test repair","description":"Workflow test","price":1250,"estimated_duration":60})
    assert service.status_code==201,service.text
    service_id=service.json()["service_id"]
    # An explicitly configured weekly schedule is required for this provider.
    assert client.put("/api/providers/availability",headers=headers(provider_token),json=[{"day_of_week":i,"start_time":"09:00","end_time":"18:00","is_available":True} for i in range(7)]).status_code==200
    assert client.get("/api/providers/availability",headers=headers(provider_token)).status_code==200
    _,customer_token=account()
    day=(date.today()+timedelta(days=7)).isoformat()
    booking_data={"service_id":service_id,"booking_date":day,"start_time":"10:00","address":"42 Example Street, Pune","problem_description":"No power in one room"}
    assert client.post("/api/bookings/",headers=headers(customer_token),json={**booking_data,"booking_date":"2000-01-01"}).status_code==422
    created=client.post("/api/bookings/",headers=headers(customer_token),json=booking_data)
    assert created.status_code==201,created.text
    assert created.json()["total_amount"]==1250 and created.json()["end_time"]=="11:00"
    assert client.post("/api/bookings/",headers=headers(customer_token),json=booking_data).status_code==409
    booking_id=created.json()["booking_id"]
    assert client.patch(f"/api/bookings/{booking_id}/cancel",headers=headers(customer_token)).status_code==200
    assert client.patch(f"/api/bookings/{booking_id}/status",headers=headers(provider_token),json={"status":"Accepted"}).status_code==409

    booking_data["start_time"]="13:00"
    second=client.post("/api/bookings/",headers=headers(customer_token),json=booking_data)
    assert second.status_code==201,second.text
    booking_id=second.json()["booking_id"]
    for next_status in ["Accepted","In Progress","Completed"]:
        changed=client.patch(f"/api/bookings/{booking_id}/status",headers=headers(provider_token),json={"status":next_status})
        assert changed.status_code==200,changed.text
    assert client.post("/api/reviews/",headers=headers(customer_token),json={"booking_id":booking_id,"rating":5,"comment":"Great work"}).status_code==201
    assert client.post("/api/reviews/",headers=headers(customer_token),json={"booking_id":booking_id,"rating":5,"comment":"Duplicate"}).status_code==409
