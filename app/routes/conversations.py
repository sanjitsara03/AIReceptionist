from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Conversation, Customer
from app.schemas import ConversationResponse
from app.auth import get_current_business_id

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    result = await db.execute(
        select(Conversation)
        .join(Conversation.customer)
        .where(Customer.business_id == business_id)
        .options(
            selectinload(Conversation.customer).selectinload(Customer.jobs),
            selectinload(Conversation.messages),
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    business_id: int = Depends(get_current_business_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .join(Conversation.customer)
        .where(Conversation.id == conversation_id, Customer.business_id == business_id)
        .options(
            selectinload(Conversation.customer).selectinload(Customer.jobs),
            selectinload(Conversation.messages),
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation
