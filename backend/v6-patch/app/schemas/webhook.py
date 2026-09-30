from pydantic import BaseModel


class IncomingTestMessage(BaseModel):
    phone_number: str
    message: str
    name: str | None = None