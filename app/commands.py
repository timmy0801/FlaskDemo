import click
from flask import current_app
from faker import Faker
import random

from app import db
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem

from datetime import datetime, timezone

fake = Faker("zh_TW")

CATEGORIES = ["電子產品", "服飾", "家居用品", "食品飲料", "運動休閒", "書籍文具"]


def register_commands(app):

    @app.cli.command("seed")
    @click.option("--users", default=10, help="建立的使用者數量")
    @click.option("--products", default=50, help="建立的商品數量")
    def seed_db(users, products):
        """填入測試假資料到資料庫"""
        click.echo("🌱 開始建立測試資料...")

        # 建立 admin 帳號
        if not User.query.filter_by(email="admin@example.com").first():
            admin = User(username="admin", email="admin@example.com", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            click.echo("  ✅ Admin 帳號建立完成 (admin@example.com / admin123)")

        # 建立一般使用者
        created_users = []
        for _ in range(users):
            user = User(
                username=fake.user_name(),
                email=fake.unique.email(),
                role="user",
            )
            user.set_password("password123")
            db.session.add(user)
            created_users.append(user)

        db.session.flush()
        click.echo(f"  ✅ 建立 {users} 位使用者")

        # 建立商品
        created_products = []
        for _ in range(products):
            product = Product(
                name=fake.word()
                + random.choice(["手機", "外套", "椅子", "咖啡", "球鞋", "筆記本"]),
                description=fake.text(max_nb_chars=150),
                price=round(random.uniform(99, 9999), 0),
                stock=random.randint(0, 200),
                category=random.choice(CATEGORIES),
                image_url=f"https://picsum.photos/seed/{fake.word()}/400/300",
            )
            db.session.add(product)
            created_products.append(product)

        db.session.flush()
        click.echo(f"  ✅ 建立 {products} 個商品")

        # 建立訂單
        order_count = 0
        for user in created_users[:5]:
            for _ in range(random.randint(1, 3)):
                order = Order(user_id=user.id)
                db.session.add(order)
                db.session.flush()

                selected_products = random.sample(
                    created_products, random.randint(1, 4)
                )
                for product in selected_products:
                    qty = random.randint(1, 3)
                    if product.stock >= qty:
                        item = OrderItem(
                            order_id=order.id,
                            product_id=product.id,
                            quantity=qty,
                            unit_price=product.price,
                        )
                        product.stock -= qty
                        db.session.add(item)

                db.session.flush()
                order.calculate_total()
                order.status = random.choice(
                    ["pending", "paid", "shipped", "delivered"]
                )
                order_count += 1

        db.session.commit()
        click.echo(f"  ✅ 建立 {order_count} 筆訂單")
        click.echo("🎉 測試資料建立完成！")

    @app.cli.command("init-db")
    def init_db():
        """建立所有資料表"""
        db.create_all()
        click.echo("✅ 資料表建立完成")

    @app.cli.command("cleanup-tokens")
    @click.option("--dry-run", is_flag=True, help="僅顯示將要刪除的資料，不實際刪除")
    def cleanup_tokens(dry_run):
        """清理過期的refresh token紀錄"""
        from app.models.refresh_token import RefreshToken

        now = datetime.now(timezone.utc)
        expired_query = RefreshToken.query.filter(RefreshToken.expires_at < now)
        expired_count = expired_query.count()
        if dry_run:
            click.echo(
                f"找到{expired_count} 筆過期的 refresh token 紀錄 (dry-run 模式，未刪除)"
            )
            return
        if expired_count == 0:
            click.echo("沒有過期的 refresh token 紀錄需要刪除。")
            return
        expired_query.delete()
        db.session.commit()
        click.echo(f" 已刪除 {expired_count} 筆過期的 refresh token")
