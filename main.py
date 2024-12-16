from datetime import datetime

import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor

# Конфигурация подключения к БД
DB_CONFIG = {
    "host": "host.docker.internal",
    "database": "kp_bd",
    "user": "kp_bd",
    "password": "kp_bd",
    "port": "5432",
}

# Подключение к БД
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        st.error(f"Ошибка подключения к базе данных: {e}")
        return None

# Инициализация состояния
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.cart = {}  # Корзина

# Функция логина
def login(username, password):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM users
                WHERE username = %s AND passwordhash = crypt(%s, passwordhash)
            """, (username, password))
            user = cur.fetchone()
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.session_state.role = user["roleid"]
                return True
            else:
                return False
    except Exception as e:
        st.error(f"Ошибка при входе: {e}")
        return False
    finally:
        conn.close()

# Функция регистрации
def register(username, email, password, role=2):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, email, passwordhash, roleid, registrationdate, isactive)
                VALUES (%s, %s, crypt(%s, gen_salt('bf')), %s, NOW(), TRUE)
            """, (username, email, password, role))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Ошибка при регистрации: {e}")
        return False
    finally:
        conn.close()

# Функция обновления данных профиля
def update_profile(user_id, username, email):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET username = %s, email = %s
                WHERE userid = %s
            """, (username, email, user_id))
            conn.commit()
            st.success("Профиль обновлен.")
    except Exception as e:
        st.error(f"Ошибка обновления профиля: {e}")
    finally:
        conn.close()

# Функция добавления заказа
def place_order(user_id, cart):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Вставка заказа и получение orderid
            cur.execute("""
                INSERT INTO orders (userid, orderdate, totalamount, orderstatus)
                VALUES (%s, NOW(), %s, 'обрабатывается') RETURNING orderid
            """, (user_id, sum(item['price'] * item['quantity'] for item in cart.values())))

            order_id = cur.fetchone()[0]  # Получаем orderid

            # Вставка деталей заказа
            for product_id, item in cart.items():
                cur.execute("""
                    INSERT INTO orderdetails (orderid, productid, quantity, price)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, product_id, item["quantity"], item["price"]))

                cur.execute("""
                    UPDATE products
                    SET stockquantity = stockquantity - %s
                    WHERE productid = %s AND stockquantity >= %s
                """, (item["quantity"], product_id, item["quantity"]))

            # Завершаем транзакцию
            conn.commit()
            st.success("Заказ успешно оформлен!")
            return True
    except Exception as e:
        conn.rollback()  # Откат транзакции в случае ошибки
        st.error(f"Ошибка оформления заказа: {e}")
        return False
    finally:
        conn.close()

# Основная функция
def main():
    if not st.session_state.logged_in:
        st.title("Добро пожаловать!")
        st.subheader("Вход или регистрация")

        tab_login, tab_register = st.tabs(["Вход", "Регистрация"])
        with tab_login:
            username = st.text_input("Логин")
            password = st.text_input("Пароль", type="password")
            if st.button("Войти"):
                if login(username, password):
                    pass
                    st.rerun()
                else:
                    st.error("Неверные данные для входа")

        with tab_register:
            username = st.text_input("Логин для регистрации")
            email = st.text_input("Email")
            password = st.text_input("Пароль для регистрации", type="password")
            if st.button("Зарегистрироваться"):
                if register(username, email, password):
                    st.success("Регистрация успешна. Войдите в систему.")
                else:
                    st.error("Ошибка регистрации")
    else:
        role = st.session_state.role
        st.sidebar.title("Навигация")
        if role == 1:  # Админ
            page = st.sidebar.selectbox("Страницы", ["Товары", "Добавить товар", "Добавить категорию", "Заказы", "Анализ заказов", "Аккаунт"])
        else:
            page = st.sidebar.selectbox("Страницы", ["Товары", "Корзина", "Мои заказы", "Мой профиль"])

        st.sidebar.button("Выйти", on_click=lambda: st.session_state.update({"logged_in": False, "user": None}))

        if page == "Товары":
            view_products(role)
        elif page == "Корзина":
            view_cart()
        elif page == "Мои заказы" or page == "Заказы":
            view_orders(role)
        elif page == "Мой профиль" or page == "Аккаунт":
            view_account()
        elif page == "Добавить товар" and role == 1:
            add_product()
        elif page == "Добавить категорию" and role == 1:
            add_category()
        elif page == "Анализ заказов" and role == 1:
            view_user_order_summary()

# Отображение товаров
# Функция просмотра товаров с поиском и фильтрацией
def view_products(role):
    st.title("Список товаров")

    conn = get_db_connection()
    if not conn:
        return

    try:
        # Выполнить запрос на получение всех категорий
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT categoryid, categoryname FROM categories")
            categories = cur.fetchall()

        # Поле для поиска
        search_query = st.text_input("Поиск товара", placeholder="Введите название товара...")

        # Выпадающий список для выбора категории
        category_options = {}
        category_options["Все категории"] = None
        for category in categories:
            category_options[category["categoryname"]] = category["categoryid"]

        selected_category = st.selectbox("Выберите категорию", list(category_options.keys()))

        # Формируем SQL-запрос на основе фильтров
        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search_query:
            query += " AND (LOWER(name) LIKE %s or LOWER(name) LIKE fix_mistake_search(%s))"
            params.append(f"%{search_query.lower()}%")
            params.append(f"%{search_query.lower()}%")

        if category_options[selected_category]:
            query += " AND categoryid = %s"
            params.append(category_options[selected_category])

        # Получение товаров из базы данных
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            products = cur.fetchall()

        # Отображение товаров
        for product in products:
            st.write(f"**{product['name']}** - {product['price']}₽")
            st.write(f"Описание: {product['description']}")
            st.write(f"На складе: {product['stockquantity']} шт.")

            if role == 1:  # Администратор
                if "editing" not in st.session_state:
                    st.session_state.editing = None

                if st.button("Удалить", key=f"delete_{product['productid']}"):
                    delete_product(product['productid'])
                    st.rerun()

                # Если нажата кнопка "Редактировать"
                if st.button("Редактировать", key=f"edit_{product['productid']}"):
                    st.session_state.editing = product['productid']
                    st.session_state.new_name = product['name']
                    st.session_state.new_price = float(product['price'])
                    st.session_state.new_stock = int(product['stockquantity'])

                # Если текущий продукт редактируется
                if st.session_state.editing == product['productid']:
                    new_name = st.text_input("Название", value=st.session_state.new_name,
                                             key=f"name_{product['productid']}")
                    new_price = st.number_input(
                        "Цена", value=st.session_state.new_price, min_value=0.0, key=f"price_{product['productid']}"
                    )
                    new_stock = st.number_input(
                        "Количество на складе", value=st.session_state.new_stock, min_value=0,
                        key=f"stock_{product['productid']}"
                    )

                    # Сохраняем новые значения в session_state
                    st.session_state.new_name = new_name
                    st.session_state.new_price = new_price
                    st.session_state.new_stock = new_stock

                    # Кнопка "Сохранить изменения"
                    if st.button("Сохранить изменения продукта", key=f"save_{product['productid']}"):
                        update_product(product['productid'], new_name, new_price, new_stock)
                        # Сбрасываем режим редактирования
                        st.session_state.editing = None
                        # st.rerun()  # Перезапускаем страницу для обновления
            else:  # Обычный пользователь
                quantity = st.number_input(
                    f"Количество для {product['name']}", min_value=1, max_value=product['stockquantity'], step=1,
                    key=f"qty_{product['productid']}"
                )
                if st.button("Добавить в корзину", key=f"add_{product['productid']}"):
                    add_to_cart(product, quantity)
                    st.success(f"{product['name']} добавлен в корзину!")
    except Exception as e:
        st.error(f"Ошибка загрузки товаров: {e}")
    finally:
        conn.close()


# Вспомогательная функция для удаления продукта (для администратора)
def delete_product(product_id):
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE productid = %s", (product_id,))
            conn.commit()
            st.success("Продукт успешно удалён!")
    except Exception as e:
        st.error(f"Ошибка удаления продукта: {e}")
    finally:
        conn.close()


def update_product(product_id, name, price, stock_quantity):
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET name = %s, price = %s, stockquantity = %s
                WHERE productid = %s
            """, (name, price, stock_quantity, product_id))
            conn.commit()
            st.success("Товар успешно обновлен!")
    except Exception as e:
        st.error(f"Ошибка обновления товара: {e}")
    finally:
        conn.close()


# Вспомогательная функция для добавления товара в корзину
def add_to_cart(product, quantity):
    if "cart" not in st.session_state:
        st.session_state.cart = {}

    product_id = product["productid"]
    if product_id in st.session_state.cart:
        st.session_state.cart[product_id]["quantity"] += quantity
    else:
        st.session_state.cart[product_id] = {
            "name": product["name"],
            "price": product["price"],
            "quantity": quantity,
        }

# Просмотр корзины
def view_cart():
    st.title("Корзина")
    cart = st.session_state.cart
    if cart:
        total = 0
        for product_id, item in cart.items():
            st.write(f"{item['name']}: {item['quantity']} шт. x {item['price']}₽")
            total += item['quantity'] * item['price']
        st.write(f"Итого: {total}₽")
        if st.button("Оформить заказ"):
            if place_order(st.session_state.user["userid"], cart):
                st.session_state.cart = {}
                st.rerun()
    else:
        st.write("Корзина пуста.")

# Управление аккаунтом
def view_account():
    st.title("Мой профиль")
    user = st.session_state.user
    username = st.text_input("Логин", value=user["username"])
    email = st.text_input("Email", value=user["email"])
    if st.button("Сохранить"):
        update_profile(user["userid"], username, email)

# Управление заказами
def view_orders(role):
    st.title("Заказы" if role == 1 else "Мои заказы")

    # Подключаемся к базе данных
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if role == 1:  # Для администратора
                search_query = st.text_input("Поиск по номеру заказа", placeholder="Введите номер заказа...")

                # Получаем все данные из представления OrderDetailsView
                # cur.execute("SELECT * FROM OrderDetailsView")
                if search_query:
                    cur.execute(f"SELECT * FROM OrderDetailsView WHERE OrderID={search_query}")
                else:
                    cur.execute("SELECT * FROM OrderDetailsView")
                orders = cur.fetchall()
                if not orders:
                    st.write("Нет заказов в системе.")
                # Создаем словарь для хранения заказов по OrderID
                orders_dict = {}
                for order in orders:
                    order_id = order['orderid']
                    if order_id not in orders_dict:
                        orders_dict[order_id] = {
                            'orderdate': order['orderdate'],
                            'orderstatus': order['orderstatus'],
                            'totalamount': order['totalamount'],
                            'items': []
                        }
                    orders_dict[order_id]['items'].append({
                        'productid': order['productid'],
                        'productname': order['name'],
                        'quantity': order['quantity'],
                        'price': order['price']
                    })

                # Выводим информацию по заказам
                for order_id, order_info in orders_dict.items():
                    st.write(f"**Заказ №{order_id}** - Статус: {order_info['orderstatus']}")
                    st.write(f"Дата: {order_info['orderdate']} - Сумма: {order_info['totalamount']}₽")
                    for item in order_info['items']:
                        st.write(
                            f"Продукт: {item['productname']} | Количество: {item['quantity']} | Цена за единицу: {item['price']}₽")

                    # Возможность изменения статуса заказа
                    new_status = st.selectbox(f"Изменить статус заказа №{order_id}",
                                              ["обрабатывается", "доставлен", "отменён"],
                                              key=f"status_{order_id}")
                    if st.button(f"Обновить статус заказа №{order_id}", key=f"update_{order_id}"):
                        cur.execute("""
                            UPDATE Orders
                            SET OrderStatus = %s
                            WHERE OrderID = %s
                        """, (new_status, order_id))
                        conn.commit()
                        st.success(f"Статус заказа №{order_id} обновлён на '{new_status}'")

            else:  # Для обычного пользователя
                user_id = st.session_state.user["userid"]
                # Получаем заказы текущего пользователя из представления OrderDetailsView
                cur.execute("SELECT * FROM OrderDetailsView WHERE UserID = %s", (user_id,))
                orders = cur.fetchall()
                if not orders:
                    st.write("У вас нет заказов.")
                # Создаем словарь для хранения заказов по OrderID
                orders_dict = {}
                for order in orders:
                    order_id = order['orderid']
                    if order_id not in orders_dict:
                        orders_dict[order_id] = {
                            'orderdate': order['orderdate'],
                            'orderstatus': order['orderstatus'],
                            'totalamount': order['totalamount'],
                            'items': []
                        }
                    orders_dict[order_id]['items'].append({
                        'productid': order['productid'],
                        'productname': order['name'],
                        'quantity': order['quantity'],
                        'price': order['price']
                    })

                # Выводим информацию по заказам
                for order_id, order_info in orders_dict.items():
                    st.write(f"**Заказ №{order_id}**") # - Статус: {order_info['orderstatus']}
                    st.write(f"Дата: {order_info['orderdate']} - Сумма: {order_info['totalamount']}₽")
                    for item in order_info['items']:
                        st.write(
                            f"Продукт: {item['productname']} | Количество: {item['quantity']} | Цена за единицу: {item['price']}₽")

                    # Ожидание подтверждения или отмены (если администратор этого не сделал)
                    if order_info['orderstatus'] == 'обрабатывается':
                        st.warning(f"Ваш заказ №{order_id} ещё обрабатывается.")
                    elif order_info['orderstatus'] == 'доставлен':
                        st.success(f"Ваш заказ №{order_id} доставлен.")
                    elif order_info['orderstatus'] == 'отменён':
                        st.error(f"Ваш заказ №{order_id} был отменён.")

    except Exception as e:
        st.error(f"Ошибка загрузки заказов: {e}")
    finally:
        conn.close()


def add_category():
    st.title("Добавление категории")
    category_name = st.text_input("Название категории")
    if st.button("Добавить категорию"):
        if category_name.strip():
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO categories (CategoryName) VALUES (%s)",
                        (category_name,),
                    )
                    conn.commit()
                    st.success(f"Категория '{category_name}' успешно добавлена!")
            except Exception as e:
                st.error(f"Ошибка при добавлении категории: {e}")
            finally:
                conn.close()
        else:
            st.error("Название категории не может быть пустым.")


# Функция добавления продукта
def add_product():
    st.title("Добавление продукта")
    conn = get_db_connection()

    uploaded_file = st.file_uploader("Загрузите JSON-файл с товарами", type="json")
    if uploaded_file:
        try:
            product_data = uploaded_file.getvalue().decode("utf-8")
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("CALL bulk_add_products(%s::json)", (product_data,))
                conn.commit()
            st.success("Товары успешно добавлены!")
        except Exception as e:
            st.error(f"Ошибка добавления товаров: {e}")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Загрузка списка категорий
            cur.execute("SELECT categoryid, categoryname FROM categories")
            categories = cur.fetchall()
            category_options = {cat['categoryname']: cat['categoryid'] for cat in categories}

        if categories:
            product_name = st.text_input("Название продукта")
            product_description = st.text_input("Описание продукта")
            product_price = st.number_input("Цена", min_value=0.0, step=0.01)
            product_stock = st.number_input("Количество на складе", min_value=0, step=1)
            selected_category = st.selectbox("Категория", list(category_options.keys()))

            if st.button("Добавить продукт"):
                if product_name.strip():
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO products (name, description, price, stockquantity, categoryid)
                                VALUES (%s, %s, %s, %s)
                                """,
                                (product_name, product_description, product_price, product_stock, category_options[selected_category]),
                            )
                            conn.commit()
                            st.success(f"Продукт '{product_name}' успешно добавлен!")
                            # st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка при добавлении продукта: {e}")
                else:
                    st.error("Название продукта не может быть пустым.")
        else:
            st.warning("Сначала создайте категорию, чтобы добавить продукт.")
    except Exception as e:
        st.error(f"Ошибка при загрузке категорий: {e}")
    finally:
        conn.close()

def view_user_order_summary():
    # Выбор даты начала и окончания периода
    start_date = st.date_input("Выберите дату начала", datetime.today())
    end_date = st.date_input("Выберите дату окончания", datetime.today())

    # Проверка, что дата начала не позже даты окончания
    if start_date > end_date:
        st.error("Дата начала не может быть позже даты окончания.")
        return

    # Подключение к базе данных
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Запрос к функции get_orders_summary_for_all_users
            cur.execute("""
                SELECT *
                FROM get_orders_summary_for_all_users(%s, %s)
            """, (start_date, end_date))
            result = cur.fetchall()
            cur.execute("""
            SELECT SUM(total_orders) as all_orders, SUM(total_amount) as all_amount
            FROM get_orders_summary_for_all_users(%s, %s)
        """, (start_date, end_date))
            result2 = cur.fetchall()

            # Выводим таблицу с результатами
            if result:
                st.write("### Сводка по заказам всех пользователей")
                st.write(f"Период: {start_date} - {end_date}")
                for res in result2:
                    st.write(f"Количество заказов: {res['all_orders']}. Общая сумма: {res['all_amount']}")
                st.write(
                    f"Таблица с количеством заказов и суммами для каждого пользователя:"
                )
                st.dataframe(result)
            else:
                st.write("Нет данных за указанный период.")

    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
    finally:
        conn.close()



# # Добавляем страницы для администратора
# def admin_pages():
#     st.sidebar.title("Администрирование")
#     admin_page = st.sidebar.selectbox("Выберите действие", ["Добавить категорию", "Добавить продукт"])
#
#     if admin_page == "Добавить категорию":
#         add_category()
#     elif admin_page == "Добавить продукт":
#         add_product()

if __name__ == "__main__":
    main()
