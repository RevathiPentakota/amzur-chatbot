from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserInfo(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    message: str
    user: UserInfo
