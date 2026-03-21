from django.db import models


class UnsignedBigIntegerField(models.BigIntegerField):
    def db_type(self, connection):
        engine = connection.settings_dict.get("ENGINE", "")
        if "mysql" in engine:
            return "bigint UNSIGNED"
        return super().db_type(connection)

    def rel_db_type(self, connection):
        engine = connection.settings_dict.get("ENGINE", "")
        if "mysql" in engine:
            return "bigint UNSIGNED"
        # Field.rel_db_type() normally falls back to self.db_type(connection).
        return self.db_type(connection)


class UnsignedBigAutoField(models.BigAutoField):
    def db_type(self, connection):
        engine = connection.settings_dict.get("ENGINE", "")
        if "mysql" in engine:
            return "bigint UNSIGNED AUTO_INCREMENT"
        return super().db_type(connection)

    def rel_db_type(self, connection):
        engine = connection.settings_dict.get("ENGINE", "")
        if "mysql" in engine:
            return "bigint UNSIGNED"
        # Match Django's built-in BigAutoField behavior exactly.
        return models.BigIntegerField().db_type(connection=connection)
