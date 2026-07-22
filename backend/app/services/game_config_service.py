from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game_config import GameConfig


async def get_config(db: AsyncSession) -> GameConfig:
    config = await db.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config
