"""Explicit, tenant-owned Project cover override. Additive table, no existing columns changed."""
from sqlalchemy import Column, ForeignKey, Integer, String
from app.db.database import Base


class ProjectCoverV7144(Base):
    __tablename__ = 'project_covers_v7144'
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), primary_key=True)
    cover_key = Column(String(32), nullable=False)
