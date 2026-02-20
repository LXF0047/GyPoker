import os
import random
import uuid
import json
import requests
import datetime

import gevent
import redis
from flask import Flask, render_template, redirect, session, url_for, request, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from poker.channel import ChannelError, MessageFormatError, MessageTimeout
from poker.channel_redis import MessageQueue
from poker.player import Player
from poker.player_client import PlayerClientConnector
from poker.db_utils import get_player_by_id, get_player_by_login_username, create_player, get_api_key, get_player_analysis_data, get_daily_ranking_list, check_and_reset_daily_chips, update_player_profile

app = Flask(__name__)
app.config["SECRET_KEY"] = "!!_-pyp0k3r-_!!"
app.debug = False
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

os.environ['REDIS_URL'] = 'redis://localhost:6379/0'

socketio = SocketIO(app)

redis_url = os.environ["REDIS_URL"]
redis = redis.from_url(redis_url)
room_control_queue = MessageQueue(redis, "texas-holdem-poker:room-control")

INVITE_CODE = "asd"
player_channels = {}

# DeepSeek API Configuration
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

FORTUNES = [
    "今日宜：诈唬。你的底牌看不见，但你的气场看得见。",
    "运气爆棚：口袋对子出现的概率提升 20%。",
    "警惕：河牌可能会带来惊天逆转，请保持冷静。",
    "上上签：今日适合激进打法，幸运女神站在你这边。",
    "运势平平：耐心等待位置，不要强行入池。",
    "大吉：你的坚果牌终将等到大鱼。",
    "今日忌：冲动All-in。留得青山在，不怕没柴烧。"
]

ACTION_SOUND_DIR = os.path.join("static", "sounds", "action")
DEFAULT_ACTION_VOICE_PACK = "base_male"
REQUIRED_ACTION_VOICE_FILES = {
    "call.wav",
    "check.wav",
    "fold.wav",
    "raise.wav",
    "allin.wav",
    "name.txt",
}


class User(UserMixin):
    def __init__(self, id, username, password, email, money, avatar=None):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.money = money
        self.avatar = avatar


@login_manager.user_loader
def load_user(user_id):
    user_data = get_player_by_id(user_id)
    if user_data:
        # Mapping: nickname -> username (User class property), username -> email (User class property)
        # chips -> money
        return User(user_data["id"], user_data["nickname"], user_data["password_hash"],
                    user_data["username"], user_data["chips"], user_data["avatar"])
    return None


@app.route("/")
@login_required
def index():
    if current_user.is_authenticated:
        return redirect(url_for("navigator"))
    else:
        return redirect(url_for("login"))


@app.route("/navigator")
@login_required
def navigator():
    analysis_data = get_player_analysis_data(current_user.id)
    stats = {"vpip": 0, "pfr": 0, "win_rate": 0, "hands": 0}

    if analysis_data:
        stats["vpip"] = analysis_data["tech_stats"].get("vpip", 0)
        stats["pfr"] = analysis_data["tech_stats"].get("pfr", 0)
        stats["win_rate"] = analysis_data["summary"].get("total_profit", 0)
        stats["hands"] = analysis_data["summary"].get("total_hands", 0)

    return render_template("navigator_page.html",
                           username=current_user.username,
                           money=current_user.money,
                           avatar=current_user.avatar,
                           stats=stats)


@app.route("/analysis")
@login_required
def analysis():
    analysis_data = get_player_analysis_data(current_user.id)
    # Ensure data is JSON serializable for the template JS
    analysis_json = json.dumps(analysis_data) if analysis_data else "{}"
    
    return render_template("player_analysis.html", 
                           analysis=analysis_data,
                           analysis_json=analysis_json,
                           username=current_user.username,
                           player_id=current_user.id)



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]  # This is the Nickname (Display Name)
        password = request.form["password"]
        email = request.form["email"]  # This is the Login Username
        invite = request.form["invite"]
        avatar = request.form.get("avatar")

        if invite != INVITE_CODE:
            flash("Invalid invite code. Please try again.")
            return render_template("new_login.html", mode="register")

        # Check if login username exists
        existing_user = get_player_by_login_username(email)

        if existing_user:
            flash("Username already exists. Please choose another one.")
            return render_template("new_login.html", mode="register")

        hashed_password = generate_password_hash(password)

        success = create_player(email, hashed_password, username, avatar)

        if success:
            flash("注册成功！请登录", "success")
            return redirect(url_for("login"))
        else:
            flash("注册失败。请重试")
            return render_template("new_login.html", mode="register")

    return render_template("new_login.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]  # Login Username
        password = request.form["password"]

        user_data = get_player_by_login_username(email)

        if user_data and check_password_hash(user_data["password_hash"], password):
            # Daily Check: Reset chips to 3000 if it's a new day
            current_chips = check_and_reset_daily_chips(user_data["id"])
            
            # Update local user_data with the potentially new chip count
            user_data["chips"] = current_chips
            
            user = User(user_data["id"], user_data["nickname"], user_data["password_hash"],
                        user_data["username"], user_data["chips"], user_data["avatar"])
            login_user(user)
            return redirect(url_for("navigator"))

        flash("Invalid username or password. Please try again.")
        return render_template("new_login.html", mode="login")

    return render_template("new_login.html", mode="login")


@app.route("/forgot-password", methods=["GET"])
def forgot_password():
    return render_template("new_login.html", mode="forgot_password")


@app.route("/reset-password", methods=["POST"])
def reset_password():
    email = request.form["email"]
    invite = request.form["invite"]
    password = request.form["password"]

    if invite != INVITE_CODE:
        flash("Invalid invite code.")
        return render_template("new_login.html", mode="forgot_password")

    user_data = get_player_by_login_username(email)
    if not user_data:
        flash("User not found.")
        return render_template("new_login.html", mode="forgot_password")

    hashed_password = generate_password_hash(password)
    success = update_player_profile(user_data["id"], password_hash=hashed_password)

    if success:
        flash("Password reset successful! Please log in.", "success")
        return redirect(url_for("login"))
    else:
        flash("Password reset failed. Please try again.")
        return render_template("new_login.html", mode="forgot_password")


@app.route('/api/get-ranking', methods=['GET'])
def get_ranking():
    ranking_data = get_daily_ranking_list()
    return jsonify(ranking_data)


def collect_action_voice_packs():
    packs = []
    action_root = os.path.join(app.root_path, ACTION_SOUND_DIR)

    if not os.path.isdir(action_root):
        return packs

    for entry in sorted(os.scandir(action_root), key=lambda item: item.name):
        if not entry.is_dir():
            continue

        folder = entry.path
        if not all(os.path.isfile(os.path.join(folder, filename)) for filename in REQUIRED_ACTION_VOICE_FILES):
            continue

        name_file = os.path.join(folder, "name.txt")
        try:
            with open(name_file, "r", encoding="utf-8") as f:
                display_name = f.read().strip()
        except OSError:
            continue

        if not display_name:
            continue

        packs.append({
            "id": entry.name,
            "name": display_name
        })

    return packs


@app.route('/api/action-voice-packs', methods=['GET'])
@login_required
def get_action_voice_packs():
    packs = collect_action_voice_packs()
    if not any(pack["id"] == DEFAULT_ACTION_VOICE_PACK for pack in packs):
        app.logger.warning("Default action voice pack '%s' is missing or invalid", DEFAULT_ACTION_VOICE_PACK)

    return jsonify({
        "default": DEFAULT_ACTION_VOICE_PACK,
        "packs": packs
    })


@app.route("/api/update-profile", methods=["POST"])
@login_required
def update_profile():
    data = request.json
    nickname = data.get("nickname")
    password = data.get("password")
    avatar = data.get("avatar")
    
    password_hash = None
    if password:
        password_hash = generate_password_hash(password)
        
    success = update_player_profile(current_user.id, nickname, password_hash, avatar)
    
    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": "Update failed"}), 500


@app.route('/api/fortune', methods=['POST'])
@login_required
def get_fortune():
    """
    DeepSeek运势预测 - 每人每天限一次
    """
    today = datetime.date.today().isoformat()
    user_id = current_user.id
    redis_key = f"fortune:{today}:{user_id}"

    # Check if user already has a fortune for today
    cached_fortune = redis.get(redis_key)
    if cached_fortune:
        return jsonify({"content": cached_fortune.decode('utf-8'), "cached": True})

    user_prompt = '请告诉我今天的运气如何，带一点博弈术语，比如‘红黑’、‘同花’、‘庄闲’等。'
    system_prompt = '你是一个在澳门赌场工作多年的资深荷官，说话风格奢华、神秘、老练。请根据当前的‘德州扑克’主题，为玩家生成一段简短的今日运势（50字以内）。'

    api_key = get_api_key('deepseek')
    if not api_key:
        fallback_content = random.choice(FORTUNES)
        redis.setex(redis_key, 86400, fallback_content)
        return jsonify({"content": fallback_content, "cached": False})

    url = f"{DEEPSEEK_BASE_URL}/v1/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            *([{"role": "system", "content": system_prompt}] if system_prompt else []),
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.5
    }

    try:
        response = requests.post(url, json=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        })
        response.raise_for_status()
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        
        # Cache the fortune for 24 hours only on success
        if content:
            redis.setex(redis_key, 86400, content)
        
        return jsonify({"content": content, "cached": False})
    except Exception as e:
        app.logger.error(f"DeepSeek API Error: {e}")
        # Fallback to local fortunes on error
        fallback_content = random.choice(FORTUNES)
        redis.setex(redis_key, 86400, fallback_content)
        return jsonify({"content": fallback_content, "cached": False})


@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "join":
            room_id = request.form.get("room-id").strip()
            if not room_id:
                return render_template("new_login.html", mode="join")

            session["room-id"] = room_id
            session["player-id"] = current_user.id
            session["player-name"] = current_user.username
            session["player-money"] = current_user.money
            # session['player-avatar'] = current_user.avatar

            return render_template("new_ui.html",
                                   mode="game",
                                   player_id=session["player-id"],
                                   username=session["player-name"],
                                   money=session["player-money"],
                                   avatar=current_user.avatar,
                                   room=session["room-id"])

        elif action == "create":
            room_id = random.randint(1000, 9999)
            session["room-id"] = room_id
            session["player-id"] = current_user.id
            session["player-name"] = current_user.username
            session["player-money"] = current_user.money
            # session['player-avatar'] = current_user.avatar

            return render_template("new_ui.html",
                                   mode="game",
                                   player_id=session["player-id"],
                                   username=session["player-name"],
                                   money=session["player-money"],
                                   avatar=current_user.avatar,
                                   room=session["room-id"])

        else:
            flash("What did you do???")
            return render_template("new_login.html", mode="join")

    return render_template("new_login.html", mode="join")


@socketio.on('connect')
def on_connect():
    app.logger.info(f"Client connected: {request.sid}")


@socketio.on('disconnect')
def on_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    sid = request.sid
    if sid in player_channels:
        player_info = player_channels[sid]
        if 'game_loop' in player_info:
            player_info['game_loop'].kill()
        if 'chat_loop' in player_info:
            player_info['chat_loop'].kill()
        del player_channels[sid]


@socketio.on('game_message')
def on_game_message(message):
    sid = request.sid
    if sid in player_channels:
        player_info = player_channels[sid]
        message_type = message.get('message_type')

        if message_type == 'chat_message':
            room_id = player_info['room_id']
            chat_channel = f"room:{room_id}:chat"
            chat_message = {
                'message_type': 'chat_message',
                'sender_id': player_info['player_id'],
                'sender_name': player_info['player_name'],
                'message': message.get('message', '')
            }
            redis.publish(chat_channel, json.dumps(chat_message))
        elif message_type == 'interaction':
            room_id = player_info['room_id']
            chat_channel = f"room:{room_id}:chat"
            interaction_message = {
                'message_type': 'interaction',
                'sender_id': player_info['player_id'],
                'action': message.get('action')
            }
            redis.publish(chat_channel, json.dumps(interaction_message))
        else:
            try:
                player_info['channel'].send_message(message)
            except (ChannelError, MessageFormatError):
                pass


@socketio.on('room_action')
def on_room_action(data):
    if "player-id" not in session:
        emit("error", {"error": "Unrecognized user"})
        return

    action = data.get("action")
    if action not in ("add-bot", "remove-bot"):
        emit("error", {"error": "Invalid room action"})
        return

    room_id = session.get("room-id")
    requester_id = session.get("player-id")
    if not room_id or not requester_id:
        emit("error", {"error": "Missing room context"})
        return

    message = {
        "message_type": "room-control",
        "action": action,
        "room_id": room_id,
        "requester_id": requester_id
    }

    if "seat_index" in data:
        message["seat_index"] = data.get("seat_index")
    if "difficulty" in data:
        message["difficulty"] = data.get("difficulty")
    if "bot_id" in data:
        message["bot_id"] = data.get("bot_id")

    try:
        room_control_queue.push(message)
    except Exception:
        emit("error", {"error": "Failed to send room action"})


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
    
    # 每次加入游戏前检查是否需要每日重置 (Daily Check)
    # 这确保了长连接用户跨天也能触发重置
    player_money = check_and_reset_daily_chips(player_id)
    session["player-money"] = player_money

    player_avatar = None
    if current_user.is_authenticated:
        player_avatar = current_user.avatar
    else:
        user_data = get_player_by_id(player_id)
        if user_data:
            player_avatar = user_data["avatar"]

    # 如果头像数据过大，截断或置空
    if player_avatar and len(player_avatar) > 150000:
        player_avatar = None

    room_id = session["room-id"]

    player_connector = PlayerClientConnector(redis, connection_channel, app.logger)

    try:
        server_channel = player_connector.connect(
            player=Player(
                id=player_id,
                name=player_name,
                money=player_money,
                avatar=player_avatar,
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

    def game_message_handler(channel_from, channel_to_ws):
        try:
            while True:
                message = channel_from.recv_message()
                if "message_type" in message and message["message_type"] == "disconnect":
                    raise ChannelError
                socketio.emit('game_message', message, room=channel_to_ws)
        except (ChannelError, MessageFormatError):
            app.logger.info(f"Player {player_id} game channel closed.")

    def chat_message_handler(room_id, channel_to_ws):
        chat_channel = f"room:{room_id}:chat"
        pubsub = redis.pubsub()
        pubsub.subscribe(chat_channel)
        app.logger.info(f"Player {player_id} subscribed to chat channel: {chat_channel}")
        for message in pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                # Default to chat_message if not specified (for backward compatibility if any)
                if 'message_type' not in data:
                    data['message_type'] = 'chat_message'

                socketio.emit('game_message', data, room=channel_to_ws)

    game_loop = gevent.spawn(game_message_handler, server_channel, request.sid)
    chat_loop = gevent.spawn(chat_message_handler, room_id, request.sid)

    player_channels[request.sid] = {
        'channel': server_channel,
        'player_id': player_id,
        'player_name': player_name,
        'room_id': room_id,
        'game_loop': game_loop,
        'chat_loop': chat_loop
    }
