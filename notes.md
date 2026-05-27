# Personal Notes

## Redis Blacklist Check After Logout

Як перевірити, що `logout` реально додає поточний `access_token` у Redis blacklist:

1. Запусти сервіси, включно з `redis`.
2. Увійди в систему.
3. Виклич `POST /api/auth/logout`.
4. Зайди в Redis CLI:

```powershell
docker exec -it redis redis-cli
```

5. Перевір наявність blacklist keys:

```redis
KEYS blacklist:access:*
```

6. Перевір TTL для конкретного ключа:

```redis
TTL blacklist:access:<jti>
```

Якщо все ок, у Redis буде ключ blacklist і позитивний TTL на час життя
відкликаного токена.

## Password Reset Token Cleanup

### Запустити вручну для перевірки

Локально:

```powershell
poetry run python -m src.scripts.cleanup_password_reset_tokens
```

У Docker:

```powershell
docker compose exec app_server poetry run python -m src.scripts.cleanup_password_reset_tokens
```

### Періодичний запуск

Через cron (якщо Docker/Linux):

```cron
0 3 * * * docker compose exec app_server poetry run python -m src.scripts.cleanup_password_reset_tokens
```

Це запускатиме cleanup щодня о `03:00`.

Для контейнерного scheduler-а в проєкті зараз використовується:

```cron
0 0 * * * python -m src.scripts.cleanup_password_reset_tokens
```

Це лежить у `scripts/cleanup-cron`.

На Windows:

- використовувати `Task Scheduler`
- action:

```powershell
poetry run python -m src.scripts.cleanup_password_reset_tokens
```

## Useful Commands

Запуск тестів:

```powershell
poetry run pytest -v tests
```

```poetry run pytest -v tests
python -m pytest test/unit
```

Pre-commit:

```powershell
pre-commit run --all-files
```

Логи cleanup scheduler:

```powershell
docker compose logs -f cleanup_scheduler
```

## DB Reset Hint

Очистити дані:

```sql
TRUNCATE table_name RESTART IDENTITY CASCADE;
```
