from fastapi import APIRouter
from typing import List
from pydantic import BaseModel
from services.dataworks_client import list_projects

router = APIRouter()

class Project(BaseModel):
    id: str
    name: str
    project_id: int

@router.get("/list", response_model=List[Project])
def list_projects_api():
    projects = list_projects()
    return [Project(**p) for p in projects]