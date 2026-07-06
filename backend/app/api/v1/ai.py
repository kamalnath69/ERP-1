"""AI chat endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import run_chat
from app.core.database import get_db
from app.core.deps import require_permissions, require_tenant
from app.models import ChatConversation, ChatMessage, Organization, User
from app.schemas import ChatMessageOut, ChatRequest, ConversationOut
from app.services.audit import log_action

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(user: User = Depends(require_permissions("ai.use")), db: Session = Depends(get_db)):
    stmt = (
        select(ChatConversation)
        .where(
            ChatConversation.organization_id == user.organization_id,
            ChatConversation.user_id == user.id,
        )
        .order_by(ChatConversation.created_at.desc())
        .limit(50)
    )
    return db.execute(stmt).scalars().all()


@router.get("/conversations/{cid}/messages", response_model=list[ChatMessageOut])
def get_messages(cid: str, user: User = Depends(require_permissions("ai.use")), db: Session = Depends(get_db)):
    conv = db.get(ChatConversation, cid)
    if not conv or conv.organization_id != user.organization_id or conv.user_id != user.id:
        raise HTTPException(404, "Not found")
    return db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == cid).order_by(ChatMessage.created_at.asc())
    ).scalars().all()


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(require_permissions("ai.use")), db: Session = Depends(get_db)):
    org = db.get(Organization, user.organization_id) if user.organization_id else None
    provider = (org.ai_provider if org else "openai") or "openai"
    model = (org.ai_model if org else "gpt-5.4") or "gpt-5.4"

    if body.conversation_id:
        conv = db.get(ChatConversation, body.conversation_id)
        if not conv or conv.organization_id != user.organization_id or conv.user_id != user.id:
            raise HTTPException(404, "Conversation not found")
    else:
        title = body.message[:60] if body.message else "New chat"
        conv = ChatConversation(
            organization_id=user.organization_id,
            user_id=user.id,
            title=title,
            provider=provider,
            model=model,
        )
        db.add(conv)
        db.flush()

    user_msg = ChatMessage(
        organization_id=user.organization_id,
        conversation_id=conv.id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(conv)

    try:
        result = await run_chat(db, user, conv, body.message)
    except Exception as exc:
        raise HTTPException(500, f"AI error: {exc}")

    assistant_msg = ChatMessage(
        organization_id=user.organization_id,
        conversation_id=conv.id,
        role="assistant",
        content=result["content"],
        tool_calls=result["tool_calls"] or None,
    )
    db.add(assistant_msg)
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.id,
        action="ai.chat",
        resource_type="conversation",
        resource_id=conv.id,
        question=body.message,
        tool=",".join(t["name"] for t in result["tool_calls"]) if result["tool_calls"] else None,
    )
    db.commit()
    db.refresh(assistant_msg)

    return {
        "conversation_id": conv.id,
        "message": {
            "id": assistant_msg.id,
            "role": "assistant",
            "content": assistant_msg.content,
            "tool_calls": assistant_msg.tool_calls,
        },
    }


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, user: User = Depends(require_permissions("ai.use")), db: Session = Depends(get_db)):
    conv = db.get(ChatConversation, cid)
    if not conv or conv.organization_id != user.organization_id or conv.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(conv)
    db.commit()
    return {"ok": True}
