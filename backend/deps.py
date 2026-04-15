from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, Role


async def get_current_user(
    x_token: str = Header(..., alias="X-Token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """通过 X-Token (openid) 获取当前用户"""
    result = await db.execute(select(User).where(User.openid == x_token))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户未登录")
    return user


def require_role(*roles: str):
    """角色权限校验依赖"""
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return checker
