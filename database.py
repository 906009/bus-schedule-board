import aiosqlite


class DB:
    def __init__(self, db_path: str = "user_favorites.db"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as connection:
            await connection.execute(
                'CREATE TABLE IF NOT EXISTS main (id INTEGER PRIMARY KEY, settings TEXT, stop TEXT, route_direction TEXT, card TEXT)'
            )
            await connection.commit()

    async def read_db(self):
        async with aiosqlite.connect(self.db_path) as connection:
            connection.row_factory = aiosqlite.Row
            async with connection.execute("SELECT id, settings, stop, route_direction, card FROM main") as cursor:
                return await cursor.fetchall()

    async def registration(self, id):
        async with aiosqlite.connect(self.db_path) as connection:
            await connection.execute(
                'INSERT OR IGNORE INTO main (id, settings, stop, route_direction, card) VALUES (?, NULL, NULL, NULL, NULL)',
                (id,)
            )
            await connection.commit()
        return await self.read_db()

    async def remove_user(self, id):
        async with aiosqlite.connect(self.db_path) as connection:
            await connection.execute("DELETE FROM main WHERE id = ?", (id,))
            await connection.commit()
        return await self.read_db()

    async def modder(self, user_id, field, value, add_FT):
        async with aiosqlite.connect(self.db_path) as connection:
            await connection.execute(
                'CREATE TABLE IF NOT EXISTS main(id INTEGER PRIMARY KEY, settings TEXT, stop TEXT, route_direction TEXT, card TEXT)')
            connection.row_factory = aiosqlite.Row

            async with connection.execute(f"SELECT {field} FROM main WHERE id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()

            if add_FT:
                current_field = result[field] if result and result[field] else ""
                existing_values = current_field.split(",") if current_field else []
                if value not in existing_values:
                    new_data = ",".join(existing_values + [value]) if existing_values else value
                    await connection.execute(f"UPDATE main SET {field} = ? WHERE id = ?", (new_data, user_id))
            else:
                if result and result[field]:
                    existing_values = result[field].split(",")
                    if value in existing_values:
                        existing_values.remove(value)
                        new_data = ",".join(existing_values)
                        await connection.execute(f"UPDATE main SET {field} = ? WHERE id = ?", (new_data, user_id))

            await connection.commit()
        return await self.read_db()

    async def add_station_favorites(self, user_id, new_stop):
        return await self.modder(user_id, 'stop', new_stop, True)

    async def remove_station_favorites(self, user_id, rm_stop):
        return await self.modder(user_id, 'stop', rm_stop, False)

    async def add_district_favorites(self, user_id, district):
        pass

    async def remove_district_favorites(self, user_id, district):
        pass

    async def add_route_direction_favorites(self, user_id, new_rd):
        return await self.modder(user_id, 'route_direction', new_rd, True)

    async def remove_route_direction_favorites(self, user_id, rm_rd):
        return await self.modder(user_id, 'route_direction', rm_rd, False)

    async def add_transport_card(self, user_id, new_card):
        return await self.modder(user_id, 'card', new_card, True)

    async def remove_transport_card(self, user_id, rm_card):
        return await self.modder(user_id, 'card', rm_card, False)
