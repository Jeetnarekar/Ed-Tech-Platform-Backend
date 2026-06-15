from typing import Any, Generic, Sequence, Type, TypeVar
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Generic repository class providing base CRUD methods utilizing SQLAlchemy 2.0.
    """
    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        """Retrieves a single record by its primary key ID."""
        statement = select(self.model).where(self.model.id == id, self.model.is_active == True)
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> Sequence[ModelType]:
        """Retrieves a list of records with offset pagination."""
        statement = (
            select(self.model)
            .where(self.model.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(statement)
        return result.scalars().all()

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        """Creates a new database record from a Pydantic schema."""
        obj_in_data = obj_in.model_dump()
        db_obj = self.model(**obj_in_data)  # type: ignore
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """Updates an existing database record."""
        obj_data = db_obj.__dict__
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
            
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
                
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        """Soft-deletes a record by setting is_active to False."""
        db_obj = await self.get(db, id)
        if db_obj:
            db_obj.is_active = False
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
        return db_obj

    async def hard_delete(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        """Hard-deletes a record from the database entirely."""
        db_obj = await self.get(db, id)
        if db_obj:
            await db.delete(db_obj)
            await db.commit()
        return db_obj
