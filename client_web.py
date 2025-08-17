import os
import random
import uuid

import gevent
import redis
from flask import Flask, render_template, redirect, session, url_for, request, flash, jsonify
from markupsafe import escape
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

from poker.channel import ChannelError, MessageFormatError, MessageTimeout
from poker.player import Player
from poker.player_client import PlayerClientConnector
from poker.database import get_db_connection, get_ranking_list

app = Flask(__name__)
app.config["SECRET_KEY"] = "!!_-pyp0k3r-_!!"
app.debug = False
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

os.environ['REDIS_URL'] = 'redis://localhost:6379/0'

socketio = SocketIO(app)

redis_url = os.environ["REDIS_URL"]
redis = redis.from_url(redis_url)

INVITE_CODE = "asd"


# sudo lsof -ti:5000 | xargs sudo kill -9


class User(UserMixin):
    def __init__(self, id, username, password, email, money, loan):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.money = money
        self.loan = loan


@login_manager.user_loader
def load_user(user_id):
    # 根据用户ID从数据库加载用户
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(user_data["id"], user_data["username"], user_data["password"],
                    user_data["email"], user_data["money"], user_data["loan"])
    return None


@app.route("/")
@login_required
def index():
    if current_user.is_authenticated:
        return redirect(url_for("join"))
    else:
        return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form["email"]
        invite = request.form["invite"]

        if invite != INVITE_CODE:
            flash("Invalid invite code. Please try again.")
            return redirect(url_for("register"))

        # 检查用户名是否已存在
        conn = get_db_connection()
        existing_user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if existing_user:
            conn.close()
            flash("Username already exists. Please choose another one.")
            return redirect(url_for("register"))

        # 加密密码并存储到数据库
        hashed_password = generate_password_hash(password)
        conn.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                     (username, hashed_password, email))
        conn.commit()
        conn.close()

        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # 从数据库获取用户信息
        conn = get_db_connection()
        user_data = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user_data and check_password_hash(user_data["password"], password):
            user = User(user_data["id"], user_data["username"], user_data["password"],
                        user_data["email"], user_data["money"], user_data["loan"])
            login_user(user)
            return redirect(url_for("join"))

        flash("Invalid username or password. Please try again.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route('/api/get-ranking', methods=['GET'])
def get_ranking():
    ranking_data = get_ranking_list()
    return jsonify(ranking_data)  # 返回 JSON 格式


@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "join":
            room_id = request.form.get("room-id").strip()
            if not room_id:
                return redirect(url_for("join"))

            # 玩家信息从数据库读取后保存在session中
            session["room-id"] = room_id
            session["player-id"] = current_user.id
            session["player-name"] = current_user.username
            session["player-money"] = current_user.money
            session['player-loan'] = current_user.loan

            return render_template("index.html",
                                   player_id=session["player-id"],
                                   username=session["player-name"],
                                   money=session["player-money"],
                                   loan=session['player-loan'],
                                   room=session["room-id"],
                                   template="game.html")

        elif action == "create":
            room_id = random.randint(1000, 9999)
            session["room-id"] = room_id
            session["player-id"] = current_user.id
            session["player-name"] = current_user.username
            session["player-money"] = current_user.money
            session['player-loan'] = current_user.loan

            return render_template("index.html",
                                   player_id=session["player-id"],
                                   username=session["player-name"],
                                   money=session["player-money"],
                                   loan=session['player-loan'],
                                   room=session["room-id"],
                                   template="game.html")

        else:
            flash("What did you do???")
            return redirect(url_for("join"))

    return render_template("join.html")


@socketio.on('connect')
def on_connect():
    app.logger.info(f"Client connected: {request.sid}")


player_channels = {}


@socketio.on('disconnect')
def on_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    sid = request.sid
    if sid in player_channels:
        del player_channels[sid]


@socketio.on('game_message')
def on_game_message(message):
    sid = request.sid
    if sid in player_channels:
        try:
            player_channels[sid].send_message(message)
        except (ChannelError, MessageFormatError):
            pass


@socketio.on('join_game')
def on_join_game(data):
    poker_game(data, "texas-holdem-poker:lobby")


def poker_game(data, connection_channel: str):
    if "player-id" not in session:
        emit("error", {"error": "Unrecognized user"})
        return

    session_id = str(uuid.uuid4())

    player_id = session["player-id"]
    player_name = session["player-name"]
    player_money = session["player-money"]
    player_loan = session["player-loan"]
    room_id = session["room-id"]

    player_connector = PlayerClientConnector(redis, connection_channel, app.logger)

    try:
        server_channel = player_connector.connect(
            player=Player(
                id=player_id,
                name=player_name,
                money=player_money,
                loan=player_loan,
                ready=False,
            ),
            session_id=session_id,
            room_id=room_id
        )
    except (ChannelError, MessageFormatError, MessageTimeout) as e:
        app.logger.error(f"Unable to connect player {player_id} to a poker server: {e}")
        emit("error", {"error": "Unable to connect to the game server"})
        return

    emit('game_connected', server_channel.connection_message)

    player_channels[request.sid] = server_channel

    def message_handler(channel_from, channel_to_ws):
        try:
            while True:
                message = channel_from.recv_message()
                if "message_type" in message and message["message_type"] == "disconnect":
                    raise ChannelError
                socketio.emit('game_message', message, room=channel_to_ws)
        except (ChannelError, MessageFormatError):
            pass

    gevent.spawn(message_handler, server_channel, request.sid)

