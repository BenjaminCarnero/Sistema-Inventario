from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Se importan los modelos para que autogenerate detecte los cambios,
# y la configuración para tomar la URL real de la base desde el .env.
from app.config import settings
from app.database import Base
from app import models  # noqa: F401  (registra las tablas en Base.metadata)

config = context.config

# La URL sale de la configuración de la app, no del .ini: así el .ini no
# guarda credenciales y desarrollo/producción usan la misma fuente.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse a la base."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base configurada."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite no soporta ALTER de columnas: batch recrea la tabla.
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
