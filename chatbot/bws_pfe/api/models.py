from typing import Any, Optional, List
from pydantic import BaseModel, Field

AVAILABLE_MODULES = [
    'eau',
    'énergie électrique',
    'gaz',
    'carburant',
    'équipements/capteurs',
    'alertes',
    'dashboard',
    'rapports',
]


class EmployeeCreate(BaseModel):
    user_id        : str
    name           : str
    allowed_modules: List[str] = []
    is_admin       : bool      = False


class EmployeeUpdate(BaseModel):
    name           : Optional[str]       = None
    allowed_modules: Optional[List[str]] = None
    is_admin       : Optional[bool]      = None


class EmployeeOut(BaseModel):
    id             : int
    user_id        : str
    name           : str
    allowed_modules: List[str]
    is_admin       : bool
    created_at     : str
    updated_at     : str


class ChatRequest(BaseModel):
    question        : str                  = Field(..., min_length=1, max_length=4000)
    sessionId       : Optional[str]        = Field(None, max_length=128)
    threadId        : Optional[str]        = Field(None, max_length=128)
    userId          : Optional[str]        = Field('default_user', max_length=128)
    allowed_modules : Optional[List[str]]  = None
    lang            : Optional[str]        = Field('fr', pattern=r'^(fr|en|ar)$')


class QuickReply(BaseModel):
    label: str
    value: str


class ChatResponse(BaseModel):
    answer        : str
    quick_replies : Optional[List[QuickReply]] = None
    backend       : str
    level         : str
    duration      : float
    thread_id     : str
    session_id    : Optional[str] = None
    message_id    : Optional[int] = None
    confidence    : Optional[str] = None


class FeedbackRequest(BaseModel):
    message_id: int
    thread_id : str
    vote      : str
    comment   : Optional[str] = None
    user_id   : Optional[str] = 'default_user'


class ThreadInfo(BaseModel):
    thread_id    : str
    title        : str
    message_count: int
    created_at   : str
    updated_at   : str
    preview      : Optional[str]  = None
    is_favorite  : Optional[bool] = False


class MessageOut(BaseModel):
    id        : Optional[int] = None
    role      : str
    content   : str
    level     : Optional[str] = None
    backend   : Optional[str] = None
    created_at: str
    feedback  : Optional[str] = None
    chart_data: Optional[Any] = None
