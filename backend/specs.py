from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from models import JobSpec as SpecModel
from db import db
from output import output

# Pydantic models for API requests
class SpecCreateRequest(BaseModel):
    name: str = Field(..., description="Spec name")
    description: Optional[str] = Field(None, description="Spec description")
    command: str = Field(..., description="Command to execute")

class SpecUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Spec name")
    description: Optional[str] = Field(None, description="Spec description")
    command: Optional[str] = Field(None, description="Command to execute")

class Specs:
    """Core specification management class with proper OOP design."""
    
    def __init__(self):
        """Initialize Specs singleton."""
        pass
    
    def create(
        self,
        name: str,
        command: str,
        description: Optional[str] = None,
        created_by: str = "system"
    ) -> SpecModel:
        """Create a new specification record in the database."""
        with db.get_session() as session:
            # Check if name already exists
            existing = session.query(SpecModel).filter(SpecModel.name == name).first()
            if existing:
                raise ValueError(f"Specification with name '{name}' already exists")
            
            # Create spec record
            spec = SpecModel(
                name=name,
                description=description,
                command=command,
                created_by=created_by,
                is_active=True
            )
            
            session.add(spec)
            session.commit()
            session.refresh(spec)
            
            output.info(f"Created specification '{name}' with command: {command}")
            return spec
    
    def get_by_id(self, spec_id: int) -> Optional[SpecModel]:
        """Get specification by database ID."""
        with db.get_session() as session:
            return session.query(SpecModel).filter(
                SpecModel.id == spec_id,
                SpecModel.is_active == True
            ).first()
    
    def get_by_name(self, name: str) -> Optional[SpecModel]:
        """Get specification by name."""
        with db.get_session() as session:
            return session.query(SpecModel).filter(
                SpecModel.name == name,
                SpecModel.is_active == True
            ).first()
    
    def list_with_count(
        self,
        limit: int = 20,
        offset: int = 0,
        name_filter: Optional[str] = None
    ) -> tuple[List[SpecModel], int]:
        """Get all active specifications with filtering and total count for pagination."""
        with db.get_session() as session:
            query = session.query(SpecModel).filter(SpecModel.is_active == True)
            
            if name_filter:
                query = query.filter(SpecModel.name.ilike(f"%{name_filter}%"))
            
            # Get total count
            total = query.count()
            
            # Get paginated results
            specs = query.offset(offset).limit(limit).all()
            
            return specs, total
    
    def update(
        self,
        spec_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        command: Optional[str] = None
    ) -> Optional[SpecModel]:
        """Update specification fields."""
        with db.get_session() as session:
            spec = session.query(SpecModel).filter(
                SpecModel.id == spec_id,
                SpecModel.is_active == True
            ).first()
            
            if not spec:
                return None
            
            # Check name conflicts if updating name
            if name is not None and name != spec.name:
                existing = session.query(SpecModel).filter(SpecModel.name == name).first()
                if existing:
                    raise ValueError(f"Specification with name '{name}' already exists")
                spec.name = name
            
            if description is not None:
                spec.description = description
                
            if command is not None:
                spec.command = command
            
            # Update timestamp handled by SQLAlchemy onupdate
            session.commit()
            session.refresh(spec)
            
            output.info(f"Updated specification {spec_id}")
            return spec
    
    def delete(self, spec_id: int) -> bool:
        """Delete a specification (soft delete)."""
        with db.get_session() as session:
            spec = session.query(SpecModel).filter(
                SpecModel.id == spec_id,
                SpecModel.is_active == True
            ).first()
            
            if not spec:
                return False
            
            # Soft delete by setting is_active to False
            spec.is_active = False
            session.commit()
            
            output.info(f"Deleted specification {spec_id} ('{spec.name}')")
            return True

# Singleton instance
specs = Specs()