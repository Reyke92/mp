from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("listings", "0001_initial"),
        ("admin_ops", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
CREATE TABLE `administration_action_type` (
  `action_type_id` bigint NOT NULL AUTO_INCREMENT,
  `action_type_name` varchar(30) NOT NULL,
  PRIMARY KEY (`action_type_id`),
  UNIQUE KEY `uq_administration_action_type_name` (`action_type_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `administration_actions` (
  `action_id` bigint NOT NULL AUTO_INCREMENT,
  `actor_user_id` int NOT NULL,
  `action_type_id` bigint NOT NULL,
  `listing_id` bigint DEFAULT NULL,
  `target_user_id` int DEFAULT NULL,
  `notes` text,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`action_id`),
  KEY `ix_admin_actions_actor` (`actor_user_id`),
  KEY `ix_admin_actions_listing` (`listing_id`),
  KEY `ix_admin_actions_target_user` (`target_user_id`),
  KEY `fk_admin_actions_action_type` (`action_type_id`),
  CONSTRAINT `fk_admin_actions_action_type`
    FOREIGN KEY (`action_type_id`) REFERENCES `administration_action_type` (`action_type_id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_admin_actions_actor`
    FOREIGN KEY (`actor_user_id`) REFERENCES `auth_user` (`id`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_admin_actions_listing`
    FOREIGN KEY (`listing_id`) REFERENCES `listings` (`listing_id`)
    ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_admin_actions_target_user`
    FOREIGN KEY (`target_user_id`) REFERENCES `auth_user` (`id`)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""",
                    reverse_sql="""
DROP TABLE IF EXISTS `administration_actions`;
DROP TABLE IF EXISTS `administration_action_type`;
""",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="AdministrationActionType",
                    fields=[
                        (
                            "action_type_id",
                            models.BigAutoField(
                                primary_key=True,
                                serialize=False,
                                db_column="action_type_id",
                            ),
                        ),
                        (
                            "action_type_name",
                            models.CharField(
                                max_length=30,
                                unique=True,
                                db_column="action_type_name",
                            ),
                        ),
                    ],
                    options={
                        "managed": True,
                        "db_table": "administration_action_type",
                    },
                ),
                migrations.CreateModel(
                    name="AdministrationAction",
                    fields=[
                        (
                            "action_id",
                            models.BigAutoField(
                                primary_key=True,
                                serialize=False,
                                db_column="action_id",
                            ),
                        ),
                        (
                            "notes",
                            models.TextField(
                                null=True,
                                blank=True,
                                db_column="notes",
                            ),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                default=django.utils.timezone.now,
                                db_column="created_at",
                            ),
                        ),
                        (
                            "actor_user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.RESTRICT,
                                related_name="administration_actions_as_actor",
                                db_column="actor_user_id",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "action_type",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.RESTRICT,
                                db_column="action_type_id",
                                to="admin_ops.administrationactiontype",
                            ),
                        ),
                        (
                            "listing",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.SET_NULL,
                                null=True,
                                blank=True,
                                db_column="listing_id",
                                to="listings.listing",
                            ),
                        ),
                        (
                            "target_user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.SET_NULL,
                                null=True,
                                blank=True,
                                related_name="administration_actions_as_target",
                                db_column="target_user_id",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "managed": True,
                        "db_table": "administration_actions",
                        "indexes": [
                            models.Index(
                                fields=["actor_user"],
                                name="ix_admin_actions_actor",
                            ),
                            models.Index(
                                fields=["listing"],
                                name="ix_admin_actions_listing",
                            ),
                            models.Index(
                                fields=["target_user"],
                                name="ix_admin_actions_target_user",
                            ),
                            models.Index(
                                fields=["action_type"],
                                name="fk_admin_actions_action_type",
                            ),
                        ],
                    },
                ),
            ],
        ),
    ]