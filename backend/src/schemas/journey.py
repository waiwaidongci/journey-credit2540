from pydantic import BaseModel,Field
class JourneyOutput(BaseModel):
    id:int
    code:str
    batch_id:int
    path:list[str]
    converted:bool
    note:str
    revision:int
class JourneyAnnotation(BaseModel):
    note:str=Field(min_length=8,max_length=1500)
class ImportRecord(BaseModel):
    code:str=Field(min_length=1,max_length=64)
    revision:int=Field(ge=1)
    batch_id:int|None=None
    path:list[str]|None=None
    converted:bool|None=None
    note:str|None=Field(default=None,max_length=1500)
    withdraw:bool=False
class ImportInput(BaseModel):
    source:str=Field(min_length=2,max_length=200)
    records:list[ImportRecord]=Field(min_length=1,max_length=2000)
class ImportRecordReport(BaseModel):
    code:str
    revision:int
    accepted:bool
    outcome:str
    detail:str
class ImportReport(BaseModel):
    applied:bool
    source:str
    summary:dict[str,int]
    records:list[ImportRecordReport]
